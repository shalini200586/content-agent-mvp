"""The author's taste profile: niche, stance, and voice, kept in a small JSON file.

The profile is used as the default brief for every draft. A voice can also be
drafted from sample posts the author pastes in (see `describe_voice`).
"""

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from content_agent.llm import ChatModel

VOICE_SYSTEM_PROMPT = (
    "You describe how a person writes. You never quote their posts and never copy their phrases. "
    "Answer in two or three short sentences covering tone, typical sentence length, "
    "and how posts usually open."
)


@dataclass
class Profile:
    niche: str = ""
    stance: str = ""
    voice: str = ""
    interests: list[str] = field(default_factory=list)


def load_profile(path: str | Path) -> Profile:
    """Read the profile, or return an empty one if none has been saved yet."""
    file = Path(path)
    if not file.exists():
        return Profile()
    data = json.loads(file.read_text(encoding="utf-8"))
    return Profile(
        niche=str(data.get("niche", "")),
        stance=str(data.get("stance", "")),
        voice=str(data.get("voice", "")),
        interests=[str(x) for x in data.get("interests", []) if str(x).strip()],
    )


def save_profile(path: str | Path, profile: Profile) -> None:
    file = Path(path)
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps(asdict(profile), indent=2), encoding="utf-8")


def describe_voice(model: ChatModel, samples: str) -> str:
    """Draft a voice description from sample posts. The author reviews it before saving."""
    return model.complete(VOICE_SYSTEM_PROMPT, f"Sample posts by the author:\n{samples}").strip()


INTERVIEW_QUESTIONS = 5
INTERVIEW_SYSTEM_PROMPT = (
    "You are interviewing a creator who posts on LinkedIn or X, to learn how they want to sound. "
    "Ask exactly one short, specific question that is different from the earlier questions. "
    "Ask about their niche, audience, opinions, tone, or the kinds of posts they like. "
    "Reply with the question only."
)
PROFILE_SYSTEM_PROMPT = (
    "You write a creator profile from interview answers. Reply with exactly three lines, "
    "in this form, and nothing else:\n"
    "NICHE: <one short phrase>\n"
    "STANCE: <one sentence on what they believe>\n"
    "VOICE: <two or three sentences on tone and style>"
)


def interview_question(model: ChatModel, history: list[tuple[str, str]]) -> str | None:
    """The next interview question, or None once enough questions have been asked."""
    if len(history) >= INTERVIEW_QUESTIONS:
        return None
    transcript = "\n".join(f"Q: {q}\nA: {a}" for q, a in history) or "(no questions yet)"
    question = model.complete(INTERVIEW_SYSTEM_PROMPT, f"Earlier questions and answers:\n{transcript}")
    return question.strip() or "What topic do you most want to post about?"


def propose_profile(model: ChatModel, history: list[tuple[str, str]]) -> Profile:
    """Turn the interview into a profile the author can review and edit."""
    transcript = "\n".join(f"Q: {q}\nA: {a}" for q, a in history)
    reply = model.complete(PROFILE_SYSTEM_PROMPT, f"Interview:\n{transcript}")
    fields = {"NICHE": "", "STANCE": "", "VOICE": ""}
    for line in reply.splitlines():
        key, _, value = line.partition(":")
        key = key.strip().upper()
        if key in fields:
            fields[key] = value.strip()
    # If the model ignored the format, keep the author's own words rather than invent a profile.
    if not any(fields.values()):
        answers = " ".join(a for _, a in history)
        fields["VOICE"] = answers[:500]
    return Profile(niche=fields["NICHE"], stance=fields["STANCE"], voice=fields["VOICE"])


INTERESTS_SYSTEM_PROMPT = (
    "You read a creator's description and list what they post about, as search keywords. "
    "Reply with up to five keywords, each one to three words, separated by commas, and nothing else. "
    "Name subjects, tools, or people (for example 'Java', 'Spring Boot'). Never use adjectives or generic words."
)
MAX_INTERESTS = 5


def extract_interests(model: ChatModel, description: str, fallback: str = "") -> list[str]:
    """Search keywords for what the creator posts about. Falls back to the niche if the model gives nothing."""
    reply = model.complete(INTERESTS_SYSTEM_PROMPT, "Creator description:" + chr(10) + description)
    keywords: list[str] = []
    for part in re.split(r'[,;\n]', reply):
        keyword = part.strip().strip(".-*").strip()
        if keyword and keyword.lower() not in {k.lower() for k in keywords} and len(keyword) <= 60:
            keywords.append(keyword)
        if len(keywords) == MAX_INTERESTS:
            break
    if not keywords and fallback.strip():
        keywords = [fallback.strip()]
    return keywords
