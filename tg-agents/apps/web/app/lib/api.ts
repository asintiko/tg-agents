export const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export type Project = { id: number; name: string; niche: string; created_at: string };
export type AgentConfig = {
  project_id: number;
  posts_per_day: number;
  window_start: string;
  window_end: string;
  min_interval_minutes: number;
  language: string;
  tone: string;
  signature_html: string | null;
  emoji_mode: string;
  include_source_link: boolean;
  image_mode: string;
};
export type FeedSource = {
  id: number;
  project_id: number;
  name: string;
  url: string;
  enabled: boolean;
  weight: number;
  created_at: string;
};
export type TelegramStatus = {
  mode: string | null;
  status: string | null;
  channels: number;
};
export type TelegramChannel = {
  id: number;
  project_id: number;
  tg_chat_id: string;
  title: string;
  username: string | null;
  enabled: boolean;
};
export type NewsItem = {
  id: number;
  title: string;
  url: string;
  created_at: string;
  published_at: string | null;
  raw_summary: string | null;
};
export type Post = {
  id: number;
  status: string;
  planned_at: string;
  published_at: string | null;
  error: string | null;
};

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init?.headers as Record<string, string> | undefined),
  };
  const res = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  return (await res.json()) as T;
}

export async function login() {
  // Auth disabled; return dummy token for compatibility
  const token = "public";
  if (typeof window !== "undefined") localStorage.setItem("token", token);
  return token;
}

export const ProjectsApi = {
  list: () => apiFetch<Project[]>("/projects"),
  create: (name: string, niche = "football") =>
    apiFetch<Project>("/projects", { method: "POST", body: JSON.stringify({ name, niche }) }),
};

export const ConfigApi = {
  get: (id: number) => apiFetch<AgentConfig>(`/projects/${id}/agent-config`),
  upsert: (id: number, payload: Partial<AgentConfig>) =>
    apiFetch<AgentConfig>(`/projects/${id}/agent-config`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
};

export const SourcesApi = {
  list: (id: number) => apiFetch<FeedSource[]>(`/projects/${id}/feed-sources`),
  create: (id: number, payload: Partial<FeedSource>) =>
    apiFetch<FeedSource>(`/projects/${id}/feed-sources`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  update: (feedId: number, payload: Partial<FeedSource>) =>
    apiFetch<FeedSource>(`/feed-sources/${feedId}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  remove: (feedId: number) =>
    apiFetch<void>(`/feed-sources/${feedId}`, { method: "DELETE" }),
};

export const TelegramApi = {
  connectBot: (projectId: number, token: string) =>
    apiFetch<TelegramStatus>(`/projects/${projectId}/telegram/bot/connect`, {
      method: "POST",
      body: JSON.stringify({ bot_token: token }),
    }),
  status: (projectId: number) =>
    apiFetch<TelegramStatus>(`/projects/${projectId}/telegram/status`),
  startQr: (projectId: number) =>
    apiFetch<{ qr_url: string; status: string }>(`/projects/${projectId}/telegram/user/qr/start`, {
      method: "POST",
    }),
  waitQr: (projectId: number) =>
    apiFetch<{ needs_password?: boolean; connected?: boolean }>(
      `/projects/${projectId}/telegram/user/qr/wait`,
      { method: "POST" },
    ),
  password: (projectId: number, password: string) =>
    apiFetch<{ status: string }>(`/projects/${projectId}/telegram/user/qr/password`, {
      method: "POST",
      body: JSON.stringify({ password }),
    }),
  testMessage: (projectId: number, text: string) =>
    apiFetch<{ sent: number }>(`/projects/${projectId}/telegram/test-message`, {
      method: "POST",
      body: JSON.stringify({ text }),
    }),
};

export const ChannelsApi = {
  list: (projectId: number) => apiFetch<TelegramChannel[]>(`/projects/${projectId}/channels`),
  create: (projectId: number, payload: Partial<TelegramChannel>) =>
    apiFetch<TelegramChannel>(`/projects/${projectId}/channels`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  update: (channelId: number, payload: Partial<TelegramChannel>) =>
    apiFetch<TelegramChannel>(`/channels/${channelId}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
};

export const NewsApi = {
  list: (projectId: number) => apiFetch<NewsItem[]>(`/projects/${projectId}/news/latest`),
};

export const PlanApi = {
  list: (projectId: number, date?: string) =>
    apiFetch<Post[]>(`/projects/${projectId}/plan${date ? `?date_str=${date}` : ""}`),
  planToday: (projectId: number) =>
    apiFetch<{ planned: number }>(`/projects/${projectId}/plan/today`, { method: "POST" }),
  runOnce: (projectId: number) =>
    apiFetch<{ processed: number }>(`/projects/${projectId}/run-once`, { method: "POST" }),
};

export const PostsApi = {
  list: (projectId: number, status?: string) =>
    apiFetch<Post[]>(
      `/projects/${projectId}/posts${status ? `?status_filter=${encodeURIComponent(status)}` : ""}`,
    ),
};
