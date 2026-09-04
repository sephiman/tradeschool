# SPDX-License-Identifier: AGPL-3.0-only
"""Exams: sampling, deferred grading, resume, review — and that they never touch practice statistics."""

from __future__ import annotations

from httpx import AsyncClient

CREDS = {"username": "examtaker", "password": "correcthorse"}


async def _auth(client: AsyncClient) -> None:
    await client.post("/api/auth/register", json={**CREDS, "locale": "en"})
    await client.post("/api/auth/login", json=CREDS)


async def _module_order(client: AsyncClient, *, examinable_only: bool = False) -> list[str]:
    course = (await client.get("/api/course")).json()
    return [
        m["id"]
        for b in course["blocks"]
        for m in b["modules"]
        if not examinable_only or m["exercisesTotal"] > 0
    ]


async def test_global_exam_covers_every_module_in_order(content_client: AsyncClient) -> None:
    await _auth(content_client)
    exam = (await content_client.post("/api/exams", json={"scope": "global"})).json()
    assert exam["scope"] == "global"
    assert exam["status"] == "open"

    q_modules = [q["moduleId"] for q in exam["questions"]]
    # One question per module WITH A BANK, in exactly the canonical module order. The epilogue (m35)
    # carries no exercises, so it is the one module a global exam skips — `_scope_modules` filters on
    # the playable bank, which is why no exam-side list has to learn about it.
    assert q_modules == await _module_order(content_client, examinable_only=True)
    assert "m35" in await _module_order(content_client) and "m35" not in q_modules
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


async def test_a_block_exam_scores_per_block_and_reveals_unanswered(content_client: AsyncClient) -> None:
    """A block exam samples one question per module and scores cleanly, unanswered included.

    RETIRED with the 2026-08-10 block-g→block-f merge: the one-question-exam edge this test used to
    pin via the single-module block-g (no `EXAM_EMPTY`, no zero division at n=1). The block-g letter
    is back as the epilogue, but its one module has no exercises, so it pins the EMPTY edge instead
    (below) and never the n=1 one; what remains pinned here is the same scoring path on f — m34's
    question now sampled under its new block.
    """
    await _auth(content_client)
    exam = (await content_client.post("/api/exams", json={"scope": "block", "blockId": "block-f"})).json()
    assert exam["scope"] == "block" and exam["blockId"] == "block-f"
    assert [q["moduleId"] for q in exam["questions"]] == ["m29", "m30", "m31", "m32", "m33", "m34"]

    submitted = (await content_client.post(f"/api/exams/{exam['id']}/submit")).json()
    result = submitted["result"]
    assert result["total"] == 6
    assert result["blocks"] == [
        {"blockId": "block-f", "title": submitted["blockTitle"], "correct": 0, "total": 6, "score": 0.0}
    ]
    # Unanswered, so incorrect — but distinguishable from a wrong answer, and the solution is revealed.
    assert all(q["unanswered"] is True for q in submitted["questions"])


async def test_global_exam_discovers_a_newly_added_module(content_client: AsyncClient) -> None:
    """A new module joins the global exam by being registered — there is no exam-side list to update."""
    await _auth(content_client)
    exam = (await content_client.post("/api/exams", json={"scope": "global"})).json()
    m34 = [q for q in exam["questions"] if q["moduleId"] == "m34"]
    assert len(m34) == 1, "the global exam did not pick up m34"
    assert m34[0]["blockId"] == "block-f"  # block-g merged into block-f, 2026-08-10
    # ...and it sampled from m34's own bank, not from somewhere else.
    assert m34[0]["exerciseId"] in {"m34-ex-1", "m34-ex-2", "m34-ex-3", "m34-ex-4"}


