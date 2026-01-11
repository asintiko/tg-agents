from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, HttpUrl

from .config import TelegramMode
from .models import JobStatus


class ChannelCreate(BaseModel):
    title: str
    telegram_chat_id: str
    mode: TelegramMode = Field(default=TelegramMode.BOT)
    active: bool = Field(default=True)


class ChannelOut(ChannelCreate):
    id: int
    created_at: datetime

    model_config = {"from_attributes": True}


class ArticleCreate(BaseModel):
    title: str
    summary: str | None = None
    url: HttpUrl
    source: str = "unknown"


class ArticleOut(ArticleCreate):
    id: int
    created_at: datetime

    model_config = {"from_attributes": True}


class PostJobCreate(BaseModel):
    channel_id: int
    article_id: int
    post_content: str
    scheduled_for: datetime | None = None


class PostJobOut(PostJobCreate):
    id: int
    status: JobStatus
    tries: int
    created_at: datetime

    model_config = {"from_attributes": True}
