from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from apps.api.config import get_settings
from apps.api.db import init_engine, init_sessionmaker
from apps.api.logging_config import configure_logging
from apps.api.time_utils import MSK_TZ, msk_now, to_utc
from apps.worker.pipeline import PostPipeline
from apps.worker.planner import PostPlanner
from apps.worker.rss import RSSCollector

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def get_worker_status() -> str:
    return "worker alive"


async def _write_heartbeat(data_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    now_msk = msk_now()
    payload = {
        "ts_utc": to_utc(now_msk).isoformat(),
        "ts_msk": now_msk.isoformat(),
        "service": "worker",
        "jobs": ["rss", "planner", "pipeline"],
    }
    (data_dir / "heartbeat.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


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
    heartbeat_dir = Path(settings.app_data_dir) / "worker"
    scheduler.add_job(_write_heartbeat, "interval", seconds=30, args=[heartbeat_dir], coalesce=True)
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
