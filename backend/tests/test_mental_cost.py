# SPDX-License-Identifier: AGPL-3.0-only
"""Friendly numbers by design (2026-08-22): the FULL parameter space of every calculation
exercise must land every solver-visible value at mental cost, and the named-mistake
distractors must survive it.

Learners draw random seeds and the printed book pins one of them, so friendliness is asserted
over the whole space, never over an instance. Two bounds, applied per operation kind:

* multiplicative step (a product or quotient the solver forms) — the result must terminate with
  at most 1 decimal (2 when |v| < 10, the unit-quantity scale: position sizes, bp products), AND
  the value or its double must fit in 3 significant digits. The double admits exactly the
  halving-shift family (18,650 = 37,300/2; 1,325 = 2,650/2) and nothing looser.
* additive step (sums/differences of already-checked values) — cheap regardless of magnitude;
  only decimal alignment is bounded (terminating, <= 3 decimals).

Alongside mental cost, the discrimination must survive: every option is a NAMED mistake (a
collapsed distractor would be silently replaced by a generic "arithmetic slip" filler — the
defect this catches) and options stay >= 4 display quanta apart.

Exemptions are BY NAME below, keyed on the permanent `key`, each carrying its flag note; an
exemption whose exercise disappears fails the suite rather than rotting silently.
"""

from __future__ import annotations

import itertools
from decimal import Decimal
from fractions import Fraction

import pytest
import yaml

from tradeschool.config import get_settings
from tradeschool.exercises.calculation import (
    CalculationConfig,
    ChoiceSpec,
    IntRangeSpec,
    _options_for_params,
)

# --- exemptions: the structurally-heavy trio from the 2026-08-22 audit, flagged not converted --

#: Calculation exercises excluded from the bounds, by permanent key. Flag note is mandatory.
EXEMPT_CALCULATION: dict[str, str] = {
    # display id m23-ex-5
    "m20-ex-5": (
        "structurally-heavy: the swing/scalper draws chain 5-6 multiplications across two "
        "bp-rates, and the chain IS the teaching (fees scale with trades, funding with time). "
        "Deserves discussion beyond digit choice; do not silently un-exempt."
    ),
}

#: Quiz variants carrying the same flag (static text, no parameter space to bound). Recorded
#: here so the exemption list is the one place the trio lives; existence is asserted below.
EXEMPT_QUIZ_VARIANTS: dict[str, tuple[str, str]] = {
    # display id m23-ex-2
    "m20-ex-2": (
        "three-bills",
        "structurally-heavy: five chained integer steps across three personas (quiz twin of "
        "m23-ex-5).",
    ),
    # display id m24-ex-4
    "m21-ex-4": (
        "slippage-worked",
        "structurally-heavy: weighted-average fill, five ops with non-round intermediates; a "
        "friendly weighting collides with the midpoint distractor, so it stays flagged.",
    ),
}

MIN_GAP_QUANTA = 4


# --- the metric ----------------------------------------------------------------------------------


def _decimal_places(v: Fraction) -> int | None:
    """Decimal places of the exact value, or None if it does not terminate (e.g. a /3)."""
    den = v.denominator
    twos = fives = 0
    while den % 2 == 0:
        den //= 2
        twos += 1
    while den % 5 == 0:
        den //= 5
        fives += 1
    return max(twos, fives) if den == 1 else None


def _significant_digits(v: Fraction, dp: int) -> int:
    scaled = abs(v.numerator) * 10**dp // v.denominator
    text = str(scaled).rstrip("0")
    return len(text) if text else 0


def mult_ok(v: Fraction) -> bool:
    """A product/quotient the solver must actually produce."""
    if v == 0:
        return True
    dp = _decimal_places(v)
    if dp is None or dp > 2 or (dp == 2 and abs(v) >= 10):
        return False
    return _significant_digits(v, dp) <= 3 or _significant_digits(2 * v, _decimal_places(2 * v) or 0) <= 3


def add_ok(v: Fraction) -> bool:
    """A sum/difference of already-checked values: only alignment is bounded."""
    dp = _decimal_places(v)
    return dp is not None and dp <= 3


