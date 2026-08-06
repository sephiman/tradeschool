# SPDX-License-Identifier: AGPL-3.0-only
"""The course's exercises as PRINT: one frozen instance per exercise, plus the answer to that instance.

The app generates a fresh random instance per attempt and reveals the solution only after answering.
A book cannot do either: the page has to hold ONE instance, chosen once and identically for every
reader, and the back of the book has to hold the answer to *that* instance. This module is where those
two constraints are met, and it is the only place in the codebase that hands a solution to a client
without a learner having answered first — see the endpoint's docstring for that trade-off.

Three rules hold it together:

**One instance, one pass.** ``generate`` is called once. The answer is read from ``grade`` against the
same ``(config, seed)`` and — through ``reveal`` — is verified by grading it back as correct. Every
number the answer quotes is then read out of *the payload being published*, never re-derived: a chart
answer's prices are indexed out of the very series the reader sees. A key that drifted from its
instance is not a wording bug, it is a wrong answer, so the shapes here make the drift impossible
rather than tested-for.

**A fixed seed per exercise.** ``print_seed`` hashes the exercise id with blake2b — deliberately not
``hash()``, which is salted per process and would print a different book every restart. Two exports of
the same content version are identical, byte for byte.

**Nothing is dropped quietly.** An exercise that cannot be printed is listed in ``excluded`` with the
reason and logged at WARNING. The reader is told too: the PDF prints a note in the lesson. An answer
key silently missing a question is the failure this guards against.
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


def print_seed(exercise_id: str) -> int:
    """The one seed this exercise is always printed at.

    blake2b of the id: stable across processes, releases and machines. ``hash()`` is not — PYTHONHASHSEED
    is randomized per process, so it would silently print a different instance on every restart while
    every determinism test that ran inside one process still passed.
    """
    digest = hashlib.blake2b(exercise_id.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big") % PRINT_SEED_SPACE


_NUMBER = re.compile(r"^m0*(\d+)-ex-0*(\d+)$")


def print_number(exercise_id: str) -> str:
    """The reader-facing label: ``m11-ex-5`` prints as ``11.5``.

    Derived from the id rather than counted, because ids are append-only and never renumbered (see
    content/README.md): a number derived from one is stable for the life of the course, and the same
    label identifies the exercise in the answer key. An id that does not fit the convention keeps its
    raw form — still unique, so the exercise ↔ answer pairing survives either way.
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
    """One ground-truth bar, priced from the PRINTED series — the answer's link to the printed chart.

    A high-swing is quoted at its high and a low-swing at its low, which is where the marker points
    on the page; anything else is quoted at its close.
    """
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
    """Shaded ground-truth zones (m30's origin zone / imbalance), checked against the printed range.

    A band is ground truth in price space and appears nowhere in the payload, so it cannot be indexed
    out of the series like an anchor can. What CAN be checked is that it names prices the printed
    chart actually reaches — a zone off the top of the page would be an answer to a different chart.
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

    seed = print_seed(exercise_id)
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
    """Every printable exercise in the course, in manifest order, each with its answer.

    One walk of the manifest, like ``course_export``, so the printed book cannot carry a different set
    of lessons from the read one. Lessons appear even when empty: the document is a complete walk, and
    the renderer looks its exercises up by lesson id.
    """
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
