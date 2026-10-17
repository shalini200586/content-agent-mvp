import pytest

from content_agent.store import InvalidTransition, PostNotFound, Store


@pytest.fixture
def store(tmp_path):
    s = Store(str(tmp_path / "test.db"))
    yield s
    s.close()


def test_new_post_is_pending(store):
    post_id = store.add_post("testing", "Body text", [])
    post = store.get_post(post_id)
    assert post.status == "pending"
    assert post.problems == []


def test_problems_are_stored_and_read_back(store):
    post_id = store.add_post("testing", "Body", ["too long", "banned phrase"])
    assert store.get_post(post_id).problems == ["too long", "banned phrase"]


def test_approve_moves_post_and_logs_it(store):
    post_id = store.add_post("testing", "Body", [])
    post = store.decide(post_id, "approved", note="looks good")
    assert post.status == "approved"
    events = [row["event"] for row in store.audit_trail(post_id)]
    assert events == ["created", "approved"]


def test_decision_cannot_be_changed(store):
    post_id = store.add_post("testing", "Body", [])
    store.decide(post_id, "rejected")
    with pytest.raises(InvalidTransition):
        store.decide(post_id, "approved")
    assert store.get_post(post_id).status == "rejected"


def test_invalid_decision_value_is_rejected(store):
    post_id = store.add_post("testing", "Body", [])
    with pytest.raises(ValueError):
        store.decide(post_id, "published")


def test_missing_post_raises(store):
    with pytest.raises(PostNotFound):
        store.get_post(999)


def test_list_filters_by_status(store):
    a = store.add_post("t", "one", [])
    store.add_post("t", "two", [])
    store.decide(a, "approved")
    approved = store.list_posts("approved")
    assert [post.id for post in approved] == [a]
    assert len(store.list_posts()) == 2
