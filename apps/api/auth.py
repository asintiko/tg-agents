from __future__ import annotations

import hmac
import time
from typing import Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import get_settings

bearer_scheme = HTTPBearer(auto_error=False)


def create_jwt(payload: dict[str, Any], expires_in_seconds: int = 3600) -> str:
    settings = get_settings()
    now = int(time.time())
    data = {"iat": now, "exp": now + expires_in_seconds, **payload}
    return jwt.encode(data, settings.encryption_key, algorithm="HS256")


def verify_admin_password(password: str) -> bool:
    settings = get_settings()
    if settings.admin_password is None:
        return False
    return hmac.compare_digest(password, settings.admin_password)


def issue_admin_token() -> str:
    return create_jwt({"sub": "admin"})


def require_admin(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> None:
    settings = get_settings()
    if not settings.admin_password:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ADMIN_PASSWORD не задан в окружении",
        )
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Требуется авторизация"
        )
    try:
        payload = jwt.decode(
            credentials.credentials, settings.encryption_key, algorithms=["HS256"]
        )
    except jwt.InvalidTokenError as exc:  # type: ignore[attr-defined]
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный токен"
        ) from exc
    if payload.get("sub") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Доступ запрещен"
        )
