"""Runs one content cycle: draft several options, review each, store them as pending.

Nothing is approved here. Every draft waits for a human decision, even if the
editor found no problems.
"""

from content_agent.drafter import draft_posts
from content_agent.editor import review_post
from content_agent.llm import ChatModel
from content_agent.store import Store


def create_drafts(
    model: ChatModel,
    store: Store,
    topic: str,
    voice_notes: str,
    count: int = 3,
) -> list[int]:
    """Draft, review, and store. Returns the new post IDs."""
    bodies = draft_posts(model, topic, voice_notes, count=count)

    post_ids = []
    for body in bodies:
        review = review_post(body)
        post_id = store.add_post(topic, body, review.problems)
        post_ids.append(post_id)
    return post_ids
