from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator, Awaitable
from contextlib import asynccontextmanager
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Annotated, Any, cast

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis
from redis.asyncio import from_url as redis_from_url
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from apps.api.auth import issue_admin_token, require_admin, verify_admin_password
from apps.api.config import Settings, get_settings
from apps.api.db import dispose_engine, get_async_session, init_engine, init_sessionmaker
from apps.api.gemini import GeminiGenerator
from apps.api.logging_config import configure_logging
from apps.api.time_utils import MSK_TZ, msk_now, to_utc
from apps.api.models import (
    AgentConfig,
    ConnectionStatus,
    EmojiMode,
    FeedSource,
    ImageMode,
    NewsItem,
    Niche,
    Post,
    PostKind,
    PostStatus,
    Project,
    CustomEmoji,
    TelegramChannel,
    TelegramConnection,
)
from apps.api.schemas import (
    AgentConfigOut,
    AgentConfigUpdate,
    FeedSourceCreate,
    FeedSourceOut,
    LoginRequest,
    AutopostStatusOut,
    ProjectStatusOut,
    NewsItemOut,
    PostOut,
    ProjectCreate,
    ProjectOut,
    TelegramAuthStatus,
    TelegramChannelCreate,
    TelegramChannelOut,
    TelegramChannelUpdate,
    TelegramPhoneCodeRequest,
    TelegramPhoneRequest,
    TelegramDiscoveredChannel,
    TelegramChannelsListOut,
    TelegramChannelsSaveRequest,
    TelegramMe,
    TelegramPasswordRequest,
    TelegramQrStartResponse,
    TelegramStatusOut,
    TestPostResponse,
    TestMessageRequest,
    TokenResponse,
    CustomEmojiOut,
)
from apps.api.telegram_user import (
    get_session_path,
    fetch_custom_emojis,
    list_user_channels,
    provide_password,
    provide_phone_code,
    reset_session,
    send_user_message,
    start_phone_login,
    start_qr_login,
    telegram_status as telethon_status,
    wait_for_qr,
)
from apps.worker.images import ImageService
from apps.worker.pipeline import PostPipeline
from apps.worker.planner import PostPlanner
from apps.worker.ranker import pick_next_news_item
from apps.worker.rss import RSSCollector

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

AdminDep = Annotated[None, Depends(require_admin)]


@app.get("/health")
async def health(session: SessionDep) -> dict[str, str]:
    try:
        await session.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        logger.exception("Database health check failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="База данных недоступна",
        ) from exc
    return {"status": "ok"}


@app.get("/ready")
async def readiness(session: SessionDep, redis: RedisDep) -> dict[str, str]:
    try:
        await session.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        logger.exception("Readiness DB check failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="База данных недоступна",
        ) from exc
    try:
        await cast(Awaitable[bool], redis.ping())
    except Exception as exc:  # noqa: BLE001
        logger.exception("Readiness Redis check failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Redis недоступен",
        ) from exc
    return {"status": "ready"}


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return init_sessionmaker(settings)


def _read_worker_heartbeat(settings: Settings) -> dict[str, Any] | None:
    path = Path(settings.app_data_dir) / "worker" / "heartbeat.json"
    if not path.exists():
        return None
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        return data
    except Exception:  # noqa: BLE001
        return None


async def _ensure_connection(
    session: AsyncSession,
    project_id: int,
    status: ConnectionStatus,
    last_connected_at: datetime | None = None,
) -> TelegramConnection:
    result = await session.execute(
        select(TelegramConnection).where(TelegramConnection.project_id == project_id)
    )
    conn = result.scalar_one_or_none()
    if not conn:
        conn = TelegramConnection(project_id=project_id, status=status)
        session.add(conn)
    conn.status = status
    conn.telethon_session_path = str(Path(get_session_path(settings)))
    if last_connected_at:
        conn.last_connected_at = to_utc(last_connected_at)
    await session.flush()
    return conn


async def _update_all_connections(
    status: ConnectionStatus, last_connected_at: datetime | None = None
) -> None:
    session_maker = get_sessionmaker()
    async with session_maker() as session:
        result = await session.execute(select(Project.id))
        project_ids = list(result.scalars().all())
        for pid in project_ids:
            await _ensure_connection(session, pid, status, last_connected_at)
        await session.commit()


async def _ensure_default_project(session: AsyncSession) -> Project:
    result = await session.execute(select(Project).order_by(Project.id))
    project = result.scalar_one_or_none()
    if project:
        return project
    project = Project(name="Default", niche=Niche.FOOTBALL)
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return project


def _config_template(project_id: int) -> AgentConfig:
    return AgentConfig(
        project_id=project_id,
        posts_per_day=8,
        window_start="09:00",
        window_end="23:59",
        min_interval_minutes=60,
        language="ru",
        tone="neutral",
        signature_html=None,
        emoji_mode=EmojiMode.BASIC,
        predictions_enabled=True,
        predictions_time_msk="10:00",
        predictions_matches_count=3,
        gemini_web_search=False,
        web_search_enabled=False,
        autopublish_enabled=True,
        brand_emoji_id=None,
        brand_emoji_fallback="⚽",
        premium_emoji_id=None,
        premium_emoji_fallback="⚡",
        premium_emoji_alt=None,
        include_source_link=False,
        image_mode=ImageMode.OG_IMAGE,
    )


