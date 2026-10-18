import json

import pytest

from content_agent.research import fetch_all_headlines, fetch_hn_headlines

HN_JSON = json.dumps(
    {
        "hits": [
            {
                "title": "Show HN: a faster pipeline runner",
                "url": "https://www.example.org/pipeline",
                "objectID": "1",
                "created_at": "2026-10-16T09:30:00.000Z",
            },
            {
                "title": "",  # empty titles are skipped
                "url": "https://example.org/empty",
                "objectID": "2",
                "created_at": "2026-10-16T08:00:00.000Z",
            },
            {
                "title": "Ask HN: how do you test pipelines?",
                "url": None,
                "objectID": "3",
                "created_at": "2026-10-15T10:00:00.000Z",
            },
        ]
    }
).encode()

RSS = b"""<?xml version="1.0"?>
<rss><channel>
  <item>
    <title>Pipelines get faster - Outlet A</title>
    <link>https://news.example/a</link>
    <source url="https://outlet-a.example">Outlet A</source>
    <pubDate>Fri, 16 Oct 2026 12:00:00 GMT</pubDate>
  </item>
</channel></rss>"""


def test_hn_headlines_use_the_article_domain_and_skip_empty_titles():
    headlines = fetch_hn_headlines("pipelines", get=lambda url: HN_JSON)

    assert [h.title for h in headlines] == [
        "Show HN: a faster pipeline runner",
        "Ask HN: how do you test pipelines?",
    ]
    assert headlines[0].source == "example.org"
    assert headlines[0].published is not None
    # A story without its own link points to its Hacker News page.
    assert headlines[1].link == "https://news.ycombinator.com/item?id=3"


def test_all_headlines_merges_sources_newest_first():
    def get(url):
        return HN_JSON if "algolia" in url else RSS

    headlines = fetch_all_headlines("pipelines", get=get)

    titles = [h.title for h in headlines]
    assert "Pipelines get faster" in titles
    assert "Show HN: a faster pipeline runner" in titles
    dates = [h.published for h in headlines if h.published]
    assert dates == sorted(dates, reverse=True)


def test_one_failing_source_does_not_stop_the_others():
    def get(url):
        if "algolia" in url:
            raise OSError("hacker news is down")
        return RSS

    headlines = fetch_all_headlines("pipelines", get=get)
    assert [h.title for h in headlines] == ["Pipelines get faster"]


def test_error_is_raised_only_when_every_source_fails():
    def get(url):
        raise OSError("offline")

    with pytest.raises(OSError):
        fetch_all_headlines("pipelines", get=get)
