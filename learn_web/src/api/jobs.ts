import { endpoints, ApiError, type JobProgress } from "../api";
import { API_BASE } from "./client";
import { session } from "../session/store";
export type Connection = "connecting" | "live" | "reconnecting" | "closed";
export type EventStream = Pick<
  EventSource,
  "addEventListener" | "close" | "onopen" | "onerror"
>;
let makeStream = (url: string): EventStream =>
  new EventSource(url, { withCredentials: true });
export function setStreamFactory(factory: typeof makeStream) {
  makeStream = factory;
}
const terminal = (job: JobProgress) =>
  ["done", "failed", "cancelled"].includes(job.state);

export function watchJob(
  id: string,
  update: (job: JobProgress) => void,
  connection: (state: Connection) => void,
  fail: (error: Error) => void,
) {
  let closed = false,
    checking = false;
  let source: EventStream | undefined;
  let fallback: ReturnType<typeof setInterval> | undefined;
  const abort = new AbortController();
  const finish = () => {
    if (closed) return;
    closed = true;
    source?.close();
    abort.abort();
    clearInterval(fallback);
    off();
    connection("closed");
  };
  const off = session.onStop(finish);
  const accept = (job: JobProgress) => {
    if (closed) return;
    if (
      !job ||
      typeof job.jobId !== "string" ||
      typeof job.state !== "string" ||
      !job.progress ||
      typeof job.progress !== "object"
    )
      throw new Error("任务进度格式错误");
    if (job.jobId !== id) return;
    update(job);
    if (terminal(job)) finish();
  };
  async function poll() {
    if (closed || checking || document.hidden) return;
    checking = true;
    try {
      accept(await endpoints.job(id, abort.signal));
    } catch (e) {
      if (!closed && e instanceof ApiError && !e.retryable) {
        fail(e);
        finish();
      }
    } finally {
      checking = false;
    }
  }
  async function connect() {
    connection("connecting");
    // This authenticated preflight can see 401/409, unlike EventSource.onerror.
    await poll();
    if (closed) return;
    const url = `${API_BASE}/jobs/${encodeURIComponent(id)}/events?${new URLSearchParams({ __le_owner: session.expected() })}`;
    source = makeStream(url);
    source.onopen = () => {
      if (!closed) {
        clearInterval(fallback);
        fallback = undefined;
        connection("live");
      }
    };
    source.onerror = () => {
      if (closed) return;
      connection("reconnecting");
      // Native EventSource reconnects; only while disconnected do we poll at 3 s.
      if (!fallback) {
        void poll();
        fallback = setInterval(() => void poll(), 3000);
      }
    };
    source.addEventListener("progress", (event) => {
      try {
        accept(JSON.parse((event as MessageEvent).data));
      } catch {
        fail(new Error("任务进度格式错误，请重新打开资料库。"));
        finish();
      }
    });
    source.addEventListener("gone", () => {
      fail(new Error("任务已不存在。"));
      finish();
    });
    source.addEventListener("end", finish);
  }
  void connect().catch((e) => {
    if (!closed) {
      fail(e);
      finish();
    }
  });
  return finish;
}