# --- solver-visible chains, one per formula (mirrors formulas.py, in exact Fractions) -------------


def _f(x: object) -> Fraction:
    return Fraction(str(x))


def _chain(formula_id: str, p: dict[str, object]) -> list[tuple[str, Fraction]]:
    """(kind, value) per solver step; kind is 'mult' or 'add'. The final entry is the answer."""
    if formula_id == "funding_payment":
        return [("mult", _f(p["notional"]) * _f(p["rate"]))]
    if formula_id == "initial_margin":
        notional = _f(p["entry"]) * _f(p["quantity"])
        return [("mult", notional), ("mult", notional / _f(p["leverage"]))]
    if formula_id == "liquidation_price":
        imr = Fraction(1) / _f(p["leverage"])
        sign = 1 if str(p["side"]) == "long" else -1
        factor = 1 - sign * imr + sign * _f(p["mmr"])
        return [("mult", imr), ("add", factor), ("mult", _f(p["entry"]) * factor)]
    if formula_id == "net_pnl":
        move = (_f(p["exit"]) - _f(p["entry"])) * (1 if str(p["side"]) == "long" else -1)
        gross = _f(p["quantity"]) * move
        both = _f(p["entry"]) + _f(p["exit"])
        fee_on_notional = _f(p["fee_rate"]) * both
        fees = fee_on_notional * _f(p["quantity"])
        return [
            ("mult", gross),
            ("add", both),
            ("mult", fee_on_notional),
            ("mult", fees),
            ("add", gross - fees),
        ]
    if formula_id == "market_cap":
        return [("mult", _f(p["price"]) * _f(p["circulating"]))]
    if formula_id == "fdv":
        return [("mult", _f(p["price"]) * _f(p["max_supply"]))]
    if formula_id == "position_size_from_risk":
        risk = _f(p["equity"]) * _f(p["risk_pct"])
        return [("mult", risk), ("mult", risk / _f(p["stop_distance"]))]
    if formula_id == "expectancy":
        win = _f(p["win_rate"]) * _f(p["avg_win"])
        loss = (1 - _f(p["win_rate"])) * _f(p["avg_loss"])
        return [("mult", win), ("mult", loss), ("add", win - loss)]
    if formula_id == "net_delta":
        return [("add", _f(p["taker_buy"]) - _f(p["taker_sell"]))]
    if formula_id == "venue_premium_pct":
        gap = _f(p["price_b"]) - _f(p["price_a"])
        return [("add", gap), ("mult", gap / _f(p["price_a"]) * 100)]
    if formula_id == "style_net_result":
        gross = _f(p["notional"]) * _f(p["gross_pct"])
        base_fee = _f(p["fee_rate"]) * _f(p["notional"]) * 2
        steps: list[tuple[str, Fraction]] = [("mult", gross), ("mult", base_fee)]
        style = str(p["style"])
        if style == "scalper":
            cost = base_fee * _f(p["round_trips"])
            steps.append(("mult", cost))
        elif style == "swing":
            funding = _f(p["funding_rate"]) * _f(p["notional"]) * _f(p["funding_intervals"])
            cost = base_fee + funding
            steps += [("mult", funding), ("add", cost)]
        else:
            cost = base_fee
        steps.append(("add", gross - cost))
        return steps
    raise KeyError(f"no solver chain declared for formula {formula_id!r} — add one here")


# --- content loading -------------------------------------------------------------------------------


def _manifest() -> dict[str, str]:
    """display id -> permanent key, for every exercise in the manifest."""
    course = yaml.safe_load(
        (get_settings().content_dir / "course.yaml").read_text(encoding="utf-8")
    )
    out: dict[str, str] = {}
    for block in course["blocks"]:
        for module in block["modules"]:
            for lesson in module["lessons"]:
                for ex in lesson.get("exercises", []):
                    out[ex["id"]] = ex.get("key", ex["id"])
    return out


