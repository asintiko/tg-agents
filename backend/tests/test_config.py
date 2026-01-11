from __future__ import annotations

import pytest

from app.config import Settings, TelegramMode


def test_bot_mode_requires_token() -> None:
    settings = Settings(feature_flags={"telegram_mode": TelegramMode.BOT}, telegram_bot_token=None)
    with pytest.raises(ValueError):
        settings.ensure_telegram_credentials()


def test_user_mode_requires_telethon_keys() -> None:
    settings = Settings(feature_flags={"telegram_mode": TelegramMode.USER})
    with pytest.raises(ValueError):
        settings.ensure_telegram_credentials()


def test_user_mode_accepts_keys() -> None:
    settings = Settings(
        feature_flags={"telegram_mode": TelegramMode.USER},
        telegram_api_id=1234,
        telegram_api_hash="hash",
        telegram_login_phone="+10000000000",
    )
    settings.ensure_telegram_credentials()
