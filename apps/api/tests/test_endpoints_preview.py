from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import pytest
from fastapi.testclient import TestClient
from redis.asyncio import Redis

from apps.api import main
from apps.api.auth import issue_admin_token
from apps.api.config import get_settings
from apps.api.db import get_sessionmaker, init_engine, init_models, init_sessionmaker
from apps.api.models import AgentConfig, FeedSource, ImageMode, NewsItem, Niche, Project
from apps.api.time_utils import msk_now


class FakeRedis:
    async def ping(self) -> bool:
        return True

    async def aclose(self) -> None:
        return None


async def _prepare_db() -> str:
    settings = get_settings()
    settings.database_url = "sqlite+aiosqlite:///:memory:"
    settings.encryption_key = "test-secret-key"
    settings.admin_password = "admin"

    main.redis_client = cast(Redis, FakeRedis())

    async def fake_get_redis() -> Redis:
        return cast(Redis, main.redis_client)

    main.get_redis = fake_get_redis

    init_engine(settings)
    init_sessionmaker(settings)
    await init_models(settings)

    session_maker = get_sessionmaker()
    async with session_maker() as session:
        project = Project(name="Test", niche=Niche.FOOTBALL)
        session.add(project)
        await session.flush()
        feed = FeedSource(
            project_id=project.id, name="Test feed", url="http://example.com", enabled=True
        )
        session.add(feed)
        await session.flush()
        session.add(
            AgentConfig(
                project_id=project.id,
                posts_per_day=1,
                window_start="00:00",
                window_end="23:59",
                min_interval_minutes=10,
                language="ru",
                tone="нейтральный",
                include_source_link=True,
                image_mode=ImageMode.WIKIMEDIA,
            )
        )
        session.add(
            NewsItem(
                project_id=project.id,
                source_id=feed.id,
                title="Новость дня",
                url="http://example.com/news",
                published_at=msk_now(),
                raw_summary="Краткое описание",
                raw_content="Полный текст новости",
                hash="hash-test",
            )
        )
        await session.commit()

    return issue_admin_token()


@pytest.mark.asyncio
async def test_news_latest_returns_items() -> None:
    token = await _prepare_db()
    with TestClient(main.app) as client:
        resp = client.get("/api/news/latest", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert data[0]["title"] == "Новость дня"


@pytest.mark.asyncio
async def test_preview_next_uses_mocked_generator(monkeypatch: pytest.MonkeyPatch) -> None:
    token = await _prepare_db()

    class DummyGenerator:
        async def generate(self, *args, **kwargs) -> SimpleNamespace:  # noqa: ANN401
            return SimpleNamespace(
                headline="Сгенерированный заголовок",
                body_html="<b>Готово</b>",
                image_query="query",
                should_post=True,
                reason_if_skip=None,
            )

    monkeypatch.setattr(main, "GeminiGenerator", DummyGenerator)

    async def fake_pick_next_news_item(*args, **kwargs) -> SimpleNamespace:  # noqa: ANN401
        return SimpleNamespace(
            id=1,
            title="Новость дня",
            url="http://example.com/news",
            raw_summary="Краткое описание",
            raw_content="Полный текст новости",
            source=SimpleNamespace(name="Test feed"),
        )

    monkeypatch.setattr(main, "pick_next_news_item", fake_pick_next_news_item)

    with TestClient(main.app) as client:
        resp = client.post("/api/preview/next", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["headline"] == "Сгенерированный заголовок"
        assert payload["body_html"] == "<b>Готово</b>"
        assert payload["news_id"] is not None
