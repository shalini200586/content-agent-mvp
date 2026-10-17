import pytest

from content_agent.llm import with_retries


def test_retries_until_success():
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise ConnectionError("server busy")
        return "ok"

    assert with_retries(flaky, base_delay=0) == "ok"
    assert len(calls) == 3


def test_gives_up_after_last_attempt():
    def always_fails():
        raise TimeoutError("too slow")

    with pytest.raises(TimeoutError):
        with_retries(always_fails, attempts=2, base_delay=0)


def test_other_errors_are_not_retried():
    calls = []

    def bad_input():
        calls.append(1)
        raise ValueError("bad prompt")

    with pytest.raises(ValueError):
        with_retries(bad_input, base_delay=0)
    assert len(calls) == 1
