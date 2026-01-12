from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from telethon import TelegramClient
from telethon.errors import (
    AuthKeyUnregisteredError,
    PasswordHashInvalidError,
    SessionPasswordNeededError,
)

from apps.api.config import Settings, get_settings
from apps.api.time_utils import msk_now

SESSION_FILENAME = "account.session"
STATUS_FILENAME = "status.json"


@dataclass(slots=True)
class PendingLogin:
    client: TelegramClient
    qr_login: Any
    session_path: str
    awaiting_password: bool = False


@dataclass(slots=True)
class PendingPhone:
    client: TelegramClient
    phone: str
    code_hash: str
    awaiting_password: bool = False


_pending: PendingLogin | None = None
_pending_phone: PendingPhone | None = None


def _ensure_creds(settings: Settings) -> None:
    if settings.telethon_api_id is None or settings.telethon_api_hash is None:
        msg = "TELETHON_API_ID или TELETHON_API_HASH не заданы в окружении"
        raise ValueError(msg)


def _session_dir(settings: Settings) -> Path:
    base = Path(settings.app_data_dir) / "telethon"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _session_path(settings: Settings) -> str:
    return str(_session_dir(settings) / SESSION_FILENAME)


def _status_path(settings: Settings) -> Path:
    return _session_dir(settings) / STATUS_FILENAME


def _build_client(settings: Settings) -> TelegramClient:
    _ensure_creds(settings)
    return TelegramClient(_session_path(settings), settings.telethon_api_id, settings.telethon_api_hash)


def _serialize_me(me: Any) -> dict[str, Any]:
    return {
        "id": getattr(me, "id", None),
        "username": getattr(me, "username", None),
        "phone": getattr(me, "phone", None),
    }


def _write_status(settings: Settings, status: str, me: Any | None = None) -> None:
    payload = {
        "status": status,
        "last_connected_at": None,
        "me": None,
    }
    if status == "connected" and me is not None:
        payload["last_connected_at"] = msk_now().isoformat()
        payload["me"] = _serialize_me(me)
    _status_path(settings).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _read_status(settings: Settings) -> dict[str, Any]:
    path = _status_path(settings)
    if not path.exists():
        return {"status": "disconnected", "last_connected_at": None, "me": None}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"status": "disconnected", "last_connected_at": None, "me": None}