async def _ensure_default_config(session: AsyncSession, project_id: int) -> AgentConfig:
    cfg = await session.scalar(select(AgentConfig).where(AgentConfig.project_id == project_id))
    if cfg:
        return cfg
    cfg = _config_template(project_id)
    session.add(cfg)
    await session.commit()
    await session.refresh(cfg)
    return cfg


@app.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest) -> TokenResponse:
    if not settings.admin_password:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ADMIN_PASSWORD не задан",
        )
    if not verify_admin_password(payload.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный пароль"
        )
    return TokenResponse(access_token=issue_admin_token())


@app.post("/api/telegram/qr/start", response_model=TelegramQrStartResponse)
async def api_telegram_qr_start(_: AdminDep) -> TelegramQrStartResponse:
    try:
        result = await start_qr_login(settings)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if result.get("status") == "connected":
        await _update_all_connections(ConnectionStatus.CONNECTED, msk_now())
    else:
        await _update_all_connections(ConnectionStatus.CONNECTING)
    return TelegramQrStartResponse(**result)


@app.post("/api/telegram/qr/wait", response_model=TelegramAuthStatus)
async def api_telegram_qr_wait(_: AdminDep) -> TelegramAuthStatus:
    try:
        result = await wait_for_qr(settings)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if result.get("status") == "connected":
        await _update_all_connections(ConnectionStatus.CONNECTED, msk_now())
    elif result.get("status") == "password_required":
        await _update_all_connections(ConnectionStatus.CONNECTING)
    else:
        await _update_all_connections(ConnectionStatus.DISCONNECTED)
    return TelegramAuthStatus(**result)


@app.post("/api/telegram/qr/password", response_model=TelegramAuthStatus)
async def api_telegram_qr_password(payload: TelegramPasswordRequest, _: AdminDep) -> TelegramAuthStatus:
    if not payload.password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Требуется пароль 2FA")
    try:
        result = await provide_password(payload.password, settings)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    await _update_all_connections(ConnectionStatus.CONNECTED, msk_now())
    return TelegramAuthStatus(**result)


@app.get("/api/telegram/status", response_model=TelegramAuthStatus)
async def api_telegram_status(_: AdminDep) -> TelegramAuthStatus:
    result = await telethon_status(settings)
    return TelegramAuthStatus(**result)


@app.delete("/api/telegram/session")
async def api_telegram_reset_session(_: AdminDep) -> dict[str, str]:
    reset_session(settings)
    await _update_all_connections(ConnectionStatus.DISCONNECTED)
    return {"status": "reset"}


@app.post("/api/rss/pull")
async def api_rss_pull(_: AdminDep) -> dict[str, int]:
    collector = RSSCollector(get_sessionmaker(), settings=settings)
    await collector.ensure_default_feeds()
    await collector.pull_all()
    await collector.close()
    return {"ok": 1}


@app.get("/api/news/latest", response_model=list[NewsItemOut])
async def api_news_latest(_: AdminDep) -> list[NewsItemOut]:
    async with get_sessionmaker()() as session:
        project = await _ensure_default_project(session)
        result = await session.execute(
            select(NewsItem)
            .where(NewsItem.project_id == project.id)
            .order_by(NewsItem.created_at.desc())
            .limit(50)
        )
        return list(result.scalars().all())


@app.post("/api/preview/next")
async def api_preview_next(_: AdminDep) -> dict[str, Any]:
    async with get_sessionmaker()() as session:
        project = await _ensure_default_project(session)
        config = await _ensure_default_config(session, project.id)
        news = await pick_next_news_item(session, project.id)
        if not news:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Нет новостей")
        generator = GeminiGenerator()
        generated = await generator.generate(news, news.source.name if news.source else "", config)
        return {
            "news_id": news.id,
            "headline": generated.headline,
            "body_html": generated.body_html,
            "image_query": generated.image_query,
            "should_post": generated.should_post,
            "reason_if_skip": generated.reason_if_skip,
        }


