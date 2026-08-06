# SPDX-License-Identifier: AGPL-3.0-only
"""Reading an instance's ground truth without a learner in front of it.

A generator only ever yields the solution from ``grade()``, and ``grade()`` needs an answer. The two
callers that legitimately want the truth anyway — the dev chart gallery and the print export — need
the same two moves, so they share them here rather than each keeping a half-complete copy:

1. ``dummy_answer`` — a *type-appropriate* throwaway, so ``grade`` reaches its reveal instead of
   raising ``InvalidAnswerError``. It must cover every quiz sub-kind: an `ordering` payload answered
   with a string, which is what the first version of this helper did, never gets that far.
2. ``reveal`` — grade once to learn the answer, rebuild it as a real submission, and grade AGAIN with
   it. The second pass is the point: if the submission the caller is about to publish does not grade
   as correct against this very seed, the answer is wrong and the caller stops. An answer key that the
   grader itself refuses is exactly the defect worth failing on.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from pydantic import BaseModel

from tradeschool.exercises.base import ExerciseGenerator, GradeResult


class RevealError(RuntimeError):
    """The ground truth could not be read back as a correct answer for this instance."""


def _first_option_id(payload: Mapping[str, object], key: str) -> str:
    options = payload.get(key)
    if isinstance(options, list) and options:
        first = options[0]
        if isinstance(first, Mapping):
            return str(first.get("id", ""))
    return ""


def _ids(payload: Mapping[str, object], key: str) -> list[str]:
    options = payload.get(key)
    if not isinstance(options, list):
        return []
    return [str(o.get("id", "")) for o in options if isinstance(o, Mapping)]


def dummy_answer(payload: Mapping[str, object]) -> dict[str, object]:
    """A throwaway answer of the right SHAPE for this payload, so ``grade`` yields its ground truth.

    Shape, not correctness: whether it happens to be right is irrelevant — only that the generator
    accepts it rather than rejecting it as malformed.
    """
    if "choices" in payload:
        choices = payload["choices"]
        first = str(choices[0]) if isinstance(choices, list) and choices else "none"
        # Both chart families read a single choice key ("divergence" for divergence charts, "label"
        # for the generic pattern charts); supplying both is harmless and covers either.
        return {"divergence": first, "label": first}

    kind = payload.get("kind")
    if kind == "true_false":
        return {"value": False}
    if kind == "multi_select":
        return {"optionIds": [_first_option_id(payload, "options")]}
    if kind == "ordering":
        return {"order": _ids(payload, "items")}
    if kind == "matching":
        lefts, rights = _ids(payload, "lefts"), _ids(payload, "rights")
        return {"pairs": dict(zip(lefts, rights, strict=False))}
    if "options" in payload:  # single_choice and calculation alike
        return {"optionId": _first_option_id(payload, "options")}
    return {"value": False}


def submission_for(correct_answer: object) -> dict[str, object]:
    """The revealed answer turned back into an answer a learner could have submitted.

    Key order matters: a calculation reveals both ``optionId`` and ``value`` (the option and what it
    reads), and it is the option that is graded.
    """
    if not isinstance(correct_answer, Mapping):
        raise RevealError(f"revealed answer is not a mapping: {correct_answer!r}")
    for key in ("optionId", "optionIds", "order", "pairs", "divergence", "label", "value"):
        if key in correct_answer:
            return {key: correct_answer[key]}
    raise RevealError(f"revealed answer names no answerable key: {sorted(correct_answer)}")


@dataclass(frozen=True)
class Revealed:
    """The verified ground truth: the answer as submitted, and the grading that accepted it."""

    submission: Mapping[str, object]
    result: GradeResult


def reveal(
    generator: ExerciseGenerator,
    config: BaseModel,
    seed: int,
    locale: str,
    payload: Mapping[str, object],
) -> Revealed:
    """Ground truth for ``(config, seed)``, verified by grading it back as a correct answer.

    ``payload`` is the instance the caller is publishing — passed in rather than regenerated, so the
    answer is read against the very thing the reader will see.
    """
    first = generator.grade(config, seed, dummy_answer(payload), locale)
    submission = submission_for(first.correct_answer)
    verified = generator.grade(config, seed, submission, locale)
    if not verified.correct:
        raise RevealError(
            f"the revealed answer {submission!r} does not grade as correct for seed {seed}"
        )
    return Revealed(submission=submission, result=verified)


def revealed_mapping(result: GradeResult) -> Mapping[str, object]:
    """``GradeResult.correct_answer`` as a mapping — every generator returns one."""
    if not isinstance(result.correct_answer, Mapping):
        raise RevealError(f"revealed answer is not a mapping: {result.correct_answer!r}")
    return cast(Mapping[str, object], result.correct_answer)
