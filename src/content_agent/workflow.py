"""Runs one content cycle: draft several options, review each, store them as pending.

Nothing is approved here. Every draft waits for a human decision, even if the
editor found no problems.
"""

from dataclasses import dataclass
from typing import Callable

from content_agent.drafter import draft_posts
from content_agent.editor import review_post
from content_agent.llm import ChatModel
from content_agent.research import (
    Headline,
    Persona,
    fetch_headlines,
    fetch_persona,
    pick_hot_topic,
    research_query,
)
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


@dataclass
class Research:
    persona: Persona
    topic: Headline
    sources: list[Headline]
    post_ids: list[int]


def research_and_draft(
    model: ChatModel,
    store: Store,
    role: str,
    count: int = 3,
    get_persona: Callable[[str], Persona] = fetch_persona,
    get_headlines: Callable[[str], list[Headline]] = fetch_headlines,
) -> Research:
    """Learn what a role does, find the hot topic in its field, and draft posts on it."""
    persona = get_persona(role)
    headlines = get_headlines(research_query(persona))
    topic, sources = pick_hot_topic(headlines, persona)

    # The drafter only sees the role's description and the stories it is built from.
    # Its rules already forbid invented facts, so the sources are the whole brief.
    brief = "\n".join(f"- {h.title} ({h.source or 'unknown outlet'})" for h in sources)
    voice_notes = f"Writing for: {persona.title}. {persona.summary}\nSource stories:\n{brief}"
    post_ids = create_drafts(model, store, f"{topic.title} ({topic.link})", voice_notes, count=count)
    return Research(persona=persona, topic=topic, sources=sources, post_ids=post_ids)