@app.post("/api/publish/next")
async def api_publish_next(_: AdminDep) -> dict[str, Any]:
    async with get_sessionmaker()() as session:
        project = await _ensure_default_project(session)
        config = await _ensure_default_config(session, project.id)
        tele = await telethon_status(settings)
        if tele.get("status") != "connected":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Telegram не подключён")
        channels_result = await session.execute(
            select(TelegramChannel)
            .where(TelegramChannel.project_id == project.id, TelegramChannel.enabled.is_(True))
            .order_by(TelegramChannel.id)
        )
        channels = list(channels_result.scalars().all())
        if not channels:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Выберите хотя бы один канал")
        news = await pick_next_news_item(session, project.id)
        if not news:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Нет новостей для публикации")
        generator = GeminiGenerator()
        generated = await generator.generate(news, news.source.name if news.source else "", config)
        if not generated.should_post:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=generated.reason_if_skip or "Контент не подходит для публикации",
            )
        text = generated.body_html
        link_preview = config.image_mode == ImageMode.LINK_PREVIEW
        image_path: str | None = None
        if config.image_mode != ImageMode.LINK_PREVIEW:
            service = ImageService(get_sessionmaker(), settings)
            try:
                if config.image_mode == ImageMode.OG_IMAGE:
                    image = await service.find_image(news.url, mode="og_image")
                    if not image and generated.image_query:
                        image = await service.find_image(generated.image_query, mode="wikimedia")
                else:
                    image = await service.find_image(generated.image_query, mode="wikimedia")
                if image:
                    image_path = image.path
            finally:
                await service.close()
        try:
            message_ids = await send_user_message(
                project.id,
                [ch.tg_chat_id for ch in channels],
                text,
                image_path=image_path,
                link_preview=link_preview if image_path is None else False,
                brand_emoji_id=config.brand_emoji_id,
                brand_emoji_fallback=config.brand_emoji_fallback or "⚽",
                premium_emoji_id=config.premium_emoji_id,
                premium_emoji_alt=config.premium_emoji_alt,
                premium_emoji_fallback=config.premium_emoji_fallback or "⚡",
                settings=settings,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to publish next news: %s", exc)
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Не удалось отправить пост") from exc

    post = Post(
        project_id=project.id,
        news_item_id=news.id,
        kind=PostKind.NEWS,
        status=PostStatus.PUBLISHED,
        planned_at=to_utc(msk_now()),
        published_at=to_utc(msk_now()),
        tg_message_id=",".join(message_ids) if message_ids else None,
        payload_json=generated.model_dump(mode="json"),
        )
        session.add(post)
        await session.commit()
        return {"ok": True, "tg_message_ids": message_ids, "news_id": news.id}


@app.post("/projects/{project_id}/preview/next")
async def project_preview_next(
    project_id: int,
    session: SessionDep,
    _: AdminDep,
) -> dict[str, Any]:
    project = await session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Проект не найден")
    config = await _ensure_default_config(session, project.id)
    news = await pick_next_news_item(session, project.id)
    if not news:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Нет новостей")
    generator = GeminiGenerator()
    generated = await generator.generate(news, news.source.name if news.source else "", config)
    return {
        "news_id": news.id,
        "headline": generated.headline,
        "body_html": generated.body_html,
        "image_query": generated.image_query,
        "should_post": generated.should_post,
        "reason_if_skip": generated.reason_if_skip,
    }


@app.post("/projects/{project_id}/preview/prediction")
async def project_preview_prediction(
    project_id: int,
    session: SessionDep,
    _: AdminDep,
) -> dict[str, Any]:
    project = await session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Проект не найден")
    config = await _ensure_default_config(session, project.id)
    if not config.predictions_enabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Прогнозы отключены")
    generator = GeminiGenerator()
    generated = await generator.generate_prediction(
        config,
        matches_count=config.predictions_matches_count or 3,
        force_web_search=True,
    )
    return {
        "headline": generated.headline,
        "body_html": generated.body_html,
        "image_query": generated.image_query,
        "should_post": generated.should_post,
        "reason_if_skip": generated.reason_if_skip,
    }


@app.post("/projects/{project_id}/publish/next")
async def project_publish_next(
    project_id: int,
    session: SessionDep,
    _: AdminDep,
) -> dict[str, Any]:
    project = await session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Проект не найден")
    config = await _ensure_default_config(session, project.id)
    tele = await telethon_status(settings)
    if tele.get("status") != "connected":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Telegram не подключён")
    channels_result = await session.execute(
        select(TelegramChannel)
        .where(
            TelegramChannel.project_id == project.id,
            TelegramChannel.enabled.is_(True),
        )
        .order_by(TelegramChannel.id)
    )
    channels = list(channels_result.scalars().all())
    if not channels:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Выберите хотя бы один канал"
        )
    news = await pick_next_news_item(session, project.id)
    if not news:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Нет новостей для публикации")
    generator = GeminiGenerator()
    generated = await generator.generate(news, news.source.name if news.source else "", config)
    if not generated.should_post:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=generated.reason_if_skip or "Контент не подходит для публикации",
        )
    text = generated.body_html
    link_preview = config.image_mode == ImageMode.LINK_PREVIEW
    image_path: str | None = None
    if config.image_mode != ImageMode.LINK_PREVIEW:
        service = ImageService(get_sessionmaker(), settings)
        try:
            if config.image_mode == ImageMode.OG_IMAGE:
                image = await service.find_image(news.url, mode="og_image")
                if not image and generated.image_query:
                    image = await service.find_image(generated.image_query, mode="wikimedia")
            else:
                image = await service.find_image(generated.image_query, mode="wikimedia")
            if image:
                image_path = image.path
        finally:
            await service.close()
    try:
        message_ids = await send_user_message(
            project.id,
            [ch.tg_chat_id for ch in channels],
            text,
            image_path=image_path,
            link_preview=link_preview if image_path is None else False,
            brand_emoji_id=config.brand_emoji_id,
            brand_emoji_fallback=config.brand_emoji_fallback or "⚽",
            premium_emoji_id=config.premium_emoji_id,
            premium_emoji_alt=config.premium_emoji_alt,
            premium_emoji_fallback=config.premium_emoji_fallback or "⚡",
            settings=settings,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to publish next news for project %s: %s", project.id, exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Не удалось отправить пост") from exc

    post = Post(
        project_id=project.id,
        news_item_id=news.id,
        kind=PostKind.NEWS,
        status=PostStatus.PUBLISHED,
        planned_at=to_utc(msk_now()),
        published_at=to_utc(msk_now()),
        tg_message_id=",".join(message_ids) if message_ids else None,
        payload_json=generated.model_dump(mode="json"),
    )
    session.add(post)
    await session.commit()
    return {"ok": True, "tg_message_ids": message_ids, "news_id": news.id}


