import { lazy, Suspense, useEffect, useRef, useState } from "react";
import {
  Link,
  useLocation,
  useNavigate,
  useSearchParams,
} from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { endpoints, type KNode } from "../api";
import { key } from "../query";
import { useProject } from "../components/ProjectContext";
import { generationStorageKey } from "../api/generation";
import GenerationAction from "../components/GenerationAction";
import ProjectCards from "../components/ProjectCards";
import {
  AutoTextarea,
  Empty,
  ErrorNotice,
  Icon,
  QueryState,
} from "../components/ui";
const Markdown = lazy(() => import("../components/Markdown"));
export default function Workbench() {
  const { id, project, projects } = useProject();
  const location = useLocation();
  const navigate = useNavigate();
  const nodes = useQuery({
    queryKey: key("nodes", id),
    queryFn: ({ signal }) => endpoints.nodes(id, signal),
    enabled: !!id,
  });
  const [params] = useSearchParams();
  const chapter = params.get("chapter");
  const current = nodes.data?.items.find((n) => String(n.id) === chapter);
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    if (!nodes.data) return;
    heading.current?.focus({ preventScroll: true });
    window.scrollTo({ top: 0, behavior: "instant" });
  }, [chapter, !!nodes.data]);
  // URL parameters select the three layers: plans → chapters → lesson.
  if (!params.has("project"))
    return (
      <>
        <div className="page-heading study-heading">
          <h1>学习工作台</h1>
          <p className="muted">选择一个学习计划，查看课程章节并继续学习。</p>
        </div>
        {projects.length ? (
          <>
            <div className="section-title spread">
              <h2>我的学习计划</h2>
              <Link className="button primary" to="/#goal">
                <Icon name="plus" />
                添加学习计划
              </Link>
            </div>
            <ProjectCards projects={projects} />
          </>
        ) : (
          <Empty title="暂无学习计划" />
        )}
      </>
    );
  return (
    <>
      {!chapter && (
        <Link className="study-back" to="/study">
          <span aria-hidden="true">←</span> 返回学习计划
        </Link>
      )}
      {chapter && (
        <Link className="study-back" to={`/study?project=${id}`}>
          <span aria-hidden="true">←</span> 返回章节目录
        </Link>
      )}
      <div className="page-heading study-heading">
        <h1 ref={heading} tabIndex={-1} className="study-title">
          {chapter ? current?.title || "章节学习" : "学习工作台"}
        </h1>
        <p className="muted">
          {chapter
            ? project?.title
            : project
              ? `${project.title} · 选择一个章节，开始今天的学习。`
              : "每天一点积累，离目标更近一步。"}
        </p>
      </div>
      {!id ? (
        <Empty title="暂无学习计划" />
      ) : (
        <>
          <QueryState query={nodes} />
          {!chapter && nodes.data && (
            <GenerationAction
              key={id}
              projectId={id}
              ready={!!nodes.data.items.length}
              onComplete={() => {
                sessionStorage.removeItem(generationStorageKey(id));
                navigate("/study", { replace: true, state: null });
              }}
              initialJobId={
                location.state?.generationProjectId === id
                  ? location.state.generationJobId
                  : undefined
              }
            />
          )}
          {nodes.data &&
            (chapter ? (
              current ? (
                <Lesson key={current.id} node={current} />
              ) : (
                <Empty
                  title="找不到该章节"
                  description="该章节可能已被移除，请返回章节目录重新选择。"
                  action={false}
                />
              )
            ) : !nodes.data.items.length ? (
              <Empty
                title="暂无学习章节"
                description="可以用 AI 生成学习路线，或到学习路线手动添加章节。"
                action={false}
              />
            ) : (
              <section
                className="chapter-directory"
                aria-labelledby="chapter-directory-title"
              >
                <div className="section-title spread">
                  <div>
                    <h2 id="chapter-directory-title">课程章节</h2>
                    <p className="muted">按自己的节奏，一次专注一个章节。</p>
                  </div>
                  <span className="badge">
                    {nodes.data.items.length} 个章节
                  </span>
                </div>
                <ol className="chapter-cards">
                  {nodes.data.items.map((n, i) => (
                    <li key={n.id}>
                      <Link
                        className="panel chapter-card"
                        to={`/study?project=${id}&chapter=${n.id}`}
                      >
                        <span className="chapter-number" aria-hidden="true">
                          {String(i + 1).padStart(2, "0")}
                        </span>
                        <div className="chapter-card-body">
                          <p className="eyebrow">
                            {n.stage || "基础学习"} · {n.code}
                          </p>
                          <h3>{n.title}</h3>
                          <div className="chapter-meta">
                            <span>预计 {n.estHours} 小时</span>
                            <span>
                              {n.status === "done"
                                ? "已学完"
                                : n.status === "learning"
                                  ? "学习中"
                                  : "未开始"}
                            </span>
                          </div>
                        </div>
                        <div className="chapter-mastery">
                          <span>掌握度 {Math.round(n.mastery * 100)}%</span>
                          <div className="chapter-meter" aria-hidden="true">
                            <span
                              style={{
                                width: `${Math.min(100, Math.max(0, n.mastery * 100))}%`,
                              }}
                            />
                          </div>
                        </div>
                        <span className="chapter-enter" aria-hidden="true">
                          进入学习 <Icon name="arrow" size={18} />
                        </span>
                      </Link>
                    </li>
                  ))}
                </ol>
              </section>
            ))}
        </>
      )}
    </>
  );
}

