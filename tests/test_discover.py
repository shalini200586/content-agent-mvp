import time
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from content_agent.api import create_app
from content_agent.llm import FakeChat
from content_agent.profile import Profile, extract_interests, save_profile
from content_agent.research import Headline, discover_topics


def story(title, outlet, day=16):
    return Headline(
        title=title,
        link="https://news.example/" + title.lower().replace(" ", "-"),
        source=outlet,
        published=datetime(2026, 10, day, tzinfo=timezone.utc),
    )


def test_extract_interests_splits_and_limits_keywords():
    model = FakeChat(["Java, Spring Boot, JVM,  Kotlin\nGraalVM, Quarkus, Micronaut"])
    keywords = extract_interests(model, "I write about Java backends")
    assert keywords == ["Java", "Spring Boot", "JVM", "Kotlin", "GraalVM"]


def test_extract_interests_falls_back_to_niche_when_model_is_silent():
    assert extract_interests(FakeChat([""]), "anything", fallback="Backend engineering") == ["Backend engineering"]


def test_discover_prefers_stories_covered_by_more_outlets():
    found = {
        "Java": [
            story("Oracle releases new Java 25 features", "Outlet A"),
            story("Oracle ships Java 25 features for developers", "Outlet B"),
            story("Java 25 features arrive from Oracle", "Outlet C"),
        ],
        "Spring Boot": [story("Spring Boot 4 adds native images", "Outlet D")],
    }
    topics = discover_topics(found)
    assert topics[0].headline.title.startswith("Oracle")
    assert len(topics[0].backing) == 3


def test_discover_keeps_the_keyword_that_found_the_topic():
    found = {"Kotlin": [story("Kotlin 3 released with new compiler", "Outlet A")]}
    assert discover_topics(found)[0].keyword == "Kotlin"


def test_discover_skips_promotional_stories_when_real_news_exists():
    found = {
        "Java": [
            story("Acme appoints Jane as director of Java tooling", "Wire", day=17),
            story("Java tooling gets a faster compiler", "Tech", day=15),
        ]
    }
    assert discover_topics(found)[0].headline.source == "Tech"


def test_discover_returns_nothing_for_no_stories():
    assert discover_topics({}) == []
    assert discover_topics({"Java": []}) == []


def make_app(tmp_path, model, headlines_by_keyword, fail=()):
    def get_headlines(keyword):
        if keyword in fail:
            raise OSError("source down")
        return headlines_by_keyword.get(keyword, [])

    return create_app(
        db_path=str(tmp_path / "d.db"),
        model_factory=lambda: model,
        get_headlines=get_headlines,
        actor="tester",
        background=False,
    )


def discover_result(client, rescan=False):
    """Start the discovery job and wait for it. Returns the job record."""
    job = client.get("/api/discover", params={"rescan": rescan}).json()
    status = {}
    for _ in range(200):
        status = client.get(f"/api/jobs/{job['job_id']}").json()
        if status["status"] != "running":
            return status
        time.sleep(0.05)
    return status


JAVA_FEED = {
    "Java": [story("Oracle releases new Java 25 features", "Outlet A"), story("Java 25 features from Oracle", "Outlet B")],
}


def test_discover_learns_interests_from_profile_and_finds_topics(tmp_path):
    model = FakeChat(["Java, Spring Boot", "1, 2", "Java 25 release" + chr(10) + "Java news" + chr(10) + "JVM update", "NONE"])
    save_profile(tmp_path / "profile.json", Profile(niche="Java backend developer", voice="direct"))
    client = TestClient(make_app(tmp_path, model, JAVA_FEED))

    data = discover_result(client)["result"]

    assert data["interests"] == ["Java", "Spring Boot"]
    assert data["topics"][0]["keyword"] == "Java"
    assert len(data["topics"][0]["backing"]) == 2
    # The learned interests are saved, so the next visit does not ask the model again.
    assert client.get("/api/profile").json()["interests"] == ["Java", "Spring Boot"]


def test_discover_needs_a_niche(tmp_path):
    client = TestClient(make_app(tmp_path, FakeChat([]), JAVA_FEED))
    job = discover_result(client)
    assert job["status"] == "error"
    assert "niche" in job["error"]


def test_discover_reports_failing_sources_without_stopping(tmp_path):
    save_profile(tmp_path / "profile.json", Profile(niche="x", interests=["Java", "Kotlin"]))
    client = TestClient(make_app(tmp_path, FakeChat(["1, 2", "NONE"]), JAVA_FEED, fail=("Kotlin",)))
    data = discover_result(client)["result"]
    assert data["topics"]
    assert data["errors"] and "Kotlin" in data["errors"][0]


def test_draft_from_a_discovered_topic_uses_the_profile_not_a_role(tmp_path):
    model = FakeChat(["1, 2", "NONE", "A post about Java 25."])
    save_profile(
        tmp_path / "profile.json",
        Profile(niche="Java backend developer", voice="direct", interests=["Java"]),
    )
    client = TestClient(make_app(tmp_path, model, JAVA_FEED))
    topic = discover_result(client)["result"]["topics"][0]

    job = client.post(
        "/api/drafts",
        json={
            "title": topic["title"],
            "link": topic["link"],
            "source": topic["source"],
            "related": [{"title": b["title"], "link": b["link"], "source": b["source"]} for b in topic["backing"]],
            "count": 1,
        },
    ).json()

    status = {}
    for _ in range(100):
        status = client.get(f"/api/jobs/{job['job_id']}").json()
        if status["status"] != "running":
            break
        time.sleep(0.05)
    assert status["status"] == "done"
    _, user = model.calls[-1]
    assert "Writing for: Java backend developer" in user
    assert "direct" in user


def test_stories_without_the_interest_terms_are_dropped():
    found = {
        "Kotlin": [story("Oracle releases Java 27 with new cryptography", "Oracle")],
        "Java": [story("Oracle releases Java 27 with new cryptography", "Oracle")],
    }
    titles = [t.keyword for t in discover_topics(found)]
    assert titles == ["Java"]
