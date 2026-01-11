from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import relationship

from .config import TelegramMode
from .db import Base


class JobStatus(str, Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


class Channel(Base):
    __tablename__ = "channels"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    telegram_chat_id = Column(String(255), nullable=False, unique=True)
    mode = Column(SqlEnum(TelegramMode), nullable=False, default=TelegramMode.BOT)
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    jobs = relationship("PostJob", back_populates="channel", cascade="all, delete-orphan")


class Article(Base):
    __tablename__ = "articles"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(500), nullable=False)
    summary = Column(Text, nullable=True)
    url = Column(String(1000), nullable=False)
    source = Column(String(255), nullable=False, default="unknown")
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    jobs = relationship("PostJob", back_populates="article", cascade="all, delete-orphan")


class PostJob(Base):
    __tablename__ = "post_jobs"

    id = Column(Integer, primary_key=True, index=True)
    channel_id = Column(Integer, ForeignKey("channels.id"), nullable=False)
    article_id = Column(Integer, ForeignKey("articles.id"), nullable=False)
    status = Column(SqlEnum(JobStatus), nullable=False, default=JobStatus.PENDING)
    scheduled_for = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    tries = Column(Integer, nullable=False, default=0)
    post_content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    channel = relationship("Channel", back_populates="jobs")
    article = relationship("Article", back_populates="jobs")
