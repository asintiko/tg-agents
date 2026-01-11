from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

from apps.api.config import Settings, get_settings


@dataclass(slots=True)
class PendingLogin:
    client: TelegramClient
    qr_login: Any
    session_path: str


_pending: dict[int, PendingLogin] = {}


def _session_path(project_id: int, settings: Settings) -> str:
    base = Path(settings.app_data_dir) / "telethon"
    base.mkdir(parents=True, exist_ok=True)
    return str(base / f"{project_id}.session")


def _build_client(project_id: int, settings: Settings) -> TelegramClient:
    if settings.telethon_api_id is None or settings.telethon_api_hash is None:
        msg = "Не заданы параметры Telethon API"
        raise ValueError(msg)
    session_path = _session_path(project_id, settings)
    return TelegramClient(session_path, settings.telethon_api_id, settings.telethon_api_hash)


async def start_qr_login(project_id: int, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    client = _build_client(project_id, settings)
    await client.connect()
    qr_login = await client.qr_login()
    _pending[project_id] = PendingLogin(
        client=client, qr_login=qr_login, session_path=_session_path(project_id, settings)
    )
    return qr_login.url


async def wait_for_qr(project_id: int) -> dict[str, bool]:
    pending = _pending.get(project_id)
    if not pending:
        raise ValueError("Нет ожидающей QR-сессии")
    try:
        await pending.qr_login.wait()
        await pending.client.disconnect()
        _pending.pop(project_id, None)
        return {"connected": True, "needs_password": False}
    except SessionPasswordNeededError:
        return {"connected": False, "needs_password": True}


async def provide_password(project_id: int, password: str) -> None:
    pending = _pending.get(project_id)
    if not pending:
        raise ValueError("Нет ожидающей QR-сессии")
    await pending.client.sign_in(password=password)
    await pending.client.disconnect()
    _pending.pop(project_id, None)


async def send_user_message(
    project_id: int,
    chat_ids: list[str],
    text: str,
    image_path: str | None = None,
    settings: Settings | None = None,
) -> None:
    settings = settings or get_settings()
    client = _build_client(project_id, settings)
    await client.connect()
    try:
        tasks: list[asyncio.Future[Any]] = []
        for chat_id in chat_ids:
            if image_path:
                tasks.append(
                    asyncio.create_task(
                        client.send_file(chat_id, image_path, caption=text, parse_mode="html")
                    )
                )
            else:
                tasks.append(
                    asyncio.create_task(client.send_message(chat_id, text, parse_mode="html"))
                )
        await asyncio.gather(*tasks)
    finally:
        await client.disconnect()
