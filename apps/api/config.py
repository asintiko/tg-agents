from __future__ import annotations

from functools import lru_cache

from cryptography.fernet import Fernet
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_prefix="", extra="ignore", env_ignore_empty=True
    )

    database_url: str = Field(default="sqlite+aiosqlite:///./tg_agents.db")
    redis_url: str = Field(default="redis://localhost:6379/0")
    gemini_api_key: str | None = None
    telethon_api_id: int | None = None
    telethon_api_hash: str | None = None
    encryption_key: str = Field(default_factory=lambda: Fernet.generate_key().decode())
    admin_password: str | None = None
    app_data_dir: str = Field(default="./data")
    admin_token_ttl_seconds: int = Field(default=86400)  # 24 часа по умолчанию

    def fernet(self) -> Fernet:
        return Fernet(self.encryption_key)

    def encrypt(self, value: str) -> str:
        return self.fernet().encrypt(value.encode("utf-8")).decode("utf-8")

    def decrypt(self, value: str) -> str:
        return self.fernet().decrypt(value.encode("utf-8")).decode("utf-8")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
