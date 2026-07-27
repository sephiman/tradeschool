# SPDX-License-Identifier: AGPL-3.0-only
"""Parametric calculation generator. The seed samples the parameters; the graded value comes from a
named `Decimal` formula. The exact result and three instantiated common-error distractors become
shuffled multiple-choice options (§D.8b); grading matches the chosen option. `Decimal` end to end (§8)."""

from __future__ import annotations

import random
from collections.abc import Mapping
from decimal import Decimal
from typing import Annotated, ClassVar, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from tradeschool.content.schema import LocalizedText
from tradeschool.exercises.base import (
    ExerciseGenerator,
    GeneratedInstance,
    GradeResult,
    InvalidAnswerError,
    rng_for,
)
from tradeschool.exercises.formulas import FORMULAS, get_formula
from tradeschool.exercises.types import ExerciseType


class IntRangeSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["int_range"]
    min: int
    max: int
    step: int = 1

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.max < self.min or self.step <= 0:
            raise ValueError("int_range requires min <= max and step > 0")
        return self


class ChoiceSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["choice"]
    values: list[str]

    @model_validator(mode="after")
    def _check(self) -> Self:
        if not self.values:
            raise ValueError("choice needs at least one value")
        return self


ParamSpec = Annotated[IntRangeSpec | ChoiceSpec, Field(discriminator="kind")]


