import pytest

from content_agent.drafter import draft_posts
from content_agent.llm import FakeChat
from content_agent.store import Store
from content_agent.workflow import create_drafts


@pytest.fixture
def store(tmp_path):
    s = Store(str(tmp_path / "test.db"))
    yield s
    s.close()


def test_draft_posts_returns_requested_count():
    model = FakeChat(["first post", "second post"])
    drafts = draft_posts(model, "topic", "notes", count=2)
    assert drafts == ["first post", "second post"]
    assert len(model.calls) == 2


def test_draft_posts_rejects_zero_count():
    with pytest.raises(ValueError):
        draft_posts(FakeChat([]), "topic", "notes", count=0)


def test_create_drafts_stores_every_draft_as_pending(store):
    model = FakeChat(["A clean post about testing.", "Another clean post."])
    ids = create_drafts(model, store, "testing", "calm tone", count=2)

    assert len(ids) == 2
    for post_id in ids:
        post = store.get_post(post_id)
        assert post.status == "pending"
        assert post.topic == "testing"


def test_create_drafts_keeps_editor_problems(store):
    model = FakeChat(["Here is your post: it is guaranteed to work."])
    (post_id,) = create_drafts(model, store, "testing", "", count=1)

    post = store.get_post(post_id)
    assert post.status == "pending"
    assert len(post.problems) == 2
