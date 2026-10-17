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


def test_approve_moves_post_and_logs_who_approved(store):
    post_id = store.add_post("testing", "Body", [])
    post = store.decide(post_id, "approved", actor="shalini", note="looks good")
    assert post.status == "approved"
    trail = store.audit_trail(post_id)
    assert [row["event"] for row in trail] == ["created", "approved"]
    assert trail[0]["actor"] == "drafter"
    assert trail[1]["actor"] == "shalini"


def test_decision_cannot_be_changed(store):
    post_id = store.add_post("testing", "Body", [])
    store.decide(post_id, "rejected", actor="shalini")
    with pytest.raises(InvalidTransition):
        store.decide(post_id, "approved", actor="shalini")
    assert store.get_post(post_id).status == "rejected"


def test_invalid_decision_value_is_rejected(store):
    post_id = store.add_post("testing", "Body", [])
    with pytest.raises(ValueError):
        store.decide(post_id, "published", actor="shalini")


def test_decision_needs_an_actor(store):
    post_id = store.add_post("testing", "Body", [])
    with pytest.raises(ValueError):
        store.decide(post_id, "approved", actor="  ")


def test_missing_post_raises(store):
    with pytest.raises(PostNotFound):
        store.get_post(999)


def test_list_filters_by_status(store):
    a = store.add_post("t", "one", [])
    store.add_post("t", "two", [])
    store.decide(a, "approved", actor="shalini")
    approved = store.list_posts("approved")
    assert [post.id for post in approved] == [a]
    assert len(store.list_posts()) == 2


def test_list_pages_with_keyset_cursor(store):
    ids = [store.add_post("t", f"post {i}", []) for i in range(5)]
    first = store.list_posts(limit=2)
    assert [p.id for p in first] == ids[:2]
    second = store.list_posts(limit=2, after_id=first[-1].id)
    assert [p.id for p in second] == ids[2:4]


def test_page_size_is_bounded(store):
    with pytest.raises(ValueError):
        store.list_posts(limit=0)
    with pytest.raises(ValueError):
        store.list_posts(limit=501)
