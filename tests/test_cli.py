import pytest

from content_agent import cli
from content_agent.llm import FakeChat
from content_agent.store import Store


@pytest.fixture
def db(tmp_path):
    return str(tmp_path / "test.db")


def run(db, *args):
    return cli.main(["--db", db, *args])


def seed(db, count, status_for=None):
    """Add posts directly to the database. Returns their ids."""
    store = Store(db)
    ids = []
    for i in range(count):
        post_id = store.add_post(f"topic {i}", f"Body {i}", [])
        if status_for:
            store.decide(post_id, status_for, actor="tester")
        ids.append(post_id)
    store.close()
    return ids


def test_draft_saves_pending_posts(db, monkeypatch, capsys):
    monkeypatch.setattr(cli, "OllamaChat", lambda **_: FakeChat(["Post one.", "Post two."]))

    assert run(db, "draft", "testing", "--count", "2") == 0

    out = capsys.readouterr().out
    assert "2 draft(s) saved as pending." in out
    store = Store(db)
    assert [p.status for p in store.list_posts()] == ["pending", "pending"]
    store.close()


def test_list_filters_by_status(db, capsys):
    seed(db, 2)
    store = Store(db)
    store.decide(1, "approved", actor="tester")
    store.close()

    run(db, "list", "--status", "approved")

    out = capsys.readouterr().out
    assert "#1  [approved]" in out
    assert "#2" not in out


def test_list_shows_more_than_one_page(db, capsys):
    seed(db, 60)

    run(db, "list")

    out = capsys.readouterr().out
    assert "#60  [pending]" in out
    assert len(out.strip().splitlines()) == 60


def test_approve_records_the_operating_user(db, monkeypatch, capsys):
    seed(db, 1)
    monkeypatch.setattr(cli.getpass, "getuser", lambda: "reviewer")

    assert run(db, "approve", "1", "--note", "good") == 0

    assert "Post #1 is now approved." in capsys.readouterr().out
    store = Store(db)
    trail = store.audit_trail(1)
    assert trail[-1]["actor"] == "reviewer"
    assert trail[-1]["detail"] == "good"
    store.close()


def test_decision_is_final(db, capsys):
    seed(db, 1)
    assert run(db, "reject", "1") == 0

    assert run(db, "approve", "1") == 1
    assert "decisions are final" in capsys.readouterr().err


def test_unknown_post_returns_error(db, capsys):
    assert run(db, "show", "99") == 1
    assert "no post with id 99" in capsys.readouterr().err


def test_export_writes_every_approved_post(db, tmp_path):
    ids = seed(db, 55, status_for="approved")
    folder = tmp_path / "out"

    assert run(db, "export", str(folder)) == 0

    files = sorted(folder.glob("post-*.txt"))
    assert len(files) == len(ids) == 55
    assert (folder / f"post-{ids[-1]}.txt").read_text(encoding="utf-8") == "Body 54\n"


def test_export_skips_unapproved_posts(db, tmp_path):
    seed(db, 1)  # stays pending
    folder = tmp_path / "out"

    run(db, "export", str(folder))

    assert list(folder.glob("post-*.txt")) == []
