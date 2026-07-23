# SPDX-License-Identifier: AGPL-3.0-only
"""Bulk instance generation for the in-app chart gallery (§ credibility gate). Returns full
instances **with ground truth** — safe only because this router is mounted solely under DEV_MODE."""

from __future__ import annotations

import io
import uuid
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import PlainTextResponse

from tradeschool.attempts.models import Attempt
from tradeschool.auth.backend import current_active_user
from tradeschool.auth.models import User
from tradeschool.content.registry import CourseRegistry
from tradeschool.content.router import get_registry
from tradeschool.db import get_async_session
from tradeschool.errors import AppError
from tradeschool.exercises.pattern_chart import PatternChartConfig, PatternChartGenerator
from tradeschool.exercises.registry import get_generator
from tradeschool.exercises.synthetic_chart import SyntheticChartConfig, SyntheticChartGenerator

router = APIRouter(tags=["dev"])


def _dummy_answer(payload: dict[str, object]) -> dict[str, object]:
    """A type-appropriate throwaway answer so grade() yields the ground truth for display."""
    if "choices" in payload:
        choices = payload["choices"]
        first = choices[0] if isinstance(choices, list) and choices else "none"
        # Both chart generators read a single choice key ("divergence" for divergence charts,
        # "label" for the generic pattern charts); supplying both is harmless and covers either.
        return {"divergence": first, "label": first}
    if "options" in payload:
        options = payload["options"]
        first = options[0]["id"] if isinstance(options, list) and options else ""
        return {"optionId": first}
    return {"value": "0"}


class GalleryItem(BaseModel):
    seed: int
    prompt: str
    payload: dict[str, object]
    groundTruth: object


class GalleryResponse(BaseModel):
    exerciseId: str
    type: str
    items: list[GalleryItem]


@router.get("/instances", response_model=GalleryResponse)
async def dev_instances(
    exercise_id: Annotated[str, Query()],
    _user: Annotated[User, Depends(current_active_user)],
    registry: Annotated[CourseRegistry, Depends(get_registry)],
    count: Annotated[int, Query(ge=1, le=60)] = 24,
    lang: Annotated[str, Query(pattern="^(en|es)$")] = "en",
) -> GalleryResponse:
    resolved = registry.get_exercise_config(exercise_id)
    if resolved is None:
        raise AppError("EXERCISE_NOT_FOUND", f"No playable exercise {exercise_id!r}.", status_code=404)
    exercise_type, config = resolved
    generator = get_generator(exercise_type)

    items: list[GalleryItem] = []
    for seed in range(1, count + 1):
        instance = generator.generate(config, seed, lang)
        ground = generator.grade(config, seed, _dummy_answer(instance.payload), lang)
        items.append(
            GalleryItem(
                seed=seed,
                prompt=instance.prompt,
                payload=instance.payload,
                groundTruth=ground.correct_answer,
            )
        )
    return GalleryResponse(exerciseId=exercise_id, type=exercise_type.value, items=items)


def _instance_for(registry: CourseRegistry, exercise_id: str, seed: int, lang: str) -> dict[str, object]:
    resolved = registry.get_exercise_config(exercise_id)
    if resolved is None:
        raise AppError("EXERCISE_NOT_FOUND", f"No playable exercise {exercise_id!r}.", status_code=404)
    exercise_type, config = resolved
    generator = get_generator(exercise_type)
    instance = generator.generate(config, seed, lang)
    ground = generator.grade(config, seed, _dummy_answer(instance.payload), lang)
    return {
        "exerciseId": exercise_id,
        "type": exercise_type.value,
        "seed": seed,
        "prompt": instance.prompt,
        "payload": instance.payload,
        "groundTruth": ground.correct_answer,
    }


