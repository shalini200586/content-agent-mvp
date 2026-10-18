"""Research step: learn what a role does, find what is being covered for it, pick a topic.

Sources are free and need no API key:
- Wikipedia's REST summary endpoint, for what a role does.
- Google News RSS search, for current coverage of the role's field.

Picking the hot topic is deterministic. A headline scores higher when other
outlets cover the same story (shared significant words) and when it matches
the role's own vocabulary. No model is involved, so the choice is repeatable
and easy to explain.
"""

import json
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Callable
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request, urlopen

USER_AGENT = "content-agent-mvp/0.1 (local research step)"
STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "your", "what", "how",
    "why", "are", "new", "its", "after", "about", "into", "over", "more", "says",
    "will", "can", "has", "have", "not", "but", "you", "all", "one", "who",
}


@dataclass
class Persona:
    title: str
    summary: str
    url: str


@dataclass
class Headline:
    title: str
    link: str
    source: str
    published: datetime | None


def _get(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=15) as response:
        return response.read()


def fetch_persona(role: str, get: Callable[[str], bytes] = _get) -> Persona:
    """Describe what a role does, using its Wikipedia summary."""
    title = role.strip().replace(" ", "_")
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote(title)}"
    data = json.loads(get(url))
    if data.get("type") == "disambiguation" or not data.get("extract"):
        raise ValueError(f"no usable Wikipedia summary for {role!r}; try a more specific title")
    page = data["content_urls"]["desktop"]["page"]
    return Persona(title=data["title"], summary=data["extract"], url=page)


def fetch_headlines(query: str, get: Callable[[str], bytes] = _get) -> list[Headline]:
    """Recent news headlines matching a search query, newest first."""
    params = urlencode({"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"})
    root = ET.fromstring(get(f"https://news.google.com/rss/search?{params}"))

    headlines = []
    for item in root.iter("item"):
        raw_title = item.findtext("title") or ""
        # Google News appends " - Outlet" to every title; keep the outlet separately.
        title, _, outlet = raw_title.rpartition(" - ")
        if not title:
            title, outlet = raw_title, ""
        source = item.findtext("source") or outlet
        published = _parse_date(item.findtext("pubDate"))
        headlines.append(
            Headline(title=title.strip(), link=item.findtext("link") or "", source=source, published=published)
        )
    headlines.sort(key=lambda h: h.published or datetime.min, reverse=True)
    return headlines


def fetch_hn_headlines(query: str, get: Callable[[str], bytes] = _get) -> list[Headline]:
    """Recent Hacker News stories matching a query, newest first. Free, no key needed."""
    params = urlencode({"query": query, "tags": "story", "hitsPerPage": 30})
    data = json.loads(get(f"https://hn.algolia.com/api/v1/search_by_date?{params}"))

    headlines = []
    for hit in data.get("hits", []):
        title = (hit.get("title") or "").strip()
        if not title:
            continue
        link = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID', '')}"
        source = urlparse(link).netloc.removeprefix("www.") or "Hacker News"
        headlines.append(
            Headline(
                title=title,
                link=link,
                source=source,
                published=_parse_iso(hit.get("created_at")),
            )
        )
    return headlines


# GDELT asks for one request every five seconds from a single client.
GDELT_MIN_INTERVAL = 5.0
_gdelt_last_call = [0.0]


def fetch_gdelt_headlines(query: str, get: Callable[[str], bytes] = _get) -> list[Headline]:
    """Recent news articles from GDELT, a free index of world news. Requests are paced to its limit."""
    if get is _get:
        wait = GDELT_MIN_INTERVAL - (time.monotonic() - _gdelt_last_call[0])
        if wait > 0:
            time.sleep(wait)
        _gdelt_last_call[0] = time.monotonic()
    params = urlencode({"query": f'"{query}"', "mode": "ArtList", "format": "json", "maxrecords": 25, "timespan": "3d"})
    data = json.loads(get(f"https://api.gdeltproject.org/api/v2/doc/doc?{params}"))

    headlines = []
    for article in data.get("articles", []):
        title = (article.get("title") or "").strip()
        if not title or not article.get("url"):
            continue
        seen = article.get("seendate", "")
        published = None
        try:
            published = datetime.strptime(seen, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        except ValueError:
            pass
        headlines.append(
            Headline(
                title=title,
                link=article["url"],
                source=article.get("domain", ""),
                published=published,
            )
        )
    return headlines


def fetch_all_headlines(query: str, get: Callable[[str], bytes] = _get) -> list[Headline]:
    """Headlines from every source, newest first. A source that fails is skipped.

    Only if every source fails is the error raised, so one outage does not stop the page.
    """
    headlines: list[Headline] = []
    errors: list[Exception] = []
    for fetch in (fetch_headlines, fetch_hn_headlines, fetch_gdelt_headlines):
        try:
            headlines.extend(fetch(query, get=get))
        except (OSError, ValueError) as error:
            errors.append(error)
    if not headlines and errors:
        raise errors[0]
    headlines.sort(key=lambda h: h.published or datetime.min, reverse=True)
    return headlines


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 3 and w not in STOPWORDS}


