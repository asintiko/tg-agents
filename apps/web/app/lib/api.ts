export const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8001";
export type TokenResponse = { access_token: string; token_type: string };

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
    status: string | null;
    channels: number;
    last_connected_at: string | null;
};
export type TelegramAuthInfo = {
  status: string;
  last_connected_at?: string | null;
  me?: { id: number | null; username: string | null; phone: string | null } | null;
};
export type TelegramChannel = {
    id: number;
    project_id: number;
  tg_chat_id: string;
  title: string;
  username: string | null;
  enabled: boolean;
};
export type DiscoveredChannel = {
  tg_chat_id: string;
  title: string;
  username: string | null;
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
export type TestPostResponse = { ok: boolean; tg_message_id?: string | null };
export type PreviewResponse = {
  news_id: number;
  headline: string;
  body_html: string;
  image_query?: string;
  should_post?: boolean;
  reason_if_skip?: string | null;
};

function buildHeaders(init?: RequestInit): Record<string, string> {
    const headers: Record<string, string> = {
        "Content-Type": "application/json",
        ...(init?.headers as Record<string, string> | undefined),
    };
    if (typeof window !== "undefined") {
        const token = localStorage.getItem("token");
        if (token) headers.Authorization = `Bearer ${token}`;
    }
    return headers;
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
    const res = await fetch(`${API_BASE}${path}`, { ...init, headers: buildHeaders(init) });
    if (!res.ok) {
        const text = await res.text();
        throw new Error(text || res.statusText);
    }
    return (await res.json()) as T;
}

export async function login(password: string) {
    const data = await apiFetch<TokenResponse>("/login", {
        method: "POST",
        body: JSON.stringify({ password }),
    });
    if (typeof window !== "undefined") localStorage.setItem("token", data.access_token);
    return data.access_token;
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
  startPhone: (projectId: number, phone: string) =>
    apiFetch<{ status: string }>(`/projects/${projectId}/telegram/user/phone/start`, {
      method: "POST",
      body: JSON.stringify({ phone }),
    }),
  submitCode: (projectId: number, code: string) =>
    apiFetch<{ status: string }>(`/projects/${projectId}/telegram/user/phone/code`, {
      method: "POST",
      body: JSON.stringify({ code }),
    }),
  testMessage: (projectId: number, text: string) =>
    apiFetch<{ sent: number }>(`/projects/${projectId}/telegram/test-message`, {
      method: "POST",
      body: JSON.stringify({ text }),
    }),
};
export const TelegramGlobalApi = {
  status: () => apiFetch<TelegramAuthInfo>("/api/telegram/status"),
  startQr: () => apiFetch<{ status: string; qr_url?: string | null }>("/api/telegram/qr/start", { method: "POST" }),
  waitQr: () => apiFetch<{ status: string; me?: any; qr_url?: string | null }>("/api/telegram/qr/wait", { method: "POST" }),
  password: (password: string) =>
    apiFetch<{ status: string; me?: any }>("/api/telegram/qr/password", {
      method: "POST",
      body: JSON.stringify({ password }),
    }),
  resetSession: () => apiFetch<{ status: string }>("/api/telegram/session", { method: "DELETE" }),
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
  discover: () => apiFetch<DiscoveredChannel[]>(`/api/telegram/channels/discover`),
  save: (channels: DiscoveredChannel[], replace = true) =>
    apiFetch<TelegramChannel[]>(`/api/channels/save`, {
      method: "POST",
      body: JSON.stringify({ channels, replace }),
    }),
  discoverForProject: (projectId: number) =>
    apiFetch<DiscoveredChannel[]>(`/projects/${projectId}/telegram/user/channels/discover`),
  importForProject: (projectId: number, channels: DiscoveredChannel[], replace = true) =>
    apiFetch<TelegramChannel[]>(`/projects/${projectId}/telegram/channels/import`, {
      method: "POST",
      body: JSON.stringify({ channels, replace }),
    }),
  listSaved: () => apiFetch<TelegramChannel[]>(`/api/channels`),
  toggle: (channelId: number, enabled: boolean) =>
    apiFetch<TelegramChannel>(`/api/channels/${channelId}`, {
      method: "PATCH",
      body: JSON.stringify({ enabled }),
    }),
};

export const TestApi = {
  send: () => apiFetch<TestPostResponse>("/api/telegram/test-post", { method: "POST" }),
};

export const NewsApi = {
  list: (projectId: number) => apiFetch<NewsItem[]>(`/projects/${projectId}/news/latest`),
  latestGlobal: () => apiFetch<NewsItem[]>(`/api/news/latest`),
  pull: () => apiFetch<{ ok: number }>(`/api/rss/pull`, { method: "POST" }),
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

export const PreviewApi = {
  next: () => apiFetch<PreviewResponse>("/api/preview/next", { method: "POST" }),
  publish: () =>
    apiFetch<{ ok: boolean; news_id: number; tg_message_ids?: string[] }>(
      "/api/publish/next",
      { method: "POST" },
    ),
};
