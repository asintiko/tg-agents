from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import pytest
from sqlalchemy import select

from apps.api.config import get_settings
from apps.api.db import dispose_engine, init_engine, init_models, init_sessionmaker
from apps.api.models import ImageCache
from apps.worker.images import ImageService


class _CountingTransport(httpx.MockTransport):
    def __init__(self) -> None:
        self.calls: list[str] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            self.calls.append(str(request.url))
            if "w/api.php" in request.url.path:
                data: dict[str, Any] = {
                    "query": {
                        "pages": {
                            "1": {
                                "title": "Test Page",
                                "thumbnail": {"source": "https://img.test/foo.jpg"},
                            }
                        }
                    }
                }
                return httpx.Response(200, json=data)
            if request.url.path.endswith("foo.jpg"):
                return httpx.Response(200, content=b"image-bytes")
            return httpx.Response(404)

        super().__init__(handler)


@pytest.mark.asyncio
async def test_image_fetch_and_cache(tmp_path: Path) -> None:
    settings = get_settings()
    settings.database_url = "sqlite+aiosqlite:///:memory:"
    settings.app_data_dir = str(tmp_path)
    init_engine(settings)
    session_maker = init_sessionmaker(settings)
    await init_models(settings)

    transport = _CountingTransport()
    client = httpx.AsyncClient(transport=transport)
    service = ImageService(session_maker, settings=settings, http_client=client)

    first = await service.find_image("football news", mode="wikimedia")
    assert first is not None
    assert Path(first.path).exists()
    assert any("w/api.php" in call for call in transport.calls)
    assert any("foo.jpg" in call for call in transport.calls)

    transport.calls.clear()
    second = await service.find_image("football news", mode="wikimedia")
    assert second is not None
    assert second.path == first.path
    assert transport.calls == []

    async with session_maker() as session:
        rows = await session.execute(select(ImageCache))
        cached = rows.scalar_one()
        cached.created_at = datetime.now(ZoneInfo("Europe/Moscow")) - timedelta(days=8)
        await session.commit()

    # Expired cache triggers fetch again
    third = await service.find_image("football news", mode="wikimedia")
    assert third is not None
    assert transport.calls  # new network usage

    await service.close()
    await dispose_engine()
