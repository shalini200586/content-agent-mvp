"""The author's taste profile: niche, stance, and voice, kept in a small JSON file.

The profile is used as the default brief for every draft. A voice can also be
drafted from sample posts the author pastes in (see `describe_voice`).
"""

import json
from dataclasses import asdict, dataclass
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
    )


def save_profile(path: str | Path, profile: Profile) -> None:
    file = Path(path)
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps(asdict(profile), indent=2), encoding="utf-8")


def describe_voice(model: ChatModel, samples: str) -> str:
    """Draft a voice description from sample posts. The author reviews it before saving."""
    return model.complete(VOICE_SYSTEM_PROMPT, f"Sample posts by the author:\n{samples}").strip()
