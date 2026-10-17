"""The drafting agent: turns a topic and voice notes into candidate posts."""

from content_agent.llm import ChatModel

SYSTEM_PROMPT = (
    "You write LinkedIn posts for a professional audience. "
    "Write in plain, first-person language. "
    "Do not invent statistics, names, quotes, or results. "
    "Keep the post under 1200 characters."
)


def draft_posts(
    model: ChatModel,
    topic: str,
    voice_notes: str,
    count: int = 3,
) -> list[str]:
    """Ask the model for `count` independent drafts on the same topic."""
    if count < 1:
        raise ValueError("count must be at least 1")

    drafts = []
    for option in range(1, count + 1):
        user_prompt = (
            f"Topic: {topic}\n"
            f"Voice notes from the author: {voice_notes}\n"
            f"Write option {option} of {count}. "
            "Return only the post text, with no introduction or commentary."
        )
        drafts.append(model.complete(SYSTEM_PROMPT, user_prompt))
    return drafts
