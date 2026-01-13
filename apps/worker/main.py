from __future__ import annotations

import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.ext.asyncio import async_sessionmaker

from apps.api.config import get_settings
from apps.api.db import init_engine, init_sessionmaker
from apps.api.logging_config import configure_logging
from apps.api.time_utils import MSK_TZ
from apps.api.models import Heartbeat
from apps.worker.pipeline import PostPipeline
from apps.worker.planner import PostPlanner
from apps.worker.rss import RSSCollector

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def get_worker_status() -> str:
    return "worker alive"


async def _write_heartbeat(session_maker: async_sessionmaker) -> None:
    async with session_maker() as session:
        session.add(Heartbeat(note="worker"))
        await session.commit()


async def run_scheduler() -> None:
    configure_logging()
    settings = get_settings()
    init_engine(settings)
    session_maker = init_sessionmaker(settings)
    collector = RSSCollector(session_maker, settings=settings)
    planner = PostPlanner(session_maker)
    pipeline = PostPipeline(session_maker, settings=settings)
    await collector.ensure_default_feeds()

    scheduler = AsyncIOScheduler(timezone=MSK_TZ)
    scheduler.add_job(collector.pull_all, "interval", minutes=5, coalesce=True)
    scheduler.add_job(planner.plan_all_projects, "cron", hour=0, minute=5, coalesce=True)
    scheduler.add_job(pipeline.run, "interval", seconds=60, coalesce=True)
    scheduler.add_job(_write_heartbeat, "interval", seconds=30, args=[session_maker], coalesce=True)
    scheduler.start()
    logger.info(get_worker_status())
    try:
        while True:
            await asyncio.sleep(60)
    except asyncio.CancelledError:
        scheduler.shutdown()
        await collector.close()
        raise


if __name__ == "__main__":
    asyncio.run(run_scheduler())
