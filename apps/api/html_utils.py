from __future__ import annotations

import html
import re
from collections.abc import Iterable
from html.parser import HTMLParser
from urllib.parse import urlparse

ALLOWED_TAGS: set[str] = {
    "b",
    "strong",
    "i",
    "em",
    "u",
    "ins",
    "s",
    "strike",
    "del",
    "tg-spoiler",
    "a",
    "code",
    "pre",
    "blockquote",
}

_SCRIPT_LIKE_TAGS = {"script", "style"}


def _sanitize_href(raw_href: str | None) -> str | None:
    if not raw_href:
        return None
    href = raw_href.strip()
    if href.lower().startswith("javascript:"):
        return None
    parsed = urlparse(href)
    if parsed.scheme and parsed.scheme not in {"http", "https"}:
        return None
    return href


class _TelegramSanitizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.result: list[str] = []
        self.tag_stack: list[str | None] = []
        self._ignore_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lower_tag = tag.lower()
        if lower_tag in _SCRIPT_LIKE_TAGS:
            self._ignore_depth += 1
            self.tag_stack.append(None)
            return
        if lower_tag not in ALLOWED_TAGS:
            self.tag_stack.append(None)
            return
        if lower_tag == "a":
            href_value = None
            for attr_name, attr_value in attrs:
                if attr_name.lower() == "href":
                    href_value = _sanitize_href(attr_value)
                    break
            if href_value is None:
                self.tag_stack.append(None)
                return
            safe_href = html.escape(href_value, quote=True)
            self.result.append(f'<a href="{safe_href}">')
            self.tag_stack.append("a")
            return
        self.result.append(f"<{lower_tag}>")
        self.tag_stack.append(lower_tag)

    def handle_endtag(self, tag: str) -> None:
        lower_tag = tag.lower()
        if lower_tag in _SCRIPT_LIKE_TAGS:
            if self.tag_stack:
                self.tag_stack.pop()
            if self._ignore_depth > 0:
                self._ignore_depth -= 1
            return
        if not self.tag_stack:
            return
        started = self.tag_stack.pop()
        if started == lower_tag:
            self.result.append(f"</{lower_tag}>")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_data(self, data: str) -> None:
        if self._ignore_depth > 0:
            return
        self.result.append(html.escape(data))

    def handle_entityref(self, name: str) -> None:
        if self._ignore_depth > 0:
            return
        self.result.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        if self._ignore_depth > 0:
            return
        self.result.append(f"&#{name};")


def sanitize_html_for_telegram(raw_html: str) -> str:
    parser = _TelegramSanitizer()
    parser.feed(raw_html)
    parser.close()
    return "".join(parser.result)


def append_signature(body_html: str, signature_html: str | None) -> str:
    if not signature_html:
        return body_html
    signature_clean = sanitize_html_for_telegram(signature_html)
    if not signature_clean.strip():
        return body_html
    if body_html:
        return f"{body_html}\n\n---\n{signature_clean}"
    return signature_clean


def render_hashtags(hashtags: Iterable[str]) -> str:
    cleaned: list[str] = []
    seen: set[str] = set()
    for tag in hashtags:
        candidate = tag.strip().lstrip("#")
        candidate = re.sub(r"[^0-9A-Za-z_]+", "", candidate)
        if not candidate:
            continue
        hashtag = f"#{candidate}"
        if hashtag.lower() in seen:
            continue
        seen.add(hashtag.lower())
        cleaned.append(hashtag)
    if not cleaned:
        return ""
    return "\n\n" + " ".join(cleaned)
