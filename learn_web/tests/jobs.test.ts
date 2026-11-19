import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { setTransport } from "../src/api/client";
import { setStreamFactory, watchJob, type EventStream } from "../src/api/jobs";
import { session } from "../src/session/store";
let source: EventStream, target: EventTarget;
const job = {
  jobId: "j1",
  kind: "index",
  state: "running",
  progress: { done: 1, total: 3 },
};
beforeEach(() => {
  vi.useFakeTimers();
  sessionStorage.clear();
  session.reset();
  session.ready({ userId: "alice", displayName: "Alice", capabilities: {} });
  target = new EventTarget();
  source = {
    close: vi.fn(),
    addEventListener: target.addEventListener.bind(
      target,
    ) as EventStream["addEventListener"],
    onopen: null,
    onerror: null,
  };
  setStreamFactory(vi.fn(() => source));
});
afterEach(() => {
  session.stop("end");
  vi.useRealTimers();
});
async function flush() {
  await vi.advanceTimersByTimeAsync(0);
}
it("polls every 3 s only while disconnected, then stops on terminal progress", async () => {
  const transport = vi.fn(async () => new Response(JSON.stringify(job)));
  setTransport(transport);
  const update = vi.fn(),
    states = vi.fn();
  watchJob("j1", update, states, vi.fn());
  await flush();
  expect(transport).toHaveBeenCalledTimes(1);
  source.onerror!.call(source as EventSource, new Event("error"));
  await flush();
  await vi.advanceTimersByTimeAsync(3000);
  expect(transport).toHaveBeenCalledTimes(3);
  source.onopen!.call(source as EventSource, new Event("open"));
  await vi.advanceTimersByTimeAsync(6000);
  expect(transport).toHaveBeenCalledTimes(3);
  target.dispatchEvent(
    new MessageEvent("progress", {
      data: JSON.stringify({ ...job, state: "done" }),
    }),
  );
  expect(states).toHaveBeenLastCalledWith("closed");
  expect(source.close).toHaveBeenCalledTimes(1);
  await vi.advanceTimersByTimeAsync(6000);
  expect(transport).toHaveBeenCalledTimes(3);
});
it("binds EventSource to the owner and closes it on account change", async () => {
  setTransport(async () => new Response(JSON.stringify(job)));
  const factory = vi.fn(() => source);
  setStreamFactory(factory);
  const update = vi.fn();
  watchJob("j1", update, vi.fn(), vi.fn());
  await flush();
  expect(factory).toHaveBeenCalledWith(
    "/api/v2/jobs/j1/events?__le_owner=alice",
  );
  const prior = update.mock.calls.length;
  session.stop("changed");
  target.dispatchEvent(
    new MessageEvent("progress", { data: JSON.stringify(job) }),
  );
  expect(update).toHaveBeenCalledTimes(prior);
  expect(source.close).toHaveBeenCalledTimes(1);
});
it("uses preflight to reject expired/mismatched sessions before opening a stream", async () => {
  setTransport(
    async () =>
      new Response('{"error":{"code":"ACCOUNT_CHANGED"}}', { status: 409 }),
  );
  const factory = vi.fn(() => source);
  setStreamFactory(factory);
  watchJob("j1", vi.fn(), vi.fn(), vi.fn());
  await flush();
  expect(factory).not.toHaveBeenCalled();
  expect(session.get().status).toBe("blocked");
});
it("ignores progress from a different job and closes malformed streams", async () => {
  setTransport(async () => new Response(JSON.stringify(job)));
  const update = vi.fn(),
    fail = vi.fn();
  watchJob("j1", update, vi.fn(), fail);
  await flush();
  const before = update.mock.calls.length;
  target.dispatchEvent(
    new MessageEvent("progress", {
      data: JSON.stringify({ ...job, jobId: "other" }),
    }),
  );
  expect(update).toHaveBeenCalledTimes(before);
  target.dispatchEvent(new MessageEvent("progress", { data: "bad JSON" }));
  expect(fail).toHaveBeenCalled();
  expect(source.close).toHaveBeenCalledTimes(1);
});

it("survives offline preflight and receives progress after reconnection", async () => {
  const transport = vi
    .fn()
    .mockRejectedValueOnce(new TypeError("offline"))
    .mockResolvedValue(new Response(JSON.stringify(job)));
  setTransport(transport);
  const update = vi.fn(),
    fail = vi.fn();
  watchJob("j1", update, vi.fn(), fail);
  await flush();
  expect(fail).not.toHaveBeenCalled();
  expect(source.close).not.toHaveBeenCalled();
  source.onopen!.call(source as EventSource, new Event("open"));
  target.dispatchEvent(
    new MessageEvent("progress", {
      data: JSON.stringify({ ...job, state: "done" }),
    }),
  );
  expect(update).toHaveBeenLastCalledWith({ ...job, state: "done" });
  expect(source.close).toHaveBeenCalledTimes(1);
});

it("keeps fallback polling through a temporary network failure", async () => {
  const transport = vi
    .fn()
    .mockResolvedValueOnce(new Response(JSON.stringify(job)))
    .mockRejectedValueOnce(new TypeError("offline"))
    .mockResolvedValueOnce(
      new Response(JSON.stringify({ ...job, state: "done" })),
    );
  setTransport(transport);
  const update = vi.fn(),
    fail = vi.fn();
  watchJob("j1", update, vi.fn(), fail);
  await flush();
  source.onerror!.call(source as EventSource, new Event("error"));
  await flush();
  expect(fail).not.toHaveBeenCalled();
  expect(source.close).not.toHaveBeenCalled();
  await vi.advanceTimersByTimeAsync(3000);
  expect(transport).toHaveBeenCalledTimes(3);
  expect(update).toHaveBeenLastCalledWith({ ...job, state: "done" });
  expect(source.close).toHaveBeenCalledTimes(1);
});
