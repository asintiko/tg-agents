from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qsl, urlparse, urlunparse

import feedparser
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from apps.api.config import Settings, get_settings
from apps.api.models import FeedSource, NewsItem, Niche, Project

TRACKING_PREFIXES = ("utm_", "fbclid", "gclid", "ref")


def canonicalize_url(url: str) -> str:
    parsed = urlparse(url)
    filtered_query = [
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if not k.startswith(TRACKING_PREFIXES)
    ]
    cleaned = parsed._replace(query="", fragment="")
    if filtered_query:
        cleaned = cleaned._replace(query="&".join(f"{k}={v}" for k, v in filtered_query))
    return urlunparse(cleaned)


def compute_hash(title: str, url: str) -> str:
    canonical = canonicalize_url(url)
    material = f"{title.lower().strip()}|{canonical}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


@dataclass(slots=True)
class NormalizedEntry:
    title: str
    url: str
    published_at: datetime | None
    summary: str | None
    content: str | None
    hash: str


class RSSCollector:
    default_feeds = [
        ("BBC Football", "https://feeds.bbci.co.uk/sport/football/rss.xml"),
        ("Transfermarkt News", "https://www.transfermarkt.com/rss/news"),
    ]

    def __init__(
        self,
        session_maker: async_sessionmaker[AsyncSession],
        settings: Settings | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.session_maker = session_maker
        self.http = http_client or httpx.AsyncClient(timeout=10.0)

    async def close(self) -> None:
        await self.http.aclose()

    async def ensure_default_feeds(self) -> None:
        async with self.session_maker() as session:
            projects_result = await session.execute(select(Project))
            projects = list(projects_result.scalars().all())
            if not projects:
                default_project = Project(name="Default Football", niche=Niche.FOOTBALL)
                session.add(default_project)
                await session.flush()
                projects = [default_project]
            for project in projects:
                if project.niche != Niche.FOOTBALL:
                    continue
                existing = await session.execute(
                    select(FeedSource.id).where(FeedSource.project_id == project.id)
                )
                if existing.first():
                    continue
                for name, url in self.default_feeds:
                    session.add(
                        FeedSource(
                            project_id=project.id,
                            name=name,
                            url=url,
                            enabled=True,
                            weight=10,
                        )
                    )
            await session.commit()

    async def pull_all(self) -> None:
        async with self.session_maker() as session:
            result = await session.execute(
                select(FeedSource, Project)
                .join(Project, FeedSource.project_id == Project.id)
                .where(FeedSource.enabled.is_(True))
            )
            for feed_source, project in result.all():
                await self._process_feed(session, project, feed_source)
            await session.commit()

    async def pull_project(self, project_id: int) -> int:
        inserted = 0
        async with self.session_maker() as session:
            project_result = await session.execute(select(Project).where(Project.id == project_id))
            project = project_result.scalar_one_or_none()
            if not project:
                return inserted
            feeds = await session.execute(
                select(FeedSource).where(
                    FeedSource.project_id == project_id,
                    FeedSource.enabled.is_(True),
                )
            )
            for feed in feeds.scalars().all():
                inserted += await self._process_feed(session, project, feed)
            await session.commit()
        return inserted

    async def _process_feed(
        self, session: AsyncSession, project: Project, feed_source: FeedSource
    ) -> int:
        try:
            response = await self.http.get(feed_source.url)
            response.raise_for_status()
        except Exception:
            return 0
        parsed = feedparser.parse(response.text)
        inserted = 0
        for entry in parsed.entries:
            normalized = self._normalize_entry(entry)
            if not normalized:
                continue
            if not self._should_accept(project, feed_source):
                if not self._passes_keyword_filter(normalized):
                    continue
            was_inserted = await self._upsert_news_item(
                session, project.id, feed_source.id, normalized
            )
            if was_inserted:
                inserted += 1
        return inserted

    def _normalize_entry(self, entry: dict[str, Any]) -> NormalizedEntry | None:
        title = str(entry.get("title") or "").strip()
        link = str(entry.get("link") or "").strip()
        if not title or not link:
            return None
        published_at = None
        published_struct = entry.get("published_parsed")
        if published_struct:
            published_at = datetime.fromtimestamp(
                feedparser._mktime_tz(published_struct), tz=UTC
            )
        summary = str(entry.get("summary") or "").strip() or None
        content = None
        if entry.get("content"):
            try:
                content = str(entry.content[0].value)  # type: ignore[attr-defined]
            except Exception:
                content = None
        url = canonicalize_url(link)
        computed_hash = compute_hash(title, url)
        return NormalizedEntry(
            title=title,
            url=url,
            published_at=published_at,
            summary=summary,
            content=content,
            hash=computed_hash,
        )

    def _should_accept(self, project: Project, feed_source: FeedSource) -> bool:
        if project.niche == Niche.FOOTBALL:
            return True
        known_feed_urls = {url for _, url in self.default_feeds}
        return feed_source.url in known_feed_urls

    def _passes_keyword_filter(self, entry: NormalizedEntry) -> bool:
        keywords = ["football", "soccer", "goal", "fifa", "uefa"]
        blob = f"{entry.title} {entry.summary or ''}".lower()
        return any(k in blob for k in keywords)

    async def _upsert_news_item(
        self, session: AsyncSession, project_id: int, source_id: int, entry: NormalizedEntry
    ) -> bool:
        result = await session.execute(
            select(NewsItem).where(NewsItem.project_id == project_id, NewsItem.hash == entry.hash)
        )
        if result.scalar_one_or_none():
            return False
        news = NewsItem(
            project_id=project_id,
            source_id=source_id,
            title=entry.title,
            url=entry.url,
            published_at=entry.published_at,
            raw_summary=entry.summary,
            raw_content=entry.content,
            hash=entry.hash,
        )
        session.add(news)
        await session.flush()
        return True
