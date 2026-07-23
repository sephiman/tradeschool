# SPDX-License-Identifier: AGPL-3.0-only
from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from tradeschool.auth.models import AccessToken

REG = {"email": "learner@example.com", "password": "correcthorse"}


async def _register(client: AsyncClient, **over: object) -> None:
    payload = {**REG, **over}
    resp = await client.post("/api/auth/register", json=payload)
    assert resp.status_code == 201, resp.text


async def test_register_returns_user_with_locale(client: AsyncClient) -> None:
    resp = await client.post("/api/auth/register", json={**REG, "locale": "es"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == REG["email"]
    assert body["locale"] == "es"
    assert "id" in body
    assert "password" not in body and "hashed_password" not in body


async def test_register_duplicate_is_rejected(client: AsyncClient) -> None:
    await _register(client)
    resp = await client.post("/api/auth/register", json=REG)
    assert resp.status_code == 400
    assert resp.json()["code"] == "USER_ALREADY_EXISTS"


async def test_register_weak_password_rejected(client: AsyncClient) -> None:
    resp = await client.post("/api/auth/register", json={"email": "a@b.com", "password": "short"})
    assert resp.status_code == 400
    assert resp.json()["code"] == "INVALID_PASSWORD"


async def test_register_invalid_email_is_validation_error(client: AsyncClient) -> None:
    resp = await client.post("/api/auth/register", json={"email": "not-an-email", "password": "correcthorse"})
    assert resp.status_code == 422
    assert resp.json()["code"] == "VALIDATION_ERROR"


async def test_me_requires_authentication(client: AsyncClient) -> None:
    resp = await client.get("/api/auth/me")
    assert resp.status_code == 401


async def test_login_sets_cookie_and_me_works(client: AsyncClient) -> None:
    await _register(client)
    login = await client.post("/api/auth/login", json=REG)
    assert login.status_code == 200
    assert login.json()["email"] == REG["email"]
    # A session cookie was set on the client's jar.
    assert client.cookies.get("tradeschool_session") is not None

    me = await client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == REG["email"]


async def test_login_bad_password_rejected(client: AsyncClient) -> None:
    await _register(client)
    resp = await client.post("/api/auth/login", json={**REG, "password": "wrongpassword"})
    assert resp.status_code == 400
    assert resp.json()["code"] == "LOGIN_BAD_CREDENTIALS"


async def test_logout_revokes_session(client: AsyncClient) -> None:
    await _register(client)
    await client.post("/api/auth/login", json=REG)
    assert (await client.get("/api/auth/me")).status_code == 200

    logout = await client.post("/api/auth/logout")
    assert logout.status_code == 204

    # Cookie cleared client-side and token destroyed server-side.
    assert (await client.get("/api/auth/me")).status_code == 401


async def test_session_is_server_revocable(client: AsyncClient, session: AsyncSession) -> None:
    """Deleting the access token in the DB immediately invalidates the cookie (no JWT)."""
    await _register(client)
    await client.post("/api/auth/login", json=REG)
    assert (await client.get("/api/auth/me")).status_code == 200

    await session.execute(delete(AccessToken))
    await session.commit()

    assert (await client.get("/api/auth/me")).status_code == 401


async def test_update_me_locale(client: AsyncClient) -> None:
    await _register(client, locale="en")
    await client.post("/api/auth/login", json=REG)
    patched = await client.patch("/api/auth/me", json={"locale": "es"})
    assert patched.status_code == 200
    assert patched.json()["locale"] == "es"
    assert (await client.get("/api/auth/me")).json()["locale"] == "es"


async def test_register_is_rate_limited(rl_client: AsyncClient) -> None:
    # Default register limit is 5/minute; the 6th request from the same IP is throttled.
    last_status = None
    for i in range(6):
        resp = await rl_client.post(
            "/api/auth/register", json={"email": f"u{i}@example.com", "password": "correcthorse"}
        )
        last_status = resp.status_code
    assert last_status == 429
    assert resp.json()["code"] == "RATE_LIMITED"
