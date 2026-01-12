from __future__ import annotations

from apps.api.html_utils import append_signature, render_hashtags, sanitize_html_for_telegram


def test_sanitize_removes_disallowed_tags_and_script_content() -> None:
    html = "<div>Hi <b>there</b><script>alert('x')</script><img src='x'/>!</div>"
    cleaned = sanitize_html_for_telegram(html)
    assert "<div" not in cleaned
    assert "<img" not in cleaned
    assert "alert" not in cleaned
    assert "<b>there</b>" in cleaned
    assert "Hi" in cleaned


def test_sanitize_keeps_allowed_tags_and_escapes() -> None:
    html = "<b>Bold</b> <i>It</i> <pre>& test</pre>"
    cleaned = sanitize_html_for_telegram(html)
    assert "<b>Bold</b>" in cleaned
    assert "<i>It</i>" in cleaned
    assert "&amp; test" in cleaned


def test_href_sanitization_blocks_javascript() -> None:
    html = '<a href="javascript:alert(1)">bad</a> <a href="https://good.com">good</a>'
    cleaned = sanitize_html_for_telegram(html)
    assert "javascript" not in cleaned.lower()
    assert "<a href=\"https://good.com\">good</a>" in cleaned
    assert "bad" in cleaned


def test_append_signature_and_render_hashtags() -> None:
    body = "Body"
    with_sig = append_signature(body, "<i>sig</i>")
    assert "---" in with_sig
    hashtags = render_hashtags(["Football", "football", "bad tag", "#123"])
    assert "#Football" in hashtags
    assert "#123" in hashtags