@app.post("/projects/{project_id}/publish/prediction")
async def project_publish_prediction(
    project_id: int,
    session: SessionDep,
    _: AdminDep,
) -> dict[str, Any]:
    project = await session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Проект не найден")
    config = await _ensure_default_config(session, project.id)
    if not config.predictions_enabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Прогнозы отключены")
    tele = await telethon_status(settings)
    if tele.get("status") != "connected":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Telegram не подключён")
    channels_result = await session.execute(
        select(TelegramChannel)
        .where(
            TelegramChannel.project_id == project.id,
            TelegramChannel.enabled.is_(True),
        )
        .order_by(TelegramChannel.id)
    )
    channels = list(channels_result.scalars().all())
    if not channels:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Выберите хотя бы один канал")
    generator = GeminiGenerator()
    generated = await generator.generate_prediction(
        config,
        matches_count=config.predictions_matches_count or 3,
        force_web_search=True,
    )
    if not generated.should_post:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=generated.reason_if_skip or "Контент не подходит для публикации",
        )
    text = generated.body_html
    try:
        message_ids = await send_user_message(
            project.id,
            [ch.tg_chat_id for ch in channels],
            text,
            image_path=None,
            link_preview=False,
            brand_emoji_id=config.brand_emoji_id,
            brand_emoji_fallback=config.brand_emoji_fallback or "⚽",
            premium_emoji_id=config.premium_emoji_id,
            premium_emoji_alt=config.premium_emoji_alt,
            premium_emoji_fallback=config.premium_emoji_fallback or "⚡",
            settings=settings,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to publish prediction for project %s: %s", project.id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="Не удалось отправить пост"
        ) from exc

    post = Post(
        project_id=project.id,
        news_item_id=None,
        kind=PostKind.PREDICTION,
        status=PostStatus.PUBLISHED,
        planned_at=to_utc(msk_now()),
        published_at=to_utc(msk_now()),
        tg_message_id=",".join(message_ids) if message_ids else None,
        payload_json=generated.model_dump(mode="json"),
    )
    session.add(post)
    await session.commit()
    return {"ok": True, "tg_message_ids": message_ids}


@app.post("/projects", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreate,
    session: SessionDep,
    _: AdminDep,
) -> ProjectOut:
    project = Project(name=payload.name, niche=payload.niche)
    session.add(project)
    await session.flush()

    # Автоконфигурация агента и RSS для удобного старта.
    session.add(_config_template(project.id))

    if project.niche == Niche.FOOTBALL:
        existing_feeds = await session.scalar(
            select(func.count()).where(FeedSource.project_id == project.id)
        )
        if not existing_feeds:
            for name, url in RSSCollector.default_feeds:
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
    await session.refresh(project)
    return project


@app.get("/projects", response_model=list[ProjectOut])
async def list_projects(
    session: SessionDep,
    _: AdminDep,
) -> list[ProjectOut]:
    result = await session.execute(select(Project).order_by(Project.id))
    return list(result.scalars().all())


@app.get("/projects/{project_id}/image/preview")
async def image_preview(
    project_id: int,
    query: str,
    session: SessionDep,
    _: AdminDep,
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
    _: AdminDep,
) -> AgentConfigOut:
    project = await session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Проект не найден")
    config = await _ensure_default_config(session, project_id)
    return config


@app.put("/projects/{project_id}/agent-config", response_model=AgentConfigOut)
async def upsert_agent_config(
    project_id: int,
    payload: AgentConfigUpdate,
    session: SessionDep,
    _: AdminDep,
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
    _: AdminDep,
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
    _: AdminDep,
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
    _: AdminDep,
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
    _: AdminDep,
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
    _: AdminDep,
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
    _: AdminDep,
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
    _: AdminDep,
) -> dict[str, int]:
    planner = PostPlanner(get_sessionmaker())
    result = await planner.plan_for_project(session, project_id, msk_now().date())
    await session.commit()
    if not result:
        raise HTTPException(status_code=404, detail="Конфигурация агента не найдена")
    return {"planned": result.planned_count}