class Tolerance(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rel: str | None = None
    abs: str | None = None


class CalculationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["calculation"]
    prompt: LocalizedText
    formula: str
    params: dict[str, ParamSpec]
    tolerance: Tolerance = Tolerance()
    round: int = 2
    unit: str | None = None
    explanation: LocalizedText | None = None

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.formula not in FORMULAS:
            raise ValueError(f"unknown formula {self.formula!r}")
        missing = set(FORMULAS[self.formula].arg_names) - set(self.params)
        if missing:
            raise ValueError(f"formula {self.formula!r} missing params: {sorted(missing)}")
        return self


def _sample_one(spec: IntRangeSpec | ChoiceSpec, rng: random.Random) -> object:
    if isinstance(spec, IntRangeSpec):
        steps = (spec.max - spec.min) // spec.step
        return spec.min + rng.randint(0, steps) * spec.step
    return rng.choice(spec.values)


def _sample_params(config: CalculationConfig, seed: int) -> dict[str, object]:
    rng = rng_for(seed)
    # dict preserves manifest order -> deterministic sampling for a given seed.
    return {name: _sample_one(spec, rng) for name, spec in config.params.items()}


def _mc_options(
    config: CalculationConfig, seed: int
) -> tuple[dict[str, object], Decimal, list[dict[str, str]], str, dict[str, str | None]]:
    """Build the shuffled multiple-choice options for a seed. Returns
    (params, exact result, options[{id,value}], correct option id, {option id -> mistake or None}).

    The correct value plus up to three instantiated common-error distractors (from the formula) become
    four options, deduped after rounding and kept to the same order of magnitude so none is eliminable
    by size alone; a labelled arithmetic-slip perturbation only pads the rare case of a collision."""
    params = _sample_params(config, seed)
    formula = get_formula(config.formula)
    expected = formula.compute(params)
    q = Decimal(10) ** -config.round
    correct_r = expected.quantize(q)
    seen: set[Decimal] = {correct_r}
    picks: list[tuple[Decimal, str | None]] = []
    slack = abs(correct_r) * 8 + Decimal(50)  # reject absurd magnitudes, allow near-zero results
    for label, value in formula.distractors(params, expected):
        vr = value.quantize(q)
        if vr in seen or abs(vr) > slack:
            continue
        seen.add(vr)
        picks.append((vr, label))
        if len(picks) == 3:
            break
    base = max(abs(correct_r), Decimal(1))
    k = 1
    while len(picks) < 3:  # rare fallback when distractors collided / were filtered out
        delta = base * Decimal("0.05") * k * (Decimal(1) if k % 2 else Decimal(-1))
        vr = (expected + delta).quantize(q)
        k += 1
        if vr in seen:
            continue
        seen.add(vr)
        picks.append((vr, "make an arithmetic slip"))

    entries: list[tuple[Decimal, str | None]] = [(correct_r, None), *picks]
    order = list(range(len(entries)))
    rng_for(seed * 1000 + 7).shuffle(order)
    options: list[dict[str, str]] = []
    diag: dict[str, str | None] = {}
    correct_id = "o0"
    for slot, idx in enumerate(order):
        oid = f"o{slot}"
        value_r, mistake = entries[idx]
        options.append({"id": oid, "value": str(value_r)})
        diag[oid] = mistake
        if mistake is None:
            correct_id = oid
    return params, expected, options, correct_id, diag


class CalculationGenerator(ExerciseGenerator):
    type: ClassVar[ExerciseType] = ExerciseType.CALCULATION

    def parse_config(self, raw: Mapping[str, object]) -> CalculationConfig:
        return CalculationConfig.model_validate(dict(raw))

    def generate(self, config: BaseModel, seed: int, locale: str) -> GeneratedInstance:
        assert isinstance(config, CalculationConfig)
        params, _expected, options, _correct_id, _diag = _mc_options(config, seed)
        prompt = config.prompt.get(locale).format(**params)
        return GeneratedInstance(
            prompt=prompt,
            payload={
                "kind": "multiple_choice",
                "options": options,
                "unit": config.unit,
                "formula": config.formula,
            },
        )

    def grade(
        self, config: BaseModel, seed: int, answer: Mapping[str, object], locale: str
    ) -> GradeResult:
        assert isinstance(config, CalculationConfig)
        chosen = answer.get("optionId")
        if not isinstance(chosen, str):
            raise InvalidAnswerError("expected an 'optionId' string")
        params, expected, options, correct_id, diag = _mc_options(config, seed)
        steps = get_formula(config.formula).explain(params, expected)
        mistake = diag.get(chosen)
        if chosen != correct_id and mistake:
            chosen_val = next((o["value"] for o in options if o["id"] == chosen), None)
            # Name the specific error the chosen distractor corresponds to (§D.8b).
            if locale == "es":
                mistake_text = _translate_mistake_es(mistake)
                prefix = f"Elegiste {chosen_val} — resultado de " if chosen_val else ""
                steps = [*steps, f"{prefix}{mistake_text}."]
            else:
                prefix = f"You picked {chosen_val} — result of " if chosen_val else ""
                steps = [*steps, f"{prefix}{mistake} (what you get if you {mistake})."]
        correct_value = next(o["value"] for o in options if o["id"] == correct_id)
        return GradeResult(
            correct=chosen == correct_id,
            correct_answer={"optionId": correct_id, "value": correct_value},
            solution_steps=steps,
            explanation=config.explanation.get(locale) if config.explanation else None,
        )


MISTAKE_TRANSLATIONS_ES: dict[str, str] = {
    "forget the maintenance-margin term": "olvidar el término de margen de mantenimiento",
    "subtract mmr as well (wrong sign)": "restar el mmr en vez de sumarlo (signo invertido)",
    "add mmr as well (wrong sign)": "sumar el mmr en vez de restarlo (signo invertido)",
    "double the initial-margin cushion": "duplicar el colchón de margen inicial",
    "use the wrong side (flip the sign)": "usar el lado equivocado (invertir el signo)",
    "count two funding intervals": "contar dos intervalos de financiación",
    "count only half an interval": "contar solo medio intervalo",
    "forget to divide by leverage (use the full notional)": "olvidar dividir entre el apalancamiento (usar el notional completo)",
    "divide by leverage minus one": "dividir entre apalancamiento menos uno",
    "divide by leverage plus one": "dividir entre apalancamiento más uno",
    "take the gross move only (forget fees)": "tomar solo el movimiento bruto (olvidar las comisiones)",
    "charge the fee on one fill instead of both": "cobrar la comisión en una sola operación en lugar de ambas",
    "read the price move the wrong way round": "calcular la variación de precio al revés",
    "misread the circulating supply (~1.5x)": "leer mal la oferta circulante (~1.5x)",
    "misread the circulating supply (~0.6x)": "leer mal la oferta circulante (~0.6x)",
    "double-count the supply": "duplicar la oferta",
    "use a supply figure ~0.5x too small": "usar una cifra de oferta ~0.5x menor",
    "use a supply figure ~1.4x too large": "usar una cifra de oferta ~1.4x mayor",
    "slip a decimal on the price (~0.9x)": "deslizar un decimal en el precio (~0.9x)",
    "double the risk percentage": "duplicar el porcentaje de riesgo",
    "halve the stop distance": "reducir a la mitad la distancia al stop",
    "assume 1% risk instead of the given percentage": "asumir un riesgo del 1% en lugar del porcentaje dado",
    "use the win rate for losses too (forget 1 - win%)": "usar la tasa de acierto para las pérdidas (olvidar 1 - win%)",
    "add the losing side instead of subtracting": "sumar la parte perdedora en lugar de restarla",
    "ignore the losing trades entirely": "ignorar por completo las operaciones perdedoras",
    "add the two sides instead of subtracting them (that is total volume, not net flow)": "sumar ambos lados en lugar de restarlos (eso es volumen total, no flujo neto)",
    "read the delta the wrong way round (sell minus buy)": "calcular el delta al revés (ventas menos compras)",
    "take only the aggressive buying and ignore the selling against it": "tomar solo las compras agresivas e ignorar las ventas",
    "divide by the other venue's price instead of the reference venue's": "dividir entre el precio del otro exchange en lugar del de referencia",
    "read the premium the wrong way round": "calcular la prima al revés",
    "forget to convert the fraction into a percentage": "olvidar convertir la fracción a porcentaje",
    "ignore trading costs (take the gross move)": "ignorar los costes de trading (tomar el movimiento bruto)",
    "treat it as a single round-trip with no funding": "tratarlo como un solo ida y vuelta sin financiación",
    "make an arithmetic slip": "hacer un error de cálculo aritmético",
}


def _translate_mistake_es(mistake: str) -> str:
    return MISTAKE_TRANSLATIONS_ES.get(mistake, mistake)

