from content_agent.drafter import ANGLES, SYSTEM_PROMPT, draft_posts
from content_agent.editor import checkable_details, review_post, unsupported_details
from content_agent.llm import FakeChat
from content_agent.store import Store
from content_agent.workflow import create_drafts

SOURCES = [
    "Penn Engineering launches a Master's Degree in Data Science in 2026.",
    "The program enrols 60 students each year.",
]


def test_numbers_and_names_are_extracted_but_common_words_are_not():
    details = checkable_details("The Penn Engineering program enrols 60 students. I think it matters.")
    assert "Penn Engineering" in details
    assert "60" in details
    assert "I" not in details and "The" not in details


def test_supported_details_pass():
    assert unsupported_details("Penn Engineering enrols 60 students.", SOURCES) == []


def test_invented_number_is_flagged():
    flagged = unsupported_details("The program enrols 80 students.", SOURCES)
    assert flagged == ["80"]


def test_invented_name_is_flagged():
    flagged = unsupported_details("Stanford Engineering enrols 60 students.", SOURCES)
    assert "Stanford Engineering" in flagged


def test_matching_ignores_case_and_thousands_separators():
    assert unsupported_details("It has 1,200 seats.", ["The hall seats 1200 people."]) == []


def test_review_reports_unsupported_details_only_when_sources_given():
    text = "Penn Engineering enrols 80 students."
    assert all("fact check" not in p for p in review_post(text).problems)
    problems = review_post(text, sources=SOURCES).problems
    assert any("'80'" in p for p in problems)


def test_drafts_take_different_angles():
    model = FakeChat(["a", "b", "c", "d"])
    draft_posts(model, "topic", "notes", count=4)
    prompts = [user for _, user in model.calls]
    assert ANGLES[0] in prompts[0]
    assert ANGLES[1] in prompts[1]
    assert len({p.split("taking ")[1].split(". ")[0] for p in prompts}) == 4


def test_system_prompt_forbids_invented_facts_and_stock_phrasing():
    assert "Never add numbers" in SYSTEM_PROMPT
    assert "game-changer" in SYSTEM_PROMPT


def test_create_drafts_flags_unsupported_and_stores_them_pending(tmp_path):
    store = Store(str(tmp_path / "fc.db"))
    model = FakeChat(["Stanford Engineering enrols 80 students.", "A clean draft."])
    ids = create_drafts(model, store, "topic", "notes", count=2, sources=SOURCES)
    flagged = store.get_post(ids[0])
    clean = store.get_post(ids[1])
    assert flagged.problems and flagged.status == "pending"
    assert clean.problems == []
    store.close()


def test_sources_are_stored_per_post(tmp_path):
    store = Store(str(tmp_path / "src.db"))
    post_id = store.add_post("topic", "body", [])
    store.add_sources(post_id, [("Headline A", "Outlet A", "https://a.example", "2026-10-16")])
    rows = store.get_sources(post_id)
    assert len(rows) == 1
    assert rows[0]["outlet"] == "Outlet A"
    assert rows[0]["link"] == "https://a.example"
    store.close()


def test_sentence_opening_words_are_not_flagged_as_names():
    text = "Typically, data teams wait. Rather than wait, we automate. Suddenly it works."
    assert checkable_details(text) == []


def test_multi_word_names_are_still_flagged_when_unsupported():
    flagged = unsupported_details("We chose Databricks last year.", ["Lakeflow launches on Azure."])
    assert "Databricks" in flagged


def test_hashtags_are_not_checked_as_facts():
    assert checkable_details("Good read. #DataEngineering #AIInData") == []
