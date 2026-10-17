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
