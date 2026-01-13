from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    event,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base
from .time_utils import to_utc


class Niche(str, enum.Enum):
    FOOTBALL = "football"
    OTHER = "other"


class EmojiMode(str, enum.Enum):
    OFF = "off"
    BASIC = "basic"
    PREMIUM = "premium"


class ImageMode(str, enum.Enum):
    WIKIMEDIA = "wikimedia"
    OG_IMAGE = "og_image"
    LINK_PREVIEW = "link_preview"


class ConnectionStatus(str, enum.Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"


class PostStatus(str, enum.Enum):
    PLANNED = "planned"
    GENERATED = "generated"
    PUBLISHED = "published"
    SKIPPED = "skipped"
    FAILED = "failed"


def enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    return [member.value for member in enum_cls]


class Heartbeat(Base):
    __tablename__ = "heartbeat"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    note: Mapped[str] = mapped_column(String(255), default="init", nullable=False)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    niche: Mapped[Niche] = mapped_column(
        Enum(Niche, values_callable=enum_values, name="niche"),
        default=Niche.FOOTBALL,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    agent_config = relationship("AgentConfig", back_populates="project", uselist=False)
    feed_sources = relationship("FeedSource", back_populates="project", cascade="all, delete")
    news_items = relationship("NewsItem", back_populates="project", cascade="all, delete")
    posts = relationship("Post", back_populates="project", cascade="all, delete")
    telegram_connections = relationship(
        "TelegramConnection", back_populates="project", cascade="all, delete"
    )
    channels = relationship("TelegramChannel", back_populates="project", cascade="all, delete")


class AgentConfig(Base):
    __tablename__ = "agent_configs"
    __table_args__ = (UniqueConstraint("project_id", name="uq_agent_config_project"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    posts_per_day: Mapped[int] = mapped_column(Integer, nullable=False)
    window_start: Mapped[str] = mapped_column(String(5), nullable=False)  # HH:MM
    window_end: Mapped[str] = mapped_column(String(5), nullable=False)
    min_interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    language: Mapped[str] = mapped_column(String(8), default="ru", nullable=False)
    tone: Mapped[str] = mapped_column(String(32), default="neutral", nullable=False)
    signature_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    emoji_mode: Mapped[EmojiMode] = mapped_column(
        Enum(EmojiMode, values_callable=enum_values, name="emojimode"),
        default=EmojiMode.OFF,
    )
    brand_emoji_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    brand_emoji_fallback: Mapped[str | None] = mapped_column(String(16), default="⚽", nullable=True)
    premium_emoji_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    premium_emoji_fallback: Mapped[str | None] = mapped_column(String(16), default="⚡", nullable=True)
    include_source_link: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    image_mode: Mapped[ImageMode] = mapped_column(
        Enum(ImageMode, values_callable=enum_values, name="imagemode"),
        default=ImageMode.WIKIMEDIA,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    project = relationship("Project", back_populates="agent_config")


class FeedSource(Base):
    __tablename__ = "feed_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    weight: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    project = relationship("Project", back_populates="feed_sources")
    news_items = relationship("NewsItem", back_populates="source")


class TelegramConnection(Base):
    __tablename__ = "telegram_connections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    telethon_session_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[ConnectionStatus] = mapped_column(
        Enum(ConnectionStatus, values_callable=enum_values, name="connectionstatus"),
        default=ConnectionStatus.DISCONNECTED,
        nullable=False,
    )
    last_connected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    project = relationship("Project", back_populates="telegram_connections")


class TelegramChannel(Base):
    __tablename__ = "telegram_channels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    tg_chat_id: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    project = relationship("Project", back_populates="channels")


class NewsItem(Base):
    __tablename__ = "news_items"
    __table_args__ = (
        UniqueConstraint("project_id", "hash", name="uq_news_item_project_hash"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    source_id: Mapped[int | None] = mapped_column(
        ForeignKey("feed_sources.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    raw_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    project = relationship("Project", back_populates="news_items")
    source = relationship("FeedSource", back_populates="news_items")
    posts = relationship("Post", back_populates="news_item")


class Post(Base):
    __tablename__ = "posts"
    __table_args__ = (
        Index("ix_posts_project_planned", "project_id", "planned_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    news_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("news_items.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[PostStatus] = mapped_column(
        Enum(PostStatus, values_callable=enum_values, name="poststatus"),
        default=PostStatus.PLANNED,
    )
    planned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    tg_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payload_json = Column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    project = relationship("Project", back_populates="posts")
    news_item = relationship("NewsItem", back_populates="posts")


class ImageCache(Base):
    __tablename__ = "image_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    query_hash: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    image_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


def _normalize_dt(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return to_utc(dt)


@event.listens_for(Post, "before_insert", propagate=True)
def _post_before_insert(_: object, __: object, target: Post) -> None:
    target.planned_at = _normalize_dt(target.planned_at)
    target.published_at = _normalize_dt(target.published_at)


@event.listens_for(Post, "before_update", propagate=True)
def _post_before_update(_: object, __: object, target: Post) -> None:
    target.planned_at = _normalize_dt(target.planned_at)
    target.published_at = _normalize_dt(target.published_at)