def _calculation_exercises() -> list[tuple[str, str, CalculationConfig]]:
    keys = _manifest()
    found = []
    for path in sorted((get_settings().content_dir / "exercises").glob("*.yaml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if raw.get("type") == "calculation":
            found.append((path.stem, keys[path.stem], CalculationConfig.model_validate(raw)))
    return found


CALCULATIONS = _calculation_exercises()


def _space(config: CalculationConfig) -> list[dict[str, object]]:
    pools = []
    for name, spec in config.params.items():
        if isinstance(spec, IntRangeSpec):
            pools.append([(name, v) for v in range(spec.min, spec.max + 1, spec.step)])
        else:
            assert isinstance(spec, ChoiceSpec)
            pools.append([(name, v) for v in spec.values])
    return [dict(combo) for combo in itertools.product(*pools)]


# --- the assertions --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("exercise_id", "key", "config"), CALCULATIONS, ids=[c[0] for c in CALCULATIONS]
)
def test_every_draw_lands_at_mental_cost(exercise_id: str, key: str, config) -> None:
    if key in EXEMPT_CALCULATION:
        pytest.skip(f"exempt by name: {EXEMPT_CALCULATION[key]}")
    space = _space(config)
    assert len(space) > 1, f"{exercise_id}: degenerate parameter space"
    bad: list[str] = []
    for params in space:
        for kind, value in _chain(config.formula, params):
            ok = mult_ok(value) if kind == "mult" else add_ok(value)
            if not ok:
                bad.append(f"{params} -> {kind} step lands on {float(value):.6g}")
                break
    assert not bad, (
        f"{exercise_id}: {len(bad)}/{len(space)} draws break the mental-cost bound, e.g.:\n  "
        + "\n  ".join(bad[:5])
    )


@pytest.mark.parametrize(
    ("exercise_id", "key", "config"), CALCULATIONS, ids=[c[0] for c in CALCULATIONS]
)
def test_named_distractors_survive_every_draw(exercise_id: str, key: str, config) -> None:
    if key in EXEMPT_CALCULATION:
        pytest.skip(f"exempt by name: {EXEMPT_CALCULATION[key]}")
    quantum = Decimal(10) ** -config.round
    floor = MIN_GAP_QUANTA * quantum
    fillers: list[str] = []
    narrow: list[str] = []
    for params in _space(config):
        _expected, options, _correct_id, diag = _options_for_params(config, params, order_seed=7)
        if any(m == "make an arithmetic slip" for m in diag.values()):
            fillers.append(str(params))
            continue
        values = sorted(Decimal(o["value"]) for o in options)
        gap = min(b - a for a, b in itertools.pairwise(values))
        if gap < floor:
            narrow.append(f"{params} -> min option gap {gap} < {floor}")
    assert not fillers, (
        f"{exercise_id}: {len(fillers)} draws collapse a named-mistake distractor into a generic "
        f"filler, e.g. {fillers[:3]}"
    )
    assert not narrow, (
        f"{exercise_id}: {len(narrow)} draws leave options closer than {MIN_GAP_QUANTA} quanta, "
        f"e.g.:\n  " + "\n  ".join(narrow[:5])
    )


def test_exemptions_name_live_content() -> None:
    """An exemption may never outlive (or predate) the exercise it flags."""
    keys = _manifest()
    by_key = {v: k for k, v in keys.items()}
    for key in EXEMPT_CALCULATION:
        display = by_key.get(key)
        assert display, f"exempt calculation key {key!r} is not in the manifest"
        raw = yaml.safe_load(
            (get_settings().content_dir / "exercises" / f"{display}.yaml").read_text(
                encoding="utf-8"
            )
        )
        assert raw.get("type") == "calculation", f"{display} is no longer a calculation exercise"
    for key, (variant_id, _note) in EXEMPT_QUIZ_VARIANTS.items():
        display = by_key.get(key)
        assert display, f"exempt quiz key {key!r} is not in the manifest"
        raw = yaml.safe_load(
            (get_settings().content_dir / "exercises" / f"{display}.yaml").read_text(
                encoding="utf-8"
            )
        )
        assert raw.get("type") == "quiz", f"{display} is no longer a quiz"
        assert any(v["id"] == variant_id for v in raw["variants"]), (
            f"{display} no longer carries flagged variant {variant_id!r}"
        )
