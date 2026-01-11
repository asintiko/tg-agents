from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, HttpUrl

from .models import (
    ConnectionStatus,
    EmojiMode,
    ImageMode,
    Niche,
    PostStatus,
    TelegramMode,
)


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ProjectCreate(BaseModel):
    name: str
    niche: Niche = Niche.FOOTBALL


class ProjectOut(ProjectCreate):
    id: int
    created_at: datetime

    model_config = {"from_attributes": True}


class AgentConfigUpdate(BaseModel):
    posts_per_day: int
    window_start: str
    window_end: str
    min_interval_minutes: int
    language: str = Field(default="ru")
    tone: str = Field(default="neutral")
    signature_html: str | None = None
    emoji_mode: EmojiMode = EmojiMode.OFF
    include_source_link: bool = True
    image_mode: ImageMode = ImageMode.WIKIMEDIA


class AgentConfigOut(AgentConfigUpdate):
    project_id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class FeedSourceCreate(BaseModel):
    name: str
    url: HttpUrl
    enabled: bool = True
    weight: int = 10


class FeedSourceOut(FeedSourceCreate):
    id: int
    project_id: int
    created_at: datetime

    model_config = {"from_attributes": True}


class NewsItemOut(BaseModel):
    id: int
    project_id: int
    source_id: int
    title: str
    url: str
    published_at: datetime | None
    raw_summary: str | None
    raw_content: str | None
    hash: str
    created_at: datetime

    model_config = {"from_attributes": True}


class PostOut(BaseModel):
    id: int
    project_id: int
    news_item_id: int | None
    status: PostStatus
    planned_at: datetime
    published_at: datetime | None
    tg_message_id: str | None
    payload_json: dict | list | str | int | float | bool | None = None
    error: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TelegramConnectionOut(BaseModel):
    id: int
    project_id: int
    mode: TelegramMode
    status: ConnectionStatus
    last_connected_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TelegramChannelOut(BaseModel):
    id: int
    project_id: int
    tg_chat_id: str
    title: str
    username: str | None
    enabled: bool

    model_config = {"from_attributes": True}


class BotConnectRequest(BaseModel):
    bot_token: str


class TestMessageRequest(BaseModel):
    text: str = "Test message"
    image_path: str | None = None


class TelegramStatusOut(BaseModel):
    mode: TelegramMode | None
    status: ConnectionStatus | None
    channels: int


class TelegramChannelCreate(BaseModel):
    tg_chat_id: str
    title: str
    username: str | None = None
    enabled: bool = True


class TelegramChannelUpdate(BaseModel):
    title: str | None = None
    username: str | None = None
    enabled: bool | None = None
