from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import TelegramMode
from ..models import Article, Channel, JobStatus, PostJob
from ..schemas import ArticleCreate, ChannelCreate, PostJobCreate


class Repository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_channels(self) -> list[Channel]:
        result = await self._session.execute(select(Channel))
        return list(result.scalars().all())

    async def get_channel(self, channel_id: int) -> Channel | None:
        result = await self._session.execute(select(Channel).where(Channel.id == channel_id))
        return result.scalar_one_or_none()

    async def get_active_channels(self) -> list[Channel]:
        result = await self._session.execute(
            select(Channel).where(Channel.active.is_(True)).order_by(Channel.id)
        )
        return list(result.scalars().all())

    async def create_channel(self, payload: ChannelCreate) -> Channel:
        channel = Channel(
            title=payload.title,
            telegram_chat_id=payload.telegram_chat_id,
            mode=payload.mode,
            active=payload.active,
        )
        self._session.add(channel)
        await self._session.commit()
        await self._session.refresh(channel)
        return channel

    async def create_article(self, payload: ArticleCreate) -> Article:
        article = Article(
            title=payload.title,
            summary=payload.summary,
            url=str(payload.url),
            source=payload.source,
        )
        self._session.add(article)
        await self._session.commit()
        await self._session.refresh(article)
        return article

    async def find_article_by_url(self, url: str) -> Article | None:
        result = await self._session.execute(select(Article).where(Article.url == url))
        return result.scalar_one_or_none()

    async def create_job(self, payload: PostJobCreate) -> PostJob:
        job = PostJob(
            channel_id=payload.channel_id,
            article_id=payload.article_id,
            post_content=payload.post_content,
            scheduled_for=payload.scheduled_for or datetime.utcnow(),
            status=JobStatus.PENDING,
        )
        self._session.add(job)
        await self._session.commit()
        await self._session.refresh(job)
        return job

    async def list_articles(self, limit: int = 50) -> list[Article]:
        result = await self._session.execute(
            select(Article).order_by(Article.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def pending_jobs(self, limit: int = 10) -> list[PostJob]:
        result = await self._session.execute(
            select(PostJob)
            .where(PostJob.status == JobStatus.PENDING)
            .order_by(PostJob.scheduled_for)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_job(self, job_id: int) -> PostJob | None:
        result = await self._session.execute(select(PostJob).where(PostJob.id == job_id))
        return result.scalar_one_or_none()

    async def mark_job(
        self, job: PostJob, status: JobStatus, *, increment_tries: bool = False
    ) -> PostJob:
        job.status = status
        if increment_tries:
            job.tries += 1
        await self._session.commit()
        await self._session.refresh(job)
        return job

    async def channels_for_mode(self, mode: TelegramMode) -> list[Channel]:
        result = await self._session.execute(
            select(Channel).where(Channel.active.is_(True), Channel.mode == mode)
        )
        return list(result.scalars().all())

    async def delete_channels(self, channel_ids: Iterable[int]) -> int:
        removed = 0
        for channel_id in channel_ids:
            channel = await self.get_channel(channel_id)
            if channel:
                await self._session.delete(channel)
                removed += 1
        await self._session.commit()
        return removed
