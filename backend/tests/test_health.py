# SPDX-License-Identifier: AGPL-3.0-only
from __future__ import annotations

from httpx import AsyncClient


async def test_health_ok(client: AsyncClient) -> None:
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"


async def test_version_reports_the_build_and_a_real_route_count(client: AsyncClient) -> None:
    """Unauthenticated on purpose: it must answer before you can log in, when you are debugging.

    The route count walks recursively. `app.routes` does NOT flatten an included router — reading it
    directly reports 5 for the whole service, which is exactly the sort of misleading signal a
    build-info endpoint exists to avoid.
    """
    response = await client.get("/api/version")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"commit", "builtAt", "routes"}
    # Unset in a test build, and "unknown" is itself a useful answer.
    assert isinstance(body["commit"], str) and body["commit"]
    assert body["routes"] > 20, "route count did not flatten the included routers"
