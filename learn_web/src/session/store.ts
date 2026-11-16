import { useSyncExternalStore } from "react";

export type SessionState = {
  status: "loading" | "ready" | "blocked";
  owner: string;
  name: string;
  message: string;
  capabilities: Record<string, boolean>;
  storage: Record<string, number> | null;
};
let state: SessionState = {
  status: "loading",
  owner: "",
  name: "",
  message: "",
  capabilities: {},
  storage: null,
};
let controller = new AbortController();
const listeners = new Set<() => void>();
const cleanup = new Set<() => void>();
const OWNER_KEY = "learn.v2.page-owner";
export const session = {
  get: () => state,
  signal: () => controller.signal,
  expected: () => state.owner || sessionStorage.getItem(OWNER_KEY) || "",
  subscribe(fn: () => void) {
    listeners.add(fn);
    return () => {
      listeners.delete(fn);
    };
  },
  onStop(fn: () => void) {
    cleanup.add(fn);
    return () => {
      cleanup.delete(fn);
    };
  },
  ready(me: {
    userId: string;
    displayName: string;
    capabilities: Record<string, boolean>;
    storage?: Record<string, number> | null;
  }) {
    if (state.status === "blocked") return;
    const expected = session.expected();
    if (expected && me.userId !== expected)
      return session.stop(
        "登录账号已变化，请从官网重新进入。原账号的学习数据仍保留。",
      );
    sessionStorage.setItem(OWNER_KEY, me.userId);
    state = {
      status: "ready",
      owner: me.userId,
      name: me.displayName,
      message: "",
      capabilities: me.capabilities,
      storage: me.storage ?? null,
    };
    listeners.forEach((fn) => fn());
  },
  stop(message: string) {
    if (state.status === "blocked") return;
    state = {
      status: "blocked",
      owner: "",
      name: "",
      message,
      capabilities: {},
      storage: null,
    };
    controller.abort();
    cleanup.forEach((fn) => fn());
    listeners.forEach((fn) => fn());
  },
  // Test-only reset; never used as a login/account switch in the application.
  reset() {
    controller.abort();
    controller = new AbortController();
    state = {
      status: "loading",
      owner: "",
      name: "",
      message: "",
      capabilities: {},
      storage: null,
    };
    listeners.forEach((fn) => fn());
  },
};
export function useSession() {
  return useSyncExternalStore(session.subscribe, session.get);
}
