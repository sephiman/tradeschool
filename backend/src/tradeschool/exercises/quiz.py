# SPDX-License-Identifier: AGPL-3.0-only
"""Quiz generator: a per-concept variant bank, laid out deterministically from the seed.

Five sub-kinds selected by a variant's `kind` field: `single_choice`, `true_false`, `multi_select`,
`ordering` and `matching`. The last three are graded all-or-nothing.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import ClassVar, Literal, Self

from pydantic import BaseModel, ConfigDict, model_validator

from tradeschool.content.schema import LocalizedText
from tradeschool.exercises.base import (
    ExerciseGenerator,
    GeneratedInstance,
    GradeResult,
    InvalidAnswerError,
    rng_for,
)
from tradeschool.exercises.types import ExerciseType


class QuizKind(StrEnum):
    SINGLE_CHOICE = "single_choice"
    TRUE_FALSE = "true_false"
    MULTI_SELECT = "multi_select"
    ORDERING = "ordering"
    MATCHING = "matching"


class QuizOption(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    text: LocalizedText
    correct: bool = False


class OrderItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    text: LocalizedText
    position: int  # 1-based position in the correct sequence


class MatchPair(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    left: LocalizedText
    right: LocalizedText


class QuizVariant(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    kind: QuizKind = QuizKind.SINGLE_CHOICE
    prompt: LocalizedText
    explanation: LocalizedText | None = None
    # single_choice / multi_select
    options: list[QuizOption] = []
    # true_false
    answer: bool | None = None
    # ordering
    items: list[OrderItem] = []
    # matching
    pairs: list[MatchPair] = []

    @model_validator(mode="after")
    def _check(self) -> Self:
        k = self.kind
        if k in (QuizKind.SINGLE_CHOICE, QuizKind.MULTI_SELECT):
            if len(self.options) < 2:
                raise ValueError(f"variant {self.id!r} needs at least 2 options")
            ids = [o.id for o in self.options]
            if len(set(ids)) != len(ids):
                raise ValueError(f"variant {self.id!r} has duplicate option ids")
            n_correct = sum(1 for o in self.options if o.correct)
            if k is QuizKind.SINGLE_CHOICE and n_correct != 1:
                raise ValueError(f"variant {self.id!r} (single_choice) needs exactly one correct option")
            if k is QuizKind.MULTI_SELECT and not (1 <= n_correct < len(self.options)):
                raise ValueError(f"variant {self.id!r} (multi_select) needs 1..n-1 correct options")
            self._forbid(exclude={"options"})
        elif k is QuizKind.TRUE_FALSE:
            if self.answer is None:
                raise ValueError(f"variant {self.id!r} (true_false) needs an 'answer' boolean")
            self._forbid(exclude={"answer"})
        elif k is QuizKind.ORDERING:
            if len(self.items) < 3:
                raise ValueError(f"variant {self.id!r} (ordering) needs at least 3 items")
            positions = sorted(i.position for i in self.items)
            if positions != list(range(1, len(self.items) + 1)):
                raise ValueError(f"variant {self.id!r} (ordering) positions must be 1..n with no gaps")
            if len({i.id for i in self.items}) != len(self.items):
                raise ValueError(f"variant {self.id!r} (ordering) has duplicate item ids")
            self._forbid(exclude={"items"})
        elif k is QuizKind.MATCHING:
            if len(self.pairs) < 3:
                raise ValueError(f"variant {self.id!r} (matching) needs at least 3 pairs")
            if len({p.id for p in self.pairs}) != len(self.pairs):
                raise ValueError(f"variant {self.id!r} (matching) has duplicate pair ids")
            self._forbid(exclude={"pairs"})
        return self

    def _forbid(self, *, exclude: set[str]) -> None:
        """Guard against filling the wrong sub-kind's fields (catches authoring mistakes early)."""
        present = {
            "options": bool(self.options),
            "answer": self.answer is not None,
            "items": bool(self.items),
            "pairs": bool(self.pairs),
        }
        for field, is_set in present.items():
            if is_set and field not in exclude:
                raise ValueError(f"variant {self.id!r} ({self.kind.value}) must not set {field!r}")


class QuizConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["quiz"]
    variants: list[QuizVariant]

    @model_validator(mode="after")
    def _check(self) -> Self:
        if not self.variants:
            raise ValueError("quiz needs at least one variant")
        if len({v.id for v in self.variants}) != len(self.variants):
            raise ValueError("duplicate variant ids")
        return self


def _shuffled(n: int, seed: int, salt: int) -> list[int]:
    """A deterministic permutation of range(n) from (seed, salt)."""
    order = list(range(n))
    rng_for(seed * 1000 + salt).shuffle(order)
    return order


