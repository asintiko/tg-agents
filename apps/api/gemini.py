from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING

from pydantic import BaseModel, HttpUrl, ValidationError, field_validator

from apps.api.config import get_settings
from apps.api.html_utils import append_signature, render_hashtags, sanitize_html_for_telegram
from apps.api.models import AgentConfig, NewsItem

logger = logging.getLogger(__name__)
MAX_BODY_LENGTH = 900

if TYPE_CHECKING:
    import google.generativeai as genai


class GeneratedPost(BaseModel):
    headline: str
    lead: str
    body_html: str
    hashtags: list[str]
    image_query: str
    source_url: HttpUrl
    should_post: bool
    reason_if_skip: str | None

    @field_validator("body_html")
    @classmethod
    def enforce_length(cls, v: str) -> str:
        if len(v) > MAX_BODY_LENGTH:
            return v[:MAX_BODY_LENGTH]
        return v


def _enforce_length(text: str) -> str:
    if len(text) > MAX_BODY_LENGTH:
        return text[:MAX_BODY_LENGTH]
    return text


def _limit_body_to_fit(body_html: str, suffix: str) -> str:
    available = MAX_BODY_LENGTH - len(suffix)
    if available <= 0:
        return ""
    if len(body_html) > available:
        return body_html[:available]
    return body_html


class GeminiGenerator:
    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or get_settings().gemini_api_key
        self.model: genai.GenerativeModel | None
        self.model = None
        if self.api_key:
            try:
                import google.generativeai as genai
            except ImportError as exc:  # pragma: no cover - import guard
                msg = "google-generativeai is required when GEMINI_API_KEY is set"
                raise ImportError(msg) from exc
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel("gemini-1.5-flash")

    async def generate(
        self, news: NewsItem, source_name: str, config: AgentConfig
    ) -> GeneratedPost:
        payload = self._build_prompt(news, source_name, config)
        last_error: Exception | None = None
        for _ in range(3):
            try:
                raw = await self._call_model(payload)
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                logger.warning("Gemini call failed, fallback to stub: %s", exc)
                break
            logger.info("Gemini raw response: %s", raw)
            try:
                data = json.loads(raw)
                post = GeneratedPost.model_validate(data)
                sanitized_body = sanitize_html_for_telegram(post.body_html)
                extras: list[str] = []
                if config.include_source_link:
                    extras.append(f'Источник: <a href="{news.url}">{news.url}</a>')
                if config.signature_html:
                    extras.append(config.signature_html)
                signature_block = (
                    sanitize_html_for_telegram("\n".join(extras)) if extras else ""
                )
                hashtags = render_hashtags(post.hashtags)
                suffix = ""
                if signature_block:
                    suffix += f"\n\n---\n{signature_block}"
                if hashtags:
                    suffix += hashtags
                trimmed_body = _limit_body_to_fit(sanitized_body, suffix)
                final_body = trimmed_body
                if signature_block:
                    final_body = append_signature(final_body, signature_block)
                if hashtags:
                    final_body = f"{final_body}{hashtags}"
                post.body_html = _enforce_length(final_body)
                return post
            except (json.JSONDecodeError, ValidationError) as exc:
                last_error = exc
                continue
        logger.warning("Falling back to simple post because Gemini failed: %s", last_error)
        return self._fallback_post(news, source_name, config)

    def _build_prompt(self, news: NewsItem, source_name: str, config: AgentConfig) -> str:
        summary = news.raw_summary or ""
        content = news.raw_content or ""
        body = (
            f"Заголовок: {news.title}\n"
            f"Ссылка: {news.url}\n"
            f"Опубликовано: {news.published_at}\n"
            f"Краткое содержание: {summary}\n"
            f"Полный текст: {content}\n"
            f"Источник: {source_name}\n"
        )
        signature = config.signature_html or ""
        include_link = "yes" if config.include_source_link else "no"
        prompt_lines = [
            "Ты Telegram-агент, который готовит посты про футбол. "
            "Используй только переданные факты. "
            "Если данных мало, устанавливай should_post=false и кратко объясняй причину в reason_if_skip.",
            "",
            f"Язык: {config.language}",
            f"Тон: {config.tone}",
            f"Режим эмодзи: {config.emoji_mode}",
            f"Добавлять ссылку на источник: {include_link}",
            f"HTML подпись (добавь, если есть): {signature}",
            "",
            "Верни ТОЛЬКО корректный JSON со следующими полями:",
            "headline, lead, body_html (<=900 символов, только безопасные для Telegram теги HTML), "
            "hashtags (список коротких тегов), image_query, source_url, should_post (bool), "
            "reason_if_skip (строка или null).",
            "",
            "Факты:",
            body,
        ]
        return "\n".join(prompt_lines).strip()

    def _fallback_post(self, news: NewsItem, source_name: str, config: AgentConfig) -> GeneratedPost:
        """Plain fallback when Gemini недоступен."""
        body_parts = [
            sanitize_html_for_telegram(news.raw_summary or news.raw_content or news.title),
        ]
        if config.include_source_link:
            body_parts.append(f'Источник: <a href="{news.url}">{news.url}</a>')
        if config.signature_html:
            body_parts.append(config.signature_html)
        body = "\n\n".join(part for part in body_parts if part)
        return GeneratedPost(
            headline=news.title,
            lead=news.raw_summary or news.title,
            body_html=_enforce_length(body),
            hashtags=[],
            image_query="",
            source_url=news.url,  # type: ignore[arg-type]
            should_post=True,
            reason_if_skip=None,
        )

    async def _call_model(self, prompt: str) -> str:
        model = self.model
        if model is None:
            # Fallback for local/dev without API key.
            return json.dumps(
                {
                    "headline": "Placeholder headline",
                    "lead": "Placeholder lead",
                    "body_html": "Placeholder body",
                    "hashtags": ["football"],
                    "image_query": "football stadium",
                    "source_url": "https://example.com",
                    "should_post": False,
                    "reason_if_skip": "Gemini API key not configured",
                }
            )

        def _sync_call() -> str:
            response = model.generate_content(prompt)
            return response.text or ""

        return await asyncio.to_thread(_sync_call)
