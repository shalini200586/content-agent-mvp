from content_agent.editor import MAX_CHARS, MAX_HASHTAGS, review_post


def test_clean_post_passes():
    review = review_post("Shipped a small improvement to our test suite this week.")
    assert review.passed
    assert review.problems == []


def test_empty_post_fails():
    review = review_post("   ")
    assert not review.passed
    assert review.problems == ["post is empty"]


def test_too_long_post_fails():
    review = review_post("a" * (MAX_CHARS + 1))
    assert not review.passed
    assert any("limit is" in problem for problem in review.problems)


def test_exactly_at_length_limit_passes():
    assert review_post("a" * MAX_CHARS).passed


def test_too_many_hashtags_fails():
    tags = " ".join(f"#tag{i}" for i in range(MAX_HASHTAGS + 1))
    review = review_post(f"Some update. {tags}")
    assert not review.passed


def test_banned_phrase_is_caught_case_insensitively():
    review = review_post("This approach is GUARANTEED to work.")
    assert not review.passed
    assert any("guaranteed" in problem for problem in review.problems)


def test_model_preamble_is_caught():
    review = review_post("Here is your post: we launched a new feature.")
    assert not review.passed
    assert any("preamble" in problem for problem in review.problems)


def test_word_forms_match_their_source():
    from content_agent.editor import unsupported_details

    sources = ["Snowflake acquires TensorStax to speed up agentic AI."]
    assert unsupported_details("Snowflake is acquiring TensorStax.", sources) == []


def test_x_platform_uses_280_character_limit():
    text = "a" * 281
    assert not review_post(text, platform="x").passed
    assert review_post("a" * 280, platform="x").passed
    assert review_post("a" * 281, platform="linkedin").passed


def test_unknown_platform_is_rejected():
    import pytest

    with pytest.raises(ValueError):
        review_post("hello", platform="myspace")
