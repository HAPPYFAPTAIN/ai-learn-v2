import { Suspense, useEffect, useRef, useState } from "react";
import {
  Link,
  NavLink,
  Outlet,
  useLocation,
  useNavigationType,
  useSearchParams,
} from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { endpoints } from "./api";
import { key } from "./query";
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
  { path: "/", icon: "home", label: "学习首页" },
  { path: "/roadmap", icon: "route", label: "学习路线" },
  { path: "/study", icon: "book", label: "学习工作台" },
  { path: "/review", icon: "review", label: "间隔复习" },
  { path: "/quiz", icon: "quiz", label: "查漏测验" },
  { path: "/dashboard", icon: "chart", label: "学习看板" },
  { path: "/chat", icon: "chat", label: "知识问答" },
  { path: "/library", icon: "folder", label: "资料库" },
  { path: "/tools", icon: "tool", label: "学习工具" },
  { path: "/models", icon: "settings", label: "模型设置" },
] as const;

const navGroups = [
  {
    id: "start",
    title: "开始学习",
    subtitle: "START HERE",
    paths: ["/", "/roadmap"],
  },
  {
    id: "study",
    title: "当前学习计划",
    subtitle: "YOUR LEARNING PATH",
    paths: ["/study"],
  },
  {
    id: "practice",
    title: "练习与复习",
    subtitle: "MAKE IT STICK",
    paths: ["/review", "/quiz", "/dashboard"],
  },
  {
    id: "knowledge",
    title: "知识与资料",
    subtitle: "ASK · READ · BUILD",
    paths: ["/chat", "/library", "/tools"],
  },
  {
    id: "settings",
    title: "设置",
    subtitle: "WORKSPACE",
    paths: ["/models"],
  },
] as const;

function groupForPath(pathname: string) {
  return (
    navGroups.find((group) => group.paths.some((path) => path === pathname))
      ?.id || "start"
  );
}

