from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.models import FeedSource, NewsItem, Post, PostStatus

KEYWORDS = [
    "transfer",
    "goal",
    "match",
    "uefa",
    "fifa",
    "premier league",
    "champions league",
]


async def pick_next_news_item(session: AsyncSession, project_id: int) -> NewsItem | None:
    used_subquery: Select[tuple[int | None]] = select(Post.news_item_id).where(
        Post.project_id == project_id,
        Post.status == PostStatus.PUBLISHED,
        Post.news_item_id.is_not(None),
    )

    result = await session.execute(
        select(NewsItem, FeedSource.weight)
        .join(FeedSource, FeedSource.id == NewsItem.source_id, isouter=True)
        .where(
            NewsItem.project_id == project_id,
            NewsItem.id.not_in(used_subquery),
        )
    )
    candidates: Sequence[tuple[NewsItem, int | None]] = [
        (row[0], row[1]) for row in result.all()
    ]
    if not candidates:
        return None

    def score(item: NewsItem, weight: int | None) -> tuple[float, float]:
        effective_weight = float(weight or 1)
        text_blob = f"{item.title} {item.raw_summary or ''}".lower()
        keyword_bonus = 3.0 if any(k in text_blob for k in KEYWORDS) else 0.0
        ts_source: datetime = item.published_at or item.created_at
        return (effective_weight + keyword_bonus, ts_source.timestamp())

    ranked = sorted(
        candidates,
        key=lambda pair: score(pair[0], pair[1]),
        reverse=True,
    )
    return ranked[0][0]
