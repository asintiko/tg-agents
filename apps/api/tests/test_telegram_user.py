from __future__ import annotations

import pytest

from telethon.tl.types import MessageEntityBold, MessageEntityCustomEmoji

from apps.api.telegram_user import _build_message_with_premium, parse_custom_emoji_id, parse_entity


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("12345", 12345),
        ("-1001234567890", -1001234567890),
        ("  42  ", 42),
        ("channel_name", "channel_name"),
        ("@handle", "@handle"),
        ("abc-123", "abc-123"),
    ],
)
def test_parse_entity(raw: str, expected: int | str) -> None:
    assert parse_entity(raw) == expected


def test_parse_custom_emoji_id() -> None:
    assert parse_custom_emoji_id("tg://emoji?id=123456") == 123456
    assert parse_custom_emoji_id("987654321") == 987654321
    assert parse_custom_emoji_id("emoji=notanumber") is None


def test_build_message_with_brand() -> None:
    text, entities = _build_message_with_premium("<b>Привет</b>", 42, "⚽")
    assert text.startswith("⚽ ")
    custom = [e for e in entities if isinstance(e, MessageEntityCustomEmoji)]
    assert len(custom) == 1
    assert custom[0].document_id == 42
    bold_entities = [e for e in entities if isinstance(e, MessageEntityBold)]
    assert bold_entities, "Bold entity should be preserved"
    assert bold_entities[0].offset >= 2
