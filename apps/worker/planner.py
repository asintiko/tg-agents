from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from zoneinfo import ZoneInfo

from apps.api.time_utils import MSK_TZ, UTC_TZ, msk_now, to_utc
from apps.api.models import AgentConfig, Post, PostStatus, Project


@dataclass(slots=True)
class PlanResult:
    project_id: int
    planned_count: int


class PostPlanner:
    def __init__(
        self,
        session_maker: async_sessionmaker[AsyncSession],
        rng: random.Random | None = None,
        now_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self.session_maker = session_maker
        self.rng = rng or random.Random()
        self.now_fn = now_fn or msk_now

    async def plan_all_projects(self) -> list[PlanResult]:
        today = self.now_fn().date()
        async with self.session_maker() as session:
            projects = await session.execute(select(Project))
            results: list[PlanResult] = []
            for project in projects.scalars().all():
                result = await self.plan_for_project(session, project.id, today)
                if result:
                    results.append(result)
            await session.commit()
        return results

    async def plan_for_project(
        self, session: AsyncSession, project_id: int, target_date: date | None = None
    ) -> PlanResult | None:
        target_date = target_date or self.now_fn().date()
        day_start_msk = datetime.combine(target_date, time.min, tzinfo=MSK_TZ)
        day_end_msk = day_start_msk + timedelta(days=1)
        cfg = await session.scalar(
            select(AgentConfig).where(AgentConfig.project_id == project_id)
        )
        if not cfg:
            return None

        start_dt, end_dt = self._window_datetimes(cfg, target_date)
        times = self._generate_times(
            posts_per_day=cfg.posts_per_day,
            window_start=start_dt,
            window_end=end_dt,
            min_interval_minutes=cfg.min_interval_minutes,
        )

        await session.execute(
            delete(Post).where(
                Post.project_id == project_id,
                Post.status == PostStatus.PLANNED,
                Post.planned_at >= to_utc(day_start_msk),
                Post.planned_at < to_utc(day_end_msk),
            )
        )

        for planned_at in times:
            session.add(
                Post(
                    project_id=project_id,
                    news_item_id=None,
                    status=PostStatus.PLANNED,
                    planned_at=to_utc(planned_at),
                )
            )
        await session.flush()
        return PlanResult(project_id=project_id, planned_count=len(times))

    def _window_datetimes(self, cfg: AgentConfig, target_date: date) -> tuple[datetime, datetime]:
        start_parts = cfg.window_start.split(":")
        end_parts = cfg.window_end.split(":")
        start_time = time(int(start_parts[0]), int(start_parts[1]), tzinfo=MSK_TZ)
        end_time = time(int(end_parts[0]), int(end_parts[1]), tzinfo=MSK_TZ)
        start_dt = datetime.combine(target_date, start_time)
        end_dt = datetime.combine(target_date, end_time)
        return start_dt, end_dt

    def _generate_times(
        self,
        posts_per_day: int,
        window_start: datetime,
        window_end: datetime,
        min_interval_minutes: int,
    ) -> list[datetime]:
        if posts_per_day <= 0:
            return []
        duration = (window_end - window_start).total_seconds()
        if duration <= 0:
            return []
        step = duration / posts_per_day
        jitter_seconds = 7 * 60
        times: list[datetime] = []
        for i in range(posts_per_day):
            base_time = window_start + timedelta(seconds=step * (i + 0.5))
            jitter = self.rng.randint(-jitter_seconds, jitter_seconds)
            candidate = base_time + timedelta(seconds=jitter)
            if candidate < window_start:
                candidate = window_start
            if candidate > window_end:
                candidate = window_end
            times.append(candidate)

        times.sort()
        min_delta = timedelta(minutes=min_interval_minutes)
        adjusted: list[datetime] = []
        for t in times:
            if adjusted and t < adjusted[-1] + min_delta:
                t = adjusted[-1] + min_delta
                if t > window_end:
                    t = window_end
            adjusted.append(t)
        return adjusted
