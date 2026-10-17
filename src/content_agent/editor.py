"""The editor: fixed, testable rules that every draft must pass before a human sees it.

These are deliberately rule-based. A rule can be tested, explained, and
changed in one place. An LLM reviewer can be added later as a second opinion.
"""

import re
from dataclasses import dataclass, field

MAX_CHARS = 1200
MAX_HASHTAGS = 5
MAX_UNSUPPORTED_REPORTED = 5
BANNED_PHRASES = ["guaranteed", "going viral", "[insert", "lorem ipsum"]
PREAMBLE_STARTS = ("here is", "here's", "sure", "certainly")

# Capitalised words that start sentences or are common in prose. They are not facts.
COMMON_WORDS = {
    "I", "I'm", "I've", "We", "We're", "It", "It's", "This", "That", "These", "Those",
    "The", "A", "An", "And", "But", "Or", "If", "When", "Where", "What", "Why", "How",
    "My", "Our", "Your", "You", "Here", "There", "Today", "Yesterday", "Most", "Many",
    "Some", "Just", "Also", "Still", "Even", "Every", "No", "Not", "So", "In", "On",
    "At", "For", "From", "With", "After", "Before", "Stay", "Let", "Think", "Imagine",
}
NUMBER_PATTERN = re.compile(r"\d[\d,.]*\d%?|\d%?")
NAME_PATTERN = re.compile(r"(?<![#\w])[A-Z][\w&'-]*(?:\s+[A-Z][\w&'-]*)*")  # hashtags are not facts
SENTENCE_ENDS = (".", "!", "?", '"', "“", "”")


@dataclass
class Review:
    problems: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.problems


def checkable_details(text: str) -> list[str]:
    """Numbers, dates, and names in a draft. These are what a fact check can verify."""
    details = NUMBER_PATTERN.findall(text)
    for match in NAME_PATTERN.finditer(text):
        words = [w for w in match.group().split() if w not in COMMON_WORDS]
        if not words:
            continue
        # A single capitalised word that opens a sentence is just prose, not a name.
        opens_sentence = match.start() == 0 or text[: match.start()].rstrip().endswith(SENTENCE_ENDS)
        if len(words) == 1 and opens_sentence:
            continue
        details.append(" ".join(words))
    seen: dict[str, None] = {}
    for detail in details:
        seen.setdefault(detail.strip(".,"), None)
    return [d for d in seen if d]


def unsupported_details(text: str, sources: list[str]) -> list[str]:
    """Details in the draft that do not appear in any source. Matching ignores case and commas."""
    corpus = " ".join(sources).lower().replace(",", "")
    return [d for d in checkable_details(text) if d.lower().replace(",", "") not in corpus]


def review_post(text: str, sources: list[str] | None = None) -> Review:
    stripped = text.strip()
    lowered = stripped.lower()
    problems: list[str] = []

    if not stripped:
        problems.append("post is empty")
        return Review(problems)

    if sources is not None:
        unsupported = unsupported_details(stripped, sources)
        for detail in unsupported[:MAX_UNSUPPORTED_REPORTED]:
            problems.append(f"fact check: {detail!r} is not in the source material")
        if len(unsupported) > MAX_UNSUPPORTED_REPORTED:
            problems.append(f"fact check: {len(unsupported) - MAX_UNSUPPORTED_REPORTED} more unsupported details")

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
