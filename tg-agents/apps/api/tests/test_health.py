from __future__ import annotations

from typing import cast

import pytest
from fastapi.testclient import TestClient
from redis.asyncio import Redis

from apps.api import main
from apps.api.config import get_settings


class FakeRedis:
    async def ping(self) -> bool:
        return True

    async def aclose(self) -> None:
        return None


@pytest.mark.asyncio
async def test_health_and_ready() -> None:
    # Point to in-memory DB for isolation.
    settings = get_settings()
    settings.database_url = "sqlite+aiosqlite:///:memory:"
    fake_redis = FakeRedis()

    async def fake_get_redis() -> Redis:
        return cast(Redis, fake_redis)

    main.redis_client = cast(Redis, fake_redis)
    main.get_redis = fake_get_redis

    with TestClient(main.app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json() == {"status": "ok"}

        ready = client.get("/ready")
        assert ready.status_code == 200
        assert ready.json() == {"status": "ready"}
