from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from apps.api.config import get_settings
from apps.api.db import get_sessionmaker, init_engine, init_models, init_sessionmaker
from apps.api.gemini import GeneratedPost
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
)
from apps.api.time_utils import msk_now
from apps.worker.pipeline import PostPipeline


async def setup_base() -> None:
    settings = get_settings()
    settings.database_url = "sqlite+aiosqlite:///:memory:"
    settings.encryption_key = "9UvWofbAB7qi56pL-2shCAmQConVAvVb2pLHM0UVDgk="
    init_engine(settings)
    init_sessionmaker(settings)
    await init_models(settings)


async def prepare(project_name: str, headline: str | None = None) -> tuple[int, int]:
    session_maker = get_sessionmaker()
    async with session_maker() as session:
        project = Project(name=project_name, niche="football")
        session.add(project)
        await session.flush()
        feed = FeedSource(project_id=project.id, name="Test", url="http://example.com", enabled=True)
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
            status=ConnectionStatus.CONNECTED,
        )
        session.add(conn)
        channel = TelegramChannel(
            project_id=project.id, tg_chat_id="123", title="Chan", username=None, enabled=True
        )
        session.add(channel)
        tz = ZoneInfo("Europe/Moscow")
        news = NewsItem(
            project_id=project.id,
            source_id=feed.id,
            title="News about team",
            url="http://example.com",
            published_at=msk_now(),
            raw_summary="Team wins match",
            raw_content="The team wins 2-0",
            hash="hash1",
        )
        session.add(news)
        await session.flush()
        if headline:
            prev = Post(
                project_id=project.id,
                news_item_id=news.id,
                planned_at=datetime.now(tz) - timedelta(hours=7),
                published_at=datetime.now(tz) - timedelta(hours=1),
                status=PostStatus.PUBLISHED,
                payload_json={"headline": headline},
            )
            session.add(prev)
        post = Post(
            project_id=project.id,
            news_item_id=news.id,
            planned_at=datetime.now(tz) - timedelta(minutes=1),
            status=PostStatus.PLANNED,
        )
        session.add(post)
        await session.commit()
        return project.id, post.id


class GenMock:
    def __init__(self, post: GeneratedPost) -> None:
        self.post = post

    async def generate(self, *args, **kwargs) -> GeneratedPost:
        return self.post


class NoImage:
    def __init__(self) -> None:
        pass

    async def find_image(self, *args, **kwargs) -> None:
        return None


@pytest.mark.asyncio
async def test_similarity_blocks_recent() -> None:
    await setup_base()
    project_id, post_id = await prepare("A", headline="Team wins big match")
    gen = GeneratedPost(
        headline="Big team match win",
        lead="lead",
        body_html="body",
        hashtags=[],
        image_query="q",
        source_url="https://example.com",
        should_post=True,
        reason_if_skip=None,
    )
    pipeline = PostPipeline(get_sessionmaker(), generator=GenMock(gen), image_service=NoImage())  # type: ignore[arg-type]
    await pipeline.run(project_id=project_id)
    async with get_sessionmaker()() as session:
        post = (await session.execute(select(Post).where(Post.id == post_id))).scalar_one()
        assert post.status == PostStatus.SKIPPED
        assert "Похоже" in (post.error or "")


@pytest.mark.asyncio
async def test_numbers_guardrail_blocks_hallucination() -> None:
    await setup_base()
    project_id, post_id = await prepare("B")
    gen = GeneratedPost(
        headline="Team wins",
        lead="lead",
        body_html="Score was 3-1",
        hashtags=[],
        image_query="q",
        source_url="https://example.com",
        should_post=True,
        reason_if_skip=None,
    )
    pipeline = PostPipeline(get_sessionmaker(), generator=GenMock(gen), image_service=NoImage())  # type: ignore[arg-type]
    await pipeline.run(project_id=project_id)
    async with get_sessionmaker()() as session:
        post = (await session.execute(select(Post).where(Post.id == post_id))).scalar_one()
        assert post.status == PostStatus.SKIPPED
        assert "числовые" in (post.error or "")
