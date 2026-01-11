from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from apps.api import main
from apps.api.auth import seed_admin
from apps.api.config import get_settings
from apps.api.db import get_sessionmaker, init_engine, init_models, init_sessionmaker
from apps.api.models import ConnectionStatus, TelegramConnection


async def setup_db() -> None:
    settings = get_settings()
    settings.database_url = "sqlite+aiosqlite:///:memory:"
    settings.admin_email = "admin@test.com"
    settings.admin_password = "secret"
    settings.encryption_key = "9UvWofbAB7qi56pL-2shCAmQConVAvVb2pLHM0UVDgk="
    init_engine(settings)
    init_sessionmaker(settings)
    await init_models(settings)
    async with get_sessionmaker()() as session:
        await seed_admin(session)


@pytest.mark.asyncio
async def test_bot_connect_encrypts_token_and_status() -> None:
    await setup_db()
    session_maker = get_sessionmaker()
    with TestClient(main.app) as client:
        token_resp = client.post("/login", json={"email": "admin@test.com", "password": "secret"})
        token = token_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        proj_resp = client.post(
            "/projects", json={"name": "Demo", "niche": "football"}, headers=headers
        )
        project_id = proj_resp.json()["id"]

        connect_resp = client.post(
            f"/projects/{project_id}/telegram/bot/connect",
            json={"bot_token": "abc123"},
            headers=headers,
        )
        assert connect_resp.status_code == 200
        status_data = connect_resp.json()
        assert status_data["mode"] == "bot"

        async with session_maker() as session:
            result = await session.execute(
                select(TelegramConnection).where(TelegramConnection.project_id == project_id)
            )
            conn = result.scalar_one()
            assert conn.bot_token_encrypted != "abc123"
            settings = get_settings()
            assert settings.decrypt(str(conn.bot_token_encrypted)) == "abc123"
            assert conn.status == ConnectionStatus.CONNECTED

        status_resp = client.get(f"/projects/{project_id}/telegram/status", headers=headers)
        assert status_resp.status_code == 200
        assert status_resp.json()["channels"] == 0


@pytest.mark.asyncio
async def test_send_test_message_uses_bot(monkeypatch: pytest.MonkeyPatch) -> None:
    await setup_db()
    calls: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)
    real_async_client = httpx.AsyncClient

    def fake_async_client(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs = dict(kwargs)
        kwargs.setdefault("transport", transport)
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr("apps.api.telegram_bot.httpx.AsyncClient", fake_async_client)

    with TestClient(main.app) as client:
        token_resp = client.post("/login", json={"email": "admin@test.com", "password": "secret"})
        token = token_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        proj_resp = client.post(
            "/projects", json={"name": "Demo2", "niche": "football"}, headers=headers
        )
        project_id = proj_resp.json()["id"]

        # connect bot
        client.post(
            f"/projects/{project_id}/telegram/bot/connect",
            json={"bot_token": "abc123"},
            headers=headers,
        )

        # add channels
        client.post(
            f"/projects/{project_id}/channels",
            json={"tg_chat_id": "100", "title": "CH1"},
            headers=headers,
        )
        client.post(
            f"/projects/{project_id}/channels",
            json={"tg_chat_id": "200", "title": "CH2"},
            headers=headers,
        )

        resp = client.post(
            f"/projects/{project_id}/telegram/test-message",
            json={"text": "Hello"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["sent"] == 2

    assert len(calls) == 2
    payloads = [json.loads(request.content.decode("utf-8")) for request in calls]
    chat_ids = {payload["chat_id"] for payload in payloads}
    assert chat_ids == {"100", "200"}
    assert all(payload["parse_mode"] == "HTML" for payload in payloads)
    assert all(payload["text"] == "Hello" for payload in payloads)
