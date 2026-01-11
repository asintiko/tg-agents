from __future__ import annotations

from app.services.news import FootballNewsFetcher, NewsArticle, PostBuilder, deduplicate_articles


def test_deduplicate_articles() -> None:
    articles = [
        NewsArticle(title="A", url="u1", summary=None, source="s"),
        NewsArticle(title="A", url="u1", summary=None, source="s"),
        NewsArticle(title="B", url="u2", summary=None, source="s"),
    ]
    unique = deduplicate_articles(articles)
    assert len(unique) == 2


def test_post_builder_trims_long_text() -> None:
    article = NewsArticle(title="Title", url="http://example.com", summary="a" * 4000, source="s")
    builder = PostBuilder(max_length=100)
    content = builder.build(article, article.summary)
    assert len(content) <= 100
    assert content.endswith("...")


def test_rss_parsing_returns_articles() -> None:
    feed = """
        <rss>
            <channel>
                <item>
                    <title>Test</title>
                    <link>http://example.com</link>
                    <description>Summary</description>
                    <source>Feed</source>
                </item>
            </channel>
        </rss>
    """
    fetcher = FootballNewsFetcher("http://example.com")
    articles = fetcher._parse_rss(feed, limit=5)
    assert articles[0].title == "Test"
    assert articles[0].url == "http://example.com"
