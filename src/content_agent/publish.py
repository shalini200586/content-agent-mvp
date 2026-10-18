"""Publishing approved posts to LinkedIn or X.

Nothing is published unless a human approved the post first, and by default
nothing is sent anywhere: the mode is "dry-run", which only returns a preview.
Set CONTENT_AGENT_PUBLISH=live and the platform token variables to post for real.

The HTTP calls follow the public APIs, but they have not been tested against a
live account here. Check the current API versions and terms before you go live.
"""

import json
import os
from typing import Callable, Protocol
from urllib.request import Request, urlopen

X_TWEETS_URL = "https://api.x.com/2/tweets"
LINKEDIN_POSTS_URL = "https://api.linkedin.com/rest/posts"
LINKEDIN_VERSION = "202405"


class PublishError(Exception):
    pass


class Publisher(Protocol):
    def publish(self, text: str) -> str:
        """Publish the text and return a link or id for it."""


class DryRunPublisher:
    def publish(self, text: str) -> str:
        return "dry-run: not sent"


def _post_json(url: str, body: dict, headers: dict[str, str]) -> dict:
    request = Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read()
            return json.loads(raw) if raw else {}
    except OSError as error:  # urllib.error.HTTPError is a subclass of OSError
        raise PublishError(f"request to {url} failed: {error}") from error


class XPublisher:
    def __init__(self, token: str, post: Callable[..., dict] = _post_json):
        self.token = token
        self.post = post

    def publish(self, text: str) -> str:
        data = self.post(X_TWEETS_URL, {"text": text}, {"Authorization": f"Bearer {self.token}"})
        tweet_id = data.get("data", {}).get("id", "")
        return f"https://x.com/i/web/status/{tweet_id}" if tweet_id else "posted"


class LinkedInPublisher:
    def __init__(self, token: str, author_urn: str, post: Callable[..., dict] = _post_json):
        self.token = token
        self.author_urn = author_urn
        self.post = post

    def publish(self, text: str) -> str:
        body = {
            "author": self.author_urn,
            "commentary": text,
            "visibility": "PUBLIC",
            "distribution": {"feedDistribution": "MAIN_FEED", "targetEntities": [], "thirdPartyDistributionChannels": []},
            "lifecycleState": "PUBLISHED",
            "isReshareDisabledByAuthor": False,
        }
        headers = {
            "Authorization": f"Bearer {self.token}",
            "LinkedIn-Version": LINKEDIN_VERSION,
            "X-Restli-Protocol-Version": "2.0.0",
        }
        self.post(LINKEDIN_POSTS_URL, body, headers)
        return "posted"


def publish_mode(env: dict[str, str] | None = None) -> str:
    env = os.environ if env is None else env
    return "live" if env.get("CONTENT_AGENT_PUBLISH", "dry-run").lower() == "live" else "dry-run"


def publisher_for(platform: str, env: dict[str, str] | None = None) -> Publisher:
    """The publisher for a platform. Raises PublishError if live mode lacks its credentials."""
    env = os.environ if env is None else env
    if publish_mode(env) == "dry-run":
        return DryRunPublisher()
    if platform == "x":
        token = env.get("X_ACCESS_TOKEN", "")
        if not token:
            raise PublishError("live X posting needs X_ACCESS_TOKEN")
        return XPublisher(token)
    if platform == "linkedin":
        token = env.get("LINKEDIN_ACCESS_TOKEN", "")
        author = env.get("LINKEDIN_AUTHOR_URN", "")
        if not token or not author:
            raise PublishError("live LinkedIn posting needs LINKEDIN_ACCESS_TOKEN and LINKEDIN_AUTHOR_URN")
        return LinkedInPublisher(token, author)
    raise PublishError(f"no publisher for platform {platform!r}")
