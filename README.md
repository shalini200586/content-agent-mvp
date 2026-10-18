# Content Agent

A right-hand assistant for creators who post daily on LinkedIn or X. It finds what is trending in your niche, checks the facts, and drafts posts for you to pick from. You stay in the loop at every step: you choose the topic, and you approve, edit, or reject each draft.

Everything runs on your own machine with [Ollama](https://ollama.com), so there is no API cost and no account to create. Nothing is published automatically. Approved posts are saved, and you decide what goes out.

## What it does

1. **Your profile (built).** You save your niche, stance, and voice in the Profile screen, and every draft uses them. The niche also drives the trending search. You can build the profile in three ways: answer five questions from the model in an interview, paste some of your posts so the model suggests a voice, or type it yourself. Nothing is saved until you press Save profile.
2. **What is hot (built).** The app searches Google News and Hacker News for your niche and lists the recent stories from both. It suggests the one covered by the most outlets, skipping press-release headlines such as staff moves and awards when there is real news. You can choose any story. Both sources are free and need no key.
3. **Facts check (built).** Drafts are written only from the story you chose and its sources. The editor flags numbers and names that don't appear in those sources. Word forms count as a match, so "acquires" matches "acquiring". It also flags banned phrases and posts over the platform limit.
4. **Drafts for LinkedIn or X (built).** The model writes several options, each from a different angle, in the style of the platform you choose.
5. **You decide (built).** Drafts wait as `pending`. You can edit them, then approve or reject. Every change is logged with who made it.
6. **Publishing (built, off by default).** Approved posts can be published to LinkedIn or X. By default nothing is sent: the button only records the step. See [Publishing](#publishing).

## Run it with Docker

This is the easiest way to use the app. You need [Docker Desktop](https://www.docker.com/products/docker-desktop/) (or Docker Engine on Linux) and about 6 GB of free disk space for the model.

```bash
git clone https://github.com/shalini200586/content-agent-mvp.git
cd content-agent-mvp
docker compose up --build
```

The first start downloads the Ollama model (`qwen2.5:7b`, about 4.7 GB). This takes a few minutes and happens once. When the logs settle, open **http://localhost:8080**.

Useful commands:

```bash
docker compose down        # stop everything; your drafts are kept
docker compose up -d       # start again in the background
docker compose logs -f api # watch the API log
```

Your posts are stored in the `data` volume. To delete them, run `docker compose down -v`.

**Already have the model in Ollama?** Point the stack at your existing model folder so it doesn't download again. Create a file named `.env` next to `docker-compose.yml`:

```
OLLAMA_DATA=C:/Users/you/.ollama     # Windows; on macOS/Linux use e.g. /home/you/.ollama
```

**Behind a company proxy or firewall that inspects HTTPS?** The containers don't trust your computer's certificate store, so news lookups fail with a certificate error. Export the proxy's root certificate as a `.crt` file (PEM format) and put it in the `certs/` folder. It's copied into the API image at build time and is git-ignored. Then run `docker compose up --build` again.

To use a different model, change `qwen2.5:7b` in `docker-compose.yml` in both the `model` service and the `api` service's `CONTENT_AGENT_MODEL`.

Already run Ollama on your computer? You can skip the bundled copy. Remove the `ollama` service and the `model` service from `docker-compose.yml`, then in the `api` service set `OLLAMA_HOST` to `http://host.docker.internal:11434`. Make sure the model is pulled on your computer with `ollama pull qwen2.5:7b`.

## Run it locally (for development)

You need Python 3.11+, Node.js 20+, and [Ollama](https://ollama.com).

```bash
# 1. Download the model
ollama pull qwen2.5:7b

# 2. Install the Python side (API, tests, CLI)
python -m venv .venv
.venv\Scripts\activate          # Windows (macOS/Linux: source .venv/bin/activate)
pip install -e ".[web,dev]"

# 3. Start the API on port 8000
uvicorn content_agent.api:app --reload --port 8000

# 4. In a second terminal, start the UI on port 5173
cd web
npm install
npm run dev
```

Open **http://localhost:5173**. The dev server forwards `/api` requests to the API.

Run the tests (no Ollama or internet needed):

```bash
pytest
```

## Web app

- **Find a topic:** type a niche, pick a story from the trending list, choose LinkedIn or X, add an optional voice note, and choose how many drafts to write. The voice box starts with your saved profile voice.
- **Drafts:** filter by pending, approved, or rejected. Open a draft to read its sources and any editor warnings, edit the text, then save, approve, or reject it. Approve is locked until your edits are saved. X drafts are checked against the 280-character limit.
- **Profile:** save your niche, stance, and voice. Every draft uses them. To get a starting voice, paste a few of your own posts into "Learn my voice from my posts" and press Suggest voice. The suggestion is only saved when you press Save profile.

## Publishing

Only approved posts can be published, and each post can be published once. The publish step is recorded in the audit log.

- **Default: dry run.** Nothing is sent. The Publish button records the step and says "Dry run".
- **Live.** Set these before starting the app (in `.env` for Docker, or in your shell):

  ```
  CONTENT_AGENT_PUBLISH=live
  X_ACCESS_TOKEN=...                 # for X posts; needs an X developer account (paid API tiers)
  LINKEDIN_ACCESS_TOKEN=...          # for LinkedIn posts; needs a LinkedIn app with posting permission
  LINKEDIN_AUTHOR_URN=urn:li:person:...
  ```

The HTTP calls follow the public X and LinkedIn APIs, but they have **not been tested against a live account**. Check the current API versions and terms before going live. Automated posting may breach a platform's terms if misused, so keep a person approving each post.

## Command line

The same pipeline is available from the terminal:

```bash
# Draft posts on a topic you choose
content-agent draft "lessons from fixing a flaky test" --voice "calm, practical, first person"

# Research a role: find its hot topic and draft posts on it
content-agent research "Data engineer" --count 3

# Review and decide
content-agent list --status pending
content-agent show 1
content-agent approve 1 --note "good, post on Tuesday"
content-agent reject 2 --note "too generic"

# Save approved posts to text files
content-agent export ./approved
```

Use `--model` to pick a different Ollama model, and `--host` if Ollama runs on another machine.

## API

The web app talks to a small JSON API (FastAPI). Interactive docs are at http://localhost:8000/docs when the API is running locally.

| Method and path | What it does |
|---|---|
| `GET /api/trending?role=` | Role summary, recent stories, and the suggested story |
| `POST /api/drafts` | Draft posts on one chosen story (`platform`: `linkedin` or `x`) |
| `GET /api/profile`, `PUT /api/profile` | Read or save your niche, stance, and voice |
| `POST /api/profile/scan` | Suggest a voice description from pasted posts (not saved) |
| `POST /api/profile/interview/question` | The next interview question, or done after five |
| `POST /api/profile/interview/profile` | A profile built from the interview answers (not saved) |
| `POST /api/posts/{id}/publish` | Publish an approved post (dry run unless live mode is set) |
| `GET /api/posts?status=` | List drafts |
| `GET /api/posts/{id}` | One draft with its sources and history |
| `PUT /api/posts/{id}` | Save an edit to a pending draft (fact-checked again) |
| `POST /api/posts/{id}/decision` | Approve or reject a pending draft |

The API has no login. Publishing is off unless you set the live tokens. The Docker setup publishes only the web port (8080), so the API is reachable only from your machine. Don't expose it to a network you don't control.

## Design decisions

- **Human approval is mandatory.** Drafts start as `pending` even when the editor finds no problems. The code has no path that publishes a post.
- **Decisions are final.** The store refuses to change an approved or rejected post. Edits are allowed only while a draft is pending, and every change is written to the audit log.
- **The editor is rule-based on purpose.** Rules are predictable and easy to explain. A model-based reviewer could be added later as a second opinion.
- **The model sits behind an interface.** Agents only know about `ChatModel`, so switching from Ollama to a hosted provider doesn't change the agent code.
- **Free news sources.** Stories come from Wikipedia, Google News RSS, and Hacker News. None needs a key. If one source is down, the others still work.
- **Your data stays local.** The profile is a plain JSON file next to the database. The only service it reaches is your local model.

## Limitations

- Fact checking is rule-based. It catches numbers and names that aren't in the sources, but it can't tell whether a claim in words is true. Read every post before you approve it.
- Drafting is slow on a laptop without a GPU. Each draft takes about a minute, so three drafts take a few minutes. The app runs drafting in the background and shows progress, but it still takes that long.
- Trending topics come from Google News and Hacker News only, and results change between runs. Coverage can favour widely syndicated stories, and press releases sometimes rank high, so read the story before you draft from it.
- The search uses the role's Wikipedia title, so a niche with an unusual name may find few stories.
- Quality depends on the local model. Small models can produce generic text, so judge drafts by reading them.
- There is no login and no scheduling. Publishing to LinkedIn and X has not been tested against live accounts.
- The editor rules are a starting list. Adjust `MAX_CHARS`, `MAX_HASHTAGS`, and `BANNED_PHRASES` in `src/content_agent/editor.py` to match your own standards.

## Next steps

1. Test publishing against a real LinkedIn and X account, with a test post, before relying on it.
2. Add more trend sources that are free to use. GDELT is an option but limits requests to one every five seconds. Reddit needs a registered app, and its terms should be checked first.
3. Let the UI show more than one story per draft.
4. Schedule approved posts for a later time.

## License

MIT. See [LICENSE](LICENSE). Anyone may use, modify, and sell this code. Check the terms of any news or social API you connect before you sell a product built on it.
