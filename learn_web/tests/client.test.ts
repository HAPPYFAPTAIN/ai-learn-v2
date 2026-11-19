import { beforeEach, describe, expect, it, vi } from "vitest";
import { request, setTransport, ApiError } from "../src/api/client";
import { session } from "../src/session/store";
import { key, queryClient } from "../src/query";
const me = { userId: "alice", displayName: "Alice", capabilities: {} };
beforeEach(() => {
  sessionStorage.clear();
  session.reset();
  queryClient.clear();
  session.ready(me);
});
describe("account-bound client", () => {
  it.each(["GET", "POST"])(
    "classifies a lost %s response without repeating the request",
    async (method) => {
      const fetcher = vi.fn(async () => {
        throw new TypeError("Failed to fetch");
      });
      setTransport(fetcher);
      await expect(request("/cards", { method })).rejects.toMatchObject({
        code: "NETWORK_ERROR",
        outcomeUnknown: method === "POST",
      });
      expect(fetcher).toHaveBeenCalledTimes(1);
    },
  );
  it("distinguishes timeout from caller cancellation and preserves uncertain write status", async () => {
    vi.useFakeTimers();
    try {
      const fetcher = vi.fn(
        (_url, init) =>
          new Promise<Response>((_resolve, reject) => {
            init?.signal?.addEventListener("abort", () =>
              reject(new DOMException("Aborted", "AbortError")),
            );
          }),
      );
      setTransport(fetcher);
      const outcome = expect(
        request("/cards", { method: "POST" }, undefined, "json", {
          timeoutMs: 50,
        }),
      ).rejects.toMatchObject({
        code: "REQUEST_TIMEOUT",
        outcomeUnknown: true,
      });
      await vi.advanceTimersByTimeAsync(51);
      await outcome;
      expect(fetcher).toHaveBeenCalledTimes(1);
      const caller = new AbortController();
      const cancelled = expect(
        request("/cards", { method: "POST" }, caller.signal),
      ).rejects.toMatchObject({ name: "AbortError" });
      caller.abort();
      await cancelled;
    } finally {
      vi.useRealTimers();
    }
  });
  it.each([200, 502])(
    "keeps ambiguous write outcome for a non-JSON response with status %i",
    async (status) => {
      setTransport(async () => new Response("<html>proxy</html>", { status }));
      await expect(request("/cards", { method: "POST" })).rejects.toMatchObject(
        { code: "INVALID_RESPONSE", outcomeUnknown: true },
      );
    },
  );
  it("binds mutations to the page account and cookie, without ticket storage", async () => {
    const fetcher = vi.fn(async () => new Response('{"ok":true}'));
    setTransport(fetcher);
    await request("/projects", { method: "POST", body: '{"title":"x"}' });
    const [url, init] = fetcher.mock.calls[0] as unknown as [
      string,
      RequestInit,
    ];
    expect(url).toBe("/api/v2/projects");
    expect(new Headers(init.headers).get("X-Learn-Expected-User")).toBe(
      "alice",
    );
    expect(init.credentials).toBe("same-origin");
    expect(init.cache).toBe("no-store");
    expect(sessionStorage.getItem("le.ticket")).toBeNull();
  });
  it("clears cached data and stops future requests on ACCOUNT_CHANGED", async () => {
    queryClient.setQueryData(key("projects"), { secret: "alice-only" });
    const transport = vi.fn(
      async () =>
        new Response(
          '{"error":{"code":"ACCOUNT_CHANGED","message":"changed"}}',
          { status: 409 },
        ),
    );
    setTransport(transport);
    await expect(request("/projects")).rejects.toMatchObject({
      code: "ACCOUNT_CHANGED",
    });
    expect(session.get().status).toBe("blocked");
    expect(queryClient.getQueryCache().getAll()).toHaveLength(0);
    await expect(request("/projects")).rejects.toMatchObject({
      name: "AbortError",
    });
    expect(transport).toHaveBeenCalledTimes(1);
  });
  it("discards a late response after the account has stopped", async () => {
    let resolve!: (response: Response) => void;
    setTransport(
      () =>
        new Promise((r) => {
          resolve = r;
        }),
    );
    const pending = request("/projects");
    session.stop("changed");
    resolve(new Response('{"items":[{"private":"old-user"}]}'));
    await expect(pending).rejects.toMatchObject({ name: "AbortError" });
  });
  it("keeps a page owner across reloads and rejects a different bootstrap identity", () => {
    session.reset();
    session.ready({ ...me, userId: "bob" });
    expect(session.get().status).toBe("blocked");
    expect(session.get().owner).toBe("");
  });
  it("discards a body that arrives after the account stopped", async () => {
    let resolve!: (text: string) => void;
    const response = new Response();
    response.text = () =>
      new Promise((r) => {
        resolve = r;
      });
    setTransport(async () => response);
    const pending = request("/projects");
    await Promise.resolve();
    session.stop("changed");
    resolve('{"private":"old-user"}');
    await expect(pending).rejects.toMatchObject({ name: "AbortError" });
  });
  it("stops even when the proxy returns an HTML login error", async () => {
    setTransport(
      async () => new Response("<html>login</html>", { status: 401 }),
    );
    await expect(request("/projects")).rejects.toMatchObject({
      code: "UNAUTHENTICATED",
    });
    expect(session.get().status).toBe("blocked");
  });
  it.each([401, 403])("stops on auth status %i", async (status) => {
    setTransport(
      async () =>
        new Response('{"error":{"code":"UNAUTHENTICATED"}}', { status }),
    );
    await expect(request("/me")).rejects.toBeInstanceOf(ApiError);
    expect(session.get().status).toBe("blocked");
  });
  it("preserves retry advice without retrying a paid operation", async () => {
    const transport = vi.fn(
      async () =>
        new Response(
          '{"error":{"code":"TENANT_BUSY","message":"busy","retryable":true,"retryAfterSeconds":5}}',
          { status: 429 },
        ),
    );
    setTransport(transport);
    await expect(
      request("/projects/1/chat", { method: "POST" }),
    ).rejects.toMatchObject({ code: "TENANT_BUSY", retryAfterSeconds: 5 });
    expect(transport).toHaveBeenCalledTimes(1);
    expect(session.get().status).toBe("ready");
  });
  it("handles a non-JSON proxy error without exposing its HTML", async () => {
    setTransport(
      async () => new Response("<html>proxy login</html>", { status: 502 }),
    );
    await expect(request("/projects")).rejects.toMatchObject({
      code: "INVALID_RESPONSE",
    });
  });
});
