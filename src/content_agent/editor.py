"""The editor: fixed, testable rules that every draft must pass before a human sees it.

These are deliberately rule-based. A rule can be tested, explained, and
changed in one place. An LLM reviewer can be added later as a second opinion.
"""

from dataclasses import dataclass, field

MAX_CHARS = 1200
MAX_HASHTAGS = 5
BANNED_PHRASES = ["guaranteed", "going viral", "[insert", "lorem ipsum"]
PREAMBLE_STARTS = ("here is", "here's", "sure", "certainly")


@dataclass
class Review:
    problems: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.problems


def review_post(text: str) -> Review:
    stripped = text.strip()
    lowered = stripped.lower()
    problems: list[str] = []

    if not stripped:
        problems.append("post is empty")
        return Review(problems)

    if len(stripped) > MAX_CHARS:
        problems.append(f"post is {len(stripped)} characters; limit is {MAX_CHARS}")

    hashtags = [word for word in stripped.split() if word.startswith("#")]
    if len(hashtags) > MAX_HASHTAGS:
        problems.append(f"{len(hashtags)} hashtags; limit is {MAX_HASHTAGS}")

    for phrase in BANNED_PHRASES:
        if phrase in lowered:
            problems.append(f"contains banned phrase: {phrase!r}")

    if lowered.startswith(PREAMBLE_STARTS):
        problems.append("starts with a model preamble instead of the post itself")

    return Review(problems)
