# Content Agent (MVP)

A small multi-step AI pipeline that drafts LinkedIn posts, checks them with fixed editorial rules, and waits for a human to approve or reject each one. Everything runs locally with [Ollama](https://ollama.com), so there is no API cost.

Nothing is published automatically. Approved posts are written to a folder, and a person decides what goes out.

## How it works

```
topic + voice notes
        │
        ▼
  drafter (LLM)  ──►  3 candidate posts
        │
        ▼
  editor (rules)  ──►  problems list per post (length, hashtags, banned phrases, preamble)
        │
        ▼
  store (SQLite) ──►  status: pending
        │
        ▼
  human: approve / reject  ──►  decision is final, every step is logged
        │
        ▼
  export (approved posts → text files)
```

| Module | Responsibility |
|---|---|
| `llm.py` | Wraps the model behind a `ChatModel` interface. `OllamaChat` for real use, `FakeChat` for tests. |
| `drafter.py` | Asks the model for several independent drafts on one topic. |
| `editor.py` | Deterministic rules. Each rule is a plain function you can test and change. |
| `store.py` | SQLite tables for posts and an audit log. Enforces that decisions can't be changed. |
| `research.py` | Finds what a role does (Wikipedia) and what is currently covered in its field (Google News RSS), then picks the hot topic. |
| `workflow.py` | Connects drafting, review, and storage into one step, and the research step on top of it. |
| `cli.py` | The command-line interface. |

## Setup

You need Python 3.11+ and Ollama.

```bash
# 1. Install Ollama from https://ollama.com, then download a model
ollama pull qwen2.5:7b

# 2. Create a virtual environment and install the project
python -m venv .venv
.venv\Scripts\activate          # Windows (on macOS/Linux: source .venv/bin/activate)
pip install -e ".[dev]"

# 3. Run the tests (no Ollama needed)
pytest
```

## Usage

```bash
# Draft three posts on a topic
content-agent draft "lessons from fixing a flaky test" --voice "calm, practical, first person"

# Review what's waiting
content-agent list --status pending
content-agent show 1

# Decide
content-agent approve 1 --note "good, post on Tuesday"
content-agent reject 2 --note "too generic"

# Save approved posts to files
content-agent export ./approved

# Research a role, find what its field is covering, and draft posts on the hot topic
content-agent research "Data engineer" --count 3
```

`research` reads the role's Wikipedia summary, searches Google News for its field, and picks the story covered by the most outlets. The drafter then gets only that story and its sources as the brief, and the drafts are saved as `pending` like any others. Both sources are free and need no key. Hot-topic picking is deterministic: outlet coverage first, then overlap with the role's vocabulary, then recency. Coverage can favour widely syndicated stories, so read the topic before you draft from it.

Use `--model` to pick a different Ollama model, and `--host` if Ollama runs on another machine.

## Design decisions

- **Human approval is mandatory.** Drafts start as `pending` even when the editor finds no problems. The code has no path that publishes a post.
- **Decisions are final.** The store refuses to change an approved or rejected post, and every change is written to `audit_log`.
- **The editor is rule-based on purpose.** Rules are predictable and easy to explain. A model-based reviewer could be added later as a second opinion.
- **The model sits behind an interface.** Agents only know about `ChatModel`, so switching from Ollama to a hosted provider doesn't change the agent code.

## Limitations

- Only drafting uses the model. Research is rule-based, so there is no engagement prediction and no publishing.
- The research step needs network access to Wikipedia and Google News. Google News search results can change between runs.
- Quality depends on the local model. Small models can produce generic text, so judge drafts by reading them.
- The editor rules are a starting list. Adjust `MAX_CHARS`, `MAX_HASHTAGS`, and `BANNED_PHRASES` in `editor.py` to match your own standards.

## Next steps

1. Add a second editor pass that asks the model whether each draft matches the author's voice.
2. Add more research sources, such as Hacker News for technical roles.
3. Connect publishing, behind an interface, once LinkedIn API access is confirmed.