@app.get("/projects/{project_id}/plan", response_model=list[PostOut])
async def get_plan(
    project_id: int,
    session: SessionDep,
    _: AdminDep,
    date_str: str | None = None,
) -> list[PostOut]:
    plan_date = msk_now().date() if not date_str else date.fromisoformat(date_str)
    day_start = datetime.combine(plan_date, time.min, tzinfo=MSK_TZ)
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


@app.get("/projects/{project_id}/autopost/status", response_model=AutopostStatusOut)
async def autopost_status(
    project_id: int,
    session: SessionDep,
    _: AdminDep,
) -> AutopostStatusOut:
    now_utc = to_utc(msk_now())
    hb = _read_worker_heartbeat(settings)
    hb_ts = None
    if hb and hb.get("ts_utc"):
        try:
            hb_ts = datetime.fromisoformat(str(hb["ts_utc"]))
        except Exception:  # noqa: BLE001
            hb_ts = None
    worker_online = bool(hb_ts and hb_ts >= now_utc - timedelta(seconds=90))
    next_result = await session.execute(
        select(Post)
        .where(Post.project_id == project_id, Post.status == PostStatus.PLANNED)
        .order_by(Post.planned_at)
        .limit(1)
    )
    next_post = next_result.scalar_one_or_none()
    planned_total = await session.scalar(
        select(func.count())
        .select_from(Post)
        .where(Post.project_id == project_id, Post.status == PostStatus.PLANNED)
    )
    last_published = await session.execute(
        select(Post.published_at)
        .where(Post.project_id == project_id, Post.status == PostStatus.PUBLISHED)
        .order_by(Post.published_at.desc())
        .limit(1)
    )
    last_published_at = last_published.scalar_one_or_none()
    return AutopostStatusOut(
        worker_online=worker_online,
        last_heartbeat=hb_ts,
        next_post_at=next_post.planned_at if next_post else None,
        next_post_kind=next_post.kind if next_post else None,
        planned_total=int(planned_total or 0),
        last_published_at=last_published_at,
    )


@app.get("/projects/{project_id}/status", response_model=ProjectStatusOut)
async def project_status(
    project_id: int,
    session: SessionDep,
    _: AdminDep,
) -> ProjectStatusOut:
    project = await session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Проект не найден")

    config = await _ensure_default_config(session, project_id)
    now_msk = msk_now()
    now_utc = to_utc(now_msk)

    hb = _read_worker_heartbeat(settings)
    hb_ts_utc = None
    hb_ts_msk = None
    if hb:
        ts_utc_raw = hb.get("ts_utc")
        ts_msk_raw = hb.get("ts_msk")
        try:
            hb_ts_utc = datetime.fromisoformat(str(ts_utc_raw)) if ts_utc_raw else None
        except Exception:  # noqa: BLE001
            hb_ts_utc = None
        try:
            hb_ts_msk = datetime.fromisoformat(str(ts_msk_raw)) if ts_msk_raw else None
        except Exception:  # noqa: BLE001
            hb_ts_msk = hb_ts_utc.astimezone(MSK_TZ) if hb_ts_utc else None
    worker_online = bool(hb_ts_utc and hb_ts_utc >= now_utc - timedelta(seconds=90))

    day_start = datetime.combine(now_msk.date(), time.min, tzinfo=MSK_TZ)
    day_end = day_start + timedelta(days=1)
    planned_today = await session.scalar(
        select(func.count())
        .select_from(Post)
        .where(
            Post.project_id == project_id,
            Post.status == PostStatus.PLANNED,
            Post.planned_at >= to_utc(day_start),
            Post.planned_at < to_utc(day_end),
        )
    )
    due_count = await session.scalar(
        select(func.count())
        .select_from(Post)
        .where(
            Post.project_id == project_id,
            Post.status == PostStatus.PLANNED,
            Post.planned_at <= now_utc,
        )
    )
    next_planned = await session.execute(
        select(Post.planned_at)
        .where(
            Post.project_id == project_id,
            Post.status == PostStatus.PLANNED,
            Post.planned_at > now_utc,
        )
        .order_by(Post.planned_at)
        .limit(1)
    )
    next_planned_at = next_planned.scalar_one_or_none()
    last_published = await session.execute(
        select(Post.published_at)
        .where(Post.project_id == project_id, Post.status == PostStatus.PUBLISHED)
        .order_by(Post.published_at.desc())
        .limit(1)
    )
    last_published_at = last_published.scalar_one_or_none()
    last_error = await session.execute(
        select(Post.error)
        .where(Post.project_id == project_id, Post.error.is_not(None))
        .order_by(Post.updated_at.desc())
        .limit(1)
    )
    last_error_msg = last_error.scalar_one_or_none()
    return ProjectStatusOut(
        worker_online=worker_online,
        worker_last_heartbeat_msk=hb_ts_msk,
        autopublish_enabled=config.autopublish_enabled,
        planned_today_count=int(planned_today or 0),
        due_count=int(due_count or 0),
        next_planned_msk=next_planned_at.astimezone(MSK_TZ) if next_planned_at else None,
        last_published_msk=last_published_at.astimezone(MSK_TZ) if last_published_at else None,
        last_error=last_error_msg,
    )


