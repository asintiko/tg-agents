from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

from pydantic import BaseModel, HttpUrl, ValidationError, field_validator

from apps.api.config import get_settings
from apps.api.html_utils import append_signature, render_hashtags, sanitize_html_for_telegram
from apps.api.models import AgentConfig, NewsItem
from apps.api.time_utils import msk_now

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


@dataclass(slots=True)
class PredictionContext:
    title: str
    url: str
    summary: str
    content: str


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
        return await self._generate_common(
            payload,
            config,
            fallback=lambda: self._fallback_post(news, config),
            news_url=news.url,
            use_web_search=config.gemini_web_search,
            allow_link=config.include_source_link,
        )

    async def generate_prediction(self, config: AgentConfig) -> GeneratedPost:
        context = self._prediction_context()
        payload = self._build_prediction_prompt(context, config)
        return await self._generate_common(
            payload,
            config,
            fallback=lambda: self._fallback_prediction(context, config),
            news_url=context.url,
            use_web_search=config.gemini_web_search,
            allow_link=False,
        )

    async def _generate_common(
        self,
        prompt: str,
        config: AgentConfig,
        *,
        fallback: Callable[[], GeneratedPost],
        news_url: str | None,
        use_web_search: bool,
        allow_link: bool = True,
    ) -> GeneratedPost:
        last_error: Exception | None = None
        reinforced_prompt = self._reinforce_ru_prompt(prompt)
        for _ in range(3):
            try:
                raw = await self._call_model(reinforced_prompt, use_web_search=use_web_search)
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                logger.warning("Gemini call failed, fallback to stub: %s", exc)
                break
            logger.info("Gemini raw response: %s", raw)
            try:
                data = json.loads(raw)
                if news_url and "source_url" not in data:
                    data["source_url"] = news_url
                post = GeneratedPost.model_validate(data)
                post.body_html = self._compose_body(
                    post.body_html,
                    post.hashtags,
                    config,
                    allow_link=allow_link,
                    news_url=news_url,
                )
                if not self._is_russian_text(f"{post.headline} {post.body_html}"):
                    raise ValueError("Ответ не на русском")
                return post
            except (json.JSONDecodeError, ValidationError, ValueError) as exc:
                last_error = exc
                reinforced_prompt = self._reinforce_ru_prompt(prompt)
                continue
        logger.warning("Falling back to simple post because Gemini failed: %s", last_error)
        return fallback()

    def _build_prompt(self, news: NewsItem, source_name: str, config: AgentConfig) -> str:
        summary = news.raw_summary or ""
        content = news.raw_content or ""
        body = (
            f"Заголовок: {news.title}\n"
            f"Ссылка: {news.url}\n"
            f"Опубликовано: {news.published_at}\n"
            f"Краткое содержание: {summary}\n"
            f"Полный текст: {content}\n"
            f"Сайт/издание: {source_name}\n"
        )
        signature = config.signature_html or ""
        include_link = "добавь естественную ссылку без слова 'Источник'" if config.include_source_link else "не добавляй ссылку"
        prompt_lines = [
            "Ты Telegram-агент, который готовит посты про футбол только на русском языке.",
            "Избегай английских слов и кальки, если модель возвращает английский — переведи на русский и перефразируй.",
            "Не вставляй строку с надписью «Источник». Ссылку можно встроить в текст нейтрально (например, «подробнее по ссылке»).",
            "Если данных мало, устанавливай should_post=false и кратко объясняй причину в reason_if_skip.",
            "",
            f"Язык: ru (игнорируй иные значения конфигурации, пиши только на русском)",
            f"Тон: {config.tone}",
            f"Режим эмодзи: {config.emoji_mode}",
            f"Ссылки: {include_link}",
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
        if config.gemini_web_search:
            prompt_lines.append(
                "Если нужно уточнить факты, используй веб-поиск, но итоговый текст пиши только на русском."
            )
        return "\n".join(prompt_lines).strip()

    def _build_prediction_prompt(self, ctx: PredictionContext, config: AgentConfig) -> str:
        prompt_lines = [
            "Сделай короткий редакторский пост с прогнозами на главные футбольные матчи сегодняшнего дня.",
            "Пиши только на русском языке, избегай ставок и агрессивных обещаний. Покажи уверенность в процентах, но без гарантий.",
            "Структура: лидовое предложение, 3-5 матчей с краткими факторами (форма, турнир, травмы, мотивация), финальный вывод.",
            "Используй эмодзи умеренно, если это уместно для тона.",
            "Верни ТОЛЬКО JSON с полями headline, lead, body_html (<=900 символов), hashtags, image_query, source_url, should_post, reason_if_skip.",
            f"Тон: {config.tone}. Эмодзи режим: {config.emoji_mode}.",
            "Если данных о матчах нет, установи should_post=false и объясни причину.",
            "Не добавляй строку с текстом «Источник» и не вставляй промо ставок.",
            "",
            f"Заголовок: {ctx.title}",
            f"Ссылка: {ctx.url}",
            f"Краткое содержание: {ctx.summary}",
            f"Полный текст: {ctx.content}",
        ]
        if config.gemini_web_search:
            prompt_lines.append(
                "При необходимости обратись к веб-поиску, но пиши итог только по-русски."
            )
        return "\n".join(prompt_lines).strip()

    def _prediction_context(self) -> PredictionContext:
        today = msk_now().date()
        date_str = today.strftime("%d.%m.%Y")
        title = f"Прогнозы на ключевые футбольные матчи {date_str}"
        url = "https://football.example.com/predictions"
        summary = "Нужен редакторский пост с аккуратными прогнозами без ставок и агрессивных обещаний."
        content = (
            "Выбери 3-5 самых заметных матчей дня (еврокубки, топ-лиги). "
            "Для каждого матча укажи команды, турнир, краткий контекст, вероятности исхода в процентах и ключевые факторы. "
            "Избегай рекомендаций ставок, делай вывод нейтральным."
        )
        return PredictionContext(title=title, url=url, summary=summary, content=content)

    def _compose_body(
        self,
        raw_body: str,
        hashtags: list[str],
        config: AgentConfig,
        *,
        allow_link: bool,
        news_url: str | None,
    ) -> str:
        sanitized_body = sanitize_html_for_telegram(raw_body or "")
        sanitized_body = self._strip_source_lines(sanitized_body)
        extras: list[str] = []
        if allow_link and config.include_source_link and news_url:
            extras.append(f'<a href="{news_url}">Подробнее</a>')
        if config.signature_html:
            extras.append(config.signature_html)
        signature_block = sanitize_html_for_telegram("\n".join(extras)) if extras else ""
        hashtags_block = render_hashtags(hashtags)
        suffix = ""
        if signature_block:
            suffix += f"\n\n---\n{signature_block}"
        if hashtags_block:
            suffix += hashtags_block
        trimmed_body = _limit_body_to_fit(sanitized_body, suffix)
        final_body = trimmed_body
        if signature_block:
            final_body = append_signature(final_body, signature_block)
        if hashtags_block:
            final_body = f"{final_body}{hashtags_block}"
        final_body = self._strip_source_lines(final_body)
        return _enforce_length(final_body)

    def _fallback_post(self, news: NewsItem, config: AgentConfig) -> GeneratedPost:
        """Plain fallback when Gemini недоступен."""
        body_parts = [
            sanitize_html_for_telegram(news.raw_summary or news.raw_content or news.title),
        ]
        if config.include_source_link and news.url:
            body_parts.append(f'<a href="{news.url}">Подробнее</a>')
        if config.signature_html:
            body_parts.append(config.signature_html)
        body = "\n\n".join(part for part in body_parts if part)
        composed = self._compose_body(
            body,
            ["футбол"],
            config,
            allow_link=config.include_source_link,
            news_url=news.url,
        )
        return GeneratedPost(
            headline=news.title,
            lead=news.raw_summary or news.title,
            body_html=composed,
            hashtags=["футбол"],
            image_query="football",
            source_url=news.url,  # type: ignore[arg-type]
            should_post=True,
            reason_if_skip=None,
        )

    def _fallback_prediction(self, ctx: PredictionContext, config: AgentConfig) -> GeneratedPost:
        today = msk_now().strftime("%d.%m.%Y")
        lines = [
            f"🔥 Прогнозы на матчи {today}",
            "— Главные встречи дня, без ставок и агрессивных обещаний.",
            "— Оценка формы команд, травм и мотивации.",
            "",
            "⚽ Матч 1 — умеренное преимущество фаворита (~55–60%).",
            "⚽ Матч 2 — равная игра, велика вероятность ничьей.",
            "⚽ Матч 3 — возможна неожиданность из-за ротации или травм.",
            "",
            "Материалы носят редакторский характер, а не совет по ставкам.",
        ]
        body = sanitize_html_for_telegram("\n".join(lines))
        composed = self._compose_body(
            body,
            ["футбол", "прогноз", "матчи"],
            config,
            allow_link=False,
            news_url=ctx.url,
        )
        return GeneratedPost(
            headline=ctx.title,
            lead=ctx.summary,
            body_html=composed,
            hashtags=["футбол", "прогноз", "матчи"],
            image_query="football predictions",
            source_url=ctx.url,
            should_post=True,
            reason_if_skip=None,
        )

    def _reinforce_ru_prompt(self, prompt: str) -> str:
        hint = (
            "\n\nВСЕГДА отвечай только на русском языке. "
            "Если модель вернула английский текст — переведи и верни итог только на русском."
        )
        return prompt if hint in prompt else f"{prompt}{hint}"

    def _is_russian_text(self, text: str) -> bool:
        cyr = len(re.findall(r"[А-Яа-яЁё]", text))
        lat = len(re.findall(r"[A-Za-z]", text))
        if cyr == 0:
            return False
        if lat == 0:
            return True
        return cyr >= lat and cyr >= 5

    def _strip_source_lines(self, text: str) -> str:
        cleaned = re.sub(r"(?im)^\\s*источник[^\\n]*$", "", text or "")
        cleaned = re.sub(r"(?im)^\\s*source[^\\n]*$", "", cleaned)
        cleaned = re.sub(r"\\n{3,}", "\\n\\n", cleaned).strip()
        return cleaned

    async def _call_model(self, prompt: str, use_web_search: bool = False) -> str:
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
            kwargs: dict[str, Any] = {}
            if use_web_search:
                kwargs["tools"] = [{"google_search_retrieval": {}}]
            try:
                response = model.generate_content(prompt, **kwargs)
            except TypeError:
                response = model.generate_content(prompt)
            return response.text or ""

        return await asyncio.to_thread(_sync_call)
