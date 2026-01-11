from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any
from xml.etree import ElementTree

import httpx


@dataclass(slots=True)
class NewsArticle:
    title: str
    url: str
    summary: str | None
    source: str


class FootballNewsFetcher:
    def __init__(self, feed_url: str, timeout: float = 10.0) -> None:
        self.feed_url = feed_url
        self.timeout = timeout

    async def fetch(self, limit: int = 5) -> list[NewsArticle]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(self.feed_url)
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            if "json" in content_type:
                return self._parse_json(response.json(), limit=limit)
            return self._parse_rss(response.text, limit=limit)

    def _parse_rss(self, xml_text: str, limit: int) -> list[NewsArticle]:
        root = ElementTree.fromstring(xml_text)
        items = root.findall(".//item")
        articles: list[NewsArticle] = []
        for item in items[:limit]:
            title = (item.findtext("title") or "").strip() or "Untitled"
            link = (item.findtext("link") or "").strip()
            description = (item.findtext("description") or "").strip()
            source = (item.findtext("source") or "unknown").strip()
            articles.append(
                NewsArticle(
                    title=title,
                    url=link,
                    summary=description or None,
                    source=source or "rss",
                )
            )
        return articles

    def _parse_json(self, payload: Any, limit: int) -> list[NewsArticle]:
        items: list[dict[str, Any]] = []
        if isinstance(payload, list):
            items = payload[:limit]
        elif isinstance(payload, dict):
            items = payload.get("items") or payload.get("articles") or []
            items = items[:limit]
        articles: list[NewsArticle] = []
        for item in items:
            title = str(item.get("title") or "Untitled")
            url = str(item.get("url") or item.get("link") or "")
            summary = item.get("summary") or item.get("description")
            source = item.get("source") or "json-feed"
            articles.append(
                NewsArticle(
                    title=title,
                    url=url,
                    summary=str(summary) if summary else None,
                    source=str(source),
                )
            )
        return articles


class PostBuilder:
    def __init__(self, max_length: int = 3800) -> None:
        self.max_length = max_length

    def build(self, article: NewsArticle, summary: str | None) -> str:
        summary_text = summary or article.summary or "Краткое содержание отсутствует."
        message = f"⚽️ {article.title}\n\n{summary_text}\n\nИсточник: {article.url}"
        return self._trim(message)

    def _trim(self, text: str) -> str:
        if len(text) <= self.max_length:
            return text
        return text[: self.max_length - 3] + "..."


def deduplicate_articles(articles: list[NewsArticle]) -> list[NewsArticle]:
    seen = set()
    unique: list[NewsArticle] = []
    for article in articles:
        key = json.dumps({"title": article.title, "url": article.url})
        if key in seen:
            continue
        seen.add(key)
        unique.append(article)
    return unique
