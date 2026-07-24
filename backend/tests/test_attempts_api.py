# SPDX-License-Identifier: AGPL-3.0-only
from __future__ import annotations

import uuid

from httpx import AsyncClient

from tradeschool.attempts.models import Attempt
from tradeschool.config import Settings
from tradeschool.content.registry import load_registry
from tradeschool.db import get_sessionmaker
from tradeschool.exercises.base import rng_for
from tradeschool.exercises.calculation import CalculationConfig, _mc_options
from tradeschool.exercises.quiz import QuizConfig, QuizKind, QuizVariant, _shuffled

CREDS = {"username": "solver", "password": "correcthorse"}


def quiz_answer(variant: QuizVariant, seed: int, correct: bool) -> dict[str, object]:
    """Build a genuinely correct or wrong answer for whatever sub-kind the seed selected."""
    k = variant.kind
    if k is QuizKind.SINGLE_CHOICE:
        cid = next(o.id for o in variant.options if o.correct)
        wid = next(o.id for o in variant.options if not o.correct)
        return {"optionId": cid if correct else wid}
    if k is QuizKind.MULTI_SELECT:
        return {"optionIds": [o.id for o in variant.options if o.correct] if correct else []}
    if k is QuizKind.TRUE_FALSE:
        return {"value": variant.answer if correct else (not variant.answer)}
    if k is QuizKind.ORDERING:
        order = [i.id for i in sorted(variant.items, key=lambda it: it.position)]
        return {"order": order if correct else list(reversed(order))}
    lorder, rorder = _shuffled(len(variant.pairs), seed, 1), _shuffled(len(variant.pairs), seed, 2)
    lid = {p: f"l{s}" for s, p in enumerate(lorder)}
    rid = {p: f"r{s}" for s, p in enumerate(rorder)}
    cmap = {lid[i]: rid[i] for i in range(len(variant.pairs))}
    if not correct:
        keys = list(cmap)
        cmap[keys[0]], cmap[keys[1]] = cmap[keys[1]], cmap[keys[0]]
    return {"pairs": cmap}


async def _auth(client: AsyncClient) -> None:
    await client.post("/api/auth/register", json={**CREDS, "locale": "en"})
    await client.post("/api/auth/login", json=CREDS)


async def _seed_of(attempt_id: str) -> int:
    async with get_sessionmaker()() as db:
        attempt = await db.get(Attempt, uuid.UUID(attempt_id))
        assert attempt is not None
        return attempt.seed


async def test_open_attempt_hides_solution(content_client: AsyncClient) -> None:
    import json

    await _auth(content_client)
    resp = await content_client.post("/api/exercises/m01-ex-1/attempts")
    assert resp.status_code == 201
    body = resp.json()
    assert body["type"] == "quiz" and body["state"] == "open" and body["prompt"]
    payload = body["payload"]
    kind = payload["kind"]
    # No solution field may ever travel to the client, whatever the sub-kind.
    blob = json.dumps(payload)
    assert '"correct"' not in blob and '"position"' not in blob and '"answer"' not in blob
    if kind in ("single_choice", "multi_select"):
        assert len(payload["options"]) >= 2
        for opt in payload["options"]:
            assert set(opt.keys()) == {"id", "text"}
    elif kind == "ordering":
        for it in payload["items"]:  # shuffled, positions withheld
            assert set(it.keys()) == {"id", "text"}
    elif kind == "matching":
        for it in payload["lefts"] + payload["rights"]:  # both sides shuffled, pairing withheld
            assert set(it.keys()) == {"id", "text"}
    else:  # true_false — the claim is the prompt, nothing else
        assert set(payload.keys()) == {"kind"}


async def test_quiz_correct_and_wrong_paths(content_client: AsyncClient, settings: Settings) -> None:
    await _auth(content_client)
    registry = load_registry(settings.content_dir)
    _, config = registry.get_exercise_config("m01-ex-1")
    assert isinstance(config, QuizConfig)

    opened = (await content_client.post("/api/exercises/m01-ex-1/attempts")).json()
    seed = await _seed_of(opened["attemptId"])
    variant = rng_for(seed).choice(config.variants)

    graded = (
        await content_client.post(
            f"/api/attempts/{opened['attemptId']}/answer",
            json={"answer": quiz_answer(variant, seed, correct=True)},
        )
    ).json()
    assert graded["correct"] is True
    assert graded["explanation"]

    # A fresh attempt answered wrong (kind-aware, since the seed may pick any sub-kind).
    opened2 = (await content_client.post("/api/exercises/m01-ex-1/attempts")).json()
    seed2 = await _seed_of(opened2["attemptId"])
    variant2 = rng_for(seed2).choice(config.variants)
    wrong = (
        await content_client.post(
            f"/api/attempts/{opened2['attemptId']}/answer",
            json={"answer": quiz_answer(variant2, seed2, correct=False)},
        )
    ).json()
    assert wrong["correct"] is False


async def test_calculation_correct_path_with_solution(
    content_client: AsyncClient, settings: Settings
) -> None:
    await _auth(content_client)
    registry = load_registry(settings.content_dir)
    _, config = registry.get_exercise_config("m06-ex-1")
    assert isinstance(config, CalculationConfig)

    opened = (await content_client.post("/api/exercises/m06-ex-1/attempts")).json()
    assert opened["type"] == "calculation" and opened["payload"]["kind"] == "multiple_choice"
    seed = await _seed_of(opened["attemptId"])
    _p, _e, _opts, correct_id, _d = _mc_options(config, seed)

    graded = (
        await content_client.post(
            f"/api/attempts/{opened['attemptId']}/answer", json={"answer": {"optionId": correct_id}}
        )
    ).json()
    assert graded["correct"] is True
    assert graded["solutionSteps"]  # the instantiated formula-with-numbers
    assert graded["correctAnswer"]["value"]


