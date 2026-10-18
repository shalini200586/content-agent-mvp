"""HTTP API for the web UI.

A thin layer over the same store and workflow the CLI uses. Each request opens its
own database connection, so the API can run requests in parallel.
"""

import getpass
import os
import threading
import uuid
from dataclasses import asdict
from typing import Callable, Iterator, Literal

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from content_agent.agent import run_discovery
from content_agent.editor import review_post
from content_agent.profile import (
    Profile,
    describe_voice,
    extract_interests,
    interview_question,
    load_profile,
    propose_profile,
    save_profile,
)
from content_agent.publish import PublishError, publish_mode, publisher_for
from content_agent.llm import ChatModel, OllamaChat
from content_agent.research import (
    Headline,
    Persona,
    discover_topics,
    fetch_all_headlines,
    fetch_persona,
    pick_hot_topic,
    research_query,
)
from content_agent.store import InvalidTransition, Post, PostNotFound, Store
from content_agent.workflow import draft_on_story


class StoryIn(BaseModel):
    title: str = Field(min_length=3, max_length=300)
    link: str = Field(default="", max_length=2000)
    source: str = Field(default="", max_length=200)


class DraftRequest(BaseModel):
    # The role is optional: when the topic comes from discovery, the profile supplies the persona.
    role: str = Field(default="", max_length=120)
    title: str = Field(min_length=3, max_length=300)
    link: str = Field(default="", max_length=2000)
    source: str = Field(default="", max_length=200)
    voice: str = Field(default="", max_length=500)
    count: int = Field(default=3, ge=1, le=5)
    platform: Literal["linkedin", "x"] = "linkedin"
    related: list[StoryIn] = Field(default_factory=list, max_length=10)


class ProfileRequest(BaseModel):
    niche: str = Field(default="", max_length=200)
    stance: str = Field(default="", max_length=500)
    voice: str = Field(default="", max_length=500)
    interests: list[str] | None = Field(default=None, max_length=5)


class ScanRequest(BaseModel):
    samples: str = Field(min_length=50, max_length=8000)


class InterviewTurn(BaseModel):
    question: str = Field(max_length=500)
    answer: str = Field(max_length=1000)


class InterviewRequest(BaseModel):
    history: list[InterviewTurn] = Field(default_factory=list, max_length=10)


class EditRequest(BaseModel):
    body: str = Field(min_length=1, max_length=5000)


class DecisionRequest(BaseModel):
    decision: Literal["approved", "rejected"]
    note: str = Field(default="", max_length=500)


