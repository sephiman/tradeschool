# SPDX-License-Identifier: AGPL-3.0-only
"""Exams: sampling coverage, deferred grading, resume, unanswered handling, review reproducibility,
and the hard requirement — exam attempts never contaminate practice statistics."""

from __future__ import annotations

from httpx import AsyncClient

CREDS = {"username": "examtaker", "password": "correcthorse"}


async def _auth(client: AsyncClient) -> None:
    await client.post("/api/auth/register", json={**CREDS, "locale": "en"})
    await client.post("/api/auth/login", json=CREDS)


async def _module_order(client: AsyncClient) -> list[str]:
    course = (await client.get("/api/course")).json()
    return [m["id"] for b in course["blocks"] for m in b["modules"]]


async def test_global_exam_covers_every_module_in_order(content_client: AsyncClient) -> None:
    await _auth(content_client)
    exam = (await content_client.post("/api/exams", json={"scope": "global"})).json()
    assert exam["scope"] == "global"
    assert exam["status"] == "open"

    q_modules = [q["moduleId"] for q in exam["questions"]]
    # One question per module, and exactly the canonical module order.
    assert q_modules == await _module_order(content_client)
    assert len(q_modules) == len(set(q_modules))  # no module twice

    # Statement only — never a solution before submission.
    for q in exam["questions"]:
        assert q["prompt"]
        assert q["correctAnswer"] is None
        assert q["solutionSteps"] == []
        assert q["answered"] is False


async def test_block_exam_scopes_to_one_block(content_client: AsyncClient) -> None:
    await _auth(content_client)
    exam = (await content_client.post("/api/exams", json={"scope": "block", "blockId": "block-a"})).json()
    assert exam["scope"] == "block" and exam["blockId"] == "block-a"
    assert {q["blockId"] for q in exam["questions"]} == {"block-a"}
    assert len(exam["questions"]) >= 1


async def test_bad_block_scope_rejected(content_client: AsyncClient) -> None:
    await _auth(content_client)
    resp = await content_client.post("/api/exams", json={"scope": "block", "blockId": "ghost"})
    assert resp.status_code == 400
    assert resp.json()["code"] == "EXAM_BAD_SCOPE"


async def test_answer_is_deferred_and_resumable(content_client: AsyncClient) -> None:
    await _auth(content_client)
    exam = (await content_client.post("/api/exams", json={"scope": "block", "blockId": "block-a"})).json()
    q0 = exam["questions"][0]
    # Answer one question — accepted, no feedback returned.
    r = await content_client.post(
        f"/api/exams/{exam['id']}/questions/{q0['attemptId']}/answer", json={"answer": {"optionId": "o0"}}
    )
    assert r.status_code == 204

    # Resume: the open session comes back with the stored answer and still no solution.
    current = (await content_client.get("/api/exams/current")).json()
    assert current is not None and current["id"] == exam["id"]
    resumed_q0 = next(q for q in current["questions"] if q["attemptId"] == q0["attemptId"])
    assert resumed_q0["answered"] is True
    assert resumed_q0["givenAnswer"] == {"optionId": "o0"}
    assert resumed_q0["correctAnswer"] is None


async def test_submit_reveals_solutions_and_flags_unanswered(content_client: AsyncClient) -> None:
    await _auth(content_client)
    exam = (await content_client.post("/api/exams", json={"scope": "block", "blockId": "block-a"})).json()
    q0 = exam["questions"][0]
    await content_client.post(
        f"/api/exams/{exam['id']}/questions/{q0['attemptId']}/answer", json={"answer": {"optionId": "o0"}}
    )
    submitted = (await content_client.post(f"/api/exams/{exam['id']}/submit", json={})).json()

    assert submitted["status"] == "submitted"
    result = submitted["result"]
    assert result["total"] == len(exam["questions"])
    assert 0.0 <= result["score"] <= 1.0
    assert len(result["blocks"]) == 1 and result["blocks"][0]["blockId"] == "block-a"

    for q in submitted["questions"]:
        # Every question now carries its worked solution + correct answer.
        assert q["correctAnswer"] is not None
        answered_q = q["attemptId"] == q0["attemptId"]
        assert q["unanswered"] is (not answered_q)
        if not answered_q:
            assert q["isCorrect"] is False  # unanswered grades incorrect


