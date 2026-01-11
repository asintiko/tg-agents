from __future__ import annotations

from ..config import Settings, TelegramMode
from .telegram_client import BotTelegramClient, TelegramSender, UserTelegramClient


class TelegramDispatcher:
    def __init__(self, settings: Settings) -> None:
        self._bot_client: TelegramSender | None = None
        self._user_client: TelegramSender | None = None
        if settings.telegram_bot_token:
            self._bot_client = BotTelegramClient(settings.telegram_bot_token)
        if settings.telegram_api_id and settings.telegram_api_hash:
            self._user_client = UserTelegramClient(
                api_id=settings.telegram_api_id,
                api_hash=settings.telegram_api_hash,
                session_name=settings.telegram_session_name,
                login_phone=settings.telegram_login_phone,
            )

    async def send(self, mode: TelegramMode, chat_id: str, message: str) -> None:
        if mode == TelegramMode.BOT:
            if not self._bot_client:
                msg = "Запрошен bot-режим, но бот не настроен."
                raise RuntimeError(msg)
            await self._bot_client.send_message(chat_id=chat_id, message=message)
            return

        if mode == TelegramMode.USER:
            if not self._user_client:
                msg = "Запрошен user-режим, но Telethon клиент не настроен."
                raise RuntimeError(msg)
            await self._user_client.send_message(chat_id=chat_id, message=message)
            return

        msg = f"Неподдерживаемый режим Telegram: {mode}"
        raise RuntimeError(msg)

    async def close(self) -> None:
        if self._bot_client and hasattr(self._bot_client, "close"):
            await self._bot_client.close()
        if self._user_client and hasattr(self._user_client, "close"):
            await self._user_client.close()
