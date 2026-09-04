# SPDX-License-Identifier: AGPL-3.0-only
"""An exam's questions come out in the order it was assembled in, not today's manifest order.

The rest of the exam suite needs a database; this one does not, because the property it checks is
about `_build_view`'s sort and nothing else. It is separate for that reason: the failure it guards
against — a display renumbering silently reordering an exam that is already in review — cannot be
reproduced against the real manifest without editing the real manifest, so it is shown here by handing
`_build_view` a frozen order that disagrees with the canonical one and requiring the frozen one to win.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from tradeschool.attempts.models import Attempt, AttemptState
from tradeschool.config import get_settings
from tradeschool.content.registry import CourseRegistry, load_registry
from tradeschool.exams.models import ExamSession
from tradeschool.exams.service import QUESTION_ORDER, _build_view, _canonical_order, _frozen_order


def _registry() -> CourseRegistry:
    return load_registry(get_settings().content_dir)


def _one_exercise_per_module(registry: CourseRegistry) -> list[str]:
    """One playable exercise key per module, in canonical order — an exam's question set."""
    keys: list[str] = []
    for _block, module in registry.manifest.iter_modules():
        playable = registry.playable_module_exercises(module.id)
        if playable:
            keys.append(registry.exercise_key(playable[0]))
    return keys


def _attempts(keys: list[str], exam_id: uuid.UUID) -> list[Attempt]:
    return [
        Attempt(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            exercise_id=key,
            seed=1234 + index,
            instance_snapshot={},
            state=AttemptState.OPEN,
            exam_session_id=exam_id,
        )
        for index, key in enumerate(keys)
    ]


def _session(rules: dict[str, object]) -> ExamSession:
    return ExamSession(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        course_id="crypto-futures",
        created_at=datetime.now(UTC),
        finished_at=None,
        rules={"scope": "global", "blockId": None, "status": "open", **rules},
    )


def test_the_frozen_order_beats_the_manifest_order() -> None:
    """A session whose recorded order disagrees with the manifest renders in the recorded one.

    Reversing is a stand-in for a renumbering: what matters is that the two orders differ, and that
    the one the exam was assembled in is the one a reader sees.
    """
    registry = _registry()
    keys = _one_exercise_per_module(registry)
    assert len(keys) > 5, "the fixture needs enough questions for an order to be visible"

    reversed_keys = list(reversed(keys))
    exam = _session({QUESTION_ORDER: reversed_keys})
    view = _build_view(exam, registry, _attempts(keys, exam.id), "en", reveal=False)

    rendered = [registry.exercise_key(q.exercise_id) for q in view.questions]
    assert rendered == reversed_keys, "the view followed the manifest instead of the frozen order"
    assert [q.index for q in view.questions] == list(range(len(rendered)))


def test_a_session_without_a_frozen_order_still_renders_canonically() -> None:
    """Sessions written before the order was frozen keep the old derivation, deterministically."""
    registry = _registry()
    keys = _one_exercise_per_module(registry)
    exam = _session({})
    assert _frozen_order(exam) is None

    view = _build_view(exam, registry, _attempts(list(reversed(keys)), exam.id), "en", reveal=False)
    rendered = [registry.exercise_key(q.exercise_id) for q in view.questions]
    assert rendered == keys, "the legacy path must still sort by the manifest's module order"

    canonical = _canonical_order(registry)
    modules = [registry.exercise_location(q.exercise_id)[1] for q in view.questions]  # type: ignore[index]
    assert modules == sorted(modules, key=lambda m: canonical[m])


def test_the_frozen_order_is_read_from_the_rules_blob() -> None:
    """It rides in the JSONB the session already has, so adding it needed no schema migration."""
    assert _frozen_order(_session({})) is None
    assert _frozen_order(_session({QUESTION_ORDER: []})) is None
    assert _frozen_order(_session({QUESTION_ORDER: ["b", "a"]})) == {"b": 0, "a": 1}
