import { get, post, patch, request, type Model } from "./api/client";
export { ApiError } from "./api/client";
export type Project = Model<"ProjectOut">;
export type KNode = Model<"NodeOut">;
export type JobProgress = Model<"JobOut">;
export const endpoints = {
  me: (signal?: AbortSignal) => get("/api/v2/me", undefined, signal),
  models: (signal?: AbortSignal) => get("/api/v2/models", undefined, signal),
  selectModel: (model: string) => patch("/api/v2/models/selection", { model }),
  projects: (signal?: AbortSignal) =>
    get("/api/v2/projects", undefined, signal),
  createProject: (body: Model<"ProjectCreate">) =>
    post("/api/v2/projects", body),
  project: (id: number, signal?: AbortSignal) =>
    get("/api/v2/projects/{project_id}", { project_id: id }, signal),
  nodes: (id: number, signal?: AbortSignal) =>
    get("/api/v2/projects/{project_id}/nodes", { project_id: id }, signal),
  createNode: (id: number, body: Model<"NodeCreate">) =>
    post("/api/v2/projects/{project_id}/nodes", body, { project_id: id }),
  patchNode: (id: number, body: Model<"NodeUpdate">) =>
    patch("/api/v2/nodes/{node_id}", body, { node_id: id }),
  notes: (id: number, signal?: AbortSignal) =>
    get("/api/v2/projects/{project_id}/notes", { project_id: id }, signal),
  createNote: (id: number, body: Model<"NoteCreate">) =>
    post("/api/v2/projects/{project_id}/notes", body, { project_id: id }),
  tasks: (id: number, signal?: AbortSignal) =>
    get("/api/v2/projects/{project_id}/tasks", { project_id: id }, signal),
  patchTask: (id: number, body: Model<"TaskUpdate">) =>
    patch("/api/v2/tasks/{task_id}", body, { task_id: id }),
  dueCards: (signal?: AbortSignal) =>
    get(
      "/api/v2/review/due",
      undefined,
      signal,
      new URLSearchParams({ limit: "20" }),
    ),
  review: (id: number, rating: number, expectedReps: number) =>
    post("/api/v2/review/{card_id}", { rating, expectedReps }, { card_id: id }),
  quizzes: (id: number, signal?: AbortSignal) =>
    get("/api/v2/projects/{project_id}/quizzes", { project_id: id }, signal),
  quiz: (id: number, signal?: AbortSignal) =>
    get("/api/v2/quizzes/{quiz_id}", { quiz_id: id }, signal),
  submitQuiz: (id: number, answers: Record<string, string>) =>
    post("/api/v2/quizzes/{quiz_id}/grade-jobs", { answers }, { quiz_id: id }),
  quizResult: (id: number, signal?: AbortSignal) =>
    get("/api/v2/quizzes/{quiz_id}/result", { quiz_id: id }, signal),
  quizGradeJob: (id: number, signal?: AbortSignal) =>
    get("/api/v2/quizzes/{quiz_id}/grade-job", { quiz_id: id }, signal),
  materials: (id: number, signal?: AbortSignal) =>
    get("/api/v2/projects/{project_id}/materials", { project_id: id }, signal),
  upload: (id: number, file: File) => {
    const body = new FormData();
    body.append("file", file);
    return request<Model<"UploadOut">>(`/projects/${id}/materials`, {
      method: "POST",
      body,
    });
  },
  materialPreview: (id: string, signal?: AbortSignal) =>
    get("/api/v2/materials/{file_id}/preview", { file_id: id }, signal),
  downloadMaterial: (id: string) =>
    request<Blob>(
      `/materials/${encodeURIComponent(id)}/download`,
      {},
      undefined,
      "blob",
    ),
  deleteMaterial: (id: string) =>
    request<void>(`/materials/${encodeURIComponent(id)}`, { method: "DELETE" }),
  indexMaterial: (id: string) =>
    request<Model<"GenerationOut">>(
      `/materials/${encodeURIComponent(id)}/index`,
      { method: "POST" },
    ),
  path: (id: number, body: Model<"PlanRequest">) =>
    post("/api/v2/projects/{project_id}/path", body, { project_id: id }),
  summary: (id: number, signal?: AbortSignal) =>
    get("/api/v2/projects/{project_id}/summary", { project_id: id }, signal),
  reports: (id: number, signal?: AbortSignal) =>
    get("/api/v2/projects/{project_id}/reports", { project_id: id }, signal),
  buildReport: (id: number) =>
    request<Model<"ReportOut">>(`/projects/${id}/reports`, { method: "POST" }),
  chat: (id: number, messages: Model<"ChatMessage">[]) =>
    post(
      "/api/v2/projects/{project_id}/chat",
      { messages },
      { project_id: id },
    ),
  conversation: (
    id: number,
    signal?: AbortSignal,
    mode: "chat" | "coach" = "chat",
  ) =>
    get(
      "/api/v2/projects/{project_id}/conversation",
      { project_id: id },
      signal,
      new URLSearchParams({ mode }),
    ),
  ask: (id: number, body: Model<"QuestionCreate">) =>
    post("/api/v2/projects/{project_id}/chat-jobs", body, { project_id: id }),
  polish: (id: number, body: Model<"PolishCreate">) =>
    post("/api/v2/projects/{project_id}/polish-jobs", body, { project_id: id }),
  polishJob: (id: number, signal?: AbortSignal) =>
    get("/api/v2/projects/{project_id}/polish-job", { project_id: id }, signal),
  job: (id: string, signal?: AbortSignal) =>
    get("/api/v2/jobs/{job_id}", { job_id: id }, signal),
  generateRoadmap: (id: number) =>
    request<Model<"GenerationOut">>(`/projects/${id}/roadmap-jobs`, {
      method: "POST",
    }),
  generateLesson: (id: number, force = false) =>
    post("/api/v2/nodes/{node_id}/lesson-jobs", { force }, { node_id: id }),
  generateAssessment: (
    id: number,
    options: {
      kind: "quiz" | "cards";
      nodeIds: number[];
      count: number;
      qtype: "mixed" | "choice" | "fill" | "short" | "practice";
    },
  ) => {
    const { kind, ...body } = options;
    return kind === "quiz"
      ? post("/api/v2/projects/{project_id}/quiz-jobs", body, {
          project_id: id,
        })
      : post("/api/v2/projects/{project_id}/card-jobs", body, {
          project_id: id,
        });
  },
  cards: (id: number, signal?: AbortSignal) =>
    get("/api/v2/projects/{project_id}/cards", { project_id: id }, signal),
};
