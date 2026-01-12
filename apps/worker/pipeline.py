from __future__ import annotations

import logging
import re
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from apps.api.config import Settings, get_settings
from apps.api.gemini import GeminiGenerator
from apps.api.time_utils import msk_now, to_utc
from apps.api.models import (
    AgentConfig,
    ConnectionStatus,
    ImageMode,
    NewsItem,
    Post,
    PostStatus,
    TelegramChannel,
    TelegramConnection,
)
from apps.api.telegram_user import get_session_path, send_user_message, telegram_status
from apps.worker.images import ImageMode as WorkerImageMode
from apps.worker.images import ImageResult, ImageService
from apps.worker.ranker import pick_next_news_item

logger = logging.getLogger(__name__)


class PostPipeline:
    def __init__(
        self,
        session_maker: async_sessionmaker[AsyncSession],
        settings: Settings | None = None,
        generator: GeminiGenerator | None = None,
        image_service: ImageService | None = None,
    ) -> None:
        self.session_maker = session_maker
        self.settings = settings or get_settings()
        self.generator = generator or GeminiGenerator()
        self.image_service = image_service or ImageService(session_maker, settings=self.settings)

    async def run(self, project_id: int | None = None) -> int:
        now = to_utc(msk_now())
        count = 0
        async with self.session_maker() as session:
            stmt = select(Post).where(Post.status == PostStatus.PLANNED, Post.planned_at <= now)
            if project_id:
                stmt = stmt.where(Post.project_id == project_id)
            result = await session.execute(stmt)
            posts = list(result.scalars().all())
            for post in posts:
                await self._process_post(session, post)
                count += 1
            await session.commit()
        return count

    async def _process_post(self, session: AsyncSession, post: Post) -> None:
        logger.info("Processing post %s for project %s", post.id, post.project_id)
        config = await self._get_agent_config(session, post.project_id)
        if not config:
            post.status = PostStatus.FAILED
            post.error = "Не найдена конфигурация агента"
            return
        news = await self._resolve_news(session, post)
        if not news:
            post.status = PostStatus.FAILED
            post.error = "Нет подходящих новостей"
            return
        try:
            generated = await self.generator.generate(
                news, news.source.name if news.source else "", config
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Gemini generation failed for post %s: %s", post.id, exc)
            post.status = PostStatus.FAILED
            post.error = str(exc)
            return

        post.payload_json = generated.model_dump(mode="json")  # type: ignore[assignment]
        if not generated.should_post:
            post.status = PostStatus.SKIPPED
            post.error = generated.reason_if_skip
            return

        guard_ok, guard_reason = await self._passes_guardrails(session, post, generated, news)
        if not guard_ok:
            post.status = PostStatus.SKIPPED
            post.error = guard_reason
            return

        text = generated.body_html
        image_path = await self._maybe_find_image(config, generated.image_query, news.url if news else None)
        link_preview = config.image_mode == ImageMode.LINK_PREVIEW and image_path is None

        connection = await self._get_connection(session, post.project_id)
        channels = await self._get_channels(session, post.project_id)
        if not channels:
            post.status = PostStatus.FAILED
            post.error = "Каналы не настроены"
            return
        if not connection:
            post.status = PostStatus.FAILED
            post.error = "Нет подключения Telegram"
            return

        chat_ids = [ch.tg_chat_id for ch in channels]
        attempts = 0
        while attempts < 2:
            try:
                await send_user_message(
                    post.project_id,
                    chat_ids,
                    text,
                    image_path=image_path,
                    link_preview=link_preview,
                    settings=self.settings,
                )
                post.tg_message_id = "sent-user"
                post.status = PostStatus.PUBLISHED
                post.published_at = to_utc(msk_now())
                return
            except Exception as exc:  # noqa: BLE001
                attempts += 1
                logger.exception(
                    "Publish failed attempt %s for post %s: %s", attempts, post.id, exc
                )
                if attempts >= 2:
                    post.status = PostStatus.FAILED
                    post.error = str(exc)
                    return

    async def _get_agent_config(self, session: AsyncSession, project_id: int) -> AgentConfig | None:
        result = await session.execute(
            select(AgentConfig).where(AgentConfig.project_id == project_id)
        )
        return result.scalar_one_or_none()

    async def _resolve_news(self, session: AsyncSession, post: Post) -> NewsItem | None:
        if post.news_item_id:
            result = await session.execute(select(NewsItem).where(NewsItem.id == post.news_item_id))
            return result.scalar_one_or_none()
        news = await pick_next_news_item(session, post.project_id)
        if news:
            post.news_item_id = news.id
        return news

    async def _maybe_find_image(
        self, config: AgentConfig, query: str, news_url: str | None
    ) -> str | None:
        if config.image_mode == ImageMode.LINK_PREVIEW:
            return None
        result: ImageResult | None = None
        if config.image_mode == ImageMode.OG_IMAGE and news_url:
            result = await self.image_service.find_image(news_url, mode="og_image")
            if not result and query:
                result = await self.image_service.find_image(query, mode="wikimedia")
        else:
            result = await self.image_service.find_image(query, mode="wikimedia")
        return result.path if result else None

    async def _get_connection(
        self, session: AsyncSession, project_id: int
    ) -> TelegramConnection | None:
        tele_status = await telegram_status(self.settings)
        if tele_status.get("status") != "connected":
            return None
        return TelegramConnection(
            project_id=project_id,
            status=ConnectionStatus.CONNECTED,
            telethon_session_path=get_session_path(self.settings),
        )

    async def _get_channels(
        self, session: AsyncSession, project_id: int
    ) -> list[TelegramChannel]:
        result = await session.execute(
            select(TelegramChannel).where(
                TelegramChannel.project_id == project_id, TelegramChannel.enabled.is_(True)
            )
        )
        return list(result.scalars().all())

    async def _passes_guardrails(
        self, session: AsyncSession, post: Post, generated: Any, news: NewsItem
    ) -> tuple[bool, str | None]:
        recent = await self._recent_headlines(session, post.project_id)
        if self._is_similar(generated.headline, recent):
            return False, "Похоже на недавний пост"

        input_text = " ".join(
            filter(
                None,
                [
                    news.title,
                    news.raw_summary or "",
                    news.raw_content or "",
                ],
            )
        ).lower()
        output_text = f"{generated.headline} {generated.body_html}".lower()
        rumor_words = {"rumor", "rumour", "insider", "reportedly", "allegedly"}
        if any(word in output_text for word in rumor_words) and not any(
            word in input_text for word in rumor_words
        ):
            return False, "Защитное правило: в источнике нет слов о слухах"

        num_pattern = re.compile(r"\b\d+(?:\.\d+)?\b")
        input_nums = set(num_pattern.findall(input_text))
        output_nums = set(num_pattern.findall(output_text))
        extra_nums = output_nums - input_nums
        if extra_nums:
            return False, "Защитное правило: числовые данные отсутствуют в источнике"
        return True, None

    async def _recent_headlines(self, session: AsyncSession, project_id: int) -> list[str]:
        six_hours_ago = to_utc(msk_now()) - timedelta(hours=6)
        result = await session.execute(
            select(Post.payload_json)
            .where(
                Post.project_id == project_id,
                Post.status == PostStatus.PUBLISHED,
                Post.published_at >= six_hours_ago,
                Post.payload_json.is_not(None),
            )
            .limit(50)
        )
        headlines: list[str] = []
        for row in result.scalars():
            if isinstance(row, dict) and "headline" in row and isinstance(row["headline"], str):
                headlines.append(row["headline"])
        return headlines

    def _is_similar(self, headline: str, recent: list[str]) -> bool:
        def tokens(text: str) -> set[str]:
            cleaned = re.sub(r"[^a-z0-9\s]", " ", text.lower())
            return {t for t in cleaned.split() if len(t) > 2}

        base = tokens(headline)
        if not base:
            return False
        for h in recent:
            comp = tokens(h)
            if not comp:
                continue
            jaccard = len(base & comp) / len(base | comp)
            if jaccard >= 0.5:
                return True
        return False
