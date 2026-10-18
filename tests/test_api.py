from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from content_agent.api import create_app
from content_agent.llm import FakeChat
from content_agent.research import Headline, Persona

PERSONA = Persona(
    title="Data engineer",
    summary="A data engineer builds pipelines that move data reliably.",
    url="https://en.wikipedia.org/wiki/Data_engineer",
)

STORIES = [
    Headline(
        title="Pipelines get faster with new tooling",
        link="https://news.example/1",
        source="Outlet A",
        published=datetime(2026, 10, 16, tzinfo=timezone.utc),
    ),
    Headline(
        title="Data teams rethink batch jobs",
        link="https://news.example/2",
        source="Outlet B",
        published=None,
    ),
]


@pytest.fixture
def client(tmp_path):
    replies = ["A clean draft about pipelines.", "Another clean draft.", "A third draft."]
    app = create_app(
        db_path=str(tmp_path / "api.db"),
        model_factory=lambda: FakeChat(replies),
        get_persona=lambda role: PERSONA,
        get_headlines=lambda query: STORIES,
        actor="tester",
        background=False,
    )
    return TestClient(app)


def test_health(client):
    assert client.get("/api/health").json() == {"ok": True}


def test_trending_returns_persona_stories_and_suggestion(client):
    data = client.get("/api/trending", params={"role": "Data engineer"}).json()

    assert data["persona"]["title"] == "Data engineer"
    assert [s["link"] for s in data["stories"]] == [s.link for s in STORIES]
    assert data["suggested"] in {s.link for s in STORIES}


def test_trending_with_no_stories_is_404(tmp_path):
    app = create_app(
        db_path=str(tmp_path / "api.db"),
        get_persona=lambda role: PERSONA,
        get_headlines=lambda query: [],
    )
    response = TestClient(app).get("/api/trending", params={"role": "Data engineer"})
    assert response.status_code == 404


def test_news_source_outage_is_502(tmp_path):
    def unreachable(query):
        raise OSError("network down")

    app = create_app(
        db_path=str(tmp_path / "api.db"),
        get_persona=lambda role: PERSONA,
        get_headlines=unreachable,
    )
    response = TestClient(app).get("/api/trending", params={"role": "Data engineer"})
    assert response.status_code == 502


def test_draft_on_chosen_story_creates_pending_posts(client):
    response = client.post(
        "/api/drafts",
        json={
            "role": "Data engineer",
            "title": STORIES[0].title,
            "link": STORIES[0].link,
            "source": STORIES[0].source,
            "voice": "calm",
            "count": 2,
        },
    )
    assert response.status_code == 201
    post_ids = response.json()["post_ids"]
    assert len(post_ids) == 2

    detail = client.get(f"/api/posts/{post_ids[0]}").json()
    assert detail["status"] == "pending"
    assert detail["sources"][0]["outlet"] == "Wikipedia"
    assert any(s["title"] == STORIES[0].title for s in detail["sources"])


def test_list_filters_by_status(client):
    ids = client.post(
        "/api/drafts",
        json={"role": "Data engineer", "title": STORIES[0].title, "count": 2},
    ).json()["post_ids"]
    client.post(f"/api/posts/{ids[0]}/decision", json={"decision": "approved"})

    pending = client.get("/api/posts", params={"status": "pending"}).json()
    approved = client.get("/api/posts", params={"status": "approved"}).json()

    assert [p["id"] for p in pending] == [ids[1]]
    assert [p["id"] for p in approved] == [ids[0]]


def test_edit_is_fact_checked_against_sources(client):
    ids = client.post(
        "/api/drafts",
        json={"role": "Data engineer", "title": STORIES[0].title, "count": 1},
    ).json()["post_ids"]

    edited = client.put(
        f"/api/posts/{ids[0]}",
        json={"body": "Pipelines cut costs by 73% this year."},
    ).json()

    assert edited["body"] == "Pipelines cut costs by 73% this year."
    assert any("73%" in problem for problem in edited["problems"])


def test_approve_records_actor_and_blocks_further_edits(client):
    ids = client.post(
        "/api/drafts",
        json={"role": "Data engineer", "title": STORIES[0].title, "count": 1},
    ).json()["post_ids"]

    approved = client.post(
        f"/api/posts/{ids[0]}/decision", json={"decision": "approved", "note": "ship it"}
    )
    assert approved.json()["status"] == "approved"

    history = client.get(f"/api/posts/{ids[0]}").json()["history"]
    assert history[-1]["actor"] == "tester"
    assert history[-1]["event"] == "approved"

    locked = client.put(f"/api/posts/{ids[0]}", json={"body": "Too late."})
    assert locked.status_code == 409


def test_decision_twice_is_a_conflict(client):
    ids = client.post(
        "/api/drafts",
        json={"role": "Data engineer", "title": STORIES[0].title, "count": 1},
    ).json()["post_ids"]
    client.post(f"/api/posts/{ids[0]}/decision", json={"decision": "rejected"})

    again = client.post(f"/api/posts/{ids[0]}/decision", json={"decision": "approved"})
    assert again.status_code == 409


def test_unknown_post_is_404(client):
    assert client.get("/api/posts/999").status_code == 404
    assert client.put("/api/posts/999", json={"body": "x"}).status_code == 404


def test_bad_draft_request_is_rejected(client):
    response = client.post("/api/drafts", json={"role": "x", "title": "y", "count": 0})
    assert response.status_code == 422


def test_drafts_run_in_background_and_can_be_polled(tmp_path):
    import time

    app = create_app(
        db_path=str(tmp_path / "bg.db"),
        model_factory=lambda: FakeChat(["background draft"]),
        get_persona=lambda role: PERSONA,
        get_headlines=lambda query: STORIES,
        actor="tester",
    )
    client = TestClient(app)
    job = client.post(
        "/api/drafts", json={"role": "Data engineer", "title": STORIES[0].title, "count": 1}
    ).json()
    assert job["job_id"]

    status = {}
    for _ in range(100):
        status = client.get(f"/api/jobs/{job['job_id']}").json()
        if status["status"] != "running":
            break
        time.sleep(0.05)
    assert status["status"] == "done"
    assert len(status["post_ids"]) == 1


def test_failed_draft_job_reports_the_error(tmp_path):
    import time

    class BrokenChat:
        def complete(self, system, user):
            raise RuntimeError("model is not running")

    app = create_app(
        db_path=str(tmp_path / "bg.db"),
        model_factory=lambda: BrokenChat(),
        get_persona=lambda role: PERSONA,
        get_headlines=lambda query: STORIES,
        actor="tester",
    )
    client = TestClient(app)
    job_id = client.post(
        "/api/drafts", json={"role": "Data engineer", "title": STORIES[0].title, "count": 1}
    ).json()["job_id"]
    status = {}
    for _ in range(100):
        status = client.get(f"/api/jobs/{job_id}").json()
        if status["status"] != "running":
            break
        time.sleep(0.05)
    assert status["status"] == "error"
    assert "model is not running" in status["error"]


def test_unknown_job_is_404(client):
    assert client.get("/api/jobs/missing").status_code == 404
