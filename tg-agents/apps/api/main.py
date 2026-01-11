from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Awaitable
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Annotated, cast

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis
from redis.asyncio import from_url as redis_from_url
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from apps.api.auth import seed_admin
from apps.api.config import Settings, get_settings
from apps.api.db import dispose_engine, get_async_session, init_engine, init_sessionmaker
from apps.api.logging_config import configure_logging
from apps.api.models import (
    AgentConfig,
    ConnectionStatus,
    FeedSource,
    NewsItem,
    Post,
    PostStatus,
    Project,
    TelegramChannel,
    TelegramConnection,
    TelegramMode,
    User,
)
from apps.api.schemas import (
    AgentConfigOut,
    AgentConfigUpdate,
    BotConnectRequest,
    FeedSourceCreate,
    FeedSourceOut,
    LoginRequest,
    NewsItemOut,
    PostOut,
    ProjectCreate,
    ProjectOut,
    TelegramChannelCreate,
    TelegramChannelOut,
    TelegramChannelUpdate,
    TelegramStatusOut,
    TestMessageRequest,
    TokenResponse,
)
from apps.api.telegram_bot import send_to_channels
from apps.api.telegram_user import provide_password, send_user_message, start_qr_login, wait_for_qr
from apps.worker.images import ImageService
from apps.worker.pipeline import PostPipeline
from apps.worker.planner import PostPlanner

logger = logging.getLogger(__name__)
settings: Settings = get_settings()
redis_client: Redis | None = None
SessionDep = Annotated[AsyncSession, Depends(get_async_session)]


async def get_redis() -> Redis:
    global redis_client
    if redis_client is None:
        redis_client = redis_from_url(settings.redis_url)
    return redis_client


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    init_engine(settings)
    init_sessionmaker(settings)
    app.state.redis = await get_redis()
    async with get_sessionmaker()() as session:
        await seed_admin(session)
    try:
        yield
    finally:
        if app.state.redis:
            await app.state.redis.aclose()
        await dispose_engine()


app = FastAPI(title="tg-agents API", lifespan=lifespan)
RedisDep = Annotated[Redis, Depends(get_redis)]
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health(session: SessionDep) -> dict[str, str]:
    try:
        await session.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        logger.exception("Database health check failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="База данных недоступна"
        ) from exc
    return {"status": "ok"}


@app.get("/ready")
async def readiness(session: SessionDep, redis: RedisDep) -> dict[str, str]:
    try:
        await session.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        logger.exception("Readiness DB check failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="База данных недоступна"
        ) from exc
    try:
        await cast(Awaitable[bool], redis.ping())
    except Exception as exc:  # noqa: BLE001
        logger.exception("Readiness Redis check failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Redis недоступен"
        ) from exc
    return {"status": "ready"}


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return init_sessionmaker(settings)


@app.post("/login", response_model=TokenResponse)
async def login(_: LoginRequest | None = None) -> TokenResponse:
    # Auth disabled: return dummy token
    return TokenResponse(access_token="public")


@app.post("/projects", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreate,
    session: SessionDep,
) -> ProjectOut:
    project = Project(name=payload.name, niche=payload.niche)
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return project


@app.get("/projects", response_model=list[ProjectOut])
async def list_projects(
    session: SessionDep,
) -> list[ProjectOut]:
    result = await session.execute(select(Project).order_by(Project.id))
    return list(result.scalars().all())


@app.get("/projects/{project_id}/image/preview")
async def image_preview(
    project_id: int,
    query: str,
    session: SessionDep,
) -> dict[str, str | None]:
    result = await session.execute(select(AgentConfig).where(AgentConfig.project_id == project_id))
    config = result.scalar_one_or_none()
    mode = config.image_mode.value if config else "wikimedia"
    service = ImageService(get_sessionmaker(), settings)
    image = await service.find_image(query, mode=mode)  # type: ignore[arg-type]
    await service.close()
    if not image:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Изображение не найдено")
    return {"path": image.path, "source": image.source}


