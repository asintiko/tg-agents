from __future__ import annotations

import pytest

from apps.api.telegram_user import parse_entity


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
