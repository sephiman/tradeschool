# SPDX-License-Identifier: AGPL-3.0-only
"""Lesson figures: spec loading, resolution-showing build, and the cached endpoint."""

from __future__ import annotations

from pathlib import Path

from httpx import AsyncClient

from tradeschool.exercises.figures import build_figure, load_figures

CONTENT = Path(__file__).resolve().parents[2] / "content"
CREDS = {"email": "figviewer@example.com", "password": "correcthorse"}


async def _auth(client: AsyncClient) -> None:
    await client.post("/api/auth/register", json={**CREDS, "locale": "en"})
    await client.post("/api/auth/login", json=CREDS)


def test_figure_builds_with_resolution_and_localized_caption() -> None:
    figures = load_figures(CONTENT)
    assert "fig-m12-bearish-regular" in figures
    spec = figures["fig-m12-bearish-regular"]

    data = build_figure(spec, "en")
    assert data["kind"] == "chart"
    panels = data["panels"]
    assert isinstance(panels, list) and len(panels) == 1
    close = panels[0]["series"]["close"]
    # The figure SHOWS the resolution: the visible window is the exercise length + the appended leg.
    assert len(close) == 120 + 24
    assert len(panels[0]["rsi"]) == len(close)
    assert len(panels[0]["annotations"]) == 2  # the two labelled swings
    # A bearish resolution reverses down off the high.
    assert min(close[-6:]) < max(close)

    assert build_figure(spec, "es")["caption"] != data["caption"]  # localized


async def test_figure_endpoint_auth_cache_and_404(content_client: AsyncClient) -> None:
    assert (await content_client.get("/api/figures/fig-m12-bearish-regular")).status_code == 401
    await _auth(content_client)

    resp = await content_client.get("/api/figures/fig-m12-bearish-regular?lang=es")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == "fig-m12-bearish-regular" and body["kind"] == "chart" and body["panels"]
    # Second call returns the same cached object.
    again = (await content_client.get("/api/figures/fig-m12-bearish-regular?lang=es")).json()
    assert again == body

    assert (await content_client.get("/api/figures/ghost")).status_code == 404
