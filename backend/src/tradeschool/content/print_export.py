# SPDX-License-Identifier: AGPL-3.0-only
"""The course's exercises as PRINT: one frozen instance per exercise, plus the answer to that instance.

The only place that hands a solution to a client before the learner answers — see the endpoint's
docstring. Three rules hold it together:

* **One instance, one pass.** Every number the answer quotes is read out of the payload being
  published, never re-derived, so a key cannot drift from its instance.
* **A fixed seed per exercise** (``print_seed``), so two exports of a content version are identical.
* **Nothing is dropped quietly.** Unprintable exercises land in ``excluded`` with a reason, logged at
  WARNING, and the PDF prints a note in the lesson.
"""

from __future__ import annotations

import hashlib
import logging
import re
from collections.abc import Callable, Mapping, Sequence
from typing import cast

from pydantic import BaseModel

from tradeschool.content.registry import CourseRegistry
from tradeschool.exercises.base import GradeResult
from tradeschool.exercises.registry import get_generator, has_generator
from tradeschool.exercises.reveal import RevealError, reveal, revealed_mapping
from tradeschool.exercises.types import ExerciseType

logger = logging.getLogger("tradeschool.content")

#: Same span the attempt flow samples from, so a print seed is an ordinary seed in every respect.
PRINT_SEED_SPACE = 2**62


class PrintExerciseError(RuntimeError):
    """This exercise cannot be printed. The message is the reason the reader and the log both get."""


