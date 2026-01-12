from __future__ import annotations

from apps.worker.images import extract_og_image


def test_extract_og_image_prefers_og_then_twitter_then_link() -> None:
    html = """
    <html>
    <head>
      <meta property="og:image" content="/images/og.jpg">
      <meta name="twitter:image" content="http://example.com/images/twitter.jpg">
      <link rel="image_src" href="http://example.com/images/link.jpg">
    </head>
    </html>
    """
    url = "http://example.com/page"
    assert extract_og_image(html, url) == "http://example.com/images/og.jpg"


def test_extract_og_image_uses_twitter_and_link_fallbacks() -> None:
    html = """
    <html>
    <head>
      <meta name="twitter:image" content="/images/twitter.jpg">
      <link rel="image_src" href="/images/link.jpg">
    </head>
    </html>
    """
    url = "http://example.com/page"
    assert extract_og_image(html, url) == "http://example.com/images/twitter.jpg"


def test_extract_og_image_relative_link_fallback() -> None:
    html = """
    <html>
    <head>
      <link rel="image_src" href="/images/link.jpg">
    </head>
    </html>
    """
    url = "http://example.com/base"
    assert extract_og_image(html, url) == "http://example.com/images/link.jpg"
