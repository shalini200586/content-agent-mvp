import json

import pytest

from content_agent.llm import FakeChat
from content_agent.research import (
    Headline,
    Persona,
    fetch_headlines,
    fetch_persona,
    pick_hot_topic,
)
from content_agent.store import Store
from content_agent.workflow import research_and_draft

PERSONA = Persona(
    title="Data engineer",
    summary="A data engineer builds pipelines that move and transform data for analytics.",
    url="https://en.wikipedia.org/wiki/Data_engineer",
)

RSS = """<?xml version="1.0"?>
<rss version="2.0"><channel>
  <item>
    <title>Data pipelines fail silently in cloud warehouses - Outlet A</title>
    <link>https://example.com/a</link>
    <pubDate>Fri, 16 Oct 2026 09:00:00 GMT</pubDate>
    <source url="https://a.example">Outlet A</source>
  </item>
  <item>
    <title>Why cloud warehouse pipelines keep failing silently - Outlet B</title>
    <link>https://example.com/b</link>
    <pubDate>Fri, 16 Oct 2026 08:00:00 GMT</pubDate>
    <source url="https://b.example">Outlet B</source>
  </item>
  <item>
    <title>Cloud warehouse pipelines failing silently costs teams hours - Outlet C</title>
    <link>https://example.com/c</link>
    <pubDate>Thu, 15 Oct 2026 08:00:00 GMT</pubDate>
    <source url="https://c.example">Outlet C</source>
  </item>
  <item>
    <title>Chip maker posts record quarterly revenue - Outlet D</title>
    <link>https://example.com/d</link>
    <pubDate>Fri, 16 Oct 2026 10:00:00 GMT</pubDate>
    <source url="https://d.example">Outlet D</source>
  </item>
</channel></rss>
""".encode()


def test_persona_comes_from_wikipedia_summary():
    payload = {
        "type": "standard",
        "title": "Data engineer",
        "extract": PERSONA.summary,
        "content_urls": {"desktop": {"page": PERSONA.url}},
    }
    persona = fetch_persona("Data engineer", get=lambda url: json.dumps(payload).encode())
    assert persona.title == "Data engineer"
    assert persona.url == PERSONA.url


def test_disambiguation_page_is_rejected():
    payload = {"type": "disambiguation", "title": "Engineer", "extract": "may refer to"}
    with pytest.raises(ValueError):
        fetch_persona("Engineer", get=lambda url: json.dumps(payload).encode())


def test_headlines_have_outlet_stripped_and_newest_first():
    headlines = fetch_headlines("data engineer", get=lambda url: RSS)
    assert headlines[0].title.startswith("Chip maker")
    assert headlines[0].source == "Outlet D"
    assert all(" - Outlet" not in h.title for h in headlines)


def test_hot_topic_is_the_story_covered_by_most_outlets():
    headlines = fetch_headlines("data engineer", get=lambda url: RSS)
    topic, backing = pick_hot_topic(headlines, PERSONA)
    assert "pipelines" in topic.title
    assert {h.source for h in backing} == {"Outlet A", "Outlet B", "Outlet C"}


def test_no_headlines_is_an_error():
    with pytest.raises(ValueError):
        pick_hot_topic([], PERSONA)


@pytest.fixture
def store(tmp_path):
    s = Store(str(tmp_path / "research.db"))
    yield s
    s.close()


def test_research_and_draft_stores_posts_grounded_in_sources(store):
    model = FakeChat(["Draft one about pipelines.", "Draft two about pipelines.", "Draft three."])
    result = research_and_draft(
        model,
        store,
        "Data engineer",
        count=3,
        get_persona=lambda role: PERSONA,
        get_headlines=lambda query: fetch_headlines("x", get=lambda url: RSS),
    )

    assert len(result.post_ids) == 3
    assert "pipelines" in result.topic.title

    # The model was briefed with the role and the backing stories, not the whole feed.
    system, user = model.calls[0]
    assert "Data engineer" in user
    assert "Outlet A" in user
    assert "Chip maker" not in user

    saved = store.get_post(result.post_ids[0])
    assert saved.topic.startswith(result.topic.title)
    assert saved.status == "pending"
