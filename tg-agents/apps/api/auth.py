from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any

import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import get_settings
from .models import User


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def verify_password(password: str, password_hash: str) -> bool:
    candidate = hash_password(password)
    return hmac.compare_digest(candidate, password_hash)


def create_jwt(payload: dict[str, Any], expires_in_seconds: int = 3600) -> str:
    settings = get_settings()
    now = int(time.time())
    data = {"iat": now, "exp": now + expires_in_seconds, **payload}
    return jwt.encode(data, settings.encryption_key, algorithm="HS256")


async def seed_admin(session: AsyncSession) -> None:
    settings = get_settings()
    if not settings.admin_email or not settings.admin_password:
        return
    result = await session.execute(select(User).where(User.email == settings.admin_email))
    user = result.scalar_one_or_none()
    if user:
        return
    admin = User(
        email=settings.admin_email,
        password_hash=hash_password(settings.admin_password),
        is_admin=True,
    )
    session.add(admin)
    await session.commit()
