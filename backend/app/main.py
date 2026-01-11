from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from .config import Settings, get_settings
from .db import get_async_session, get_engine, get_session_maker, init_db
from .schemas import ArticleCreate, ArticleOut, ChannelCreate, ChannelOut, PostJobCreate, PostJobOut
from .services.llm import GeminiClient
from .services.news import FootballNewsFetcher, PostBuilder
from .services.queue import PostQueue, PostTask
from .services.repository import Repository
from .services.scheduler import NewsScheduler, QueueWorker
from .services.telegram_dispatcher import TelegramDispatcher

settings: Settings = get_settings()
engine = get_engine()
session_maker = get_session_maker()
queue = PostQueue(settings.post_queue_max_size)
dispatcher = TelegramDispatcher(settings)
news_fetcher = FootballNewsFetcher(settings.news_feed_url)
llm_client = GeminiClient(settings.gemini_api_key)
post_builder = PostBuilder()
queue_worker = QueueWorker(queue, dispatcher, session_maker)
scheduler = NewsScheduler(settings, queue, session_maker, news_fetcher, llm_client, post_builder)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db(engine)
    worker_task = asyncio.create_task(queue_worker.run())
    scheduler_task = asyncio.create_task(scheduler.run())
    try:
        yield
    finally:
        await queue_worker.stop()
        await scheduler.stop()
        worker_task.cancel()
        scheduler_task.cancel()
        await dispatcher.close()


app = FastAPI(title="Telegram Auto-News Agent", lifespan=lifespan)


@app.get("/health")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


SessionDep = Annotated[AsyncSession, Depends(get_async_session)]


@app.get("/channels", response_model=list[ChannelOut])
async def list_channels(session: SessionDep) -> list[ChannelOut]:
    repo = Repository(session)
    return await repo.list_channels()


@app.post("/channels", response_model=ChannelOut, status_code=status.HTTP_201_CREATED)
async def create_channel(payload: ChannelCreate, session: SessionDep) -> ChannelOut:
    repo = Repository(session)
    return await repo.create_channel(payload)


@app.post("/articles", response_model=ArticleOut, status_code=status.HTTP_201_CREATED)
async def create_article(payload: ArticleCreate, session: SessionDep) -> ArticleOut:
    repo = Repository(session)
    return await repo.create_article(payload)


@app.get("/articles", response_model=list[ArticleOut])
async def list_articles(session: SessionDep) -> list[ArticleOut]:
    repo = Repository(session)
    return await repo.list_articles()


@app.post("/jobs/manual", response_model=PostJobOut, status_code=status.HTTP_201_CREATED)
async def manual_post(payload: PostJobCreate, session: SessionDep) -> PostJobOut:
    repo = Repository(session)
    channel = await repo.get_channel(payload.channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Канал не найден")
    job = await repo.create_job(payload)
    await queue.enqueue(
        PostTask(
            chat_id=channel.telegram_chat_id,
            content=payload.post_content,
            mode=channel.mode,
            job_id=job.id,
        )
    )
    return job
