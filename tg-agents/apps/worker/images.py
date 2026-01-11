from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from apps.api.config import Settings, get_settings
from apps.api.models import ImageCache

ImageMode = Literal["wikimedia", "og_image", "link_preview"]
CACHE_TTL = timedelta(days=7)


@dataclass(slots=True)
class ImageResult:
    path: str
    source: str | None = None


class ImageService:
    def __init__(
        self,
        session_maker: async_sessionmaker[AsyncSession],
        settings: Settings | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.session_maker = session_maker
        self.settings = settings or get_settings()
        self.http = http_client or httpx.AsyncClient(timeout=10.0)

    async def close(self) -> None:
        await self.http.aclose()

    def _hash_query(self, query: str, mode: ImageMode) -> str:
        material = f"{mode}:{query.lower().strip()}"
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    async def _get_cached(self, session: AsyncSession, query_hash: str) -> ImageResult | None:
        result = await session.execute(
            select(ImageCache).where(
                ImageCache.query_hash == query_hash,
                ImageCache.created_at > datetime.now(UTC) - CACHE_TTL,
            )
        )
        cached = result.scalar_one_or_none()
        if not cached:
            return None
        if not Path(cached.image_path).exists():
            return None
        return ImageResult(path=cached.image_path, source=cached.source)

    async def _store_cache(
        self, session: AsyncSession, query_hash: str, image_path: str, source: str | None
    ) -> None:
        await session.execute(
            ImageCache.__table__.delete().where(ImageCache.query_hash == query_hash)
        )
        session.add(ImageCache(query_hash=query_hash, image_path=image_path, source=source))
        await session.commit()

    async def find_image(
        self, image_query: str, mode: ImageMode = "wikimedia"
    ) -> ImageResult | None:
        query_hash = self._hash_query(image_query, mode)
        async with self.session_maker() as session:
            cached = await self._get_cached(session, query_hash)
            if cached:
                return cached

            if mode == "wikimedia":
                result = await self._fetch_wikimedia(image_query, query_hash)
            else:
                result = None

            if result:
                await self._store_cache(session, query_hash, result.path, result.source)
                return result
            return None

    async def _fetch_wikimedia(self, image_query: str, query_hash: str) -> ImageResult | None:
        search_params: dict[str, str | int] = {
            "action": "query",
            "format": "json",
            "prop": "pageimages",
            "piprop": "thumbnail|original",
            "pithumbsize": 800,
            "generator": "search",
            "gsrlimit": 1,
            "gsrsearch": image_query,
        }
        resp = await self.http.get("https://en.wikipedia.org/w/api.php", params=search_params)
        resp.raise_for_status()
        data = resp.json()
        pages = data.get("query", {}).get("pages", {})
        if not pages:
            return None
        page = next(iter(pages.values()))
        thumb = page.get("thumbnail", {}).get("source")
        original = page.get("original", {}).get("source")
        image_url = original or thumb
        if not image_url:
            return None
        image_path = await self._download_image(image_url, query_hash)
        return ImageResult(path=image_path, source=page.get("title"))

    async def _download_image(self, image_url: str, query_hash: str) -> str:
        response = await self.http.get(image_url)
        response.raise_for_status()
        suffix = Path(urlparse(image_url).path).suffix or ".jpg"
        images_dir = Path(self.settings.app_data_dir) / "images"
        images_dir.mkdir(parents=True, exist_ok=True)
        file_path = images_dir / f"{query_hash}{suffix}"
        file_path.write_bytes(response.content)
        return str(file_path)
