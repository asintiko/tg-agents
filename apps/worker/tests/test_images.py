from __future__ import annotations

from apps.worker.images import extract_og_image


def test_extract_og_image_prefers_og() -> None:
    html = """
    <html><head>
    <meta property="og:image" content="https://example.com/og.jpg">
    <meta name="twitter:image" content="https://example.com/tw.jpg">
    </head><body></body></html>
    """
    url = "https://example.com/article"
    assert extract_og_image(html, url) == "https://example.com/og.jpg"


def test_extract_og_image_fallback_relative() -> None:
    html = """
    <html><head>
    <meta name="twitter:image" content="/images/pic.png">
    <link rel="image_src" href="/images/fallback.jpg">
    </head></html>
    """
    url = "https://example.org/page"
    assert extract_og_image(html, url) == "https://example.org/images/pic.png"
