from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest
from pydantic import HttpUrl
from sqlalchemy import select

from apps.api.config import get_settings
from apps.api.db import get_sessionmaker, init_engine, init_models, init_sessionmaker
from apps.api.gemini import GeminiGenerator, GeneratedPost
from apps.api.models import (
    AgentConfig,
    ConnectionStatus,
    FeedSource,
    ImageMode,
    NewsItem,
    Post,
    PostStatus,
    Project,
    TelegramChannel,
    TelegramConnection,
    TelegramMode,
)
from apps.worker.images import ImageService
from apps.worker.pipeline import PostPipeline


class FakeGenerator(GeminiGenerator):
    def __init__(self, post: GeneratedPost) -> None:
        super().__init__(api_key=None)
        self.post = post

    async def generate(
        self, news: NewsItem, source_name: str, config: AgentConfig
    ) -> GeneratedPost:
        return self.post


class FakeImageService(ImageService):
    def __init__(self) -> None:
        super().__init__(get_sessionmaker(), settings=get_settings())

    async def find_image(self, image_query: str, mode: str = "wikimedia") -> Any:
        return None


async def setup_base() -> None:
    settings = get_settings()
    settings.database_url = "sqlite+aiosqlite:///:memory:"
    settings.admin_email = "admin@test.com"
    settings.admin_password = "secret"
    init_engine(settings)
    init_sessionmaker(settings)
    await init_models(settings)


async def create_project_with_data() -> tuple[int, int]:
    session_maker = get_sessionmaker()
    async with session_maker() as session:
        project = Project(name="P", niche="football")
        session.add(project)
        await session.flush()
        feed = FeedSource(
            project_id=project.id, name="Test", url="http://example.com", enabled=True
        )
        session.add(feed)
        config = AgentConfig(
            project_id=project.id,
            posts_per_day=1,
            window_start="00:00",
            window_end="23:59",
            min_interval_minutes=10,
            image_mode=ImageMode.WIKIMEDIA,
            language="ru",
            tone="neutral",
        )
        session.add(config)
        conn = TelegramConnection(
            project_id=project.id,
            mode=TelegramMode.BOT,
            bot_token_encrypted=get_settings().encrypt("token"),
            status=ConnectionStatus.CONNECTED,
        )
        session.add(conn)
        channel = TelegramChannel(
            project_id=project.id, tg_chat_id="123", title="Chan", username=None, enabled=True
        )
        session.add(channel)
        news = NewsItem(
            project_id=project.id,
            source_id=feed.id,
            title="News",
            url="http://example.com",
            published_at=datetime.now(UTC),
            hash="hash1",
        )
        session.add(news)
        await session.flush()
        post = Post(
            project_id=project.id,
            news_item_id=news.id,
            planned_at=datetime.now(UTC) - timedelta(minutes=1),
            status=PostStatus.PLANNED,
        )
        session.add(post)
        await session.commit()
        return project.id, post.id


@pytest.mark.asyncio
async def test_pipeline_skips_when_should_post_false(monkeypatch: pytest.MonkeyPatch) -> None:
    await setup_base()
    project_id, post_id = await create_project_with_data()
    gen_post = GeneratedPost(
        headline="h",
        lead="l",
        body_html="body",
        hashtags=[],
        image_query="q",
        source_url=cast(HttpUrl, "https://example.com"),
        should_post=False,
        reason_if_skip="not enough data",
    )
    pipeline = PostPipeline(
        get_sessionmaker(), generator=FakeGenerator(gen_post), image_service=FakeImageService()
    )
    await pipeline.run(project_id=project_id)
    async with get_sessionmaker()() as session:
        result = await session.execute(select(Post).where(Post.id == post_id))
        post = result.scalar_one()
        assert post.status == PostStatus.SKIPPED
        assert post.error == "not enough data"


@pytest.mark.asyncio
async def test_pipeline_publishes_with_bot(monkeypatch: pytest.MonkeyPatch) -> None:
    await setup_base()
    project_id, post_id = await create_project_with_data()
    gen_post = GeneratedPost(
        headline="h",
        lead="l",
        body_html="body",
        hashtags=["one"],
        image_query="q",
        source_url=cast(HttpUrl, "https://example.com"),
        should_post=True,
        reason_if_skip=None,
    )
    sent: list[str] = []

    async def fake_send(
        token: str, chat_ids: list[str], text: str, image_path: str | None = None
    ) -> None:
        sent.extend(chat_ids)

    monkeypatch.setattr("apps.worker.pipeline.send_to_channels", fake_send)
    pipeline = PostPipeline(
        get_sessionmaker(), generator=FakeGenerator(gen_post), image_service=FakeImageService()
    )
    await pipeline.run(project_id=project_id)
    async with get_sessionmaker()() as session:
        result = await session.execute(select(Post).where(Post.id == post_id))
        post = result.scalar_one()
        assert post.status == PostStatus.PUBLISHED
        assert post.published_at is not None
    assert sent == ["123"]


@pytest.mark.asyncio
async def test_pipeline_marks_failed_on_publish_error(monkeypatch: pytest.MonkeyPatch) -> None:
    await setup_base()
    project_id, post_id = await create_project_with_data()
    gen_post = GeneratedPost(
        headline="h",
        lead="l",
        body_html="body",
        hashtags=[],
        image_query="q",
        source_url=cast(HttpUrl, "https://example.com"),
        should_post=True,
        reason_if_skip=None,
    )

    async def fake_send(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("send failed")

    monkeypatch.setattr("apps.worker.pipeline.send_to_channels", fake_send)
    pipeline = PostPipeline(
        get_sessionmaker(), generator=FakeGenerator(gen_post), image_service=FakeImageService()
    )
    await pipeline.run(project_id=project_id)
    async with get_sessionmaker()() as session:
        result = await session.execute(select(Post).where(Post.id == post_id))
        post = result.scalar_one()
        assert post.status == PostStatus.FAILED
        assert "send failed" in (post.error or "")
