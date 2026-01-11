from __future__ import annotations

import asyncio

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import TelegramMode
from app.db import init_db
from app.schemas import ArticleCreate, ChannelCreate, PostJobCreate
from app.services.queue import PostQueue, PostTask
from app.services.repository import Repository
from app.services.scheduler import QueueWorker


class StubDispatcher:
    def __init__(self) -> None:
        self.sent: list[tuple[TelegramMode, str, str]] = []

    async def send(self, mode: TelegramMode, chat_id: str, message: str) -> None:
        self.sent.append((mode, chat_id, message))

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_queue_worker_marks_jobs() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    await init_db(engine)
    session_maker: async_sessionmaker[AsyncSession] = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )

    async with session_maker() as session:
        repo = Repository(session)
        channel = await repo.create_channel(
            ChannelCreate(
                title="Test",
                telegram_chat_id="@chat",
                mode=TelegramMode.BOT,
                active=True,
            )
        )
        article = await repo.create_article(
            ArticleCreate(title="T", summary="S", url="http://example.com", source="s")
        )
        job = await repo.create_job(
            PostJobCreate(
                channel_id=channel.id,
                article_id=article.id,
                post_content="content",
                scheduled_for=None,
            )
        )

    queue = PostQueue(max_size=10)
    dispatcher = StubDispatcher()
    worker = QueueWorker(queue, dispatcher, session_maker)
    worker_task = asyncio.create_task(worker.run())
    await queue.enqueue(
        PostTask(
            chat_id=channel.telegram_chat_id,
            content="content",
            mode=TelegramMode.BOT,
            job_id=job.id,
        )
    )
    await asyncio.sleep(0.1)
    await worker.stop()
    worker_task.cancel()

    async with session_maker() as session:
        repo = Repository(session)
        updated_job = await repo.get_job(job.id)
        assert updated_job is not None
        assert updated_job.status.value == "sent"
    assert dispatcher.sent, "Dispatcher did not send messages"