def create_app(
    db_path: str | None = None,
    model_factory: Callable[[], ChatModel] | None = None,
    get_persona: Callable[[str], Persona] = fetch_persona,
    get_headlines: Callable[[str], list[Headline]] = fetch_all_headlines,
    actor: str | None = None,
    background: bool = True,
) -> FastAPI:
    db_path = db_path or os.environ.get("CONTENT_AGENT_DB", "content_agent.db")
    make_model = model_factory or (
        lambda: OllamaChat(model=os.environ.get("CONTENT_AGENT_MODEL", "qwen2.5:7b"))
    )
    who = actor or os.environ.get("CONTENT_AGENT_ACTOR") or _current_user()
    profile_path = os.environ.get("CONTENT_AGENT_PROFILE") or os.path.join(
        os.path.dirname(os.path.abspath(db_path)), "profile.json"
    )
    persona_cache: dict[str, Persona] = {}
    # Drafting takes minutes on a laptop, so it runs in the background and the client polls.
    # State is kept in memory: fine for one local user, lost on restart.
    jobs: dict[str, dict] = {}

    app = FastAPI(title="Content Agent", version="0.1.0")

    @app.exception_handler(PostNotFound)
    def _not_found(_, error: PostNotFound):
        return JSONResponse({"detail": str(error)}, status_code=404)

    @app.exception_handler(InvalidTransition)
    def _conflict(_, error: InvalidTransition):
        return JSONResponse({"detail": str(error)}, status_code=409)

    @app.exception_handler(ValueError)
    def _bad_value(_, error: ValueError):
        return JSONResponse({"detail": str(error)}, status_code=422)

    def store_dep() -> Iterator[Store]:
        store = Store(db_path)
        try:
            yield store
        finally:
            store.close()

    def persona_for(role: str) -> Persona:
        key = role.strip().lower()
        if key not in persona_cache:
            persona_cache[key] = get_persona(role)
        return persona_cache[key]

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True}

    @app.get("/api/trending")
    def trending_stories(role: str) -> dict:
        try:
            persona = persona_for(role)
            headlines = get_headlines(research_query(persona))
        except OSError as error:
            raise HTTPException(502, f"could not reach a news source: {error}") from error
        if not headlines:
            raise HTTPException(404, "no recent stories found for this role")
        topic, _ = pick_hot_topic(headlines, persona)
        return {
            "persona": {"title": persona.title, "summary": persona.summary, "url": persona.url},
            "suggested": topic.link,
            "stories": [_headline_json(h) for h in headlines],
        }

    @app.get("/api/profile")
    def get_profile() -> dict:
        return asdict(load_profile(profile_path))

    @app.put("/api/profile")
    def put_profile(body: ProfileRequest) -> dict:
        current = load_profile(profile_path)
        interests = current.interests if body.interests is None else [i.strip() for i in body.interests if i.strip()]
        profile = Profile(
            niche=body.niche.strip(), stance=body.stance.strip(), voice=body.voice.strip(), interests=interests
        )
        save_profile(profile_path, profile)
        return asdict(profile)

    @app.post("/api/profile/scan")
    def scan_profile(body: ScanRequest) -> dict:
        """Suggest a voice description from sample posts. Nothing is saved until the author accepts it."""
        return {"voice": describe_voice(make_model(), body.samples)}

    @app.post("/api/profile/interview/question")
    def interview_next(body: InterviewRequest) -> dict:
        """The next interview question, or done once enough have been answered."""
        question = interview_question(make_model(), [(t.question, t.answer) for t in body.history])
        return {"done": question is None, "question": question or ""}

    @app.post("/api/profile/interview/profile")
    def interview_profile(body: InterviewRequest) -> dict:
        """A profile built from the answers. Nothing is saved until the author accepts it."""
        return asdict(propose_profile(make_model(), [(t.question, t.answer) for t in body.history]))

    @app.get("/api/publish/status")
    def publish_status() -> dict:
        return {"mode": publish_mode()}

    @app.post("/api/posts/{post_id}/publish")
    def publish_post(post_id: int, store: Store = Depends(store_dep)) -> dict:
        post = store.get_post(post_id)
        try:
            publisher = publisher_for(post.platform)
            url = publisher.publish(post.body)
        except PublishError as error:
            raise HTTPException(502, str(error)) from error
        store.record_publication(post_id, url, actor=who)
        return {"mode": publish_mode(), "result": url}

    def run_draft_job(
        job_id: str, persona: Persona, story: Headline, related: list[Headline], voice: str, body: DraftRequest
    ) -> None:
        store = Store(db_path)
        try:
            post_ids = draft_on_story(
                make_model(),
                store,
                persona,
                story,
                related=related,
                count=body.count,
                voice=voice,
                platform=body.platform,
            )
            jobs[job_id] = {"status": "done", "post_ids": post_ids, "error": ""}
        except Exception as error:  # the job record carries the message to the client
            jobs[job_id] = {"status": "error", "post_ids": [], "error": str(error)}
        finally:
            store.close()

    def run_discovery_job(job_id: str, rescan: bool) -> None:
        try:
            profile = load_profile(profile_path)
            if rescan or not profile.interests:
                basis = profile.niche.strip()
                if not basis:
                    raise ValueError("Describe your niche in the Profile tab first.")
                profile.interests = extract_interests(make_model(), basis, fallback=profile.niche)
                save_profile(profile_path, profile)
            if not profile.interests:
                raise ValueError("Could not work out your interests. Add some in the Profile tab.")

            run = run_discovery(make_model(), profile.niche, profile.interests, get_headlines)
            if not run.topics:
                raise ValueError("No recent stories fit your niche yet. Agent steps: " + " | ".join(run.steps))
            result = {
                "interests": profile.interests,
                "steps": run.steps,
                "errors": [step for step in run.steps if "failed" in step],
                "topics": [
                    {
                        **_headline_json(t.headline),
                        "keyword": t.keyword,
                        "backing": [_headline_json(h) for h in t.backing],
                    }
                    for t in run.topics
                ],
            }
            jobs[job_id] = {"status": "done", "post_ids": [], "error": "", "result": result}
        except Exception as error:
            jobs[job_id] = {"status": "error", "post_ids": [], "error": str(error), "result": None}

    @app.get("/api/discover")
    def discover(rescan: bool = False) -> dict:
        """Start the discovery agent in the background. Poll /api/jobs/{job_id} for the topics."""
        job_id = uuid.uuid4().hex
        jobs[job_id] = {"status": "running", "post_ids": [], "error": "", "result": None}
        if background:
            threading.Thread(target=run_discovery_job, args=(job_id, rescan), daemon=True).start()
        else:
            run_discovery_job(job_id, rescan)
        return {"job_id": job_id, **jobs[job_id]}

    @app.post("/api/drafts", status_code=201)
    def create_drafts_for_story(body: DraftRequest) -> dict:
        profile = load_profile(profile_path)
        if body.role.strip():
            try:
                persona = persona_for(body.role)
            except OSError as error:
                raise HTTPException(502, f"could not reach Wikipedia: {error}") from error
        else:
            # No role given: the profile describes the author instead of a Wikipedia page.
            persona = Persona(
                title=profile.niche or "Creator",
                summary=" ".join(x for x in [profile.niche, profile.stance] if x) or "A creator who posts online.",
                url="",
            )
        voice = body.voice or profile.voice
        if profile.stance:
            voice = f"{voice}. Stance: {profile.stance}" if voice else f"Stance: {profile.stance}"
        story = Headline(title=body.title, link=body.link, source=body.source, published=None)
        related = [Headline(title=r.title, link=r.link, source=r.source, published=None) for r in body.related]

        job_id = uuid.uuid4().hex
        jobs[job_id] = {"status": "running", "post_ids": [], "error": ""}
        if background:
            threading.Thread(
                target=run_draft_job, args=(job_id, persona, story, related, voice, body), daemon=True
            ).start()
        else:
            run_draft_job(job_id, persona, story, related, voice, body)
        return {"job_id": job_id, **jobs[job_id]}

    @app.get("/api/jobs/{job_id}")
    def job_status(job_id: str) -> dict:
        if job_id not in jobs:
            raise HTTPException(404, f"no job with id {job_id}")
        return {"job_id": job_id, **jobs[job_id]}

    @app.get("/api/posts")
    def list_posts(
        status: Literal["pending", "approved", "rejected"] | None = None,
        limit: int = 50,
        after_id: int = 0,
        store: Store = Depends(store_dep),
    ) -> list[dict]:
        return [_post_json(p) for p in store.list_posts(status, limit=limit, after_id=after_id)]

    @app.get("/api/posts/{post_id}")
    def get_post(post_id: int, store: Store = Depends(store_dep)) -> dict:
        post = store.get_post(post_id)
        return {
            **_post_json(post),
            "sources": [dict(row) for row in store.get_sources(post_id)],
            "history": [dict(row) for row in store.audit_trail(post_id)],
        }

    @app.put("/api/posts/{post_id}")
    def edit_post(post_id: int, body: EditRequest, store: Store = Depends(store_dep)) -> dict:
        store.get_post(post_id)  # 404 first, before any checks
        # Edits are checked against the same material the draft was written from.
        rows = store.get_sources(post_id)
        material = [r["title"] for r in rows] + [r["outlet"] for r in rows if r["outlet"]]
        review = review_post(body.body, sources=material, platform=store.get_post(post_id).platform)
        return _post_json(store.update_body(post_id, body.body, review.problems, actor=who))

    @app.post("/api/posts/{post_id}/decision")
    def decide(post_id: int, body: DecisionRequest, store: Store = Depends(store_dep)) -> dict:
        return _post_json(store.decide(post_id, body.decision, actor=who, note=body.note))

    return app


def _headline_json(h: Headline) -> dict:
    return {
        "title": h.title,
        "link": h.link,
        "source": h.source,
        "published": h.published.isoformat() if h.published else "",
    }


def _post_json(post: Post) -> dict:
    return {
        "id": post.id,
        "topic": post.topic,
        "body": post.body,
        "status": post.status,
        "problems": post.problems,
        "created_at": post.created_at,
        "platform": post.platform,
    }


def _current_user() -> str:
    try:
        return getpass.getuser()
    except (OSError, KeyError):
        # Inside a container there may be no user name to read.
        return "local-user"


app = create_app()