async def test_review_reproduces_exactly(content_client: AsyncClient) -> None:
    await _auth(content_client)
    exam = (await content_client.post("/api/exams", json={"scope": "block", "blockId": "block-a"})).json()
    await content_client.post(f"/api/exams/{exam['id']}/submit", json={})
    first = (await content_client.get(f"/api/exams/{exam['id']}/review")).json()
    second = (await content_client.get(f"/api/exams/{exam['id']}/review")).json()
    # Seeds persist per attempt → the review is byte-stable across reloads.
    assert first == second
    assert all(q["correctAnswer"] is not None for q in first["questions"])


async def test_same_scope_restart_abandons_prior(content_client: AsyncClient) -> None:
    await _auth(content_client)
    first = (await content_client.post("/api/exams", json={"scope": "global"})).json()
    second = (await content_client.post("/api/exams", json={"scope": "global"})).json()
    assert first["id"] != second["id"]

    # Only the newest open session is current; the prior one was abandoned.
    current = (await content_client.get("/api/exams/current")).json()
    assert current["id"] == second["id"]
    # Abandoned sessions count toward nothing — history stays empty until something is submitted.
    assert (await content_client.get("/api/exams")).json() == []

    # The abandoned one can't be rendered as in-progress.
    stale = await content_client.get(f"/api/exams/{first['id']}")
    assert stale.status_code == 409


async def test_history_lists_submitted_only(content_client: AsyncClient) -> None:
    await _auth(content_client)
    exam = (await content_client.post("/api/exams", json={"scope": "block", "blockId": "block-a"})).json()
    await content_client.post(f"/api/exams/{exam['id']}/submit", json={})
    history = (await content_client.get("/api/exams")).json()
    assert len(history) == 1
    row = history[0]
    assert row["id"] == exam["id"] and row["scope"] == "block" and row["blockId"] == "block-a"
    assert row["total"] >= 1 and 0.0 <= row["score"] <= 1.0


async def _practice_once(client: AsyncClient, exercise_id: str) -> None:
    """One full practice attempt (answered) to build practice statistics."""
    inst = (await client.post(f"/api/exercises/{exercise_id}/attempts")).json()
    options = inst["payload"].get("options") or [{"id": "o0"}]
    answer = {"answer": {"optionId": options[0]["id"]}}
    await client.post(f"/api/attempts/{inst['attemptId']}/answer", json=answer)


async def test_exam_attempts_do_not_contaminate_practice_stats(content_client: AsyncClient) -> None:
    """The isolation guard: every practice signal is identical before and after an exam runs."""
    await _auth(content_client)
    # Build some practice history first (calculations → guaranteed optionId answers).
    await _practice_once(content_client, "m04-ex-1")
    await _practice_once(content_client, "m05-ex-1")

    me_before = (await content_client.get("/api/stats/me")).json()
    global_before = (await content_client.get("/api/stats/global")).json()
    course_before = (await content_client.get("/api/course")).json()

    # Run and submit a full global exam (23 exam attempts across every module).
    exam = (await content_client.post("/api/exams", json={"scope": "global"})).json()
    for q in exam["questions"]:
        await content_client.post(
            f"/api/exams/{exam['id']}/questions/{q['attemptId']}/answer", json={"answer": {"optionId": "o0"}}
        )
    await content_client.post(f"/api/exams/{exam['id']}/submit", json={})

    me_after = (await content_client.get("/api/stats/me")).json()
    global_after = (await content_client.get("/api/stats/global")).json()
    course_after = (await content_client.get("/api/course")).json()

    # Not one practice aggregate moved.
    assert me_after == me_before
    assert global_after == global_before
    # Course-page mastery + the started/Continue signal are unmoved too (full isolation).
    assert course_after == course_before
