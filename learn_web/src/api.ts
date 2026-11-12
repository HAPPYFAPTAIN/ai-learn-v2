/** 官网内嵌的 API 客户端。
 *
 * 门票（ticket）由官网在打开页面时通过 `?ticket=` 带过来，存内存 + sessionStorage，
 * 刷新不丢；每一步都带 X-Learn-Ticket，后端据此换租户。
 */

const API_BASE = (import.meta.env.VITE_API_BASE ?? "").replace(/\/$/, "");
const TICKET_KEY = "le.ticket";

function readTicket(): string {
  const fromUrl = new URLSearchParams(window.location.search).get("ticket");
  if (fromUrl) {
    sessionStorage.setItem(TICKET_KEY, fromUrl);
    // 门票留在地址栏会跟着分享/截图泄露，取到就抹掉。
    const url = new URL(window.location.href);
    url.searchParams.delete("ticket");
    window.history.replaceState({}, "", url);
    return fromUrl;
  }
  return sessionStorage.getItem(TICKET_KEY) ?? "";
}

let ticket = readTicket();

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
  }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (ticket) headers.set("X-Learn-Ticket", ticket);
  if (init.body && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${API_BASE}/api/v2${path}`, { ...init, headers });
  if (response.status === 204) return undefined as T;

  const text = await response.text();
  const data = text ? JSON.parse(text) : {};
  if (!response.ok) {
    const error = data?.error ?? {};
    throw new ApiError(response.status, error.code ?? "UNKNOWN", error.message ?? response.statusText);
  }
  return data as T;
}

// ---- 类型：与后端响应字段一一对应（camelCase） ----

export interface Project {
  id: number;
  title: string;
  goal: string;
  status: string;
  createdAt: string;
}

export interface KNode {
  id: number;
  projectId: number;
  code: string;
  title: string;
  description: string;
  stage: string;
  estHours: number;
  difficulty: number;
  mastery: number;
  status: string;
}

export interface Card {
  id: number;
  front: string;
  back: string;
  state: number;
  nextReview: string;
}

export interface QuizSummary {
  id: number;
  title: string;
  quizType: string;
  createdAt: string;
}

export interface Material {
  fileId: string;
  name: string;
  sizeBytes: number;
  sha256: string;
  createdAt: string;
}

export interface WeekPlan {
  index: number;
  hours: number;
  items: { nodeId: number; code: string; title: string; hours: number }[];
}

export interface DailyReport {
  id: number;
  date: string;
  content: string;
  studyMinutes: number;
  cardsReviewed: number;
  nodesProgressed: number;
}

export interface JobProgress {
  jobId: string;
  kind: string;
  state: string;
  progress: { done?: number; total?: number };
  error?: string | null;
}

export const endpoints = {
  projects: () => api<{ items: Project[] }>("/projects"),
  createProject: (body: { title: string; goal?: string; weeklyHours?: number }) =>
    api<Project>("/projects", { method: "POST", body: JSON.stringify(body) }),
  project: (id: number) => api<Project>(`/projects/${id}`),
  nodes: (id: number) => api<{ items: KNode[] }>(`/projects/${id}/nodes`),
  createNode: (id: number, body: Partial<KNode>) =>
    api<KNode>(`/projects/${id}/nodes`, { method: "POST", body: JSON.stringify(body) }),
  patchNode: (nodeId: number, body: Partial<KNode>) =>
    api<KNode>(`/nodes/${nodeId}`, { method: "PATCH", body: JSON.stringify(body) }),
  dueCards: (limit = 20) => api<{ items: Card[] }>(`/review/due?limit=${limit}`),
  review: (cardId: number, rating: number) =>
    api<Card>(`/review/${cardId}`, { method: "POST", body: JSON.stringify({ rating }) }),
  quizzes: (id: number) => api<{ items: QuizSummary[] }>(`/projects/${id}/quizzes`),
  materials: (id: number) => api<{ items: Material[] }>(`/projects/${id}/materials`),
  upload: (id: number, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return api<{ fileId: string; jobId: string | null }>(`/projects/${id}/materials`, {
      method: "POST",
      body: form,
    });
  },
  path: (id: number, weeks: number, hoursPerWeek: number) =>
    api<{ weeks: WeekPlan[]; totalHours: number }>(`/projects/${id}/path`, {
      method: "POST",
      body: JSON.stringify({ weeks, hoursPerWeek }),
    }),
  reports: (id: number) => api<{ items: DailyReport[] }>(`/projects/${id}/reports`),
  buildReport: (id: number) => api<DailyReport>(`/projects/${id}/reports`, { method: "POST" }),
  chat: (projectId: number, messages: { role: string; content: string }[], background = false) =>
    api<{ eventId: string; content: string; model: string; usage: Record<string, unknown> }>(
      `/projects/${projectId}/chat`,
      { method: "POST", body: JSON.stringify({ messages, background }) },
    ),
  job: (jobId: string) => api<JobProgress>(`/jobs/${jobId}`),
};
