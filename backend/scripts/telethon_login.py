from __future__ import annotations

import asyncio
from pathlib import Path
import sys

from telethon import TelegramClient

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.config import TelegramMode, get_settings  # noqa: E402


async def main() -> None:
    settings = get_settings()
    if settings.telegram_mode != TelegramMode.USER:
        print("Set NEWS_AGENT_TELEGRAM_MODE=user to use Telethon login.")
        return
    if settings.telegram_api_id is None or settings.telegram_api_hash is None:
        print("Missing TELEGRAM API credentials. Update .env and retry.")
        return

    client = TelegramClient(
        settings.telegram_session_name, settings.telegram_api_id, settings.telegram_api_hash
    )
    await client.connect()
    if await client.is_user_authorized():
        print("User session already authorized.")
        await client.disconnect()
        return

    qr_login = await client.qr_login()
    print("Scan this QR URL with Telegram to authorize:\n", qr_login.url)
    await qr_login.wait()
    print("Authorization completed.")
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
