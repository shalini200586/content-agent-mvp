import { useCallback, useEffect, useState } from "react";
import { api, Platform, PostDetail, PostSummary, Profile, Status, Story, Trending } from "./api";

type Tab = "find" | "drafts" | "profile";

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
          <button role="tab" aria-selected={tab === "profile"} onClick={() => setTab("profile")}>
            Profile
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
        ) : tab === "drafts" ? (
          <Drafts focusId={pendingFocus} onFocusHandled={() => setPendingFocus(null)} />
        ) : (
          <ProfileScreen />
        )}
      </main>
    </div>
  );
}

function FindTopic({ onDrafted }: { onDrafted: (postId: number) => void }) {
  const [role, setRole] = useState("");
  const [voice, setVoice] = useState("");
  const [count, setCount] = useState(3);
  const [platform, setPlatform] = useState<Platform>("linkedin");
  const [result, setResult] = useState<Trending | null>(null);
  const [chosen, setChosen] = useState<Story | null>(null);
  const [busy, setBusy] = useState<"search" | "draft" | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Start from the saved voice in the profile, so the author does not retype it.
  useEffect(() => {
    api.profile().then((profile) => {
      if (profile.voice) setVoice((current) => current || profile.voice);
    }).catch(() => {});
  }, []);

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
      // Drafting runs in the background, so poll until it finishes.
      let job = await api.draft({ role: role.trim(), story: chosen, voice, count, platform });
      while (job.status === "running") {
        await new Promise((resolve) => setTimeout(resolve, 2000));
        job = await api.job(job.job_id);
      }
      if (job.status === "error") throw new Error(job.error || "drafting failed");
      onDrafted(job.post_ids[0]);
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
                <span>Platform</span>
                <select value={platform} onChange={(e) => setPlatform(e.target.value as Platform)}>
                  <option value="linkedin">LinkedIn</option>
                  <option value="x">X</option>
                </select>
              </label>
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
                {busy === "draft" ? "Writing (this can take a few minutes)..." : "Draft on this story"}
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
                  #{post.id} · {post.platform === "x" ? "X" : "LinkedIn"}
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

            {selected.status === "approved" && <PublishPanel post={selected} onPublished={() => open(selected.id)} />}

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

function ProfileScreen() {
  const [profile, setProfile] = useState<Profile>({ niche: "", stance: "", voice: "" });
  const [interview, setInterview] = useState<{ question: string; answer: string }[]>([]);
  const [currentQuestion, setCurrentQuestion] = useState<string | null>(null);
  const [answer, setAnswer] = useState("");
  const [interviewBusy, setInterviewBusy] = useState(false);
  const [samples, setSamples] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<"save" | "scan" | null>(null);

  useEffect(() => {
    api.profile().then(setProfile).catch((e) => setError((e as Error).message));
  }, []);

  async function save() {
    setBusy("save");
    setError(null);
    setMessage(null);
    try {
      setProfile(await api.saveProfile(profile));
      setMessage("Saved. New drafts will use this profile.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  async function scan() {
    setBusy("scan");
    setError(null);
    setMessage(null);
    try {
      const { voice } = await api.scanVoice(samples);
      // Shown in the voice box for review. Nothing is saved until the author presses Save.
      setProfile((current) => ({ ...current, voice }));
      setMessage("Suggested voice added below. Edit it if needed, then save.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  async function startInterview() {
    setInterviewBusy(true);
    setError(null);
    try {
      const next = await api.interviewNext([]);
      setInterview([]);
      setCurrentQuestion(next.question);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setInterviewBusy(false);
    }
  }

  async function answerQuestion() {
    if (!currentQuestion || answer.trim().length === 0) return;
    const history = [...interview, { question: currentQuestion, answer: answer.trim() }];
    setInterviewBusy(true);
    setError(null);
    try {
      const next = await api.interviewNext(history);
      setInterview(history);
      setAnswer("");
      if (next.done) {
        setCurrentQuestion(null);
        const proposed = await api.interviewProfile(history);
        setProfile(proposed);
        setMessage("Here is a profile built from your answers. Edit it, then press Save profile.");
      } else {
        setCurrentQuestion(next.question);
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setInterviewBusy(false);
    }
  }

  return (
    <section className="stack">
      <div className="card">
        <h2>Your profile</h2>
        <p className="muted">The niche, stance, and voice that every draft is written from.</p>

        <label className="field">
          <span>Niche</span>
          <input
            value={profile.niche}
            onChange={(e) => setProfile({ ...profile, niche: e.target.value })}
            placeholder="e.g. Data engineering"
          />
        </label>
        <label className="field">
          <span>Stance (what you believe about it)</span>
          <input
            value={profile.stance}
            onChange={(e) => setProfile({ ...profile, stance: e.target.value })}
            placeholder="e.g. Reliable pipelines matter more than new tools"
          />
        </label>
        <label className="field">
          <span>Voice</span>
          <textarea
            rows={3}
            value={profile.voice}
            onChange={(e) => setProfile({ ...profile, voice: e.target.value })}
            placeholder="calm, practical, first person"
          />
        </label>
        <div className="row between">
          <span className="muted small">{message}</span>
          <button className="primary" onClick={save} disabled={busy !== null}>
            {busy === "save" ? "Saving..." : "Save profile"}
          </button>
        </div>
      </div>

      <div className="card">
        <h3>Build it with a short interview</h3>
        <p className="muted small">The model asks five questions, then writes a profile from your answers.</p>
        {currentQuestion === null && (
          <div className="row actions">
            <span className="spacer" />
            <button onClick={startInterview} disabled={interviewBusy}>
              {interview.length > 0 ? "Start again" : "Start interview"}
            </button>
          </div>
        )}
        {currentQuestion !== null && (
          <>
            <p className="muted small">Question {interview.length + 1} of 5</p>
            <p><strong>{currentQuestion}</strong></p>
            <textarea
              rows={3}
              value={answer}
              onChange={(e) => setAnswer(e.target.value)}
              aria-label="Your answer"
            />
            <div className="row actions">
              <span className="spacer" />
              <button className="primary" onClick={answerQuestion} disabled={interviewBusy || answer.trim().length === 0}>
                {interviewBusy ? "Thinking..." : interview.length === 4 ? "Finish" : "Next"}
              </button>
            </div>
          </>
        )}
      </div>

      <div className="card">
        <h3>Learn my voice from my posts</h3>
        <p className="muted small">Paste a few of your own posts. The model suggests a voice description, which you can edit.</p>
        <textarea
          rows={6}
          value={samples}
          onChange={(e) => setSamples(e.target.value)}
          placeholder="Paste at least a few sentences of your posts here"
          aria-label="Sample posts"
        />
        <div className="row actions">
          <span className="spacer" />
          <button onClick={scan} disabled={busy !== null || samples.trim().length < 50}>
            {busy === "scan" ? "Reading..." : "Suggest voice"}
          </button>
        </div>
      </div>

      {error && <div className="notice error">{error}</div>}
    </section>
  );
}

function PublishPanel({ post, onPublished }: { post: PostDetail; onPublished: () => void }) {
  const [mode, setMode] = useState<"dry-run" | "live">("dry-run");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const alreadyPublished = post.history.some((h) => h.event === "published");

  useEffect(() => {
    api.publishStatus().then((s) => setMode(s.mode)).catch(() => {});
  }, []);

  async function publish() {
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      const result = await api.publish(post.id);
      setNote(result.mode === "dry-run" ? `Dry run: ${result.result}` : `Published: ${result.result}`);
      onPublished();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="notice publish">
      <div className="row between">
        <span>
          {alreadyPublished
            ? "Already published."
            : mode === "dry-run"
              ? "Dry run: pressing Publish records it but sends nothing."
              : `Ready to publish to ${post.platform === "x" ? "X" : "LinkedIn"}.`}
        </span>
        {!alreadyPublished && (
          <button className="primary" onClick={publish} disabled={busy}>
            {busy ? "Publishing..." : "Publish"}
          </button>
        )}
      </div>
      {note && <p className="muted small">{note}</p>}
      {error && <p className="small" style={{ color: "var(--danger)" }}>{error}</p>}
    </div>
  );
}