async def test_a_block_with_no_exercises_cannot_be_examined(content_client: AsyncClient) -> None:
    """The epilogue block is real content with nothing to grade: 409 EXAM_EMPTY, not an empty exam."""
    await _auth(content_client)
    resp = await content_client.post("/api/exams", json={"scope": "block", "blockId": "block-g"})
    assert resp.status_code == 409
    assert resp.json()["code"] == "EXAM_EMPTY"


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
    current = (await content_client.get("/api/exams/open")).json()[0]
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

    # Only one sitting is open; the prior one of the same scope was abandoned.
    current = (await content_client.get("/api/exams/open")).json()[0]
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


async def test_every_open_sitting_is_reachable_not_just_the_newest(content_client: AsyncClient) -> None:
    """Two scopes can be open at once, and the older one used to have no route in the UI.

    `start_exam` closes an open session only of the SAME scope, so a block exam started while a global
    one is unfinished leaves both open. The old `/current` answered with the newest alone, which left
    the other consuming its questions with no way to resume or abandon it.
    """
    await _auth(content_client)
    globally = (await content_client.post("/api/exams", json={"scope": "global"})).json()
    per_block = (
        await content_client.post("/api/exams", json={"scope": "block", "blockId": "block-a"})
    ).json()
    assert globally["id"] != per_block["id"]

    open_sittings = (await content_client.get("/api/exams/open")).json()
    assert [s["id"] for s in open_sittings] == [per_block["id"], globally["id"]], "newest first"
    # Both are genuinely still in progress: each renders, rather than 409-ing as a closed session does.
    for sitting in open_sittings:
        assert (await content_client.get(f"/api/exams/{sitting['id']}")).status_code == 200

    # And starting a third of one scope closes only that scope's sitting.
    again = (await content_client.post("/api/exams", json={"scope": "global"})).json()
    still_open = [s["id"] for s in (await content_client.get("/api/exams/open")).json()]
    assert set(still_open) == {again["id"], per_block["id"]}


async def test_question_order_is_frozen_at_assembly(content_client: AsyncClient) -> None:
    """The order is recorded when the exam is built, not re-derived from the manifest at each render."""
    await _auth(content_client)
    exam = (await content_client.post("/api/exams", json={"scope": "global"})).json()
    first = [q["exerciseId"] for q in exam["questions"]]

    # Every render agrees with the assembly, including the reveal path after submission.
    rendered = (await content_client.get(f"/api/exams/{exam['id']}")).json()
    assert [q["exerciseId"] for q in rendered["questions"]] == first
    assert [q["index"] for q in rendered["questions"]] == list(range(len(first)))
    submitted = (await content_client.post(f"/api/exams/{exam['id']}/submit", json={})).json()
    assert [q["exerciseId"] for q in submitted["questions"]] == first
    reviewed = (await content_client.get(f"/api/exams/{exam['id']}/review")).json()
    assert [q["exerciseId"] for q in reviewed["questions"]] == first


async def test_a_different_block_of_the_same_scope_abandons_nothing(content_client: AsyncClient) -> None:
    """The abandon rule is scope AND block, and the web's confirmation dialog is built on exactly it.

    `ExamPage` asks before starting only when an open sitting shares both, so if the server ever
    widened this to "any open block exam" the web would abandon a sitting it never warned about.
    """
    await _auth(content_client)
    first = (await content_client.post("/api/exams", json={"scope": "block", "blockId": "block-a"})).json()
    second = (await content_client.post("/api/exams", json={"scope": "block", "blockId": "block-b"})).json()

    still_open = {s["id"] for s in (await content_client.get("/api/exams/open")).json()}
    assert still_open == {first["id"], second["id"]}, "a different block must not be abandoned"

    # ...and the same block does abandon, which is the branch the dialog exists to warn about.
    third = (await content_client.post("/api/exams", json={"scope": "block", "blockId": "block-a"})).json()
    after = {s["id"] for s in (await content_client.get("/api/exams/open")).json()}
    assert after == {third["id"], second["id"]}
    assert (await content_client.get(f"/api/exams/{first['id']}")).status_code == 409
