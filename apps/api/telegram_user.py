from __future__ import annotations

import asyncio
import base64
import json
from dataclasses import dataclass
import re
from pathlib import Path
from typing import Any

from telethon import TelegramClient
from telethon.errors import (
    AuthKeyUnregisteredError,
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    PasswordHashInvalidError,
    SessionPasswordNeededError,
)
from telethon.extensions import html as telethon_html
from telethon.tl.types import MessageEntityCustomEmoji, TypeMessageEntity

from apps.api.config import Settings, get_settings
from apps.api.time_utils import msk_now

SESSION_FILENAME = "account.session"
STATUS_FILENAME = "status.json"
_telethon_lock = asyncio.Lock()


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
        "first_name": getattr(me, "first_name", None),
        "last_name": getattr(me, "last_name", None),
    }


async def _download_photo_b64(client: TelegramClient, me: Any) -> str | None:
    try:
        file = await client.download_profile_photo(me, bytes)
    except Exception:
        return None
    if not file:
        return None
    return f"data:image/jpeg;base64,{base64.b64encode(file).decode('utf-8')}"


def _write_status(settings: Settings, status: str, me: Any | None = None, photo_b64: str | None = None) -> None:
    payload = {
        "status": status,
        "last_connected_at": None,
        "me": None,
        "me_photo_b64": photo_b64,
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
    async with _telethon_lock:
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
            photo_b64 = await _download_photo_b64(client, me)
            await client.disconnect()
            _write_status(settings, "connected", me, photo_b64)
            return {"status": "connected", "me": _serialize_me(me), "me_photo_b64": photo_b64}

        qr_login = await client.qr_login()
        _pending = PendingLogin(client=client, qr_login=qr_login, session_path=_session_path(settings))
        _write_status(settings, "waiting_for_scan")
        return {"status": "waiting_for_scan", "qr_url": qr_login.url}


async def wait_for_qr(settings: Settings | None = None) -> dict[str, Any]:
    global _pending
    settings = settings or get_settings()
    if not _pending:
        raise ValueError("QR-код не запущен или уже истёк, запустите сканирование заново")
    async with _telethon_lock:
        try:
            await _pending.qr_login.wait()
            me = await _pending.client.get_me()
            photo_b64 = await _download_photo_b64(_pending.client, me)
            await _pending.client.disconnect()
            _write_status(settings, "connected", me, photo_b64)
            return {"status": "connected", "me": _serialize_me(me), "me_photo_b64": photo_b64}
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
    phone = phone.strip()
    if not phone:
        raise ValueError("Укажите номер телефона в международном формате")
    _ensure_creds(settings)
    async with _telethon_lock:
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

        try:
            sent = await client.send_code_request(phone)
        except Exception:
            await client.disconnect()
            raise
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
    async with _telethon_lock:
        try:
            if not _pending_phone.client.is_connected():
                await _pending_phone.client.connect()
            await _pending_phone.client.sign_in(
                phone=_pending_phone.phone,
                code=code,
                phone_code_hash=_pending_phone.code_hash or None,
            )
            me = await _pending_phone.client.get_me()
            photo_b64 = await _download_photo_b64(_pending_phone.client, me)
            _write_status(settings, "connected", me, photo_b64)
            return {"status": "connected", "me": _serialize_me(me), "me_photo_b64": photo_b64}
        except SessionPasswordNeededError:
            _pending_phone.awaiting_password = True
            _write_status(settings, "password_required")
            return {"status": "password_required"}
        except PhoneCodeInvalidError as exc:
            await _pending_phone.client.disconnect()
            _pending_phone = None
            _write_status(settings, "disconnected")
            raise ValueError("Неверный код из Telegram, запросите новый.") from exc
        except PhoneCodeExpiredError as exc:
            await _pending_phone.client.disconnect()
            _pending_phone = None
            _write_status(settings, "disconnected")
            raise ValueError("Срок действия кода истёк, отправьте запрос ещё раз.") from exc
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
    async with _telethon_lock:
        try:
            if _pending and _pending.awaiting_password:
                if not _pending.client.is_connected():
                    await _pending.client.connect()
                await _pending.client.sign_in(password=password)
                me = await _pending.client.get_me()
                photo_b64 = await _download_photo_b64(_pending.client, me)
                _write_status(settings, "connected", me, photo_b64)
                return {"status": "connected", "me": _serialize_me(me), "me_photo_b64": photo_b64}
            if _pending_phone and _pending_phone.awaiting_password:
                if not _pending_phone.client.is_connected():
                    await _pending_phone.client.connect()
                await _pending_phone.client.sign_in(password=password)
                me = await _pending_phone.client.get_me()
                photo_b64 = await _download_photo_b64(_pending_phone.client, me)
                _write_status(settings, "connected", me, photo_b64)
                return {"status": "connected", "me": _serialize_me(me), "me_photo_b64": photo_b64}
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


def parse_custom_emoji_id(raw: str | None) -> int | None:
    """Извлекает numeric ID из tg://emoji?id=... или строки с числом."""
    if not raw:
        return None
    match = re.search(r"(?:id=)?(\d+)", raw)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _build_message_with_premium(
    html_text: str,
    premium_emoji_id: int | None,
    fallback_char: str | None,
) -> tuple[str, list[TypeMessageEntity]]:
    text, entities = telethon_html.parse(html_text or "")
    prefix = (fallback_char or "").strip()
    custom_entities: list[TypeMessageEntity] = []
    if premium_emoji_id is not None:
        prefix = prefix or "⚡"
        try:
            custom_entities.append(
                MessageEntityCustomEmoji(offset=0, length=len(prefix), document_id=premium_emoji_id)
            )
        except Exception:
            custom_entities = []
    if prefix:
        spacer = " " if text else ""
        text = f"{prefix}{spacer}{text}" if text else prefix
        shift = len(prefix) + (1 if spacer else 0)
        for ent in entities:
            ent.offset += shift
    if custom_entities:
        entities = custom_entities + list(entities)
    return text, list(entities)


async def send_user_message(
    project_id: int,
    chat_ids: list[str],
    text: str,
    image_path: str | None = None,
    link_preview: bool | None = None,
    brand_emoji_id: int | str | None = None,
    brand_emoji_fallback: str | None = None,
    premium_emoji_id: int | str | None = None,
    premium_emoji_fallback: str | None = None,
    settings: Settings | None = None,
) -> list[str]:
    settings = settings or get_settings()
    async with _telethon_lock:
        client = _build_client(settings)
        await client.connect()
        try:
            raw_emoji = brand_emoji_id if brand_emoji_id is not None else premium_emoji_id
            emoji_id = parse_custom_emoji_id(str(raw_emoji) if raw_emoji is not None else None)
            message_text, entities = _build_message_with_premium(
                text,
                emoji_id,
                (brand_emoji_fallback or premium_emoji_fallback) or ("⚡" if emoji_id else ""),
            )
            tasks: list[asyncio.Future[Any]] = []
            for chat_id in chat_ids:
                entity = parse_entity(chat_id)
                if image_path:
                    tasks.append(
                        asyncio.create_task(
                            client.send_file(
                                entity,
                                image_path,
                                caption=message_text,
                                parse_mode=None,
                                caption_entities=entities,
                            )
                        )
                    )
                else:
                    kwargs: dict[str, Any] = {
                        "parse_mode": None,
                        "formatting_entities": entities,
                    }
                    if link_preview is not None:
                        kwargs["link_preview"] = link_preview
                    tasks.append(
                        asyncio.create_task(client.send_message(entity, message_text, **kwargs))
                    )
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
        async with _telethon_lock:
            client = _build_client(settings)
            try:
                await client.connect()
                if not await client.is_user_authorized():
                    _write_status(settings, "disconnected")
                    return {
                        "status": "disconnected",
                        "last_connected_at": status.get("last_connected_at"),
                        "me": None,
                        "me_photo_b64": None,
                    }
                me = await client.get_me()
                photo_b64 = await _download_photo_b64(client, me)
                _write_status(settings, "connected", me, photo_b64)
                return {
                    "status": "connected",
                    "last_connected_at": status.get("last_connected_at"),
                    "me": _serialize_me(me),
                    "me_photo_b64": photo_b64,
                }
            except AuthKeyUnregisteredError:
                _write_status(settings, "disconnected")
                return {
                    "status": "disconnected",
                    "last_connected_at": status.get("last_connected_at"),
                    "me": None,
                    "me_photo_b64": None,
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
    async with _telethon_lock:
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
                role = "creator" if getattr(entity, "creator", False) else ("admin" if rights else "member")
                channels.append(
                    {
                        "tg_chat_id": str(dialog.id),
                        "title": dialog.name,
                        "username": getattr(entity, "username", None),
                        "can_post": can_post,
                        "role": role,
                    }
                )
            return channels
        finally:
            await client.disconnect()
