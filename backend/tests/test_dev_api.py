# SPDX-License-Identifier: AGPL-3.0-only
"""Dev-only endpoints: the exact URL shapes /api/dev/attempts (with seed) and /api/dev/charts/data."""

from __future__ import annotations

from httpx import AsyncClient

CREDS = {"username": "devuser", "password": "correcthorse"}


async def _auth(client: AsyncClient) -> None:
    await client.post("/api/auth/register", json={**CREDS, "locale": "en"})
    await client.post("/api/auth/login", json=CREDS)


async def test_dev_attempts_includes_seed(content_client: AsyncClient) -> None:
    await _auth(content_client)
    await content_client.post("/api/exercises/m12-ex-1/attempts")
    resp = await content_client.get("/api/dev/attempts?exercise_id=m12-ex-1")
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    assert "seed" in rows[0] and isinstance(rows[0]["seed"], int)


async def test_dev_chart_data_json_includes_warmup_and_reproduces(content_client: AsyncClient) -> None:
    await _auth(content_client)
    resp = await content_client.get("/api/dev/charts/data?exercise_id=m12-ex-1&seed=5&fmt=json")
    assert resp.status_code == 200
    data = resp.json()
    assert data["warmup"] > 0 and len(data["rows"]) == data["warmup"] + 120
    # Warm-up rows are flagged non-visible; visible rows carry a visibleIndex.
    assert data["rows"][0]["visible"] is False
    assert data["rows"][data["warmup"]]["visible"] is True
    assert data["rows"][data["warmup"]]["visibleIndex"] == 0
    assert "rsi" in data["rows"][0] and "close" in data["rows"][0]


async def test_dev_chart_data_csv(content_client: AsyncClient) -> None:
    await _auth(content_client)
    resp = await content_client.get("/api/dev/charts/data?exercise_id=m12-ex-1&seed=5&fmt=csv")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    header = resp.text.splitlines()[0]
    assert header.startswith("row_index,visible,visible_index,time,open,high,low,close,volume,rsi")


async def test_dev_instances_pattern_chart(content_client: AsyncClient) -> None:
    await _auth(content_client)
    resp = await content_client.get("/api/dev/instances?exercise_id=m08-ex-1&count=5")
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "pattern_chart" and len(data["items"]) == 5
    item = data["items"][0]
    assert "label" in item["groundTruth"]  # generic pattern label, not a divergence
    assert "levels" in item["payload"]  # the S/R level is exposed for review


async def test_dev_chart_data_pattern_oi_reproduces(content_client: AsyncClient) -> None:
    await _auth(content_client)
    resp = await content_client.get("/api/dev/charts/data?exercise_id=m19-ex-1&seed=3&fmt=json")
    assert resp.status_code == 200
    data = resp.json()
    assert data["indicator"] == "oi" and data["warmup"] > 0
    assert "label" in data["groundTruth"]
    # The open-interest series is exported alongside OHLC for review.
    assert "oi" in data["rows"][data["warmup"]]


async def test_dev_endpoints_require_auth(content_client: AsyncClient) -> None:
    assert (await content_client.get("/api/dev/attempts?exercise_id=m12-ex-1")).status_code == 401
    assert (
        await content_client.get("/api/dev/charts/data?exercise_id=m12-ex-1&seed=1")
    ).status_code == 401
