import type { paths } from "./schema";
import { session } from "../session/store";

const configured = import.meta.env.VITE_API_BASE?.replace(/\/$/, "");
// API must share the origin so the official short-ticket cookie stays authoritative.
export const API_BASE =
  configured ||
  (import.meta.env.PROD ? "/official/learn-everything/api/v2" : "/api/v2");
if (new URL(API_BASE, location.origin).origin !== location.origin)
  throw new Error("API 必须同源部署，请使用本地代理。");

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly retryable = false,
    readonly retryAfterSeconds?: number,
    readonly outcomeUnknown = false,
  ) {
    super(message);
  }
}
export type Transport = typeof fetch;
let transport: Transport = (...args) => fetch(...args);
export function setTransport(value: Transport) {
  transport = value;
}
export type Model<K extends keyof import("./schema").components["schemas"]> =
  import("./schema").components["schemas"][K];
type Verb = "get" | "post" | "patch" | "delete";
type Route<M extends Verb> = {
  [P in keyof paths]: M extends keyof paths[P]
    ? paths[P][M] extends undefined
      ? never
      : P
    : never;
}[keyof paths];
type Operation<P extends keyof paths, M extends Verb> = M extends keyof paths[P]
  ? NonNullable<paths[P][M]>
  : never;
type Json<T> = T extends { content: { "application/json": infer J } }
  ? J
  : never;
type Reply<O> = O extends { responses: infer R }
  ? Json<R[Extract<keyof R, 200 | 201 | 202>]>
  : never;
type Body<O> = O extends { requestBody: infer B } ? Json<B> : never;

export async function request<T>(
  path: string,
  init: RequestInit = {},
  signal?: AbortSignal,
  responseType: "json" | "blob" = "json",
  options: { transport?: Transport; timeoutMs?: number } = {},
): Promise<T> {
  if (session.get().status === "blocked")
    throw new DOMException("Session stopped", "AbortError");
  const headers = new Headers(init.headers);
  const owner = session.expected();
  if (owner) headers.set("X-Learn-Expected-User", owner);
  if (init.body && !(init.body instanceof FormData))
    headers.set("Content-Type", "application/json");
  const abort = new AbortController();
  let timedOut = false;
  const writing = !["GET", "HEAD", "OPTIONS"].includes(
    (init.method || "GET").toUpperCase(),
  );
  const signals = [session.signal(), signal].filter(Boolean) as AbortSignal[];
  const cancel = () => abort.abort();
  signals.forEach((s) => {
    if (s.aborted) cancel();
    else s.addEventListener("abort", cancel, { once: true });
  });
  const timeout = setTimeout(
    () => {
      timedOut = true;
      cancel();
    },
    options.timeoutMs ?? (path.endsWith("/chat") ? 120_000 : 30_000),
  );
  try {
    const response = await (options.transport || transport)(
      `${API_BASE}${path}`,
      {
        ...init,
        headers,
        credentials: "same-origin",
        cache: "no-store",
        signal: abort.signal,
      },
    );
    if (abort.signal.aborted || session.get().status === "blocked")
      throw new DOMException("Request cancelled", "AbortError");
    // A proxy may return an HTML error; the status still invalidates the session.
    if (response.status === 401 || response.status === 403) {
      const message =
        response.status === 403
          ? "当前账号暂无使用资格，请从官网查看。"
          : "登录已过期，请从官网重新进入。";
      session.stop(message);
      throw new ApiError(
        response.status,
        response.status === 401 ? "UNAUTHENTICATED" : "ENTITLEMENT_REQUIRED",
        message,
      );
    }
    if (
      response.status === 409 &&
      response.headers.get("X-Learn-Error") === "ACCOUNT_CHANGED"
    ) {
      session.stop("登录账号已变化，请从官网重新进入。");
      throw new ApiError(409, "ACCOUNT_CHANGED", "登录账号已变化");
    }
    if (response.ok && responseType === "blob") {
      const blob = await response.blob();
      if (abort.signal.aborted || session.get().status === "blocked")
        throw new DOMException("Request cancelled", "AbortError");
      return blob as T;
    }
    const text = response.status === 204 ? "" : await response.text();
    if (abort.signal.aborted || session.get().status === "blocked")
      throw new DOMException("Request cancelled", "AbortError");
    let data;
    try {
      data = text ? JSON.parse(text) : undefined;
    } catch {
      throw new ApiError(
        response.status,
        "INVALID_RESPONSE",
        "服务返回了无法识别的内容，请检查 API 代理或登录状态。",
        false,
        undefined,
        writing && (response.ok || response.status >= 500),
      );
    }
    if (!response.ok) {
      const e = data?.error ?? {};
      const error = new ApiError(
        response.status,
        e.code || "HTTP_ERROR",
        e.message || `请求失败 (${response.status})`,
        !!e.retryable,
        e.retryAfterSeconds,
        writing && response.status >= 500,
      );
      if (error.code === "ACCOUNT_CHANGED")
        session.stop(
          "登录账号已变化，请从官网重新进入。原账号的学习数据仍保留。",
        );
      throw error;
    }
    return data as T;
  } catch (error) {
    // Session/user cancellation keeps its original semantics and must never
    // invite another write under a stopped or changed identity.
    if (
      session.get().status === "blocked" ||
      signals.some((s) => s.aborted) ||
      error instanceof ApiError
    )
      throw error;
    if (timedOut)
      throw new ApiError(
        0,
        "REQUEST_TIMEOUT",
        "等待服务器响应超时，请检查连接后核对结果。",
        false,
        undefined,
        writing,
      );
    if (
      error instanceof TypeError ||
      (error instanceof Error && error.name === "AbortError")
    )
      throw new ApiError(
        0,
        "NETWORK_ERROR",
        "连接中断，请检查网络后核对结果。",
        false,
        undefined,
        writing,
      );
    throw error;
  } finally {
    clearTimeout(timeout);
    signals.forEach((s) => s.removeEventListener("abort", cancel));
  }
}
function url(template: string, params: Record<string, string | number> = {}) {
  return template
    .replace(/\{(\w+)\}/g, (_, key) => {
      if (!(key in params)) throw new Error(`Missing path parameter: ${key}`);
      return encodeURIComponent(params[key]);
    })
    .replace(/^\/api\/v2/, "");
}
export function get<P extends Route<"get">>(
  path: P,
  params?: Record<string, string | number>,
  signal?: AbortSignal,
  query?: URLSearchParams,
) {
  return request<Reply<Operation<P, "get">>>(
    url(path, params) + (query?.size ? `?${query}` : ""),
    {},
    signal,
  );
}
export function post<P extends Route<"post">>(
  path: P,
  body: Body<Operation<P, "post">>,
  params?: Record<string, string | number>,
) {
  return request<Reply<Operation<P, "post">>>(url(path, params), {
    method: "POST",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}
export function patch<P extends Route<"patch">>(
  path: P,
  body: Body<Operation<P, "patch">>,
  params?: Record<string, string | number>,
) {
  return request<Reply<Operation<P, "patch">>>(url(path, params), {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}
