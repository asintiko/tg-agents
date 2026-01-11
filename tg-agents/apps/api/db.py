from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import declarative_base

from .config import Settings, get_settings

naming_convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
metadata_obj = MetaData(naming_convention=naming_convention)
Base = declarative_base(metadata=metadata_obj)

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def init_engine(settings: Settings | None = None) -> AsyncEngine:
    global _engine
    settings = settings or get_settings()
    if _engine is None:
        _engine = create_async_engine(settings.database_url, future=True, echo=False)
    return _engine


def get_engine() -> AsyncEngine:
    return _engine or init_engine()


def init_sessionmaker(settings: Settings | None = None) -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            get_engine(), expire_on_commit=False, class_=AsyncSession
        )
    return _sessionmaker


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return _sessionmaker or init_sessionmaker()


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    session_maker = get_sessionmaker()
    async with session_maker() as session:
        yield session


async def dispose_engine() -> None:
    if _engine:
        await _engine.dispose()


async def init_models(settings: Settings | None = None) -> None:
    engine = init_engine(settings)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