function Lesson({ node }: { node: KNode }) {
  const { id } = useProject();
  const client = useQueryClient();
  const [tab, setTab] = useState("内容");
  const [note, setNote] = useState("");
  const notes = useQuery({
    queryKey: key("notes", id),
    queryFn: ({ signal }) => endpoints.notes(id, signal),
    enabled: tab === "笔记",
  });
  const tasks = useQuery({
    queryKey: key("tasks", id),
    queryFn: ({ signal }) => endpoints.tasks(id, signal),
    enabled: tab === "练习",
  });
  const save = useMutation({
    mutationFn: () =>
      endpoints.createNote(id, { nodeId: node.id, content: note.trim() }),
    onSuccess: () => {
      setNote("");
      void client.invalidateQueries({ queryKey: key("notes", id) });
    },
  });
  const progress = useMutation({
    mutationFn: () =>
      endpoints.patchNode(node.id, { status: "done", mastery: 1 }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: key("nodes", id) });
      void client.invalidateQueries({ queryKey: key("summary", id) });
    },
  });
  const completeTask = useMutation({
    mutationFn: (taskId: number) =>
      endpoints.patchTask(taskId, { status: "done" }),
    onSuccess: () =>
      void client.invalidateQueries({ queryKey: key("tasks", id) }),
  });
  return (
    <article className="panel lesson-panel">
      <p className="eyebrow">
        {node.stage || "当前章节"} / {node.code}
      </p>
      <div className="tabs" role="tablist" aria-label="章节内容">
        {["内容", "笔记", "练习"].map((t) => (
          <button
            key={t}
            role="tab"
            aria-selected={tab === t}
            id={`tab-${t}`}
            aria-controls="lesson-tabpanel"
            onClick={() => setTab(t)}
          >
            {t}
          </button>
        ))}
      </div>
      <div role="tabpanel" id="lesson-tabpanel" aria-labelledby={`tab-${tab}`}>
        {tab === "内容" && (
          <>
            <Suspense fallback={<p>正在加载内容…</p>}>
              <Markdown key={node.description} hideExerciseAnswers>
                {node.description || "本章节暂无内容。"}
              </Markdown>
            </Suspense>
            <GenerationAction
              projectId={id}
              nodeId={node.id}
              ready={node.contentVersion > 0 && node.description.length >= 100}
            />
            <button
              className="primary"
              disabled={progress.isPending || node.status === "done"}
              onClick={() => progress.mutate()}
            >
              {node.status === "done"
                ? "已完成学习"
                : progress.isPending
                  ? "正在保存…"
                  : "标记为已学完"}
            </button>
            <ErrorNotice error={progress.error} />
            <Link
              className="button study-ask"
              to={`/chat?project=${id}&chapter=${node.id}`}
            >
              向助教提问 <Icon name="chat" size={16} />
            </Link>
          </>
        )}
        {tab === "笔记" && (
          <>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                if (note.trim() && !save.isPending) save.mutate();
              }}
            >
              <label htmlFor="lesson-note">记下你的理解</label>
              <AutoTextarea
                id="lesson-note"
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="一个想通的概念、一段自己的总结…"
                required
              />
              <button
                className="primary"
                disabled={!note.trim() || save.isPending}
              >
                {save.isPending ? "保存中…" : "保存笔记"}
              </button>
              <ErrorNotice error={save.error} />
            </form>
            <QueryState query={notes} />
            {notes.data?.items
              .filter((n) => n.nodeId === node.id)
              .map((n) => (
                <div className="note-card" key={n.id}>
                  <Suspense fallback={null}>
                    <Markdown>{n.content}</Markdown>
                  </Suspense>
                </div>
              ))}
          </>
        )}
        {tab === "练习" && (
          <>
            <QueryState query={tasks} />
            {tasks.data?.items
              .filter((t) => t.nodeId === node.id)
              .map((t) => (
                <div className="note-card" key={t.id}>
                  <h3>{t.title}</h3>
                  <p>{t.description}</p>
                  <button
                    disabled={completeTask.isPending || t.status === "done"}
                    onClick={() => completeTask.mutate(t.id)}
                  >
                    {t.status === "done" ? "已完成" : "标记完成"}
                  </button>
                </div>
              ))}
            {tasks.data &&
              !tasks.data.items.some((t) => t.nodeId === node.id) && (
                <p className="muted">本章节暂无练习。</p>
              )}
            <ErrorNotice error={completeTask.error} />
          </>
        )}
      </div>
    </article>
  );
}