# Press-release style headlines: staff moves, awards, and corporate announcements.
# They are real headlines, but they rarely make a post worth writing about.
PROMOTIONAL_PATTERN = re.compile(
    r"\b(appoints?|appointed|elevates?|elevated|promotes?|promoted|names?|named (?:as )?(?:head|chief|director|vp)"
    r"|to (?:director|head|chief|vp)|hires?|hired|joins?|awarded|recognized as|earns?|honou?red)\b",
    re.IGNORECASE,
)


def is_promotional(title: str) -> bool:
    return bool(PROMOTIONAL_PATTERN.search(title))


def pick_hot_topic(headlines: list[Headline], persona: Persona) -> tuple[Headline, list[Headline]]:
    """Return the headline with the most cross-outlet coverage, and the stories that back it.

    Two headlines count as the same story when they share at least three
    significant words. Role vocabulary breaks ties, and recency breaks the rest.
    Promotional headlines (staff moves, awards) are skipped unless nothing else exists.
    """
    if not headlines:
        raise ValueError("no headlines found for this role")

    role_words = _words(persona.title + " " + persona.summary)
    word_sets = [_words(h.title) for h in headlines]

    def score(index: int) -> tuple[int, int, int]:
        same_story = [
            other for other, words in enumerate(word_sets)
            if other != index and len(word_sets[index] & words) >= 3
        ]
        coverage = len(same_story) + 1
        relevance = len(word_sets[index] & role_words)
        recency = -index  # headlines are already newest first
        return (coverage, relevance, recency)

    # Prefer real news. Press-release headlines are used only when nothing else is left.
    candidates = [i for i, h in enumerate(headlines) if not is_promotional(h.title)] or list(range(len(headlines)))
    best = max(candidates, key=score)
    backing = [headlines[best]] + [
        h for i, h in enumerate(headlines)
        if i != best and len(word_sets[best] & word_sets[i]) >= 3
    ]
    return headlines[best], backing


def research_query(persona: Persona) -> str:
    """Search terms for the role: its Wikipedia title.

    Both news sources treat the words as "all of these", so the title alone keeps
    results on topic. Adding summary words with OR made Hacker News return almost nothing.
    """
    return persona.title


@dataclass
class Topic:
    headline: Headline
    keyword: str
    backing: list[Headline]


def _recency(headline: Headline) -> float:
    return headline.published.timestamp() if headline.published else 0.0


def discover_topics(headlines_by_keyword: dict[str, list[Headline]], limit: int = 8) -> list[Topic]:
    """Hot topics across several interests, ranked by how many outlets cover the same story.

    Stories that share three or more significant words count as one story. Promotional
    headlines rank last. Each topic keeps the stories that back it, for the fact check.
    """
    # A story is about an interest only if its title contains one of the interest's own terms.
    # This keeps "Practical Magic" (a film) out of a search for "practical" methods.
    pool = [
        (keyword, h)
        for keyword, found in headlines_by_keyword.items()
        for h in found
        if _terms(keyword) & _terms(h.title)
    ]
    if not pool:
        return []
    words = [_words(h.title) for _, h in pool]

    def group_of(i: int) -> list[int]:
        return [j for j in range(len(pool)) if j == i or len(words[i] & words[j]) >= 3]

    def rank(i: int) -> tuple:
        group = group_of(i)
        outlets = {pool[j][1].source for j in group if pool[j][1].source}
        return (not is_promotional(pool[i][1].title), len(outlets), len(group), _recency(pool[i][1]))

    used: set[int] = set()
    topics: list[Topic] = []
    for i in sorted(range(len(pool)), key=rank, reverse=True):
        if i in used:
            continue
        group = group_of(i)
        used.update(group)
        keyword, headline = pool[i]
        topics.append(Topic(headline=headline, keyword=keyword, backing=[pool[j][1] for j in group]))
        if len(topics) == limit:
            break
    return topics


def _terms(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in STOPWORDS and len(t) >= 2}