class QuizGenerator(ExerciseGenerator):
    type: ClassVar[ExerciseType] = ExerciseType.QUIZ

    def parse_config(self, raw: Mapping[str, object]) -> QuizConfig:
        return QuizConfig.model_validate(dict(raw))

    def _variant(self, config: QuizConfig, seed: int) -> QuizVariant:
        return rng_for(seed).choice(config.variants)

    def generate(self, config: BaseModel, seed: int, locale: str) -> GeneratedInstance:
        assert isinstance(config, QuizConfig)
        v = self._variant(config, seed)
        payload: dict[str, object] = {"kind": v.kind.value}

        if v.kind in (QuizKind.SINGLE_CHOICE, QuizKind.MULTI_SELECT):
            order = _shuffled(len(v.options), seed, 0)
            payload["options"] = [
                {"id": v.options[i].id, "text": v.options[i].text.get(locale)} for i in order
            ]
        elif v.kind is QuizKind.TRUE_FALSE:
            pass  # the claim is the prompt; the client renders True/False
        elif v.kind is QuizKind.ORDERING:
            order = _shuffled(len(v.items), seed, 0)
            payload["items"] = [
                {"id": v.items[i].id, "text": v.items[i].text.get(locale)} for i in order
            ]
        elif v.kind is QuizKind.MATCHING:
            lorder = _shuffled(len(v.pairs), seed, 1)
            rorder = _shuffled(len(v.pairs), seed, 2)
            payload["lefts"] = [
                {"id": f"l{slot}", "text": v.pairs[i].left.get(locale)}
                for slot, i in enumerate(lorder)
            ]
            payload["rights"] = [
                {"id": f"r{slot}", "text": v.pairs[i].right.get(locale)}
                for slot, i in enumerate(rorder)
            ]

        return GeneratedInstance(prompt=v.prompt.get(locale), payload=payload)

    def grade(
        self, config: BaseModel, seed: int, answer: Mapping[str, object], locale: str
    ) -> GradeResult:
        assert isinstance(config, QuizConfig)
        v = self._variant(config, seed)
        explanation = v.explanation.get(locale) if v.explanation else None

        if v.kind is QuizKind.SINGLE_CHOICE:
            selected = answer.get("optionId")
            if not isinstance(selected, str):
                raise InvalidAnswerError("expected an 'optionId' string")
            correct_opt = next(o for o in v.options if o.correct)
            return GradeResult(
                correct=selected == correct_opt.id,
                correct_answer={"optionId": correct_opt.id, "text": correct_opt.text.get(locale)},
                explanation=explanation,
            )

        if v.kind is QuizKind.MULTI_SELECT:
            selected = answer.get("optionIds")
            if not isinstance(selected, list) or not all(isinstance(x, str) for x in selected):
                raise InvalidAnswerError("expected an 'optionIds' list of strings")
            correct_ids = {o.id for o in v.options if o.correct}
            return GradeResult(
                correct=set(selected) == correct_ids,
                correct_answer={
                    "optionIds": sorted(correct_ids),
                    "texts": [o.text.get(locale) for o in v.options if o.correct],
                },
                explanation=explanation,
            )

        if v.kind is QuizKind.TRUE_FALSE:
            value = answer.get("value")
            if not isinstance(value, bool):
                raise InvalidAnswerError("expected a boolean 'value'")
            return GradeResult(
                correct=value == v.answer,
                correct_answer={"value": v.answer},
                explanation=explanation,
            )

        if v.kind is QuizKind.ORDERING:
            order = answer.get("order")
            if not isinstance(order, list) or not all(isinstance(x, str) for x in order):
                raise InvalidAnswerError("expected an 'order' list of item ids")
            correct_order = [i.id for i in sorted(v.items, key=lambda it: it.position)]
            by_id = {i.id: i.text.get(locale) for i in v.items}
            return GradeResult(
                correct=list(order) == correct_order,
                correct_answer={"order": correct_order, "texts": [by_id[i] for i in correct_order]},
                explanation=explanation,
            )

        # matching
        pairs = answer.get("pairs")
        if not isinstance(pairs, dict):
            raise InvalidAnswerError("expected a 'pairs' mapping of left-id -> right-id")
        lorder = _shuffled(len(v.pairs), seed, 1)
        rorder = _shuffled(len(v.pairs), seed, 2)
        left_id = {pair_idx: f"l{slot}" for slot, pair_idx in enumerate(lorder)}
        right_id = {pair_idx: f"r{slot}" for slot, pair_idx in enumerate(rorder)}
        correct_map = {left_id[i]: right_id[i] for i in range(len(v.pairs))}
        readable = [
            {"left": v.pairs[i].left.get(locale), "right": v.pairs[i].right.get(locale)}
            for i in range(len(v.pairs))
        ]
        return GradeResult(
            correct={str(k): str(val) for k, val in pairs.items()} == correct_map,
            correct_answer={"pairs": correct_map, "readable": readable},
            explanation=explanation,
        )