@app.post("/projects/{project_id}/telegram/emojis/sync")
async def sync_custom_emojis_endpoint(
    project_id: int,
    session: SessionDep,
    _: AdminDep,
) -> dict[str, int]:
    project = await session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Проект не найден")
    try:
        sets_count, emojis = await fetch_custom_emojis(settings)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    synced = 0
    for item in emojis:
        doc_id = int(item.get("document_id"))
        alt = str(item.get("alt") or "").strip()
        if not alt:
            continue
        existing = await session.get(CustomEmoji, doc_id)
        if existing:
            existing.alt = alt
            existing.stickerset_title = item.get("stickerset_title")
            existing.stickerset_id = item.get("stickerset_id")
        else:
            session.add(
                CustomEmoji(
                    document_id=doc_id,
                    alt=alt,
                    stickerset_title=item.get("stickerset_title"),
                    stickerset_id=item.get("stickerset_id"),
                )
            )
        synced += 1
    await session.commit()
    return {"synced_sets": sets_count, "synced_emojis": synced}


@app.get("/projects/{project_id}/telegram/emojis", response_model=list[CustomEmojiOut])
async def list_custom_emojis(
    project_id: int,
    session: SessionDep,
    _: AdminDep,
    query: str = "",
    limit: int = 50,
) -> list[CustomEmojiOut]:
    project = await session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Проект не найден")
    stmt = select(CustomEmoji).order_by(CustomEmoji.updated_at.desc())
    if query:
        pattern = f"%{query.lower()}%"
        stmt = stmt.where(
            func.lower(CustomEmoji.alt).like(pattern)
            | func.lower(CustomEmoji.stickerset_title).like(pattern)
        )
    stmt = stmt.limit(max(1, min(limit, 200)))
    result = await session.execute(stmt)
    return list(result.scalars().all())


