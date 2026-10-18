import pytest
from fastapi.testclient import TestClient

from content_agent.api import create_app
from content_agent.drafter import X_SYSTEM_PROMPT, draft_posts
from content_agent.llm import FakeChat
from content_agent.profile import Profile, describe_voice, load_profile, save_profile
from content_agent.research import Headline, Persona

PERSONA = Persona(title="Data engineer", summary="Builds data pipelines.", url="https://example.org")
STORY = Headline(title="Pipelines get faster", link="https://news.example/1", source="Outlet A", published=None)


def test_missing_profile_loads_empty(tmp_path):
    assert load_profile(tmp_path / "none.json") == Profile()


def test_profile_round_trips(tmp_path):
    path = tmp_path / "profile.json"
    save_profile(path, Profile(niche="data", stance="pipelines matter", voice="calm"))
    assert load_profile(path) == Profile(niche="data", stance="pipelines matter", voice="calm")


def test_x_drafts_use_the_short_prompt():
    model = FakeChat(["a short post"])
    draft_posts(model, "topic", "", count=1, platform="x")
    system, _ = model.calls[0]
    assert system == X_SYSTEM_PROMPT
    assert "280 characters" in system


def test_unknown_platform_is_rejected():
    with pytest.raises(ValueError):
        draft_posts(FakeChat([]), "topic", "", count=1, platform="myspace")


def test_describe_voice_uses_samples_and_returns_text():
    model = FakeChat(["Short sentences. Opens with a question."])
    assert describe_voice(model, "Some sample post text that is long enough.") == "Short sentences. Opens with a question."
    _, user = model.calls[0]
    assert "Sample posts" in user


@pytest.fixture
def client(tmp_path):
    app = create_app(
        db_path=str(tmp_path / "api.db"),
        model_factory=lambda: FakeChat(["x draft one", "x draft two"]),
        get_persona=lambda role: PERSONA,
        get_headlines=lambda query: [STORY],
        actor="tester",
        background=False,
    )
    return TestClient(app)


def test_profile_endpoints_save_and_return(client):
    assert client.get("/api/profile").json() == {"niche": "", "stance": "", "voice": ""}
    saved = client.put("/api/profile", json={"niche": "data", "stance": "pipelines", "voice": "calm"})
    assert saved.json() == {"niche": "data", "stance": "pipelines", "voice": "calm"}
    assert client.get("/api/profile").json()["niche"] == "data"


def test_scan_suggests_voice_without_saving(client):
    response = client.post("/api/profile/scan", json={"samples": "x" * 60})
    assert response.status_code == 200
    assert "voice" in response.json()
    assert client.get("/api/profile").json()["voice"] == ""


def test_x_draft_is_saved_with_platform_and_checked_at_280(client):
    ids = client.post(
        "/api/drafts",
        json={"role": "Data engineer", "title": STORY.title, "count": 1, "platform": "x"},
    ).json()["post_ids"]
    post = client.get(f"/api/posts/{ids[0]}").json()
    assert post["platform"] == "x"

    long_edit = client.put(f"/api/posts/{ids[0]}", json={"body": "a" * 281}).json()
    assert any("x limit is 280" in p for p in long_edit["problems"])


def test_profile_voice_is_used_when_request_has_none(tmp_path):
    model = FakeChat(["one draft"])
    app = create_app(
        db_path=str(tmp_path / "api.db"),
        model_factory=lambda: model,
        get_persona=lambda role: PERSONA,
        get_headlines=lambda query: [STORY],
        actor="tester",
        background=False,
    )
    save_profile(tmp_path / "profile.json", Profile(voice="warm and direct", stance="pipelines first"))

    TestClient(app).post("/api/drafts", json={"role": "Data engineer", "title": STORY.title, "count": 1})

    _, user = model.calls[0]
    assert "warm and direct" in user
    assert "Stance: pipelines first" in user
