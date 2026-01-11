from __future__ import annotations

from enum import Enum
from functools import lru_cache

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class TelegramMode(str, Enum):
    BOT = "bot"
    USER = "user"


class FeatureFlags(BaseModel):
    telegram_mode: TelegramMode = Field(
        default=TelegramMode.BOT,
        description="Selects whether bot token or Telethon user mode is used.",
    )
    scheduler_enabled: bool = Field(default=True, description="Enable periodic news fetcher.")
    use_llm_for_summaries: bool = Field(default=True, description="Use Gemini to summarize news.")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NEWS_AGENT_", env_file=".env", extra="ignore")

    database_url: str = Field(default="postgresql+asyncpg://user:pass@localhost:5432/news_agent")
    gemini_api_key: str | None = Field(default=None)
    news_feed_url: str = Field(
        default="https://www.espn.com/espn/rss/soccer/news",
        description="RSS/JSON feed containing football news.",
    )
    scheduler_interval_seconds: int = Field(default=900, ge=60)
    telegram_bot_token: str | None = Field(default=None)
    telegram_api_id: int | None = Field(default=None)
    telegram_api_hash: str | None = Field(default=None)
    telegram_session_name: str = Field(default="telegram_user_session")
    telegram_login_phone: str | None = Field(default=None)
    post_queue_max_size: int = Field(default=200, ge=1)
    feature_flags: FeatureFlags = Field(default_factory=FeatureFlags)

    @property
    def telegram_mode(self) -> TelegramMode:
        return self.feature_flags.telegram_mode

    def ensure_telegram_credentials(self) -> None:
        if self.telegram_mode == TelegramMode.BOT:
            if not self.telegram_bot_token:
                msg = "telegram_bot_token обязателен в режиме bot"
                raise ValueError(msg)
        if self.telegram_mode == TelegramMode.USER:
            missing = [
                name
                for name, value in [
                    ("telegram_api_id", self.telegram_api_id),
                    ("telegram_api_hash", self.telegram_api_hash),
                ]
                if value in (None, "")
            ]
            if missing:
                msg = f"Отсутствуют ключи Telethon: {', '.join(missing)}"
                raise ValueError(msg)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