@app.post("/projects/{project_id}/feeds/pull")
async def manual_pull(
    project_id: int,
    session: SessionDep,
    _: AdminDep,
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
    _: AdminDep,
    limit: int = 50,
) -> list[NewsItemOut]:
    result = await session.execute(
        select(NewsItem)
        .where(NewsItem.project_id == project_id)
        .order_by(NewsItem.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


@app.get("/projects/{project_id}/telegram/status", response_model=TelegramStatusOut)
async def telegram_status(
    project_id: int,
    session: SessionDep,
    _: AdminDep,
) -> TelegramStatusOut:
    tele = await telethon_status(settings)
    status_value: ConnectionStatus | None = None
    if tele.get("status") == "connected":
        status_value = ConnectionStatus.CONNECTED
    elif tele.get("status") in {"waiting_for_scan", "password_required", "connecting"}:
        status_value = ConnectionStatus.CONNECTING
    elif tele.get("status") == "disconnected":
        status_value = ConnectionStatus.DISCONNECTED

    result = await session.execute(
        select(TelegramConnection).where(TelegramConnection.project_id == project_id)
    )
    conn = result.scalar_one_or_none()
    if status_value and conn:
        conn.status = status_value
        if tele.get("last_connected_at"):
            try:
                conn.last_connected_at = to_utc(
                    datetime.fromisoformat(str(tele["last_connected_at"]))
                )
            except Exception:  # noqa: BLE001
                conn.last_connected_at = conn.last_connected_at
        await session.commit()

    channels_count = await session.scalar(
        select(func.count())
        .select_from(TelegramChannel)
        .where(TelegramChannel.project_id == project_id)
    )
    return TelegramStatusOut(
        status=status_value or (conn.status if conn else None),
        channels=int(channels_count or 0),
        last_connected_at=tele.get("last_connected_at")
        if status_value == ConnectionStatus.CONNECTED
        else (conn.last_connected_at if conn else None),
        me=tele.get("me"),
        me_photo_b64=tele.get("me_photo_b64"),
    )


@app.post("/projects/{project_id}/channels", response_model=TelegramChannelOut, status_code=201)
async def add_channel(
    project_id: int,
    payload: TelegramChannelCreate,
    session: SessionDep,
    _: AdminDep,
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
    _: AdminDep,
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
    _: AdminDep,
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


@app.delete("/channels/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_channel(
    channel_id: int,
    session: SessionDep,
    _: AdminDep,
) -> None:
    result = await session.execute(select(TelegramChannel).where(TelegramChannel.id == channel_id))
    channel = result.scalar_one_or_none()
    if not channel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Канал не найден")
    await session.delete(channel)
    await session.commit()
    return None


async def _import_channels_for_project(
    session: AsyncSession, project_id: int, payload: TelegramChannelsSaveRequest
) -> list[TelegramChannel]:
    if payload.replace:
        await session.execute(delete(TelegramChannel).where(TelegramChannel.project_id == project_id))
    existing_result = await session.execute(
        select(TelegramChannel).where(TelegramChannel.project_id == project_id)
    )
    existing = {ch.tg_chat_id: ch for ch in existing_result.scalars().all()}
    for ch in payload.channels:
        if ch.tg_chat_id in existing:
            channel = existing[ch.tg_chat_id]
            channel.title = ch.title
            channel.username = ch.username
            channel.enabled = True
        else:
            session.add(
                TelegramChannel(
                    project_id=project_id,
                    tg_chat_id=ch.tg_chat_id,
                    title=ch.title,
                    username=ch.username,
                    enabled=True,
                )
            )
    await session.commit()
    result = await session.execute(
        select(TelegramChannel).where(TelegramChannel.project_id == project_id)
    )
    return list(result.scalars().all())


@app.get("/api/telegram/channels/discover", response_model=list[TelegramDiscoveredChannel])
async def discover_channels(_: AdminDep) -> list[TelegramDiscoveredChannel]:
    tele = await telethon_status(settings)
    if tele.get("status") != "connected":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Telegram не подключён: войдите по QR",
        )
    channels = await list_user_channels(settings)
    return [
        TelegramDiscoveredChannel(
            tg_chat_id=ch["tg_chat_id"],
            title=ch["title"],
            username=ch.get("username"),
        )
        for ch in channels
    ]


@app.post("/api/channels/save", response_model=list[TelegramChannelsListOut])
async def save_channels(
    payload: TelegramChannelsSaveRequest,
    session: SessionDep,
    _: AdminDep,
) -> list[TelegramChannelsListOut]:
    project = await _ensure_default_project(session)
    return await _import_channels_for_project(session, project.id, payload)


@app.get("/api/channels", response_model=list[TelegramChannelsListOut])
async def list_saved_channels(
    session: SessionDep,
    _: AdminDep,
) -> list[TelegramChannelsListOut]:
    project = await _ensure_default_project(session)
    result = await session.execute(
        select(TelegramChannel).where(TelegramChannel.project_id == project.id)
    )
    return list(result.scalars().all())


@app.patch("/api/channels/{channel_id}", response_model=TelegramChannelsListOut)
async def patch_channel(
    channel_id: int,
    payload: TelegramChannelUpdate,
    session: SessionDep,
    _: AdminDep,
) -> TelegramChannelsListOut:
    result = await session.execute(
        select(TelegramChannel).where(TelegramChannel.id == channel_id)
    )
    channel = result.scalar_one_or_none()
    if not channel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Канал не найден")
    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(channel, key, value)
    await session.commit()
    await session.refresh(channel)
    return channel


@app.get(
    "/projects/{project_id}/telegram/user/channels/discover",
    response_model=list[TelegramDiscoveredChannel],
)
async def discover_project_channels(
    project_id: int,
    session: SessionDep,
    _: AdminDep,
) -> list[TelegramDiscoveredChannel]:
    project = await session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Проект не найден")
    tele = await telethon_status(settings)
    if tele.get("status") != "connected":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Telegram не подключён: войдите по QR",
        )
    channels = await list_user_channels(settings)
    return [
        TelegramDiscoveredChannel(
            tg_chat_id=ch["tg_chat_id"],
            title=ch["title"],
            username=ch.get("username"),
            can_post=ch.get("can_post"),
            role=ch.get("role"),
        )
        for ch in channels
    ]


@app.post(
    "/projects/{project_id}/telegram/channels/import",
    response_model=list[TelegramChannelsListOut],
)
async def import_project_channels(
    project_id: int,
    payload: TelegramChannelsSaveRequest,
    session: SessionDep,
    _: AdminDep,
) -> list[TelegramChannelsListOut]:
    project = await session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Проект не найден")
    return await _import_channels_for_project(session, project_id, payload)


@app.post("/projects/{project_id}/channels/import", response_model=list[TelegramChannelsListOut])
async def import_project_channels_new(
    project_id: int,
    payload: TelegramChannelsSaveRequest,
    session: SessionDep,
    _: AdminDep,
) -> list[TelegramChannelsListOut]:
    project = await session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Проект не найден")
    return await _import_channels_for_project(session, project_id, payload)


@app.post("/projects/{project_id}/telegram/user/qr/start")
async def start_user_qr(
    project_id: int,
    session: SessionDep,
    _: AdminDep,
) -> dict[str, str]:
    try:
        result = await start_qr_login(settings)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    await _ensure_connection(session, project_id, ConnectionStatus.CONNECTING)
    if result.get("status") == "connected":
        last_connected = msk_now()
        await _ensure_connection(session, project_id, ConnectionStatus.CONNECTED, last_connected)
        await session.commit()
        return {"status": "connected", "qr_url": None}
    await session.commit()
    return {"qr_url": result.get("qr_url", ""), "status": "connecting"}


@app.post("/projects/{project_id}/telegram/user/phone/start")
async def start_user_phone(
    project_id: int,
    payload: TelegramPhoneRequest,
    session: SessionDep,
    _: AdminDep,
) -> dict[str, str]:
    try:
        result = await start_phone_login(payload.phone, settings)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    await _ensure_connection(session, project_id, ConnectionStatus.CONNECTING)
    await session.commit()
    return {"status": result.get("status", "code_sent")}


@app.post("/projects/{project_id}/telegram/user/phone/code")
async def submit_user_phone_code(
    project_id: int,
    payload: TelegramPhoneCodeRequest,
    session: SessionDep,
    _: AdminDep,
) -> dict[str, str]:
    try:
        result = await provide_phone_code(payload.code, settings)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if result.get("status") == "connected":
        await _ensure_connection(session, project_id, ConnectionStatus.CONNECTED, msk_now())
    elif result.get("status") == "password_required":
        await _ensure_connection(session, project_id, ConnectionStatus.CONNECTING)
    await session.commit()
    return {"status": result.get("status", "connected")}


@app.post("/projects/{project_id}/telegram/user/qr/wait")
async def wait_user_qr(
    project_id: int,
    session: SessionDep,
    _: AdminDep,
) -> dict[str, bool]:
    try:
        result = await wait_for_qr(settings)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if result.get("status") == "connected":
        await _ensure_connection(session, project_id, ConnectionStatus.CONNECTED, msk_now())
        await session.commit()
        return {"connected": True}
    if result.get("status") == "password_required":
        await _ensure_connection(session, project_id, ConnectionStatus.CONNECTING)
        await session.commit()
        return {"needs_password": True}
    await _ensure_connection(session, project_id, ConnectionStatus.DISCONNECTED)
    await session.commit()
    return {"connected": False}


@app.post("/projects/{project_id}/telegram/user/qr/password")
async def password_user_qr(
    project_id: int,
    password: dict[str, str],
    session: SessionDep,
    _: AdminDep,
) -> dict[str, str]:
    pwd = password.get("password")
    if not pwd:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Требуется пароль")
    try:
        result = await provide_password(pwd, settings)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    await _ensure_connection(session, project_id, ConnectionStatus.CONNECTED, msk_now())
    await session.commit()
    return {"status": result.get("status", "connected")}


@app.post("/projects/{project_id}/run-once")
async def run_pipeline_once(
    project_id: int,
    _: AdminDep,
) -> dict[str, int]:
    pipeline = PostPipeline(get_sessionmaker(), settings=settings)
    processed = await pipeline.run(project_id=project_id)
    return {"processed": processed}


@app.post("/projects/{project_id}/telegram/test-message")
async def send_test_message(
    project_id: int,
    payload: TestMessageRequest,
    session: SessionDep,
    _: AdminDep,
) -> dict[str, int]:
    tele = await telethon_status(settings)
    if tele.get("status") != "connected":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Telegram не подключён"
        )
    await _ensure_connection(session, project_id, ConnectionStatus.CONNECTED, msk_now())
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
    config = await session.scalar(
        select(AgentConfig).where(AgentConfig.project_id == project_id)
    )
    try:
        chat_ids = [ch.tg_chat_id for ch in channels]
        await send_user_message(
            project_id,
            chat_ids,
            payload.text,
            image_path=payload.image_path,
            premium_emoji_id=config.premium_emoji_id if config else None,
            premium_emoji_alt=config.premium_emoji_alt if config else None,
            premium_emoji_fallback=(config.premium_emoji_fallback if config else None) or "⚡",
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to send Telegram message: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="Не удалось отправить сообщение в Telegram"
        ) from exc
    return {"sent": len(channels)}