export default function App() {
  const me = useSession();
  const [assistantContext, setAssistantContext] =
    useState<AssistantPageContext>({});
  const { query, value, invalid } = useProjects();
  const location = useLocation();
  const navigationType = useNavigationType();
  const [params, setParams] = useSearchParams();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [expandedGroup, setExpandedGroup] = useState<string | null>(() =>
    groupForPath(location.pathname),
  );
  const [theme, setTheme] = useState(
    () => document.documentElement.dataset.theme || "dark",
  );
  const [mobile, setMobile] = useState(
    () => window.matchMedia("(max-width: 850px)").matches,
  );
  const closeButton = useRef<HTMLButtonElement>(null);
  const restoreFocus = useRef<HTMLElement | null>(null);
  const chapterId = params.get("chapter");
  const pageLabel =
    nav.find((item) => item.path === location.pathname)?.label || "学习";
  const section = groupForPath(location.pathname);
  const group = navGroups.find((item) => item.id === section) || navGroups[0];
  // The first page of a group stands for the whole chapter in the breadcrumb.
  const groupHome = group.paths[0] === location.pathname;
  const nodes = useQuery({
    queryKey: key("nodes", value.id),
    queryFn: ({ signal }) => endpoints.nodes(value.id, signal),
    enabled:
      !!value.id &&
      (drawerOpen || (location.pathname === "/study" && params.has("chapter"))),
  });
  const currentChapter = nodes.data?.items.find(
    (node) => String(node.id) === chapterId,
  );

  useEffect(() => {
    if (!document.documentElement.dataset.theme)
      document.documentElement.dataset.theme = "dark";
  }, []);
  // Each navigation group carries its own accent, like a chapter theme.
  useEffect(() => {
    document.documentElement.dataset.section = section;
  }, [section]);
  // A link opens the new page at its top. Going back or forward returns the
  // reader to the place they left, as the browser would.
  useEffect(() => {
    if (navigationType === "POP") return;
    window.scrollTo({ top: 0, behavior: "instant" });
  }, [location.pathname]);
  useEffect(() => {
    const media = window.matchMedia("(max-width: 850px)");
    const update = () => {
      setMobile(media.matches);
      setDrawerOpen(false);
    };
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);
  useEffect(() => {
    if (!drawerOpen) return;
    setExpandedGroup(groupForPath(location.pathname));
    const focusClose = () => {
      if (!closeButton.current?.closest("#primary-nav")?.contains(document.activeElement))
        closeButton.current?.focus({ preventScroll: true });
    };
    const frame = requestAnimationFrame(focusClose);
    const timer = window.setTimeout(focusClose, 80);
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      cancelAnimationFrame(frame);
      window.clearTimeout(timer);
      document.body.style.overflow = previous;
    };
  }, [drawerOpen]);
  useEffect(() => {
    if (!drawerOpen) return;
    const escape = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      closeDrawer();
    };
    document.addEventListener("keydown", escape);
    return () => document.removeEventListener("keydown", escape);
  }, [drawerOpen]);

  function openDrawer(trigger: HTMLElement) {
    restoreFocus.current = trigger;
    setDrawerOpen(true);
  }
  function closeDrawer(returnFocus = true) {
    setDrawerOpen(false);
    if (returnFocus) requestAnimationFrame(() => restoreFocus.current?.focus());
  }
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
          <div className="app-shell">
            <aside
              className="nav-rail"
              aria-label="章节导航轨"
              inert={drawerOpen || mobile}
            >
              <button
                type="button"
                className="rail-menu"
                aria-label="打开导航"
                aria-expanded={drawerOpen}
                aria-controls="primary-nav"
                onClick={(event) => openDrawer(event.currentTarget)}
              >
                <span />
                <span />
                <span />
              </button>
              <span className="rail-word" aria-hidden="true">
                章节
              </span>
            </aside>

            <aside
              className={`sidebar chapter-drawer ${drawerOpen ? "is-open" : ""}`}
              id="primary-nav"
              aria-label="章节与学习导航"
              inert={!drawerOpen}
            >
              <div className="drawer-heading">
                <Link
                  to="/"
                  className="drawer-brand"
                  onClick={() => closeDrawer(false)}
                >
                  <span className="drawer-brand-mark">A</span>
                  <span>
                    AI Learn<small>让学习，有迹可循</small>
                  </span>
                </Link>
                <button
                  ref={closeButton}
                  type="button"
                  className="drawer-close"
                  aria-label="收起侧栏"
                  title="关闭章节导航"
                  onClick={() => closeDrawer()}
                >
                  <span aria-hidden="true">×</span>
                </button>
              </div>

              <div className="drawer-scroll">
                <p className="nav-caption">导航</p>
                <nav aria-label="主导航" className="drawer-groups">
                  {navGroups.map((group) => {
                    const expanded = expandedGroup === group.id;
                    return (
                      <section
                        className="drawer-nav-group"
                        data-section={group.id}
                        key={group.id}
                      >
                        <button
                          type="button"
                          className={`drawer-group-trigger ${expanded ? "is-expanded" : ""} ${
                            groupForPath(location.pathname) === group.id
                              ? "is-current"
                              : ""
                          }`}
                          aria-expanded={expanded}
                          aria-controls={`drawer-group-${group.id}`}
                          onClick={() =>
                            setExpandedGroup(expanded ? null : group.id)
                          }
                        >
                          <span>
                            <strong>{group.title}</strong>
                            <small>{group.subtitle}</small>
                          </span>
                          <span className="drawer-group-toggle" aria-hidden>
                            {expanded ? "−" : "+"}
                          </span>
                        </button>
                        <div
                          className={`drawer-subnav-shell ${expanded ? "is-open" : ""}`}
                          id={`drawer-group-${group.id}`}
                          aria-hidden={!expanded}
                          inert={!expanded}
                        >
                          <div className="drawer-subnav">
                            {group.paths.map((path) => {
                              const item = nav.find(
                                (entry) => entry.path === path,
                              );
                              if (!item) return null;
                              return (
                                <NavLink
                                  key={path}
                                  to={`${path}${
                                    path !== "/study" && params.get("project")
                                      ? `?project=${params.get("project")}`
                                      : ""
                                  }`}
                                  end={path === "/"}
                                  onClick={() => closeDrawer(false)}
                                >
                                  {item.label}
                                </NavLink>
                              );
                            })}
                            {group.id === "study" && (
                              <div className="drawer-chapter-list">
                                {!value.id ? (
                                  <p className="drawer-empty">
                                    选择一个学习计划后，这里会显示章节。
                                  </p>
                                ) : nodes.isPending ? (
                                  <p className="drawer-empty">正在读取章节…</p>
                                ) : nodes.data?.items.length ? (
                                  <ol>
                                    {nodes.data.items.map((node, index) => (
                                      <li key={node.id}>
                                        <Link
                                          className={
                                            String(node.id) === chapterId
                                              ? "active"
                                              : ""
                                          }
                                          to={`/study?project=${value.id}&chapter=${node.id}`}
                                          onClick={() => closeDrawer(false)}
                                        >
                                          <span>
                                            {String(index + 1).padStart(2, "0")}
                                          </span>
                                          <div>
                                            <strong>{node.title}</strong>
                                            <small>
                                              {node.stage || "基础学习"} ·{" "}
                                              {node.status === "done"
                                                ? "已完成"
                                                : node.status === "learning"
                                                  ? "学习中"
                                                  : "未开始"}
                                            </small>
                                          </div>
                                        </Link>
                                      </li>
                                    ))}
                                  </ol>
                                ) : (
                                  <p className="drawer-empty">
                                    当前计划还没有章节。
                                  </p>
                                )}
                              </div>
                            )}
                          </div>
                        </div>
                      </section>
                    );
                  })}
                </nav>
              </div>

              <div className="drawer-bottom">
                <div className="avatar">{me.name.slice(0, 1)}</div>
                <div>
                  <strong>{me.name}</strong>
                  <small>{__DEMO__ ? "本地演示空间" : "个人学习空间"}</small>
                </div>
                <span className="online-dot" aria-label="已连接" />
              </div>
              <p className="drawer-credit">
                字体{" "}
                <a
                  href="https://hyperos.mi.com/font/zh/download/"
                  target="_blank"
                  rel="noreferrer"
                >
                  MiSans
                </a>{" "}
                · 小米
              </p>
            </aside>

            {drawerOpen && (
              <button
                className="nav-backdrop"
                aria-label="关闭导航"
                onClick={() => closeDrawer()}
              />
            )}

            <div className="main-shell">
              <header className="topbar">
                <button
                  type="button"
                  className="icon-button mobile-menu"
                  aria-label="打开导航"
                  aria-expanded={drawerOpen}
                  aria-controls="primary-nav"
                  onClick={(event) => openDrawer(event.currentTarget)}
                >
                  <Icon name="menu" />
                </button>
                {location.pathname === "/study" && chapterId ? (
                  <Link
                    className="study-back topbar-study-back"
                    to={`/study?project=${value.id}`}
                  >
                    <span aria-hidden="true">←</span> 返回章节目录
                  </Link>
                ) : null}
                <div className="breadcrumb">
                  <Link to="/" className="crumb-brand">
                    AI Learn
                  </Link>
                  <span aria-hidden="true">—</span>
                  <strong className={groupHome ? "is-current" : undefined}>
                    {group.title}
                  </strong>
                  {!groupHome && (
                    <>
                      <span aria-hidden="true">/</span>
                      <strong className="is-current">{pageLabel}</strong>
                    </>
                  )}
                  {currentChapter && (
                    <>
                      <span aria-hidden="true">/</span>
                      <em>{currentChapter.title}</em>
                    </>
                  )}
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
                  <Link
                    className="icon-button topbar-settings"
                    to="/models"
                    aria-label="打开模型设置"
                    title="模型设置"
                  >
                    <Icon name="settings" />
                  </Link>
                </div>
              </header>
              {__DEMO__ && (
                <div className="demo-notice" role="note">
                  本地演示 ·
                  使用临时示例数据，刷新后重置，不调用模型、不连接你的真实账户。
                </div>
              )}
              <ConnectionStatus />
              {/* If a page still has to be fetched, only this area waits, and
                  the page already on screen stays until the next one is ready.
                  The boundary outlives every page on purpose: main is keyed,
                  so a boundary inside it would be new on each navigation and
                  would show its fallback at once. */}
              <Suspense
                fallback={
                  <p role="status" className="loading route-loading">
                    正在打开页面…
                  </p>
                }
              >
                <main
                  id="main-content"
                  className={
                    location.pathname === "/study" && chapterId
                      ? "route-lesson"
                      : undefined
                  }
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
              </Suspense>
              <footer>
                <span>AI Learn — 把好奇，变成每天的进步。</span>
                <span>
                  字体{" "}
                  <a
                    href="https://hyperos.mi.com/font/zh/download/"
                    target="_blank"
                    rel="noreferrer"
                  >
                    MiSans
                  </a>{" "}
                  / Xiaomi
                </span>
              </footer>
            </div>
          </div>
          <GlobalAssistant key={me.owner} context={assistantContext} />
        </AssistantContext.Provider>
      </ProjectContext.Provider>
    </DraftProtection>
  );
}
