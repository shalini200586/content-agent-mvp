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
    sources: list[str] | None = None,
) -> list[int]:
    """Draft, fact-check, and store. Returns the new post IDs.

    `sources` is the text a draft may rely on. By default that is the topic and
    the author's voice notes, since those are the only facts the author gave.
    """
    bodies = draft_posts(model, topic, voice_notes, count=count)
    material = sources if sources is not None else [topic, voice_notes]

    post_ids = []
    for body in bodies:
        review = review_post(body, sources=material)
        post_id = store.add_post(topic, body, review.problems)
        post_ids.append(post_id)
    return post_ids


@dataclass
class Research:
    persona: Persona
    topic: Headline
    sources: list[Headline]
    post_ids: list[int]


def draft_on_story(
    model: ChatModel,
    store: Store,
    persona: Persona,
    story: Headline,
    related: list[Headline] | None = None,
    count: int = 3,
    voice: str = "",
) -> list[int]:
    """Draft posts on one chosen story, grounded only in that story and its sources.

    `related` lists other stories on the same topic. They are optional extra sources.
    `voice` is the author's own tone notes, passed to the drafter as-is.
    """
    sources = [story] + [h for h in (related or []) if h.link != story.link]

    # The drafter only sees the role's description and the stories it is built from.
    # Its rules already forbid invented facts, so the sources are the whole brief.
    brief = "\n".join(f"- {h.title} ({h.source or 'unknown outlet'})" for h in sources)
    voice_notes = f"Writing for: {persona.title}. {persona.summary}\nSource stories:\n{brief}"
    if voice:
        voice_notes += f"\nAuthor's voice: {voice}"
    # Outlet names are facts too: a draft may say "Databricks" because a headline came from it.
    material = [persona.summary] + [h.title for h in sources] + [h.source for h in sources if h.source]
    post_ids = create_drafts(
        model, store, f"{story.title} ({story.link})", voice_notes, count=count, sources=material
    )

    # The role summary is stored too, so an edited draft is checked against the same material.
    stories = [(persona.summary, "Wikipedia", persona.url, "")] + [
        (h.title, h.source, h.link, h.published.isoformat() if h.published else "")
        for h in sources
    ]
    for post_id in post_ids:
        store.add_sources(post_id, stories)
    return post_ids


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
    post_ids = draft_on_story(model, store, persona, topic, related=sources, count=count)
    return Research(persona=persona, topic=topic, sources=sources, post_ids=post_ids)
