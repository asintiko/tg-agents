from __future__ import annotations

import datetime as dt
import random
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from apps.api import main
from apps.api.config import get_settings
from apps.api.db import get_sessionmaker, init_engine, init_models, init_sessionmaker
from apps.api.models import AgentConfig, Post, PostStatus, Project
from apps.worker.planner import PostPlanner


async def setup_db() -> None:
    settings = get_settings()
    settings.database_url = "sqlite+aiosqlite:///:memory:"
    settings.admin_password = "secret"
    init_engine(settings)
    init_sessionmaker(settings)
    await init_models(settings)


@pytest.mark.asyncio
async def test_generate_times_within_window_and_min_interval() -> None:
    await setup_db()
    session_maker = get_sessionmaker()
    planner = PostPlanner(session_maker, rng=random.Random(0))
    tz = ZoneInfo("Europe/Moscow")
    start = dt.datetime(2024, 1, 1, 9, 0, tzinfo=tz)
    end = dt.datetime(2024, 1, 1, 12, 0, tzinfo=tz)
    times = planner._generate_times(
        posts_per_day=3,
        window_start=start,
        window_end=end,
        min_interval_minutes=30,
    )
    assert len(times) == 3
    assert all(start <= t <= end for t in times)
    for a, b in zip(times, times[1:], strict=False):
        assert (b - a).total_seconds() >= 30 * 60


@pytest.mark.asyncio
async def test_idempotent_planning() -> None:
    await setup_db()
    session_maker = get_sessionmaker()
    async with session_maker() as session:
        project = Project(name="P1", niche="football")
        session.add(project)
        await session.flush()
        cfg = AgentConfig(
            project_id=project.id,
            posts_per_day=2,
            window_start="09:00",
            window_end="10:00",
            min_interval_minutes=10,
        )
        session.add(cfg)
        await session.commit()

    planner = PostPlanner(session_maker, rng=random.Random(1))
    async with session_maker() as session:
        result1 = await planner.plan_for_project(session, project.id)
        await session.commit()
        result2 = await planner.plan_for_project(session, project.id)
        await session.commit()
        assert result1 is not None
        assert result2 is not None
        posts = await session.execute(select(Post).where(Post.project_id == project.id))
        assert len(posts.scalars().all()) == 2


@pytest.mark.asyncio
async def test_plan_today_endpoint_creates_posts() -> None:
    await setup_db()
    session_maker = get_sessionmaker()
    async with session_maker() as session:
        project = Project(name="P1", niche="football")
        session.add(project)
        await session.flush()
        cfg = AgentConfig(
            project_id=project.id,
            posts_per_day=1,
            window_start="08:00",
            window_end="09:00",
            min_interval_minutes=10,
        )
        session.add(cfg)
        await session.commit()

    with TestClient(main.app) as client:
        token_resp = client.post("/login", json={"password": "secret"})
        token = token_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        resp = client.post(f"/projects/{project.id}/plan/today", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["planned"] == 1

        get_resp = client.get(f"/projects/{project.id}/plan", headers=headers)
        assert get_resp.status_code == 200
        posts = get_resp.json()
        assert len(posts) == 1
        assert posts[0]["status"] == PostStatus.PLANNED.value
