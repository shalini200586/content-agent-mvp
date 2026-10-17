"""A small wrapper around a chat model.

Agents depend on the ChatModel protocol, not on Ollama directly. That keeps the
agents easy to test (with FakeChat) and lets you switch providers later.
"""

from typing import Protocol

import ollama


class ChatModel(Protocol):
    def complete(self, system: str, user: str) -> str: ...


class OllamaChat:
    """Sends chat requests to a locally running Ollama server."""

    def __init__(self, model: str = "qwen2.5:7b", host: str | None = None):
        self.model = model
        self.client = ollama.Client(host=host) if host else ollama.Client()

    def complete(self, system: str, user: str) -> str:
        response = self.client.chat(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return response["message"]["content"].strip()


class FakeChat:
    """Returns canned replies in order. Used by the tests."""

    def __init__(self, replies: list[str]):
        self.replies = list(replies)
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        if not self.replies:
            raise RuntimeError("FakeChat ran out of replies")
        return self.replies.pop(0)