def _chart_rows(
    registry: CourseRegistry, exercise_id: str, seed: int, lang: str
) -> tuple[dict[str, list[Any]], int, object, str]:
    """Return (columns, warmup, groundTruth, indicator).

    For synthetic charts the columns include the WARM-UP rows (indicator convergence), so the RSI
    column is exactly reproducible by recomputing Wilder's RSI over the full `close` column. The
    chart hides those rows; `visible`/`visible_index` mark which rows the learner actually sees.
    """
    resolved = registry.get_exercise_config(exercise_id)
    if resolved is None:
        raise AppError("EXERCISE_NOT_FOUND", f"No playable exercise {exercise_id!r}.", status_code=404)
    exercise_type, config = resolved

    if isinstance(config, SyntheticChartConfig):
        gen = cast(SyntheticChartGenerator, get_generator(exercise_type))
        f = gen.full_data(config, seed)
        s = f.series
        cols: dict[str, list[Any]] = {
            "time": s.time, "open": s.open, "high": s.high, "low": s.low, "close": s.close,
            "volume": s.volume, "rsi": f.rsi, "macd": f.macd_line,
            "macd_signal": f.macd_signal, "macd_hist": f.macd_hist,
        }
        ground: dict[str, object] = {"divergence": f.target.value, "swing1": f.swing1, "swing2": f.swing2}
        return cols, f.warmup, ground, config.indicator

    if isinstance(config, PatternChartConfig):
        pgen = cast(PatternChartGenerator, get_generator(exercise_type))
        pf = pgen.full_data(config, seed)
        ps = pf.series
        pcols: dict[str, list[Any]] = {
            "time": ps.time, "open": ps.open, "high": ps.high, "low": ps.low, "close": ps.close,
            "volume": ps.volume, "rsi": pf.rsi, "macd": pf.macd_line,
            "macd_signal": pf.macd_signal, "macd_hist": pf.macd_hist,
        }
        pcols.update({f"overlay_{k}": v for k, v in pf.overlays.items()})  # e.g. overlay_ema50
        if pf.oi:
            pcols["oi"] = pf.oi  # open-interest series (m17 derivatives)
        pground: dict[str, object] = {
            "label": pf.label, "annotations": pf.annotations, "levels": pf.levels
        }
        return pcols, pf.warmup, pground, pf.indicator

    data = _instance_for(registry, exercise_id, seed, lang)
    payload = data["payload"]
    if not isinstance(payload, dict) or "series" not in payload:
        raise AppError("NOT_A_CHART", f"{exercise_id!r} is not a chart exercise.", status_code=400)
    sd = cast("dict[str, Any]", payload["series"])
    macd = cast("dict[str, Any]", payload.get("macd") or {})
    cols = {
        "time": sd["time"], "open": sd["open"], "high": sd["high"], "low": sd["low"],
        "close": sd["close"], "volume": sd["volume"], "rsi": payload.get("rsi") or [],
        "macd": macd.get("line", []), "macd_signal": macd.get("signal", []),
        "macd_hist": macd.get("hist", []),
    }
    return cols, 0, data["groundTruth"], str(payload.get("indicator", "rsi"))


@router.get("/charts/data")
async def dev_chart_data(
    exercise_id: Annotated[str, Query()],
    seed: Annotated[int, Query(ge=0)],
    _user: Annotated[User, Depends(current_active_user)],
    registry: Annotated[CourseRegistry, Depends(get_registry)],
    lang: Annotated[str, Query(pattern="^(en|es)$")] = "en",
    fmt: Annotated[str, Query(pattern="^(json|csv)$")] = "json",
) -> object:
    """Exact data behind a rendered chart for a given seed: full OHLC + the RSI/MACD as computed
    and rendered, INCLUDING warm-up rows so the RSI reproduces from `close`. Recompute Wilder's RSI
    over the full `close` column and compare the `rsi` column — they match exactly."""
    cols, warmup, ground, indicator = _chart_rows(registry, exercise_id, seed, lang)
    n = len(cols["close"])
    base_keys = ["time", "open", "high", "low", "close", "volume", "rsi", "macd", "macd_signal", "macd_hist"]
    keys = base_keys + [k for k in cols if k not in base_keys]  # append overlay columns, if any

    if fmt == "json":
        rows = [
            {"rowIndex": i, "visible": i >= warmup, "visibleIndex": (i - warmup) if i >= warmup else None,
             **{k: cols[k][i] if i < len(cols[k]) else None for k in keys}}
            for i in range(n)
        ]
        return {
            "exerciseId": exercise_id, "seed": seed, "indicator": indicator, "warmup": warmup,
            "groundTruth": ground, "rows": rows,
        }

    buf = io.StringIO()
    buf.write("row_index,visible,visible_index," + ",".join(keys) + "\n")
    for i in range(n):
        head = [i, 1 if i >= warmup else 0, (i - warmup) if i >= warmup else ""]
        rest = [cols[k][i] if i < len(cols[k]) else "" for k in keys]
        buf.write(",".join(str(v) for v in head + rest) + "\n")
    filename = f"{exercise_id}-seed{seed}.csv"
    return PlainTextResponse(
        buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


class DevAttempt(BaseModel):
    attemptId: uuid.UUID
    seed: int
    state: str
    isCorrect: bool | None
    createdAt: str


@router.get("/attempts", response_model=list[DevAttempt])
async def dev_attempts(
    exercise_id: Annotated[str, Query()],
    user: Annotated[User, Depends(current_active_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> list[DevAttempt]:
    """Your own attempts for an exercise WITH their seeds — so a past chart can be reproduced
    exactly via /dev/charts/data. Dev-only (seeds aren't exposed in production)."""
    rows = await session.scalars(
        select(Attempt)
        .where(Attempt.user_id == user.id, Attempt.exercise_id == exercise_id)
        .order_by(Attempt.created_at.desc())
    )
    return [
        DevAttempt(
            attemptId=a.id,
            seed=a.seed,
            state=a.state.value,
            isCorrect=a.is_correct,
            createdAt=a.created_at.isoformat(),
        )
        for a in rows.all()
    ]