def print_seed(exercise_key: str) -> int:
    """The one seed this exercise is always printed at — a function of the permanent KEY, never the
    display id, so a display renumbering cannot silently reprint the book with new instances.

    blake2b, not ``hash()``: PYTHONHASHSEED is per-process, so that would print a different book on
    every restart while every in-process determinism test still passed.
    """
    digest = hashlib.blake2b(exercise_key.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big") % PRINT_SEED_SPACE


_NUMBER = re.compile(r"^m0*(\d+)-ex-0*(\d+)$")


def print_number(exercise_id: str) -> str:
    """The reader-facing label: ``m11-ex-5`` prints as ``11.5``.

    Derived from the id, not counted, since ids are append-only and never renumbered. An id that does
    not fit the convention keeps its raw form, so the exercise ↔ answer pairing survives either way.
    """
    match = _NUMBER.match(exercise_id)
    return f"{int(match[1])}.{int(match[2])}" if match else exercise_id


# --- answers -------------------------------------------------------------------------------------
# Each adapter returns the answer to ONE printed instance. They deliberately return *ids* into the
# printed payload (option ids, item ids, bar indices) rather than re-stating the text: the renderer
# resolves them against the same payload it lays out, so the key cannot name an option the page does
# not show. Only values that exist nowhere in the payload — a chart's ground-truth prices — are copied
# out, and those are read from the payload's own series.


def _series(payload: Mapping[str, object]) -> Mapping[str, Sequence[float]]:
    series = payload.get("series")
    if not isinstance(series, Mapping):
        raise PrintExerciseError("chart payload carries no series")
    return cast(Mapping[str, Sequence[float]], series)


def _anchor(
    series: Mapping[str, Sequence[float]], index: int, kind: str, label: str
) -> dict[str, object]:
    """One ground-truth bar, priced from the PRINTED series — the answer's link to the printed chart."""
    closes = series["close"]
    if not 0 <= index < len(closes):
        raise PrintExerciseError(f"ground-truth bar {index} is outside the printed {len(closes)} bars")
    price = {"high": series["high"], "low": series["low"]}.get(kind, closes)[index]
    return {
        "index": index,
        "time": series["time"][index],
        "kind": kind,
        "label": label,
        "price": price,
    }


def _zones(
    series: Mapping[str, Sequence[float]], bands: object
) -> list[dict[str, object]]:
    """Shaded ground-truth zones (m34), checked to name prices the printed chart actually reaches.

    A band lives in price space and is absent from the payload, so it cannot be indexed out of the
    series the way an anchor can.
    """
    if not isinstance(bands, list) or not bands:
        return []
    floor, ceiling = min(series["low"]), max(series["high"])
    out: list[dict[str, object]] = []
    for band in bands:
        if not isinstance(band, Mapping):
            continue
        low, high = float(cast(float, band["low"])), float(cast(float, band["high"]))
        if high < floor or low > ceiling:
            raise PrintExerciseError(
                f"ground-truth zone {low}..{high} outside the printed range {floor}..{ceiling}"
            )
        out.append(
            {"low": low, "high": high, "kind": band.get("kind", ""), "label": band.get("label", "")}
        )
    return out


def _quiz_answer(
    payload: Mapping[str, object], result: GradeResult, _config: BaseModel
) -> dict[str, object]:
    revealed = revealed_mapping(result)
    kind = str(payload.get("kind", "single_choice"))
    answer: dict[str, object] = {"kind": kind}
    if kind == "true_false":
        answer["value"] = bool(revealed["value"])
    elif kind == "multi_select":
        answer["optionIds"] = list(cast(Sequence[str], revealed["optionIds"]))
    elif kind == "ordering":
        answer["order"] = list(cast(Sequence[str], revealed["order"]))
    elif kind == "matching":
        answer["pairs"] = dict(cast(Mapping[str, str], revealed["pairs"]))
    else:  # single_choice
        answer["optionIds"] = [str(revealed["optionId"])]
    return answer


def _calculation_answer(
    _payload: Mapping[str, object], result: GradeResult, config: BaseModel
) -> dict[str, object]:
    revealed = revealed_mapping(result)
    unit = getattr(config, "unit", None)
    return {
        "kind": "calculation",
        "optionIds": [str(revealed["optionId"])],
        # `numericValue`, not `value`: a true/false answer already owns `value`, and one key that is a
        # boolean here and a decimal string there is a trap for every consumer.
        "numericValue": str(revealed["value"]),
        "unit": unit,
        # The worked solution the app shows after answering — the reason a calculation answer is
        # worth printing at all, since the option alone teaches nothing.
        "steps": list(result.solution_steps),
    }


def _divergence_answer(
    payload: Mapping[str, object], result: GradeResult, _config: BaseModel
) -> dict[str, object]:
    revealed = revealed_mapping(result)
    label = str(revealed["divergence"])
    series = _series(payload)
    anchors: list[dict[str, object]] = []
    if label != "none":
        # Which extreme the two swings are read at — the same rule the app's markers use.
        kind = "high" if label.startswith("bearish") else "low"
        for number, key in enumerate(("swing1", "swing2"), start=1):
            index = revealed.get(key)
            if isinstance(index, int):
                anchors.append(_anchor(series, index, kind, str(number)))
    return {"kind": "chart", "label": label, "anchors": anchors, "zones": []}


def _pattern_answer(
    payload: Mapping[str, object], result: GradeResult, _config: BaseModel
) -> dict[str, object]:
    revealed = revealed_mapping(result)
    series = _series(payload)
    annotations = revealed.get("annotations")
    anchors = [
        _anchor(
            series,
            int(cast(int, a["index"])),
            str(a.get("kind", "")),
            str(a.get("label", "")),
        )
        for a in cast(Sequence[Mapping[str, object]], annotations or [])
    ]
    return {
        "kind": "chart",
        "label": str(revealed["label"]),
        "anchors": anchors,
        "zones": _zones(series, revealed.get("bands")),
    }


AnswerAdapter = Callable[[Mapping[str, object], GradeResult, BaseModel], dict[str, object]]

#: One adapter per printable type. A type absent here has no print form, and its exercises are
#: excluded by name rather than by silence — which is what makes adding a type a visible decision.
ADAPTERS: dict[ExerciseType, AnswerAdapter] = {
    ExerciseType.QUIZ: _quiz_answer,
    ExerciseType.CALCULATION: _calculation_answer,
    ExerciseType.SYNTHETIC_CHART: _divergence_answer,
    ExerciseType.FIXTURE_CHART: _divergence_answer,
    ExerciseType.PATTERN_CHART: _pattern_answer,
}

#: Types whose instance is a chart, and so needs an off-screen capture before it can be typeset.
CHART_TYPES = frozenset(
    {ExerciseType.SYNTHETIC_CHART, ExerciseType.FIXTURE_CHART, ExerciseType.PATTERN_CHART}
)


# --- building ------------------------------------------------------------------------------------


def build_print_exercise(
    registry: CourseRegistry, exercise_id: str, locale: str
) -> dict[str, object]:
    """One exercise as it will be printed: the frozen instance, and the answer to it.

    Raises ``PrintExerciseError`` with a reader-facing reason for anything that cannot be printed.
    """
    resolved = registry.get_exercise_config(exercise_id)
    if resolved is None:
        raise PrintExerciseError("declared in the manifest but not authored yet")
    exercise_type, config = resolved
    if not has_generator(exercise_type):
        raise PrintExerciseError(f"no generator for type {exercise_type.value!r}")
    adapter = ADAPTERS.get(exercise_type)
    if adapter is None:
        raise PrintExerciseError(f"no print form for type {exercise_type.value!r}")

    seed = print_seed(registry.exercise_key(exercise_id))
    generator = get_generator(exercise_type)
    instance = generator.generate(config, seed, locale)
    try:
        revealed = reveal(generator, config, seed, locale, instance.payload)
    except RevealError as exc:
        raise PrintExerciseError(str(exc)) from exc

    answer = adapter(instance.payload, revealed.result, config)
    answer["explanation"] = revealed.result.explanation
    return {
        "id": exercise_id,
        "number": print_number(exercise_id),
        "type": exercise_type.value,
        "isChart": exercise_type in CHART_TYPES,
        "seed": seed,
        "prompt": instance.prompt,
        # Exactly what an attempt would show, ground truth and all its markers still withheld: the
        # printed chart is cut before its resolution because the generated instance already is.
        "payload": instance.payload,
        "answer": answer,
    }


def build_print_exercises(registry: CourseRegistry, locale: str) -> dict[str, object]:
    """Every printable exercise in manifest order, each with its answer. Empty lessons still appear."""
    lessons: list[dict[str, object]] = []
    excluded: list[dict[str, str]] = []
    for _, module in registry.manifest.iter_modules():
        for lesson in module.lessons:
            printed: list[dict[str, object]] = []
            for exercise in lesson.exercises:
                try:
                    printed.append(build_print_exercise(registry, exercise.id, locale))
                except PrintExerciseError as exc:
                    logger.warning(
                        "print export: excluding exercise %s (%s) from lesson %s — %s",
                        exercise.id,
                        exercise.type.value,
                        lesson.id,
                        exc,
                    )
                    excluded.append(
                        {
                            "id": exercise.id,
                            "number": print_number(exercise.id),
                            "lessonId": lesson.id,
                            "type": exercise.type.value,
                            "reason": str(exc),
                        }
                    )
            lessons.append({"lessonId": lesson.id, "moduleId": module.id, "exercises": printed})
    return {"locale": locale, "lessons": lessons, "excluded": excluded}