@app.get("/projects/{project_id}/agent-config", response_model=AgentConfigOut)
async def get_agent_config(
    project_id: int,
    session: SessionDep,
) -> AgentConfigOut:
    result = await session.execute(select(AgentConfig).where(AgentConfig.project_id == project_id))
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Конфигурация агента не найдена"
        )
    return config


@app.put("/projects/{project_id}/agent-config", response_model=AgentConfigOut)
async def upsert_agent_config(
    project_id: int,
    payload: AgentConfigUpdate,
    session: SessionDep,
) -> AgentConfigOut:
    result = await session.execute(select(AgentConfig).where(AgentConfig.project_id == project_id))
    config = result.scalar_one_or_none()
    if config:
        for key, value in payload.model_dump().items():
            setattr(config, key, value)
    else:
        config = AgentConfig(project_id=project_id, **payload.model_dump())
        session.add(config)
    await session.commit()
    await session.refresh(config)
    return config


@app.get("/projects/{project_id}/feed-sources", response_model=list[FeedSourceOut])
async def list_feed_sources(
    project_id: int,
    session: SessionDep,
) -> list[FeedSourceOut]:
    result = await session.execute(
        select(FeedSource).where(FeedSource.project_id == project_id).order_by(FeedSource.id)
    )
    return list(result.scalars().all())


@app.post("/projects/{project_id}/feed-sources", response_model=FeedSourceOut, status_code=201)
async def create_feed_source(
    project_id: int,
    payload: FeedSourceCreate,
    session: SessionDep,
) -> FeedSourceOut:
    feed = FeedSource(project_id=project_id, **payload.model_dump())
    session.add(feed)
    await session.commit()
    await session.refresh(feed)
    return feed


@app.put("/feed-sources/{feed_id}", response_model=FeedSourceOut)
async def update_feed_source(
    feed_id: int,
    payload: FeedSourceCreate,
    session: SessionDep,
) -> FeedSourceOut:
    result = await session.execute(select(FeedSource).where(FeedSource.id == feed_id))
    feed = result.scalar_one_or_none()
    if not feed:
        raise HTTPException(status_code=404, detail="Источник не найден")
    for key, value in payload.model_dump().items():
        setattr(feed, key, value)
    await session.commit()
    await session.refresh(feed)
    return feed


@app.delete("/feed-sources/{feed_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_feed_source(
    feed_id: int,
    session: SessionDep,
) -> None:
    result = await session.execute(select(FeedSource).where(FeedSource.id == feed_id))
    feed = result.scalar_one_or_none()
    if not feed:
        raise HTTPException(status_code=404, detail="Источник не найден")
    await session.delete(feed)
    await session.commit()
    return None


