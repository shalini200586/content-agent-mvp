"""A small discovery agent: search, judge relevance, and search again when results are weak.

The loop is deliberately simple and every step is recorded, so the author can see
what the agent searched, what it kept, and why it searched again.

    1. Search the news sources for each query.
    2. Ask the model which headlines really fit the author's niche.
    3. If fewer than `min_topics` topics were found, ask the model for new queries
       and go back to step 1, up to `rounds` times.
"""

import re
from dataclasses import dataclass, field
from typing import Callable

from content_agent.llm import ChatModel
from content_agent.research import Headline, Topic, discover_topics

PLAN_SYSTEM_PROMPT = (
    "You search the news for a creator. Given their niche and the searches already tried, "
    "suggest three new short news search queries (one to four words each) that find what is "
    "happening now in their niche. Reply with the queries, one per line, and nothing else."
)
PICK_SYSTEM_PROMPT = (
    "You judge news headlines for a creator. Say which numbered headlines are about the creator's niche "
    "and would support a post they could write. Reply with the numbers only, separated by commas. "
    "Reply NONE if no headline fits."
)
MAX_TITLES_PER_QUERY = 30  # keeps the prompt small enough for a local model


@dataclass
class AgentRun:
    topics: list[Topic]
    steps: list[str] = field(default_factory=list)
    queries: list[str] = field(default_factory=list)


def plan_queries(model: ChatModel, niche: str, tried: list[str]) -> list[str]:
    reply = model.complete(
        PLAN_SYSTEM_PROMPT,
        f"Niche: {niche}\nSearches already tried: {', '.join(tried) or 'none'}",
    )
    queries = []
    for line in reply.splitlines():
        query = line.strip().strip("-*.0123456789) ").strip()
        if query and query.lower() not in {q.lower() for q in tried + queries} and len(query) <= 60:
            queries.append(query)
    return queries[:3]


def pick_relevant(model: ChatModel, niche: str, titles: list[str]) -> set[int]:
    """Indices of the headlines the model judges relevant to the niche."""
    numbered = "\n".join(f"{i + 1}. {title}" for i, title in enumerate(titles))
    reply = model.complete(PICK_SYSTEM_PROMPT, f"Niche: {niche}\nHeadlines:\n{numbered}")
    if reply.strip().upper().startswith("NONE"):
        return set()
    picked = {int(n) - 1 for n in re.findall(r"\d+", reply)}
    return {i for i in picked if 0 <= i < len(titles)}


def run_discovery(
    model: ChatModel,
    niche: str,
    interests: list[str],
    get_headlines: Callable[[str], list[Headline]],
    rounds: int = 2,
    min_topics: int = 3,
    limit: int = 8,
) -> AgentRun:
    run = AgentRun(topics=[])
    queries = list(interests)
    relevant: dict[str, list[Headline]] = {}

    for round_number in range(1, rounds + 1):
        found: list[tuple[str, Headline]] = []
        for query in queries:
            try:
                stories = get_headlines(query)
            except OSError as error:
                run.steps.append(f"Searching '{query}' failed: {error}")
                continue
            run.steps.append(f"Searched '{query}': {len(stories)} stories")
            found.extend((query, story) for story in stories[:MAX_TITLES_PER_QUERY])
            run.queries.append(query)

        if found:
            picked = pick_relevant(model, niche, [story.title for _, story in found])
            for index in sorted(picked):
                query, story = found[index]
                relevant.setdefault(query, []).append(story)
            run.steps.append(f"Round {round_number}: kept {len(picked)} of {len(found)} stories as relevant")

        run.topics = discover_topics(relevant, limit=limit)
        run.steps.append(f"Round {round_number}: {len(run.topics)} topic(s) found")
        if len(run.topics) >= min_topics or round_number == rounds:
            break

        queries = plan_queries(model, niche, run.queries)
        if not queries:
            run.steps.append("No new search ideas from the model; stopping")
            break
        run.steps.append(f"Trying new searches: {', '.join(queries)}")

    return run
