from __future__ import annotations

import asyncio
from datetime import datetime
import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..config import Settings
from ..models import JobStatus
from ..schemas import ArticleCreate, PostJobCreate
from .llm import GeminiClient
from .news import FootballNewsFetcher, NewsArticle, PostBuilder, deduplicate_articles
from .queue import PostQueue, PostTask
from .repository import Repository
from .telegram_dispatcher import TelegramDispatcher

logger = logging.getLogger(__name__)


class QueueWorker:
    def __init__(
        self,
        queue: PostQueue,
        dispatcher: TelegramDispatcher,
        session_maker: async_sessionmaker[AsyncSession],
    ) -> None:
        self._queue = queue
        self._dispatcher = dispatcher
        self._session_maker = session_maker
        self._running = True

    async def run(self) -> None:
        while self._running:
            try:
                task = await self._queue.dequeue()
            except asyncio.CancelledError:
                break
            try:
                await self._dispatcher.send(
                    mode=task.mode, chat_id=task.chat_id, message=task.content
                )
                await self._mark_job(task, JobStatus.SENT)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Failed to send Telegram message: %s", exc)
                await self._mark_job(task, JobStatus.FAILED, increment=True)
            finally:
                self._queue.mark_done()

    async def _mark_job(
        self, task: PostTask, status: JobStatus, *, increment: bool = False
    ) -> None:
        if task.job_id is None:
            return
        async with self._session_maker() as session:
            repo = Repository(session)
            job = await repo.get_job(task.job_id)
            if job:
                await repo.mark_job(job, status, increment_tries=increment)

    async def stop(self) -> None:
        self._running = False


class NewsScheduler:
    def __init__(
        self,
        settings: Settings,
        queue: PostQueue,
        session_maker: async_sessionmaker[AsyncSession],
        fetcher: FootballNewsFetcher,
        llm: GeminiClient,
        builder: PostBuilder,
    ) -> None:
        self._settings = settings
        self._queue = queue
        self._session_maker = session_maker
        self._fetcher = fetcher
        self._llm = llm
        self._builder = builder
        self._running = True

    async def run(self) -> None:
        if not self._settings.feature_flags.scheduler_enabled:
            return
        while self._running:
            try:
                await self.tick()
                await asyncio.sleep(self._settings.scheduler_interval_seconds)
            except asyncio.CancelledError:
                break
            except Exception as exc:  # noqa: BLE001
                logger.exception("Scheduler tick failed: %s", exc)

    async def tick(self) -> None:
        articles = deduplicate_articles(await self._fetcher.fetch(limit=3))
        async with self._session_maker() as session:
            repo = Repository(session)
            channels = await repo.get_active_channels()
            for article in articles:
                article_model = await self._persist_article(repo, article)
                if not article_model:
                    continue
                summary = await self._summarize(article)
                content = self._builder.build(article, summary)
                for channel in channels:
                    job = await repo.create_job(
                        PostJobCreate(
                            channel_id=channel.id,
                            article_id=article_model.id,
                            post_content=content,
                            scheduled_for=datetime.utcnow(),
                        )
                    )
                    await self._queue.enqueue(
                        PostTask(
                            chat_id=channel.telegram_chat_id,
                            content=content,
                            mode=channel.mode,
                            job_id=job.id,
                        )
                    )

    async def _persist_article(self, repo: Repository, article: NewsArticle):
        if not article.url:
            return None
        existing = await repo.find_article_by_url(article.url)
        if existing:
            return None
        try:
            payload = ArticleCreate(
                title=article.title,
                summary=article.summary,
                url=article.url,
                source=article.source,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Skip article due to validation error: %s", exc)
            return None
        return await repo.create_article(payload)

    async def _summarize(self, article: NewsArticle) -> str | None:
        if not self._settings.feature_flags.use_llm_for_summaries:
            return article.summary
        return await self._llm.summarize(article.summary or article.title)

    async def stop(self) -> None:
        self._running = False