async def start_qr_login(settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    _ensure_creds(settings)
    global _pending
    global _pending_phone
    if _pending:
        try:
            await _pending.client.disconnect()
        except Exception:
            pass
        _pending = None
    if _pending_phone:
        try:
            await _pending_phone.client.disconnect()
        except Exception:
            pass
        _pending_phone = None
    client = _build_client(settings)
    await client.connect()
    if await client.is_user_authorized():
        me = await client.get_me()
        await client.disconnect()
        _write_status(settings, "connected", me)
        return {"status": "connected", "me": _serialize_me(me)}

    qr_login = await client.qr_login()
    _pending = PendingLogin(client=client, qr_login=qr_login, session_path=_session_path(settings))
    _write_status(settings, "waiting_for_scan")
    return {"status": "waiting_for_scan", "qr_url": qr_login.url}


async def wait_for_qr(settings: Settings | None = None) -> dict[str, Any]:
    global _pending
    settings = settings or get_settings()
    if not _pending:
        raise ValueError("QR-код не запущен или уже истёк, запустите сканирование заново")
    try:
        await _pending.qr_login.wait()
        me = await _pending.client.get_me()
        await _pending.client.disconnect()
        _write_status(settings, "connected", me)
        return {"status": "connected", "me": _serialize_me(me)}
    except SessionPasswordNeededError:
        _pending.awaiting_password = True
        _write_status(settings, "password_required")
        return {"status": "password_required"}
    except Exception as exc:  # noqa: BLE001
        await _pending.client.disconnect()
        _write_status(settings, "disconnected")
        raise ValueError(f"QR устарел или недействителен, запустите заново ({exc})") from exc
    finally:
        if _pending and not _pending.awaiting_password:
            _pending = None


async def start_phone_login(phone: str, settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    _ensure_creds(settings)
    global _pending
    global _pending_phone
    # Сброс любых старых сессий ожидания.
    if _pending:
        try:
            await _pending.client.disconnect()
        except Exception:
            pass
        _pending = None
    if _pending_phone:
        try:
            await _pending_phone.client.disconnect()
        except Exception:
            pass
        _pending_phone = None

    client = _build_client(settings)
    await client.connect()
    if await client.is_user_authorized():
        me = await client.get_me()
        await client.disconnect()
        _write_status(settings, "connected", me)
        return {"status": "connected", "me": _serialize_me(me)}

    sent = await client.send_code_request(phone)
    _pending_phone = PendingPhone(
        client=client,
        phone=phone,
        code_hash=getattr(sent, "phone_code_hash", None) or "",
    )
    _write_status(settings, "waiting_for_code")
    return {"status": "waiting_for_code"}


async def provide_phone_code(code: str, settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    global _pending_phone
    if not _pending_phone:
        raise ValueError("Код не ожидается, запустите вход по номеру заново")
    try:
        await _pending_phone.client.sign_in(code=code)
        me = await _pending_phone.client.get_me()
        _write_status(settings, "connected", me)
        return {"status": "connected", "me": _serialize_me(me)}
    except SessionPasswordNeededError:
        _pending_phone.awaiting_password = True
        _write_status(settings, "password_required")
        return {"status": "password_required"}
    except Exception as exc:  # noqa: BLE001
        await _pending_phone.client.disconnect()
        _pending_phone = None
        _write_status(settings, "disconnected")
        raise ValueError(f"Не удалось войти по коду: {exc}") from exc
    finally:
        if _pending_phone and not _pending_phone.awaiting_password:
            await _pending_phone.client.disconnect()
            _pending_phone = None


async def provide_password(password: str, settings: Settings | None = None) -> dict[str, Any]:
    global _pending
    global _pending_phone
    settings = settings or get_settings()
    if not ((_pending and _pending.awaiting_password) or (_pending_phone and _pending_phone.awaiting_password)):
        raise ValueError("Текущая сессия не ждёт пароль, перезапустите вход")
    try:
        if _pending and _pending.awaiting_password:
            await _pending.client.sign_in(password=password)
            me = await _pending.client.get_me()
            _write_status(settings, "connected", me)
            return {"status": "connected", "me": _serialize_me(me)}
        if _pending_phone and _pending_phone.awaiting_password:
            await _pending_phone.client.sign_in(password=password)
            me = await _pending_phone.client.get_me()
            _write_status(settings, "connected", me)
            return {"status": "connected", "me": _serialize_me(me)}
        raise ValueError("Текущая сессия не ждёт пароль, перезапустите вход")
    except PasswordHashInvalidError as exc:
        raise ValueError("Неверный пароль 2FA") from exc
    except SessionPasswordNeededError as exc:
        raise ValueError("Требуется пароль 2FA") from exc
    except Exception as exc:  # noqa: BLE001
        raise ValueError("Не удалось завершить вход, перезапустите QR") from exc
    finally:
        if _pending:
            try:
                await _pending.client.disconnect()
            except Exception:
                pass
            _pending = None
        if _pending_phone:
            try:
                await _pending_phone.client.disconnect()
            except Exception:
                pass
            _pending_phone = None


def parse_entity(chat_id: str) -> int | str:
    """Возвращает int для числовых chat_id (включая отрицательные), иначе исходную строку."""
    chat_id = chat_id.strip()
    if chat_id and chat_id.lstrip("-").isdigit():
        try:
            return int(chat_id)
        except ValueError:
            return chat_id
    return chat_id


async def send_user_message(
    project_id: int,
    chat_ids: list[str],
    text: str,
    image_path: str | None = None,
    link_preview: bool | None = None,
    settings: Settings | None = None,
) -> list[str]:
    settings = settings or get_settings()
    client = _build_client(settings)
    await client.connect()
    try:
        tasks: list[asyncio.Future[Any]] = []
        for chat_id in chat_ids:
            entity = parse_entity(chat_id)
            if image_path:
                tasks.append(
                    asyncio.create_task(
                        client.send_file(entity, image_path, caption=text, parse_mode="html")
                    )
                )
            else:
                kwargs: dict[str, Any] = {"parse_mode": "html"}
                if link_preview is not None:
                    kwargs["link_preview"] = link_preview
                tasks.append(asyncio.create_task(client.send_message(entity, text, **kwargs)))
        results = await asyncio.gather(*tasks)
        ids: list[str] = []
        for res in results:
            msg_id = getattr(res, "id", None)
            if msg_id is not None:
                ids.append(str(msg_id))
        return ids
    finally:
        await client.disconnect()


async def telegram_status(settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    status = _read_status(settings)
    if _pending and status["status"] in {"waiting_for_scan", "password_required"}:
        return status

    if status.get("status") == "connected":
        client = _build_client(settings)
        try:
            await client.connect()
            if not await client.is_user_authorized():
                _write_status(settings, "disconnected")
                return {
                    "status": "disconnected",
                    "last_connected_at": status.get("last_connected_at"),
                    "me": None,
                }
            me = await client.get_me()
            _write_status(settings, "connected", me)
            return {
                "status": "connected",
                "last_connected_at": status.get("last_connected_at"),
                "me": _serialize_me(me),
            }
        except AuthKeyUnregisteredError:
            _write_status(settings, "disconnected")
            return {
                "status": "disconnected",
                "last_connected_at": status.get("last_connected_at"),
                "me": None,
            }
        finally:
            await client.disconnect()

    return status


def get_session_path(settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    return _session_path(settings)


def reset_session(settings: Settings | None = None) -> None:
    """Удаляет Telethon-сессию и сбрасывает статус."""
    global _pending
    settings = settings or get_settings()
    _pending = None
    session_file = Path(_session_path(settings))
    status_file = _status_path(settings)
    if session_file.exists():
        try:
            session_file.unlink()
        except FileNotFoundError:
            pass
    if status_file.exists():
        try:
            status_file.unlink()
        except FileNotFoundError:
            pass


async def list_user_channels(settings: Settings | None = None) -> list[dict[str, Any]]:
    settings = settings or get_settings()
    client = _build_client(settings)
    await client.connect()
    try:
        if not await client.is_user_authorized():
            raise ValueError("Аккаунт не подключён, сначала авторизуйтесь по QR")
        channels: list[dict[str, Any]] = []
        async for dialog in client.iter_dialogs():
            if not dialog.is_channel:
                continue
            entity = dialog.entity
            can_post = bool(getattr(entity, "creator", False))
            rights = getattr(entity, "admin_rights", None)
            if rights:
                can_post = can_post or bool(getattr(rights, "post_messages", False)) or bool(
                    getattr(rights, "edit_messages", False)
                )
            if not can_post:
                continue
            channels.append(
                {
                    "tg_chat_id": str(dialog.id),
                    "title": dialog.name,
                    "username": getattr(entity, "username", None),
                }
            )
        return channels
    finally:
        await client.disconnect()