async def test_answer_is_single_shot(content_client: AsyncClient, settings: Settings) -> None:
    await _auth(content_client)
    _, config = load_registry(settings.content_dir).get_exercise_config("m01-ex-1")
    assert isinstance(config, QuizConfig)
    opened = (await content_client.post("/api/exercises/m01-ex-1/attempts")).json()
    seed = await _seed_of(opened["attemptId"])
    variant = rng_for(seed).choice(config.variants)
    ans = {"answer": quiz_answer(variant, seed, correct=True)}
    first = await content_client.post(f"/api/attempts/{opened['attemptId']}/answer", json=ans)
    assert first.status_code == 200
    again = await content_client.post(f"/api/attempts/{opened['attemptId']}/answer", json=ans)
    assert again.status_code == 409
    assert again.json()["code"] == "ATTEMPT_ALREADY_RESOLVED"


async def test_opening_new_attempt_abandons_prior_unanswered(content_client: AsyncClient) -> None:
    await _auth(content_client)
    first = (await content_client.post("/api/exercises/m01-ex-1/attempts")).json()
    await content_client.post("/api/exercises/m01-ex-1/attempts")  # opening again abandons the first
    listing = (await content_client.get("/api/attempts?exercise_id=m01-ex-1")).json()
    states = {a["attemptId"]: a["state"] for a in listing}
    assert states[first["attemptId"]] == "abandoned"


async def test_review_replays_from_seed_and_reveals_solution(
    content_client: AsyncClient, settings: Settings
) -> None:
    await _auth(content_client)
    _, config = load_registry(settings.content_dir).get_exercise_config("m01-ex-1")
    assert isinstance(config, QuizConfig)
    opened = (await content_client.post("/api/exercises/m01-ex-1/attempts")).json()
    seed = await _seed_of(opened["attemptId"])
    variant = rng_for(seed).choice(config.variants)
    ans = quiz_answer(variant, seed, correct=True)
    await content_client.post(f"/api/attempts/{opened['attemptId']}/answer", json={"answer": ans})
    review = (await content_client.get(f"/api/attempts/{opened['attemptId']}")).json()
    assert review["state"] == "answered"
    assert review["prompt"] == opened["prompt"]  # same scenario, replayed from the seed
    assert review["givenAnswer"] == ans
    assert review["correctAnswer"] is not None


async def test_synthetic_chart_flow(content_client: AsyncClient, settings: Settings) -> None:
    from tradeschool.exercises.synthetic_chart import SyntheticChartConfig, SyntheticChartGenerator

    await _auth(content_client)
    registry = load_registry(settings.content_dir)
    _, config = registry.get_exercise_config("m12-ex-1")
    assert isinstance(config, SyntheticChartConfig)

    opened = (await content_client.post("/api/exercises/m12-ex-1/attempts")).json()
    assert opened["type"] == "synthetic_chart"
    payload = opened["payload"]
    assert "series" in payload and "rsi" in payload and "choices" in payload
    # The planted divergence must not be exposed before answering.
    assert "divergence" not in payload and "swing1" not in payload

    seed = await _seed_of(opened["attemptId"])
    truth = SyntheticChartGenerator().grade(config, seed, {"divergence": "none"}, "en")
    correct_choice = truth.correct_answer["divergence"]  # type: ignore[index]

    graded = (
        await content_client.post(
            f"/api/attempts/{opened['attemptId']}/answer", json={"answer": {"divergence": correct_choice}}
        )
    ).json()
    assert graded["correct"] is True
    assert graded["correctAnswer"]["divergence"] == correct_choice


async def test_pattern_chart_flow(content_client: AsyncClient, settings: Settings) -> None:
    from tradeschool.exercises.pattern_chart import PatternChartConfig, PatternChartGenerator

    await _auth(content_client)
    registry = load_registry(settings.content_dir)
    _, config = registry.get_exercise_config("m08-ex-1")  # fakeout injector
    assert isinstance(config, PatternChartConfig)

    opened = (await content_client.post("/api/exercises/m08-ex-1/attempts")).json()
    assert opened["type"] == "pattern_chart"
    payload = opened["payload"]
    assert "series" in payload and "choices" in payload
    # The planted label and its annotations must not be exposed before answering (§8).
    assert "label" not in payload and "annotations" not in payload

    seed = await _seed_of(opened["attemptId"])
    truth = PatternChartGenerator().grade(config, seed, {"label": "no_break"}, "en")
    correct_label = truth.correct_answer["label"]  # type: ignore[index]

    graded = (
        await content_client.post(
            f"/api/attempts/{opened['attemptId']}/answer", json={"answer": {"label": correct_label}}
        )
    ).json()
    assert graded["correct"] is True
    assert graded["correctAnswer"]["label"] == correct_label


async def test_unknown_exercise_is_404(content_client: AsyncClient) -> None:
    await _auth(content_client)
    unknown = await content_client.post("/api/exercises/ghost/attempts")
    assert unknown.status_code == 404
    assert unknown.json()["code"] == "EXERCISE_NOT_FOUND"


async def test_attempts_require_auth(content_client: AsyncClient) -> None:
    assert (await content_client.post("/api/exercises/m01-ex-1/attempts")).status_code == 401


async def test_cannot_touch_others_attempt(content_client: AsyncClient) -> None:
    await _auth(content_client)
    fake = uuid.uuid4()
    assert (await content_client.get(f"/api/attempts/{fake}")).status_code == 404
