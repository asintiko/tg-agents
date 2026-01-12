from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
from fastapi.testclient import TestClient
from redis.asyncio import Redis

from apps.api import main
from apps.api.auth import issue_admin_token
from apps.api.config import get_settings
from apps.api.db import init_engine, init_models, init_sessionmaker
from apps.worker.rss import RSSCollector


class FakeRedis:
    async def ping(self) -> bool:
        return True

    async def aclose(self) -> None:
        return None


async def _prepare_db() -> str:
    settings = get_settings()
    db_path = Path("test_projects.db")
    if db_path.exists():
        db_path.unlink()
    settings.database_url = f"sqlite+aiosqlite:///{db_path}"
    settings.encryption_key = "test-secret-key"
    settings.admin_password = "admin"

    main.redis_client = cast(Redis, FakeRedis())

    async def fake_get_redis() -> Redis:
        return cast(Redis, main.redis_client)

    main.get_redis = fake_get_redis

    init_engine(settings)
    init_sessionmaker(settings)
    await init_models(settings)
    return issue_admin_token()


@pytest.mark.asyncio
async def test_project_creation_provisions_config_and_feeds() -> None:
    token = await _prepare_db()
    with TestClient(main.app) as client:
        resp = client.post(
            "/projects",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "Auto project", "niche": "football"},
        )
        assert resp.status_code == 201
        project_id = resp.json()["id"]

        cfg = client.get(
            f"/projects/{project_id}/agent-config",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert cfg.status_code == 200

        feeds = client.get(
            f"/projects/{project_id}/feed-sources",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert feeds.status_code == 200
        payload = feeds.json()
        assert len(payload) >= len(RSSCollector.default_feeds)


@pytest.mark.asyncio
async def test_agent_config_get_always_present() -> None:
    token = await _prepare_db()
    with TestClient(main.app) as client:
        resp = client.post(
            "/projects",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "Auto project 2", "niche": "football"},
        )
        assert resp.status_code == 201
        project_id = resp.json()["id"]

        cfg = client.get(
            f"/projects/{project_id}/agent-config",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert cfg.status_code == 200
        data = cfg.json()
        assert data["posts_per_day"] == 8
        assert data["image_mode"] == "og_image"
