"""SQLite storage for drafts, their review status, and an audit log.

Lifecycle of a post:

    pending --approve--> approved
    pending --reject---> rejected

Once a post is approved or rejected, its status cannot change. The store
enforces this, so a bug elsewhere can't quietly re-open a decision.
"""

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    topic      TEXT NOT NULL,
    body       TEXT NOT NULL,
    status     TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'rejected')),
    problems   TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_posts_status ON posts(status, id);

CREATE TABLE IF NOT EXISTS audit_log (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id INTEGER NOT NULL REFERENCES posts(id),
    event   TEXT NOT NULL,
    detail  TEXT NOT NULL DEFAULT '',
    actor   TEXT NOT NULL DEFAULT '',
    at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sources (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id   INTEGER NOT NULL REFERENCES posts(id),
    title     TEXT NOT NULL,
    outlet    TEXT NOT NULL DEFAULT '',
    link      TEXT NOT NULL DEFAULT '',
    published TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_sources_post ON sources(post_id);
"""


@dataclass
class Post:
    id: int
    topic: str
    body: str
    status: str
    problems: list[str]
    created_at: str


class PostNotFound(Exception):
    pass


class InvalidTransition(Exception):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: str = "content_agent.db"):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    def add_post(
        self, topic: str, body: str, problems: list[str], actor: str = "drafter"
    ) -> int:
        cursor = self.conn.execute(
            "INSERT INTO posts (topic, body, status, problems, created_at) "
            "VALUES (?, ?, 'pending', ?, ?)",
            (topic, body, "\n".join(problems), _now()),
        )
        post_id = cursor.lastrowid
        self._log(post_id, "created", f"{len(problems)} editor problem(s)", actor)
        self.conn.commit()
        return post_id

    def get_post(self, post_id: int) -> Post:
        row = self.conn.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone()
        if row is None:
            raise PostNotFound(f"no post with id {post_id}")
        return _to_post(row)

    def list_posts(
        self, status: str | None = None, limit: int = 50, after_id: int = 0
    ) -> list[Post]:
        """Return one page of posts, oldest first. Pass the last id seen as `after_id`."""
        if limit < 1 or limit > 500:
            raise ValueError("limit must be between 1 and 500")
        if status is None:
            rows = self.conn.execute(
                "SELECT * FROM posts WHERE id > ? ORDER BY id LIMIT ?", (after_id, limit)
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM posts WHERE status = ? AND id > ? ORDER BY id LIMIT ?",
                (status, after_id, limit),
            ).fetchall()
        return [_to_post(row) for row in rows]

    def decide(self, post_id: int, decision: str, actor: str, note: str = "") -> Post:
        """Move a pending post to 'approved' or 'rejected', recording who decided."""
        if decision not in ("approved", "rejected"):
            raise ValueError(f"decision must be 'approved' or 'rejected', not {decision!r}")
        if not actor.strip():
            raise ValueError("a decision needs an actor")

        post = self.get_post(post_id)
        if post.status != "pending":
            raise InvalidTransition(
                f"post {post_id} is already {post.status}; decisions are final"
            )

        self.conn.execute(
            "UPDATE posts SET status = ? WHERE id = ?", (decision, post_id)
        )
        self._log(post_id, decision, note, actor)
        self.conn.commit()
        return self.get_post(post_id)

    def update_body(self, post_id: int, body: str, problems: list[str], actor: str) -> Post:
        """Save an edit to a pending draft. Approved and rejected posts cannot change."""
        if not actor.strip():
            raise ValueError("an edit needs an actor")
        if not body.strip():
            raise ValueError("a post cannot be empty")

        post = self.get_post(post_id)
        if post.status != "pending":
            raise InvalidTransition(f"post {post_id} is already {post.status}; it cannot be edited")

        self.conn.execute(
            "UPDATE posts SET body = ?, problems = ? WHERE id = ?",
            (body, "\n".join(problems), post_id),
        )
        self._log(post_id, "edited", f"{len(problems)} editor problem(s) after edit", actor)
        self.conn.commit()
        return self.get_post(post_id)

    def add_sources(self, post_id: int, sources: list[tuple[str, str, str, str]]) -> None:
        """Record the stories a draft was built from: (title, outlet, link, published)."""
        self.conn.executemany(
            "INSERT INTO sources (post_id, title, outlet, link, published) VALUES (?, ?, ?, ?, ?)",
            [(post_id, title, outlet, link, published) for title, outlet, link, published in sources],
        )
        self.conn.commit()

    def get_sources(self, post_id: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT title, outlet, link, published FROM sources WHERE post_id = ? ORDER BY id",
            (post_id,),
        ).fetchall()

    def audit_trail(self, post_id: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT event, detail, actor, at FROM audit_log WHERE post_id = ? ORDER BY id",
            (post_id,),
        ).fetchall()

    def _log(self, post_id: int, event: str, detail: str, actor: str) -> None:
        self.conn.execute(
            "INSERT INTO audit_log (post_id, event, detail, actor, at) VALUES (?, ?, ?, ?, ?)",
            (post_id, event, detail, actor, _now()),
        )


def _to_post(row: sqlite3.Row) -> Post:
    problems = row["problems"].split("\n") if row["problems"] else []
    return Post(
        id=row["id"],
        topic=row["topic"],
        body=row["body"],
        status=row["status"],
        problems=problems,
        created_at=row["created_at"],
    )
