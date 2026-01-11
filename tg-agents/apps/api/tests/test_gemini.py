from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from apps.api.gemini import GeminiGenerator
from apps.api.html_utils import sanitize_html_for_telegram
from apps.api.models import AgentConfig, EmojiMode, ImageMode, NewsItem


def _sample_config(
    include_source_link: bool = True, signature_html: str | None = None
) -> AgentConfig:
    return AgentConfig(
        project_id=1,
        posts_per_day=1,
        window_start="00:00",
        window_end="23:59",
        min_interval_minutes=10,
        language="ru",
        tone="neutral",
        signature_html=signature_html,
        emoji_mode=EmojiMode.BASIC,
        include_source_link=include_source_link,
        image_mode=ImageMode.WIKIMEDIA,
    )


def _sample_news() -> NewsItem:
    return NewsItem(
        project_id=1,
        source_id=None,
        title="Match report",
        url="https://example.com/article",
        published_at=datetime(2024, 1, 1, tzinfo=UTC),
        raw_summary="A short summary",
        raw_content="Full content",
        hash="hash123",
    )


@pytest.mark.asyncio
async def test_generate_truncates_and_appends_link(monkeypatch: pytest.MonkeyPatch) -> None:
    generator = GeminiGenerator(api_key=None)
    long_body = "<b>" + ("x" * 950) + "</b><script>alert('bad')</script>"
    payload = {
        "headline": "Headline",
        "lead": "Lead",
        "body_html": long_body,
        "hashtags": ["football"],
        "image_query": "football",
        "source_url": "https://example.com",
        "should_post": True,
        "reason_if_skip": None,
    }

    async def fake_call(_: str) -> str:
        return json.dumps(payload)

    monkeypatch.setattr(generator, "_call_model", fake_call)
    post = await generator.generate(_sample_news(), "Test Source", _sample_config())

    assert len(post.body_html) <= 900
    assert "script" not in post.body_html.lower()
    assert "Источник: <a href=\"https://example.com/article\">" in post.body_html
    assert "#football" in post.body_html
    assert "---" in post.body_html


@pytest.mark.asyncio
async def test_generate_retries_on_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    generator = GeminiGenerator(api_key=None)
    valid_payload = {
        "headline": "Valid",
        "lead": "Lead",
        "body_html": "Body",
        "hashtags": [],
        "image_query": "query",
        "source_url": "https://example.com",
        "should_post": True,
        "reason_if_skip": None,
    }
    responses = iter(["not-json", json.dumps(valid_payload)])

    async def fake_call(_: str) -> str:
        return next(responses)

    monkeypatch.setattr(generator, "_call_model", fake_call)
    post = await generator.generate(
        _sample_news(), "Test Source", _sample_config(include_source_link=False)
    )
    assert post.headline == "Valid"
    assert post.body_html == "Body"


def test_sanitize_html_keeps_allowed_tags() -> None:
    html = "<div><b>Bold</b><i>It</i><span>drop</span><script>bad</script></div>"
    cleaned = sanitize_html_for_telegram(html)
    assert "<div>" not in cleaned
    assert "<span" not in cleaned
    assert "<script" not in cleaned
    assert "<b>Bold</b>" in cleaned
    assert "<i>It</i>" in cleaned
