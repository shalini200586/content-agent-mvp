"""Command-line interface: draft posts, review them, approve or reject, export."""

import argparse
import sys
from pathlib import Path

from content_agent.llm import OllamaChat
from content_agent.store import InvalidTransition, PostNotFound, Store
from content_agent.workflow import create_drafts


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="content-agent", description=__doc__)
    parser.add_argument("--db", default="content_agent.db", help="SQLite database file")
    sub = parser.add_subparsers(dest="command", required=True)

    draft = sub.add_parser("draft", help="generate draft posts for a topic")
    draft.add_argument("topic")
    draft.add_argument("--voice", default="", help="notes about the author's tone")
    draft.add_argument("--count", type=int, default=3)
    draft.add_argument("--model", default="qwen2.5:7b")
    draft.add_argument("--host", default=None, help="Ollama server URL")

    lst = sub.add_parser("list", help="list posts")
    lst.add_argument("--status", choices=["pending", "approved", "rejected"])

    show = sub.add_parser("show", help="show one post, its problems, and its history")
    show.add_argument("post_id", type=int)

    approve = sub.add_parser("approve", help="approve a pending post")
    approve.add_argument("post_id", type=int)
    approve.add_argument("--note", default="")

    reject = sub.add_parser("reject", help="reject a pending post")
    reject.add_argument("post_id", type=int)
    reject.add_argument("--note", default="")

    export = sub.add_parser("export", help="write approved posts to a folder")
    export.add_argument("folder")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    store = Store(args.db)
    try:
        if args.command == "draft":
            model = OllamaChat(model=args.model, host=args.host)
            ids = create_drafts(model, store, args.topic, args.voice, count=args.count)
            for post_id in ids:
                post = store.get_post(post_id)
                _print_post(post)
            print(f"\n{len(ids)} draft(s) saved as pending.")

        elif args.command == "list":
            for post in store.list_posts(args.status):
                flag = " (has problems)" if post.problems else ""
                print(f"#{post.id}  [{post.status}]  {post.topic}{flag}")

        elif args.command == "show":
            _print_post(store.get_post(args.post_id))
            print("\nHistory:")
            for event in store.audit_trail(args.post_id):
                print(f"  {event['at']}  {event['event']}  {event['detail']}")

        elif args.command in ("approve", "reject"):
            decision = "approved" if args.command == "approve" else "rejected"
            post = store.decide(args.post_id, decision, args.note)
            print(f"Post #{post.id} is now {post.status}.")

        elif args.command == "export":
            folder = Path(args.folder)
            folder.mkdir(parents=True, exist_ok=True)
            approved = store.list_posts("approved")
            for post in approved:
                (folder / f"post-{post.id}.txt").write_text(post.body + "\n", encoding="utf-8")
            print(f"Exported {len(approved)} approved post(s) to {folder}.")

    except (PostNotFound, InvalidTransition, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    finally:
        store.close()
    return 0


def _print_post(post) -> None:
    print(f"--- Post #{post.id} [{post.status}] topic: {post.topic}")
    print(post.body)
    if post.problems:
        print("Editor problems:")
        for problem in post.problems:
            print(f"  - {problem}")
    print()
