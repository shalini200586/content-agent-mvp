import pytest

from content_agent.drafter import SYSTEM_PROMPT, draft_posts
from content_agent.llm import FakeChat


def test_prompt_includes_topic_and_voice_notes():
    model = FakeChat(["draft"])
    draft_posts(model, "remote work", "calm, first person", count=1)

    system, user = model.calls[0]
    assert system == SYSTEM_PROMPT
    assert "Topic: remote work" in user
    assert "Voice notes from the author: calm, first person" in user


def test_each_option_is_numbered_in_its_prompt():
    model = FakeChat(["a", "b", "c"])
    draft_posts(model, "topic", "", count=3)

    prompts = [user for _, user in model.calls]
    assert "Write option 1 of 3." in prompts[0]
    assert "Write option 2 of 3." in prompts[1]
    assert "Write option 3 of 3." in prompts[2]


def test_default_count_is_three():
    model = FakeChat(["a", "b", "c"])
    assert len(draft_posts(model, "topic", "")) == 3


@pytest.mark.parametrize("count", [0, -1])
def test_rejects_count_below_one(count):
    with pytest.raises(ValueError):
        draft_posts(FakeChat([]), "topic", "", count=count)
