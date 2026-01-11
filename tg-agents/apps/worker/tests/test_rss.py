from __future__ import annotations

import pytest
from sqlalchemy import func, select

from apps.api.config import get_settings
from apps.api.db import dispose_engine, init_engine, init_models, init_sessionmaker
from apps.api.models import FeedSource, NewsItem, Project
from apps.worker.rss import NormalizedEntry, RSSCollector, canonicalize_url, compute_hash


@pytest.mark.asyncio
async def test_canonicalize_url_strips_tracking() -> None:
    url = "https://example.com/article?utm_source=newsletter&fbclid=123#section"
    cleaned = canonicalize_url(url)
    assert "utm_source" not in cleaned
    assert "fbclid" not in cleaned
    assert "#" not in cleaned


@pytest.mark.asyncio
async def test_hash_deduplication() -> None:
    settings = get_settings()
    settings.database_url = "sqlite+aiosqlite:///:memory:"
    init_engine(settings)
    session_maker = init_sessionmaker(settings)
    await init_models(settings)

    collector = RSSCollector(session_maker, settings)
    async with session_maker() as session:
        project = Project(name="Test", niche="football")
        session.add(project)
        await session.commit()
        await session.refresh(project)
        feed = FeedSource(
            project_id=project.id, name="Test Feed", url="http://example.com", enabled=True
        )
        session.add(feed)
        await session.commit()
        await session.refresh(feed)

        entry = NormalizedEntry(
            title="Hello",
            url="http://example.com/a",
            published_at=None,
            summary=None,
            content=None,
            hash=compute_hash("Hello", "http://example.com/a"),
        )

        inserted_first = await collector._upsert_news_item(session, project.id, feed.id, entry)
        inserted_second = await collector._upsert_news_item(session, project.id, feed.id, entry)
        await session.commit()
        assert inserted_first is True
        assert inserted_second is False

        result = await session.execute(
            select(func.count()).select_from(NewsItem).where(NewsItem.project_id == project.id)
        )
        assert result.scalar_one() == 1
    await collector.close()
    await dispose_engine()
