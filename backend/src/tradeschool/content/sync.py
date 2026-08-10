# SPDX-License-Identifier: AGPL-3.0-only
"""Reconcile the manifest into the DB skeleton by permanent KEY (§4.2).

Rows absent from the manifest are marked inactive, never hard-deleted, so historical progress
survives. The DB stores keys, never display ids — keys are chosen once and never renamed, so a
display renumbering leaves every row (and every learner's progress) untouched. Order is a plain
attribute. Course and block ids double as their keys.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tradeschool.config import Settings
from tradeschool.content.models import Block, Course, Exercise, Lesson, Module, SkeletonModel
from tradeschool.content.registry import CourseRegistry, load_registry
from tradeschool.content.schema import Manifest

logger = logging.getLogger("tradeschool.content")


@dataclass
class SyncSummary:
    inserted: int = 0
    updated: int = 0
    deactivated: int = 0

    def __str__(self) -> str:
        return (
            f"Course sync: {self.inserted} inserted, {self.updated} updated, "
            f"{self.deactivated} deactivated."
        )


async def reconcile(manifest: Manifest, session: AsyncSession) -> SyncSummary:
    summary = SyncSummary()

    async def upsert(
        model: type[SkeletonModel],
        rows: dict[str, dict[str, object]],
    ) -> None:
        existing = {row.id: row for row in (await session.scalars(select(model))).all()}
        for identifier, attrs in rows.items():
            current = existing.get(identifier)
            if current is None:
                session.add(model(id=identifier, active=True, **attrs))
                summary.inserted += 1
            else:
                changed = not current.active
                for key, value in attrs.items():
                    if getattr(current, key) != value:
                        setattr(current, key, value)
                        changed = True
                if not current.active:
                    current.active = True
                if changed:
                    summary.updated += 1
        for identifier, current in existing.items():
            if identifier not in rows and current.active:
                current.active = False
                summary.deactivated += 1

    courses: dict[str, dict[str, object]] = {}
    blocks: dict[str, dict[str, object]] = {}
    modules: dict[str, dict[str, object]] = {}
    lessons: dict[str, dict[str, object]] = {}
    exercises: dict[str, dict[str, object]] = {}

    course_id = manifest.course.id
    # `assumes` names modules by display id in the manifest (it is hand-written); the DB stores keys.
    module_key = {m.id: m.key for _, m in manifest.iter_modules()}
    courses[course_id] = {"order_index": 1}
    for b_index, block in enumerate(manifest.blocks, start=1):
        blocks[block.id] = {"course_id": course_id, "order_index": b_index}
        for m_index, module in enumerate(block.modules, start=1):
            modules[module.key] = {
                "course_id": course_id,
                "block_id": block.id,
                "order_index": m_index,
                "assumes": [module_key[dep] for dep in module.assumes],
            }
            for l_index, lesson in enumerate(module.lessons, start=1):
                lessons[lesson.key] = {"module_id": module.key, "order_index": l_index}
                for e_index, exercise in enumerate(lesson.exercises, start=1):
                    exercises[exercise.key] = {
                        "module_id": module.key,
                        "lesson_id": lesson.key,
                        "type": exercise.type,
                        "order_index": e_index,
                    }

    # Parents before children so foreign keys resolve on insert.
    await upsert(Course, courses)
    await session.flush()
    await upsert(Block, blocks)
    await upsert(Module, modules)
    await session.flush()
    await upsert(Lesson, lessons)
    await session.flush()
    await upsert(Exercise, exercises)
    await session.commit()

    logger.info("%s", summary)
    return summary


async def sync_content(settings: Settings, session: AsyncSession) -> tuple[CourseRegistry, SyncSummary]:
    """Load + validate the registry and reconcile it. Returns the registry for serving."""
    registry = load_registry(settings.content_dir)
    summary = await reconcile(registry.manifest, session)
    return registry, summary


async def sync_content_cli(settings: Settings) -> str:
    from tradeschool.db import dispose_engine, get_sessionmaker, init_engine

    init_engine(settings.database_url)
    try:
        async with get_sessionmaker()() as session:
            _, summary = await sync_content(settings, session)
        return str(summary)
    finally:
        await dispose_engine()
