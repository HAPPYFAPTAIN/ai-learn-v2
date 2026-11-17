import { useEffect, useState, type ReactNode } from "react";
import { endpoints } from "../api";
import { session, useSession } from "./store";
import { renewOfficial } from "./official";

export default function SessionGate({ children }: { children: ReactNode }) {
  const state = useSession();
  const [error, setError] = useState("");
  const [attempt, retry] = useState(0);
  useEffect(() => {
    const abort = new AbortController();
    let active = false;
    async function check() {
      if (active || abort.signal.aborted || session.get().status === "blocked")
        return;
      active = true;
      try {
        if (!__DEMO__ && session.get().owner)
          await renewOfficial(session.get().owner, abort.signal);
        const me = await endpoints.me(abort.signal);
        if (!abort.signal.aborted) {
          session.ready(me);
          setError("");
        }
      } catch (e) {
        if (abort.signal.aborted || session.get().status === "blocked") return;
        if (e instanceof Error && /登录|账号|资格/.test(e.message))
          session.stop(e.message);
        else setError("无法连接学习服务。请检查 API 是否启动，稍后重试。");
      } finally {
        active = false;
      }
    }
    void check();
    const timer = setInterval(() => {
      if (!document.hidden) void check();
    }, 120_000);
    const storage = (e: StorageEvent) => {
      if (e.key !== "aethericai-community-access-token" && e.key !== null)
        return;
      // Clear immediately: never show the previous account while verifying a new login.
      session.stop("官网登录状态已变化，请从官网重新进入学习应用。");
    };
    const visible = () => {
      if (!document.hidden) void check();
    };
    const restored = (e: PageTransitionEvent) => {
      if (e.persisted) session.stop("页面已从历史缓存恢复，请从官网重新进入。");
    };
    window.addEventListener("storage", storage);
    window.addEventListener("pageshow", restored);
    document.addEventListener("visibilitychange", visible);
    return () => {
      abort.abort();
      clearInterval(timer);
      window.removeEventListener("storage", storage);
      window.removeEventListener("pageshow", restored);
      document.removeEventListener("visibilitychange", visible);
    };
  }, [attempt]);
  if (state.status === "blocked")
    return (
      <main className="gate">
        <div className="panel">
          <p className="eyebrow">会话已停止</p>
          <h1>请重新进入学习应用</h1>
          <p role="alert">{state.message}</p>
          <a
            className="button primary"
            href="/official/products/learn-everything/"
          >
            从官网重新进入
          </a>
        </div>
      </main>
    );
  if (state.status === "loading")
    return (
      <main className="gate">
        <div className="panel">
          <h1>正在连接你的学习空间</h1>
          <p role="status">{error || "正在确认账号…"}</p>
          {error && (
            <button onClick={() => retry((n) => n + 1)}>重新连接</button>
          )}
        </div>
      </main>
    );
  return (
    <>
      {error && (
        <div role="status" className="connection-notice">
          {error}
        </div>
      )}
      {children}
    </>
  );
}
