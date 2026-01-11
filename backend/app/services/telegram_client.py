from __future__ import annotations

from typing import Protocol

import httpx
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

from ..config import Settings, TelegramMode


class TelegramSender(Protocol):
    async def send_message(self, chat_id: str, message: str) -> None: ...


class BotTelegramClient(TelegramSender):
    def __init__(self, token: str, timeout: float = 10.0) -> None:
        self._token = token
        self._client = httpx.AsyncClient(timeout=timeout)

    async def send_message(self, chat_id: str, message: str) -> None:
        url = f"https://api.telegram.org/bot{self._token}/sendMessage"
        response = await self._client.post(url, json={"chat_id": chat_id, "text": message})
        if response.status_code != 200 or not response.json().get("ok", False):
            detail = response.text
            msg = f"Telegram Bot API вернул ошибку: {detail}"
            raise RuntimeError(msg)

    async def close(self) -> None:
        await self._client.aclose()


class UserTelegramClient(TelegramSender):
    def __init__(
        self,
        api_id: int,
        api_hash: str,
        session_name: str,
        login_phone: str | None,
    ) -> None:
        self._client = TelegramClient(session_name, api_id, api_hash)
        self._login_phone = login_phone

    async def _ensure_connected(self) -> None:
        if not self._client.is_connected():
            await self._client.connect()

        if not await self._client.is_user_authorized():
            if not self._login_phone:
                msg = "В режиме user требуется login_phone для первичного QR/логина."
                raise RuntimeError(msg)
            try:
                await self._client.send_code_request(self._login_phone)
            except SessionPasswordNeededError:
                msg = "Включена двухфакторная аутентификация — завершите вход вручную."
                raise RuntimeError(msg) from None
            raise RuntimeError(
                "Пользовательская сессия не авторизована. Запустите помощник Telethon для входа по QR/коду."
            )

    async def send_message(self, chat_id: str, message: str) -> None:
        await self._ensure_connected()
        await self._client.send_message(entity=chat_id, message=message)

    async def close(self) -> None:
        await self._client.disconnect()


def build_telegram_client(settings: Settings) -> TelegramSender:
    if settings.telegram_mode == TelegramMode.BOT:
        if not settings.telegram_bot_token:
            msg = "telegram_bot_token обязателен в режиме bot"
            raise ValueError(msg)
        return BotTelegramClient(settings.telegram_bot_token)

    if settings.telegram_mode == TelegramMode.USER:
        if settings.telegram_api_id is None or settings.telegram_api_hash is None:
            msg = "telethon api_id/api_hash обязательны в режиме user"
            raise ValueError(msg)
        return UserTelegramClient(
            api_id=settings.telegram_api_id,
            api_hash=settings.telegram_api_hash,
            session_name=settings.telegram_session_name,
            login_phone=settings.telegram_login_phone,
        )

    msg = f"Неизвестный режим telegram: {settings.telegram_mode}"
    raise ValueError(msg)
