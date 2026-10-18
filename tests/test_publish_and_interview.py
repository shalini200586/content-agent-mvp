import pytest
from fastapi.testclient import TestClient

from content_agent.api import create_app
from content_agent.llm import FakeChat
from content_agent.profile import propose_profile, interview_question
from content_agent.publish import (
    DryRunPublisher,
    LinkedInPublisher,
    PublishError,
    XPublisher,
    publisher_for,
)
from content_agent.research import Headline, Persona

PERSONA = Persona(title="Data engineer", summary="Builds data pipelines.", url="https://example.org")
STORY = Headline(title="Pipelines get faster", link="https://news.example/1", source="Outlet A", published=None)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("CONTENT_AGENT_PUBLISH", raising=False)
    app = create_app(
        db_path=str(tmp_path / "api.db"),
        model_factory=lambda: FakeChat(["A clean post about pipelines."]),
        get_persona=lambda role: PERSONA,
        get_headlines=lambda query: [STORY],
        actor="tester",
    )
    return TestClient(app)


def draft(client, platform="linkedin"):
    return client.post(
        "/api/drafts",
        json={"role": "Data engineer", "title": STORY.title, "count": 1, "platform": platform},
    ).json()["post_ids"][0]


def test_pending_post_cannot_be_published(client):
    post_id = draft(client)
    assert client.post(f"/api/posts/{post_id}/publish").status_code == 409


def test_default_mode_is_dry_run_and_records_once(client):
    post_id = draft(client)
    client.post(f"/api/posts/{post_id}/decision", json={"decision": "approved"})

    first = client.post(f"/api/posts/{post_id}/publish")
    assert first.status_code == 200
    assert first.json() == {"mode": "dry-run", "result": "dry-run: not sent"}

    history = client.get(f"/api/posts/{post_id}").json()["history"]
    assert history[-1]["event"] == "published"
    assert history[-1]["actor"] == "tester"

    assert client.post(f"/api/posts/{post_id}/publish").status_code == 409


def test_live_mode_without_token_is_refused(client, monkeypatch):
    monkeypatch.setenv("CONTENT_AGENT_PUBLISH", "live")
    post_id = draft(client, platform="x")
    client.post(f"/api/posts/{post_id}/decision", json={"decision": "approved"})
    response = client.post(f"/api/posts/{post_id}/publish")
    assert response.status_code == 502
    assert "X_ACCESS_TOKEN" in response.json()["detail"]


def test_publish_status_reports_mode(client, monkeypatch):
    assert client.get("/api/publish/status").json() == {"mode": "dry-run"}
    monkeypatch.setenv("CONTENT_AGENT_PUBLISH", "live")
    assert client.get("/api/publish/status").json() == {"mode": "live"}


def test_x_publisher_sends_text_and_returns_link():
    sent = {}

    def fake_post(url, body, headers):
        sent.update(url=url, body=body, headers=headers)
        return {"data": {"id": "123"}}

    link = XPublisher("token", post=fake_post).publish("hello")
    assert sent["url"].endswith("/2/tweets")
    assert sent["body"] == {"text": "hello"}
    assert sent["headers"]["Authorization"] == "Bearer token"
    assert link == "https://x.com/i/web/status/123"


def test_linkedin_publisher_sends_commentary_as_the_author():
    sent = {}
    LinkedInPublisher("token", "urn:li:person:1", post=lambda u, b, h: sent.update(body=b) or {}).publish("hi")
    assert sent["body"]["commentary"] == "hi"
    assert sent["body"]["author"] == "urn:li:person:1"


def test_publisher_selection(monkeypatch):
    assert isinstance(publisher_for("x", env={}), DryRunPublisher)
    env = {"CONTENT_AGENT_PUBLISH": "live", "LINKEDIN_ACCESS_TOKEN": "t", "LINKEDIN_AUTHOR_URN": "urn:li:person:1"}
    assert isinstance(publisher_for("linkedin", env=env), LinkedInPublisher)
    with pytest.raises(PublishError):
        publisher_for("linkedin", env={"CONTENT_AGENT_PUBLISH": "live"})


def test_interview_asks_five_questions_then_stops(client):
    history = []
    for i in range(5):
        response = client.post("/api/profile/interview/question", json={"history": history}).json()
        assert response["done"] is False
        history.append({"question": response["question"], "answer": f"answer {i}"})
    final = client.post("/api/profile/interview/question", json={"history": history}).json()
    assert final["done"] is True


def test_profile_is_parsed_from_labelled_lines():
    model = FakeChat(["NICHE: Data engineering\nSTANCE: Reliable pipelines matter.\nVOICE: Calm and direct."])
    profile = propose_profile(model, [("Who is it for?", "Engineers")])
    assert profile.niche == "Data engineering"
    assert profile.stance == "Reliable pipelines matter."
    assert profile.voice == "Calm and direct."


def test_profile_falls_back_to_the_authors_words_when_format_is_ignored():
    profile = propose_profile(FakeChat(["Sure, here is a profile!"]), [("Tone?", "Warm and honest")])
    assert profile.voice == "Warm and honest"
    assert profile.niche == ""


def test_interview_question_falls_back_when_model_is_silent():
    assert interview_question(FakeChat([" "]), []).endswith("?")
