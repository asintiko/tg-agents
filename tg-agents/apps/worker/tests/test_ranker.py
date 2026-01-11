from __future__ import annotations

import datetime as dt

import pytest

from apps.api.config import get_settings
from apps.api.db import get_sessionmaker, init_engine, init_models, init_sessionmaker
from apps.api.models import FeedSource, NewsItem, Post, PostStatus, Project
from apps.worker.ranker import pick_next_news_item


async def setup_db() -> None:
    settings = get_settings()
    settings.database_url = "sqlite+aiosqlite:///:memory:"
    init_engine(settings)
    init_sessionmaker(settings)
    await init_models(settings)


@pytest.mark.asyncio
async def test_excludes_published_news() -> None:
    await setup_db()
    session_maker = get_sessionmaker()
    async with session_maker() as session:
        project = Project(name="P1", niche="football")
        session.add(project)
        await session.flush()
        feed = FeedSource(project_id=project.id, name="F1", url="http://example.com", enabled=True)
        session.add(feed)
        await session.flush()
        news1 = NewsItem(
            project_id=project.id,
            source_id=feed.id,
            title="Old story",
            url="http://example.com/1",
            hash="h1",
        )
        news2 = NewsItem(
            project_id=project.id,
            source_id=feed.id,
            title="Fresh story",
            url="http://example.com/2",
            hash="h2",
        )
        session.add_all([news1, news2])
        await session.flush()
        session.add(
            Post(
                project_id=project.id,
                news_item_id=news1.id,
                status=PostStatus.PUBLISHED,
                planned_at=dt.datetime.now(dt.UTC),
            )
        )
        await session.commit()

        picked = await pick_next_news_item(session, project.id)
        assert picked is not None
        assert picked.id == news2.id


@pytest.mark.asyncio
async def test_prefers_weight_and_recency() -> None:
    await setup_db()
    session_maker = get_sessionmaker()
    async with session_maker() as session:
        project = Project(name="P1", niche="football")
        session.add(project)
        await session.flush()
        feed_low = FeedSource(
            project_id=project.id, name="Low", url="http://low", enabled=True, weight=1
        )
        feed_high = FeedSource(
            project_id=project.id, name="High", url="http://high", enabled=True, weight=10
        )
        session.add_all([feed_low, feed_high])
        await session.flush()
        older = NewsItem(
            project_id=project.id,
            source_id=feed_high.id,
            title="High weight old",
            url="http://high/1",
            hash="hh1",
            published_at=dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
            created_at=dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
        )
        newer = NewsItem(
            project_id=project.id,
            source_id=feed_low.id,
            title="Low weight new",
            url="http://low/1",
            hash="lw1",
            published_at=dt.datetime(2024, 2, 1, tzinfo=dt.UTC),
            created_at=dt.datetime(2024, 2, 1, tzinfo=dt.UTC),
        )
        session.add_all([older, newer])
        await session.commit()

        picked = await pick_next_news_item(session, project.id)
        assert picked is not None
        # Weight advantage should beat recency.
        assert picked.id == older.id
