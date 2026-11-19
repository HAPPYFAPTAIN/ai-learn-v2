import { useState } from "react";
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
import { useSession } from "./session/store";
const nav = [
  ["/", "home", "学习首页"],
  ["/study", "book", "学习工作台"],
  ["/roadmap", "route", "学习路线"],
  ["/chat", "chat", "知识问答"],
  ["/library", "folder", "资料库"],
  ["/review", "review", "间隔复习"],
  ["/quiz", "quiz", "查漏测验"],
  ["/dashboard", "chart", "学习看板"],
  ["/tools", "tool", "学习工具"],
  ["/models", "settings", "模型设置"],
];
export default function App() {
  const me = useSession();
  const { query, value, invalid } = useProjects();
  const location = useLocation();
  const [params, setParams] = useSearchParams();
  const [open, setOpen] = useState(false);
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
        <div className="app-shell">
          <aside
            className={`sidebar ${open ? "is-open" : ""}`}
            id="primary-nav"
          >
            <Link to="/" className="brand" onClick={() => setOpen(false)}>
              <span className="brand-mark">
                <Icon name="book" size={23} />
              </span>
              <span>
                AI Learn<small>让学习，有迹可循</small>
              </span>
            </Link>
            <p className="nav-caption">学习空间</p>
            <nav aria-label="主导航">
              {nav.map(([path, icon, label]) => (
                <NavLink
                  key={path}
                  to={`${path}${path !== "/study" && params.get("project") ? `?project=${params.get("project")}` : ""}`}
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
                className="icon-button mobile-menu"
                aria-label="打开导航"
                aria-expanded={open}
                aria-controls="primary-nav"
                onClick={() => setOpen((v) => !v)}
              >
                <Icon name="menu" />
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
      </ProjectContext.Provider>
    </DraftProtection>
  );
}
