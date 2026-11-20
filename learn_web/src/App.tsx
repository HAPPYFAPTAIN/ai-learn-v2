import { useEffect, useRef, useState } from "react";
import {
  Link,
  NavLink,
  Outlet,
  useLocation,
  useSearchParams,
} from "react-router-dom";
import { ProjectContext, useProjects } from "./components/ProjectContext";
import ProjectPicker from "./components/ProjectPicker";
import DraftProtection from "./components/DraftProtection";
import ConnectionStatus from "./components/ConnectionStatus";
import { Icon, QueryState, ErrorNotice } from "./components/ui";
import GlobalAssistant from "./components/GlobalAssistant";
import {
  AssistantContext,
  type AssistantPageContext,
} from "./components/AssistantContext";
import { useSession } from "./session/store";
const nav = [
  ["/", "home", "学习首页"],
  ["/roadmap", "route", "学习路线"],
  ["/study", "book", "学习工作台"],
  ["/review", "review", "间隔复习"],
  ["/quiz", "quiz", "查漏测验"],
  ["/dashboard", "chart", "学习看板"],
  ["/chat", "chat", "知识问答"],
  ["/library", "folder", "资料库"],
  ["/tools", "tool", "学习工具"],
  ["/models", "settings", "模型设置"],
];
export default function App() {
  const me = useSession();
  const [assistantContext, setAssistantContext] =
    useState<AssistantPageContext>({});
  const { query, value, invalid } = useProjects();
  const location = useLocation();
  const [params, setParams] = useSearchParams();
  const [open, setOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(() => {
    try {
      return localStorage.getItem("learn.sidebar.collapsed") === "true";
    } catch {
      return false;
    }
  });
  const [mobile, setMobile] = useState(
    () => window.matchMedia("(max-width: 850px)").matches,
  );
  const collapseButton = useRef<HTMLButtonElement>(null);
  const expandButton = useRef<HTMLButtonElement>(null);
  const mobileButton = useRef<HTMLButtonElement>(null);
  const restoreFocus = useRef(false);
  useEffect(() => {
    const media = window.matchMedia("(max-width: 850px)");
    const update = () => {
      setMobile(media.matches);
      setOpen(false);
    };
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);
  useEffect(() => {
    if (!restoreFocus.current) return;
    restoreFocus.current = false;
    (mobile
      ? mobileButton
      : collapsed
        ? expandButton
        : collapseButton
    ).current?.focus();
  }, [collapsed, mobile, open]);
  function toggleSidebar() {
    restoreFocus.current = true;
    if (mobile) {
      setOpen(false);
      return;
    }
    const next = !collapsed;
    setCollapsed(next);
    try {
      localStorage.setItem("learn.sidebar.collapsed", String(next));
    } catch {
      // The layout still works when browser storage is unavailable.
    }
  }
  const [theme, setTheme] = useState(
    () => document.documentElement.dataset.theme || "light",
  );
  function toggleTheme() {
    const next = theme === "light" ? "dark" : "light";
    setTheme(next);
    document.documentElement.dataset.theme = next;
    localStorage.setItem("learn.theme", next);
  }
  return (
    <DraftProtection>
      <ProjectContext.Provider value={value}>
        <AssistantContext.Provider value={setAssistantContext}>
          <div className={`app-shell ${collapsed ? "sidebar-collapsed" : ""}`}>
            <aside
              className={`sidebar ${open ? "is-open" : ""}`}
              id="primary-nav"
              inert={mobile ? !open : collapsed}
            >
              <div className="sidebar-heading">
                <Link to="/" className="brand" onClick={() => setOpen(false)}>
                  <span className="brand-mark">
                    <Icon name="book" size={23} />
                  </span>
                  <span>
                    AI Learn<small>让学习，有迹可循</small>
                  </span>
                </Link>
                <button
                  ref={collapseButton}
                  type="button"
                  className="icon-button sidebar-collapse"
                  aria-label="收起侧栏"
                  title="收起侧栏，专注学习"
                  aria-expanded={mobile ? open : !collapsed}
                  aria-controls="primary-nav"
                  onClick={toggleSidebar}
                >
                  <Icon name="chevron-left" />
                </button>
              </div>
              <p className="nav-caption">学习空间</p>
              <nav aria-label="主导航">
                {nav.map(([path, icon, label]) => (
                  <NavLink
                    key={path}
                    to={`${path}${path !== "/study" && params.get("project") ? `?project=${params.get("project")}` : ""}`}
                    className={
                      path === "/chat" || path === "/models"
                        ? "nav-group-start"
                        : undefined
                    }
                    end={path === "/"}
                    onClick={() => setOpen(false)}
                  >
                    <Icon name={icon} />
                    <span>{label}</span>
                  </NavLink>
                ))}
              </nav>
              <div className="sidebar-bottom">
                <div className="avatar">{me.name.slice(0, 1)}</div>
                <div>
                  <strong>{me.name}</strong>
                  <small>{__DEMO__ ? "本地演示空间" : "个人学习空间"}</small>
                </div>
                <span className="online-dot" aria-label="已连接" />
              </div>
            </aside>
            {open && (
              <button
                className="nav-backdrop"
                aria-label="关闭导航"
                onClick={() => setOpen(false)}
              />
            )}
            <div className="main-shell">
              <header className="topbar">
                <button
                  ref={mobileButton}
                  className="icon-button mobile-menu"
                  aria-label="打开导航"
                  aria-expanded={open}
                  aria-controls="primary-nav"
                  onClick={() => setOpen((v) => !v)}
                >
                  <Icon name="menu" />
                </button>
                <button
                  ref={expandButton}
                  type="button"
                  className="icon-button sidebar-expand"
                  aria-label="展开侧栏"
                  title="展开侧栏"
                  aria-expanded={!collapsed}
                  aria-controls="primary-nav"
                  onClick={toggleSidebar}
                >
                  <Icon name="chevron-right" />
                </button>
                <div className="breadcrumb">
                  我的学习空间 <span>/</span>{" "}
                  <strong>
                    {nav.find(([p]) => p === location.pathname)?.[2] || "学习"}
                  </strong>
                </div>
                <div className="topbar-actions">
                  <ProjectPicker
                    projects={value.projects}
                    value={value.id}
                    onChange={(id) => {
                      const next = new URLSearchParams(params);
                      next.set("project", String(id));
                      next.delete("chapter");
                      next.delete("quiz");
                      setParams(next);
                    }}
                  />
                  <button
                    className="icon-button"
                    aria-label={
                      theme === "light" ? "切换深色主题" : "切换浅色主题"
                    }
                    onClick={toggleTheme}
                  >
                    <Icon name={theme === "light" ? "moon" : "sun"} />
                  </button>
                </div>
              </header>
              {__DEMO__ && (
                <div className="demo-notice" role="note">
                  本地演示 ·
                  使用临时示例数据，刷新后重置，不调用模型、不连接你的真实账户。
                </div>
              )}
              <ConnectionStatus />
              <main
                id="main-content"
                key={`${me.owner}:${value.id}:${location.pathname}`}
              >
                {query.isPending || query.error ? (
                  <QueryState query={query} />
                ) : invalid ? (
                  <ErrorNotice
                    error={
                      new Error("找不到该学习计划，请在右上角选择其他计划。")
                    }
                  />
                ) : (
                  <Outlet />
                )}
              </main>
              <footer>
                AI Learn <span>把好奇，变成每天的进步。</span>
              </footer>
            </div>
          </div>
          <GlobalAssistant key={me.owner} context={assistantContext} />
        </AssistantContext.Provider>
      </ProjectContext.Provider>
    </DraftProtection>
  );
}