@app.post("/api/telegram/test-post", response_model=TestPostResponse)
async def api_test_post(_: AdminDep, session: SessionDep) -> TestPostResponse:
    tele = await telethon_status(settings)
    if tele.get("status") != "connected":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Telegram не подключён"
        )
    project = await _ensure_default_project(session)
    channels_result = await session.execute(
        select(TelegramChannel)
        .where(
            TelegramChannel.project_id == project.id,
            TelegramChannel.enabled.is_(True),
        )
        .order_by(TelegramChannel.id)
    )
    channels = list(channels_result.scalars().all())
    if not channels:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Выберите хотя бы один канал"
        )
    config = await _ensure_default_config(session, project.id)
    text = (
        "✅ Тестовая публикация\n"
        f"Время (МСК): {msk_now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        "Если вы это видите — система работает."
    )
    try:
        message_ids = await send_user_message(
            project.id,
            [channels[0].tg_chat_id],
            text,
            image_path=None,
            premium_emoji_id=config.premium_emoji_id,
            premium_emoji_alt=config.premium_emoji_alt,
            premium_emoji_fallback=config.premium_emoji_fallback or "⚡",
            settings=settings,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to send Telegram test post: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Не удалось отправить тестовое сообщение",
        ) from exc
    await _ensure_connection(session, project.id, ConnectionStatus.CONNECTED, msk_now())
    await session.commit()
    return TestPostResponse(ok=True, tg_message_id=message_ids[0] if message_ids else None)