@app.get("/projects/{project_id}/news-items", response_model=list[NewsItemOut])
async def latest_news_items(
    project_id: int,
    session: SessionDep,
    limit: int = 20,
) -> list[NewsItemOut]:
    result = await session.execute(
        select(NewsItem)
        .where(NewsItem.project_id == project_id)
        .order_by(NewsItem.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


@app.get("/projects/{project_id}/posts", response_model=list[PostOut])
async def list_posts(
    project_id: int,
    session: SessionDep,
    status_filter: PostStatus | None = None,
) -> list[PostOut]:
    stmt = select(Post).where(Post.project_id == project_id).order_by(Post.planned_at.desc())
    if status_filter:
        stmt = stmt.where(Post.status == status_filter)
    result = await session.execute(stmt)
    return list(result.scalars().all())


@app.post("/projects/{project_id}/plan/today")
async def plan_today(
    project_id: int,
    session: SessionDep,
) -> dict[str, int]:
    planner = PostPlanner(get_sessionmaker())
    result = await planner.plan_for_project(session, project_id, datetime.now(UTC).date())
    await session.commit()
    if not result:
        raise HTTPException(status_code=404, detail="Конфигурация агента не найдена")
    return {"planned": result.planned_count}


@app.get("/projects/{project_id}/plan", response_model=list[PostOut])
async def get_plan(
    project_id: int,
    session: SessionDep,
    date_str: str | None = None,
) -> list[PostOut]:
    plan_date = datetime.now(UTC).date() if not date_str else date.fromisoformat(date_str)
    day_start = datetime.combine(plan_date, time.min, tzinfo=UTC)
    day_end = day_start + timedelta(days=1)
    result = await session.execute(
        select(Post)
        .where(
            Post.project_id == project_id,
            Post.planned_at >= day_start,
            Post.planned_at < day_end,
        )
        .order_by(Post.planned_at)
    )
    return list(result.scalars().all())


@app.post("/projects/{project_id}/feeds/pull")
async def manual_pull(
    project_id: int,
    session: SessionDep,
) -> dict[str, int]:
    from apps.worker.rss import RSSCollector

    collector = RSSCollector(get_sessionmaker(), settings)
    inserted = await collector.pull_project(project_id)
    await collector.close()
    return {"inserted": inserted}


@app.get("/projects/{project_id}/news/latest", response_model=list[NewsItemOut])
async def latest_news(
    project_id: int,
    session: SessionDep,
    limit: int = 50,
) -> list[NewsItemOut]:
    result = await session.execute(
        select(NewsItem)
        .where(NewsItem.project_id == project_id)
        .order_by(NewsItem.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


@app.post("/projects/{project_id}/telegram/bot/connect", response_model=TelegramStatusOut)
async def connect_bot(
    project_id: int,
    payload: BotConnectRequest,
    session: SessionDep,
) -> TelegramStatusOut:
    encrypted = settings.encrypt(payload.bot_token)
    result = await session.execute(
        select(TelegramConnection).where(
            TelegramConnection.project_id == project_id,
            TelegramConnection.mode == TelegramMode.BOT,
        )
    )
    conn = result.scalar_one_or_none()
    now = datetime.now(UTC)
    if conn:
        conn.bot_token_encrypted = encrypted
        conn.last_connected_at = now
        conn.status = ConnectionStatus.CONNECTED
    else:
        conn = TelegramConnection(
            project_id=project_id,
            mode=TelegramMode.BOT,
            bot_token_encrypted=encrypted,
            last_connected_at=now,
            status=ConnectionStatus.CONNECTED,
        )
        session.add(conn)
    await session.commit()
    return TelegramStatusOut(mode=TelegramMode.BOT, status=conn.status, channels=0)


@app.get("/projects/{project_id}/telegram/status", response_model=TelegramStatusOut)
async def telegram_status(
    project_id: int,
    session: SessionDep,
) -> TelegramStatusOut:
    result = await session.execute(
        select(TelegramConnection).where(TelegramConnection.project_id == project_id)
    )
    conn = result.scalar_one_or_none()
    channels_count = await session.scalar(
        select(func.count())
        .select_from(TelegramChannel)
        .where(TelegramChannel.project_id == project_id)
    )
    if conn:
        return TelegramStatusOut(
            mode=conn.mode, status=conn.status, channels=int(channels_count or 0)
        )
    return TelegramStatusOut(mode=None, status=None, channels=int(channels_count or 0))


@app.post("/projects/{project_id}/channels", response_model=TelegramChannelOut, status_code=201)
async def add_channel(
    project_id: int,
    payload: TelegramChannelCreate,
    session: SessionDep,
) -> TelegramChannelOut:
    channel = TelegramChannel(
        project_id=project_id,
        tg_chat_id=payload.tg_chat_id,
        title=payload.title,
        username=payload.username,
        enabled=payload.enabled,
    )
    session.add(channel)
    await session.commit()
    await session.refresh(channel)
    return channel


@app.get("/projects/{project_id}/channels", response_model=list[TelegramChannelOut])
async def list_channels(
    project_id: int,
    session: SessionDep,
) -> list[TelegramChannelOut]:
    result = await session.execute(
        select(TelegramChannel).where(TelegramChannel.project_id == project_id)
    )
    return list(result.scalars().all())


@app.put("/channels/{channel_id}", response_model=TelegramChannelOut)
async def update_channel(
    channel_id: int,
    payload: TelegramChannelUpdate,
    session: SessionDep,
) -> TelegramChannelOut:
    result = await session.execute(select(TelegramChannel).where(TelegramChannel.id == channel_id))
    channel = result.scalar_one_or_none()
    if not channel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Канал не найден")
    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(channel, key, value)
    await session.commit()
    await session.refresh(channel)
    return channel


@app.post("/projects/{project_id}/telegram/user/qr/start")
async def start_user_qr(
    project_id: int,
    session: SessionDep,
) -> dict[str, str]:
    try:
        qr_url = await start_qr_login(project_id, settings)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    result = await session.execute(
        select(TelegramConnection).where(
            TelegramConnection.project_id == project_id,
            TelegramConnection.mode == TelegramMode.USER,
        )
    )
    conn = result.scalar_one_or_none()
    if not conn:
        conn = TelegramConnection(
            project_id=project_id,
            mode=TelegramMode.USER,
            status=ConnectionStatus.CONNECTING,
        )
        session.add(conn)
    conn.status = ConnectionStatus.CONNECTING
    conn.telethon_session_path = str(
        (Path(settings.app_data_dir) / "telethon" / f"{project_id}.session").resolve()
    )
    await session.commit()
    return {"qr_url": qr_url, "status": "connecting"}


@app.post("/projects/{project_id}/telegram/user/qr/wait")
async def wait_user_qr(
    project_id: int,
    session: SessionDep,
) -> dict[str, bool]:
    try:
        result = await wait_for_qr(project_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if result.get("connected"):
        conn_result = await session.execute(
            select(TelegramConnection).where(
                TelegramConnection.project_id == project_id,
                TelegramConnection.mode == TelegramMode.USER,
            )
        )
        conn = conn_result.scalar_one_or_none()
        if conn:
            conn.status = ConnectionStatus.CONNECTED
            conn.last_connected_at = datetime.now(UTC)
            await session.commit()
    if result.get("needs_password"):
        return {"needs_password": True}
    return {"connected": True}


@app.post("/projects/{project_id}/telegram/user/qr/password")
async def password_user_qr(
    project_id: int,
    password: dict[str, str],
    session: SessionDep,
) -> dict[str, str]:
    pwd = password.get("password")
    if not pwd:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Требуется пароль")
    try:
        await provide_password(project_id, pwd)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    conn_result = await session.execute(
        select(TelegramConnection).where(
            TelegramConnection.project_id == project_id,
            TelegramConnection.mode == TelegramMode.USER,
        )
    )
    conn = conn_result.scalar_one_or_none()
    if conn:
        conn.status = ConnectionStatus.CONNECTED
        conn.last_connected_at = datetime.now(UTC)
        await session.commit()
    return {"status": "connected"}


@app.post("/projects/{project_id}/run-once")
async def run_pipeline_once(
    project_id: int,
) -> dict[str, int]:
    pipeline = PostPipeline(get_sessionmaker(), settings=settings)
    processed = await pipeline.run(project_id=project_id)
    return {"processed": processed}


@app.post("/projects/{project_id}/telegram/test-message")
async def send_test_message(
    project_id: int,
    payload: TestMessageRequest,
    session: SessionDep,
) -> dict[str, int]:
    conn_result = await session.execute(
        select(TelegramConnection).where(
            TelegramConnection.project_id == project_id,
        )
    )
    conn = conn_result.scalar_one_or_none()
    if not conn:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Telegram не подключен"
        )
    channels_result = await session.execute(
        select(TelegramChannel).where(
            TelegramChannel.project_id == project_id,
            TelegramChannel.enabled.is_(True),
        )
    )
    channels = list(channels_result.scalars().all())
    if not channels:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Нет настроенных каналов"
        )
    try:
        chat_ids = [ch.tg_chat_id for ch in channels]
        if conn.mode == TelegramMode.BOT:
            if not conn.bot_token_encrypted:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail="Бот не подключен"
                )
            token = settings.decrypt(conn.bot_token_encrypted)
            await send_to_channels(token, chat_ids, payload.text, image_path=payload.image_path)
        else:
            await send_user_message(
                project_id, chat_ids, payload.text, image_path=payload.image_path
            )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to send Telegram message: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="Не удалось отправить сообщение в Telegram"
        ) from exc
    return {"sent": len(channels)}
