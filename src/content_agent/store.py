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

CREATE TABLE IF NOT EXISTS audit_log (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id INTEGER NOT NULL REFERENCES posts(id),
    event   TEXT NOT NULL,
    detail  TEXT NOT NULL DEFAULT '',
    at      TEXT NOT NULL
);
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

    def add_post(self, topic: str, body: str, problems: list[str]) -> int:
        cursor = self.conn.execute(
            "INSERT INTO posts (topic, body, status, problems, created_at) "
            "VALUES (?, ?, 'pending', ?, ?)",
            (topic, body, "\n".join(problems), _now()),
        )
        post_id = cursor.lastrowid
        self._log(post_id, "created", f"{len(problems)} editor problem(s)")
        self.conn.commit()
        return post_id

    def get_post(self, post_id: int) -> Post:
        row = self.conn.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone()
        if row is None:
            raise PostNotFound(f"no post with id {post_id}")
        return _to_post(row)

    def list_posts(self, status: str | None = None) -> list[Post]:
        if status is None:
            rows = self.conn.execute("SELECT * FROM posts ORDER BY id").fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM posts WHERE status = ? ORDER BY id", (status,)
            ).fetchall()
        return [_to_post(row) for row in rows]

    def decide(self, post_id: int, decision: str, note: str = "") -> Post:
        """Move a pending post to 'approved' or 'rejected'."""
        if decision not in ("approved", "rejected"):
            raise ValueError(f"decision must be 'approved' or 'rejected', not {decision!r}")

        post = self.get_post(post_id)
        if post.status != "pending":
            raise InvalidTransition(
                f"post {post_id} is already {post.status}; decisions are final"
            )

        self.conn.execute(
            "UPDATE posts SET status = ? WHERE id = ?", (decision, post_id)
        )
        self._log(post_id, decision, note)
        self.conn.commit()
        return self.get_post(post_id)

    def audit_trail(self, post_id: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT event, detail, at FROM audit_log WHERE post_id = ? ORDER BY id",
            (post_id,),
        ).fetchall()

    def _log(self, post_id: int, event: str, detail: str) -> None:
        self.conn.execute(
            "INSERT INTO audit_log (post_id, event, detail, at) VALUES (?, ?, ?, ?)",
            (post_id, event, detail, _now()),
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
