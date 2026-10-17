import { useCallback, useEffect, useState } from "react";
import { api, PostDetail, PostSummary, Status, Story, Trending } from "./api";

type Tab = "find" | "drafts";

export default function App() {
  const [tab, setTab] = useState<Tab>("find");
  const [pendingFocus, setPendingFocus] = useState<number | null>(null);

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">Content Agent</div>
        <nav className="segmented" role="tablist">
          <button role="tab" aria-selected={tab === "find"} onClick={() => setTab("find")}>
            Find a topic
          </button>
          <button role="tab" aria-selected={tab === "drafts"} onClick={() => setTab("drafts")}>
            Drafts
          </button>
        </nav>
      </header>

      <main>
        {tab === "find" ? (
          <FindTopic
            onDrafted={(id) => {
              setPendingFocus(id);
              setTab("drafts");
            }}
          />
        ) : (
          <Drafts focusId={pendingFocus} onFocusHandled={() => setPendingFocus(null)} />
        )}
      </main>
    </div>
  );
}

function FindTopic({ onDrafted }: { onDrafted: (postId: number) => void }) {
  const [role, setRole] = useState("");
  const [voice, setVoice] = useState("");
  const [count, setCount] = useState(3);
  const [result, setResult] = useState<Trending | null>(null);
  const [chosen, setChosen] = useState<Story | null>(null);
  const [busy, setBusy] = useState<"search" | "draft" | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function search() {
    setBusy("search");
    setError(null);
    setChosen(null);
    try {
      const data = await api.trending(role.trim());
      setResult(data);
      setChosen(data.stories.find((s) => s.link === data.suggested) ?? data.stories[0] ?? null);
    } catch (e) {
      setResult(null);
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  async function draft() {
    if (!result || !chosen) return;
    setBusy("draft");
    setError(null);
    try {
      const { post_ids } = await api.draft({ role: role.trim(), story: chosen, voice, count });
      onDrafted(post_ids[0]);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  return (
    <section className="stack">
      <div className="card">
        <h2>What do you post about?</h2>
        <p className="muted">
          Name a role or niche. Its Wikipedia summary anchors the voice, and recent news shows what is trending.
        </p>
        <form
          className="row"
          onSubmit={(e) => {
            e.preventDefault();
            if (role.trim().length >= 2) search();
          }}
        >
          <input
            value={role}
            onChange={(e) => setRole(e.target.value)}
            placeholder="e.g. Data engineer"
            aria-label="Role or niche"
          />
          <button className="primary" disabled={busy !== null || role.trim().length < 2}>
            {busy === "search" ? "Searching..." : "Find stories"}
          </button>
        </form>
      </div>

      {error && <div className="notice error">{error}</div>}

      {result && (
        <>
          <div className="card">
            <h3>{result.persona.title}</h3>
            <p className="muted clamp">{result.persona.summary}</p>
          </div>

          <div className="card">
            <h3>Trending now</h3>
            <ul className="stories">
              {result.stories.map((story) => (
                <li key={story.link}>
                  <label className={chosen?.link === story.link ? "story selected" : "story"}>
                    <input
                      type="radio"
                      name="story"
                      checked={chosen?.link === story.link}
                      onChange={() => setChosen(story)}
                    />
                    <span>
                      <span className="story-title">{story.title}</span>
                      <span className="muted small">
                        {story.source || "unknown outlet"}
                        {story.link === result.suggested && <span className="badge">Suggested</span>}
                      </span>
                    </span>
                  </label>
                </li>
              ))}
            </ul>
          </div>

          <div className="card">
            <h3>Draft options</h3>
            <label className="field">
              <span>Your voice (optional)</span>
              <input
                value={voice}
                onChange={(e) => setVoice(e.target.value)}
                placeholder="calm, practical, first person"
              />
            </label>
            <div className="row between">
              <label className="field inline">
                <span>Drafts</span>
                <select value={count} onChange={(e) => setCount(Number(e.target.value))}>
                  {[1, 2, 3, 4, 5].map((n) => (
                    <option key={n} value={n}>
                      {n}
                    </option>
                  ))}
                </select>
              </label>
              <button className="primary" disabled={!chosen || busy !== null} onClick={draft}>
                {busy === "draft" ? "Writing..." : "Draft on this story"}
              </button>
            </div>
          </div>
        </>
      )}
    </section>
  );
}

function Drafts({ focusId, onFocusHandled }: { focusId: number | null; onFocusHandled: () => void }) {
  const [status, setStatus] = useState<Status>("pending");
  const [posts, setPosts] = useState<PostSummary[]>([]);
  const [selected, setSelected] = useState<PostDetail | null>(null);
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const loadList = useCallback(async (nextStatus: Status) => {
    setError(null);
    try {
      setPosts(await api.posts(nextStatus));
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  const open = useCallback(async (id: number) => {
    setError(null);
    try {
      const detail = await api.post(id);
      setSelected(detail);
      setText(detail.body);
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    loadList(status);
  }, [status, loadList]);

  useEffect(() => {
    if (focusId !== null) {
      setStatus("pending");
      open(focusId);
      onFocusHandled();
    }
  }, [focusId, open, onFocusHandled]);

  async function save() {
    if (!selected) return;
    setSaving(true);
    setError(null);
    try {
      await api.edit(selected.id, text);
      await open(selected.id);
      await loadList(status);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  async function decide(decision: "approved" | "rejected") {
    if (!selected) return;
    setError(null);
    try {
      await api.decide(selected.id, decision);
      setSelected(null);
      setText("");
      await loadList(status);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const editable = selected?.status === "pending";
  const dirty = selected !== null && text !== selected.body;

  return (
    <section className="split">
      <aside className="card list">
        <div className="segmented small-seg">
          {(["pending", "approved", "rejected"] as Status[]).map((s) => (
            <button key={s} aria-selected={status === s} onClick={() => setStatus(s)}>
              {s}
            </button>
          ))}
        </div>
        {posts.length === 0 && <p className="muted">No {status} drafts.</p>}
        <ul>
          {posts.map((post) => (
            <li key={post.id}>
              <button
                className={selected?.id === post.id ? "post-item active" : "post-item"}
                onClick={() => open(post.id)}
              >
                <span className="post-topic">{post.topic.split(" (")[0]}</span>
                <span className="muted small">
                  #{post.id}
                  {post.problems.length > 0 && <span className="badge warn">{post.problems.length} to check</span>}
                </span>
              </button>
            </li>
          ))}
        </ul>
      </aside>

      <div className="card detail">
        {error && <div className="notice error">{error}</div>}
        {!selected && <p className="muted">Pick a draft to read, edit, or decide on it.</p>}
        {selected && (
          <>
            <div className="row between">
              <h3>Draft #{selected.id}</h3>
              <span className={`status ${selected.status}`}>{selected.status}</span>
            </div>
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              disabled={!editable}
              rows={10}
              aria-label="Draft text"
            />
            <div className="muted small">{text.length} characters</div>

            {selected.problems.length > 0 && (
              <div className="notice warn">
                <strong>Check before approving</strong>
                <ul>
                  {selected.problems.map((p) => (
                    <li key={p}>{p}</li>
                  ))}
                </ul>
              </div>
            )}

            {selected.sources.length > 0 && (
              <details>
                <summary>Sources ({selected.sources.length})</summary>
                <ul className="sources">
                  {selected.sources.map((s) => (
                    <li key={s.link + s.title}>
                      {s.link ? (
                        <a href={s.link} target="_blank" rel="noreferrer">
                          {s.title}
                        </a>
                      ) : (
                        s.title
                      )}
                      <span className="muted small"> {s.outlet}</span>
                    </li>
                  ))}
                </ul>
              </details>
            )}

            {editable && (
              <div className="row actions">
                <button onClick={save} disabled={!dirty || saving}>
                  {saving ? "Saving..." : "Save edit"}
                </button>
                <span className="spacer" />
                <button className="danger" onClick={() => decide("rejected")}>
                  Reject
                </button>
                <button className="primary" onClick={() => decide("approved")} disabled={dirty}>
                  Approve
                </button>
              </div>
            )}
            {dirty && editable && <p className="muted small">Save your edit before approving.</p>}
          </>
        )}
      </div>
    </section>
  );
}
