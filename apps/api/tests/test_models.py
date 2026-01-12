from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from apps.api import main
from apps.api.config import get_settings
from apps.api.db import get_sessionmaker, init_engine, init_models, init_sessionmaker
from apps.api.models import NewsItem, Project


async def setup_inmemory_db() -> None:
    settings = get_settings()
    settings.database_url = "sqlite+aiosqlite:///:memory:"
    settings.admin_password = "secret"
    init_engine(settings)
    init_sessionmaker(settings)
    await init_models(settings)


@pytest.mark.asyncio
async def test_admin_login_and_project_creation() -> None:
    await setup_inmemory_db()
    with TestClient(main.app) as client:
        token_resp = client.post("/login", json={"password": "secret"})
        assert token_resp.status_code == 200
        token = token_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        create_resp = client.post(
            "/projects", json={"name": "Demo", "niche": "football"}, headers=headers
        )
        assert create_resp.status_code == 201
        assert create_resp.json()["name"] == "Demo"


@pytest.mark.asyncio
async def test_news_item_hash_uniqueness() -> None:
    await setup_inmemory_db()
    session_maker = get_sessionmaker()
    async with session_maker() as session:
        project = Project(name="P1", niche="football")
        session.add(project)
        await session.commit()
        await session.refresh(project)
        item1 = NewsItem(
            project_id=project.id,
            source_id=None,
            title="t1",
            url="http://example.com",
            hash="abc",
        )
        session.add(item1)
        await session.commit()
        item2 = NewsItem(
            project_id=project.id,
            source_id=None,
            title="t2",
            url="http://example.com/2",
            hash="abc",
        )
        session.add(item2)
        with pytest.raises(IntegrityError):
            await session.commit()
            await session.rollback()


@pytest.mark.asyncio
async def test_agent_config_upsert() -> None:
    await setup_inmemory_db()
    session_maker = get_sessionmaker()
    async with session_maker() as session:
        project = Project(name="ConfigProj", niche="football")
        session.add(project)
        await session.commit()
        await session.refresh(project)
    with TestClient(main.app) as client:
        token_resp = client.post("/login", json={"password": "secret"})
        token = token_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        put_resp = client.put(
            f"/projects/{project.id}/agent-config",
            headers=headers,
            json={
                "posts_per_day": 3,
                "window_start": "09:00",
                "window_end": "18:00",
                "min_interval_minutes": 60,
                "language": "ru",
                "tone": "neutral",
                "signature_html": "<b>sig</b>",
                "emoji_mode": "basic",
                "include_source_link": True,
                "image_mode": "wikimedia",
            },
        )
        assert put_resp.status_code == 200
        put_resp2 = client.put(
            f"/projects/{project.id}/agent-config",
            headers=headers,
            json={
                "posts_per_day": 5,
                "window_start": "08:00",
                "window_end": "20:00",
                "min_interval_minutes": 45,
                "language": "en",
                "tone": "warm",
                "signature_html": None,
                "emoji_mode": "premium",
                "include_source_link": False,
                "image_mode": "og_image",
            },
        )
        assert put_resp2.status_code == 200
        data = put_resp2.json()
        assert data["posts_per_day"] == 5
        assert data["tone"] == "warm"
