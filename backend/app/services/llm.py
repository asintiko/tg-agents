from __future__ import annotations

import asyncio

import google.generativeai as genai


class GeminiClient:
    def __init__(self, api_key: str | None) -> None:
        self._api_key = api_key
        self._model = None
        if api_key:
            genai.configure(api_key=api_key)
            self._model = genai.GenerativeModel("gemini-pro")

    async def summarize(self, text: str, max_tokens: int = 180) -> str:
        if not text:
            return ""
        if self._model is None:
            return self._fallback_summary(text, max_tokens)

        def _sync_call() -> str:
            response = self._model.generate_content(
                f"Summarize this football news in 3 sentences for Telegram:\n{text}"
            )
            return response.text or self._fallback_summary(text, max_tokens)

        return await asyncio.to_thread(_sync_call)

    def _fallback_summary(self, text: str, max_tokens: int) -> str:
        shortened = text.strip()
        if len(shortened) <= max_tokens:
            return shortened
        return shortened[: max_tokens - 3] + "..."
