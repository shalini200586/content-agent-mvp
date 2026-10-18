// Typed wrappers around the FastAPI server in src/content_agent/api.py.

export type Status = "pending" | "approved" | "rejected";

export interface Story {
  title: string;
  link: string;
  source: string;
  published: string;
}

export interface Trending {
  persona: { title: string; summary: string; url: string };
  suggested: string;
  stories: Story[];
}

export type Platform = "linkedin" | "x";

export interface PostSummary {
  id: number;
  topic: string;
  body: string;
  status: Status;
  problems: string[];
  created_at: string;
  platform: Platform;
}

export interface Profile {
  niche: string;
  stance: string;
  voice: string;
}

export interface PostDetail extends PostSummary {
  sources: { title: string; outlet: string; link: string; published: string }[];
  history: { event: string; detail: string; actor: string; at: string }[];
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(typeof data.detail === "string" ? data.detail : `Request failed (${response.status})`);
  }
  return data as T;
}

export const api = {
  trending: (role: string) =>
    request<Trending>(`/api/trending?role=${encodeURIComponent(role)}`),

  draft: (body: { role: string; story: Story; voice: string; count: number; platform: Platform }) =>
    request<{ post_ids: number[] }>("/api/drafts", {
      method: "POST",
      body: JSON.stringify({
        role: body.role,
        title: body.story.title,
        link: body.story.link,
        source: body.story.source,
        voice: body.voice,
        count: body.count,
        platform: body.platform,
      }),
    }),

  profile: () => request<Profile>("/api/profile"),

  saveProfile: (profile: Profile) =>
    request<Profile>("/api/profile", { method: "PUT", body: JSON.stringify(profile) }),

  scanVoice: (samples: string) =>
    request<{ voice: string }>("/api/profile/scan", { method: "POST", body: JSON.stringify({ samples }) }),

  interviewNext: (history: { question: string; answer: string }[]) =>
    request<{ done: boolean; question: string }>("/api/profile/interview/question", {
      method: "POST",
      body: JSON.stringify({ history }),
    }),

  interviewProfile: (history: { question: string; answer: string }[]) =>
    request<Profile>("/api/profile/interview/profile", {
      method: "POST",
      body: JSON.stringify({ history }),
    }),

  publishStatus: () => request<{ mode: "dry-run" | "live" }>("/api/publish/status"),

  publish: (id: number) =>
    request<{ mode: string; result: string }>(`/api/posts/${id}/publish`, { method: "POST" }),

  posts: (status: Status) => request<PostSummary[]>(`/api/posts?status=${status}&limit=100`),

  post: (id: number) => request<PostDetail>(`/api/posts/${id}`),

  edit: (id: number, body: string) =>
    request<PostSummary>(`/api/posts/${id}`, { method: "PUT", body: JSON.stringify({ body }) }),

  decide: (id: number, decision: "approved" | "rejected") =>
    request<PostSummary>(`/api/posts/${id}/decision`, {
      method: "POST",
      body: JSON.stringify({ decision }),
    }),
};
