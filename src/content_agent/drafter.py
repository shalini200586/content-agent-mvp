"""The drafting agent: turns a topic and voice notes into candidate posts."""

from content_agent.llm import ChatModel

SYSTEM_PROMPT = (
    "You write LinkedIn posts for a professional audience, in the first person. "
    "Sound like a specific person who has thought about this, not a press release. "
    "Open with a concrete observation, a small scene, or a question, never a greeting or 'Excited to share'. "
    "Vary sentence length, and use one concrete example or analogy. "
    "Use only facts that appear in the source material or the author's notes. "
    "Never invent personal experiences, employers, projects, or results for the author, even to make a story vivid. "
    "If a story would need details you do not have, write an observation or an opinion instead. "
    "Never add numbers, dates, names, quotes, or results that are not there; leave the detail out instead. "
    "Do not use emojis, 'game-changer', 'stay ahead', 'dive deep', or 'in today's fast-paced world'. "
    "Use at most three hashtags, at the end. "
    "Keep the post under 1200 characters."
)

X_SYSTEM_PROMPT = (
    "You write posts for X (formerly Twitter) in the first person. "
    "Sound like a specific person, not a brand. Be short and direct. "
    "Use only facts that appear in the source material or the author's notes. "
    "Never add numbers, dates, names, quotes, or results that are not there. "
    "Do not use emojis. Use at most one hashtag. "
    "Keep the post under 280 characters."
)
PLATFORM_PROMPTS = {"linkedin": SYSTEM_PROMPT, "x": X_SYSTEM_PROMPT}

# Each option takes a different angle, so the drafts are not three rewrites of one idea.
ANGLES = [
    "a counterintuitive take that challenges the usual view",
    "a scene from how the field works day to day, described without inventing any events",
    "a question for the reader that the topic raises",
    "a warning that people in this role should hear early",
]


def draft_posts(
    model: ChatModel,
    topic: str,
    voice_notes: str,
    count: int = 3,
    platform: str = "linkedin",
) -> list[str]:
    """Ask the model for `count` independent drafts on the same topic."""
    if count < 1:
        raise ValueError("count must be at least 1")
    if platform not in PLATFORM_PROMPTS:
        raise ValueError(f"unknown platform {platform!r}; use one of {', '.join(PLATFORM_PROMPTS)}")
    system_prompt = PLATFORM_PROMPTS[platform]

    drafts = []
    for option in range(1, count + 1):
        angle = ANGLES[(option - 1) % len(ANGLES)]
        user_prompt = (
            f"Topic: {topic}\n"
            f"Voice notes from the author: {voice_notes}\n"
            f"Write option {option} of {count}, taking {angle}. "
            "Return only the post text, with no introduction or commentary."
        )
        drafts.append(model.complete(system_prompt, user_prompt))
    return drafts
