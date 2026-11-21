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
import { useStudyMinutes } from "../components/useStudyMinutes";
import { generationStorageKey } from "../api/generation";
import GenerationAction from "../components/GenerationAction";
import AssessmentGenerator from "../components/AssessmentGenerator";
import ProjectCards from "../components/ProjectCards";
import LessonAnnotations from "../components/LessonAnnotations";
import ReadingTools from "../components/ReadingTools";
import NotesManager from "../components/NotesManager";
import { useConfirmDiscard } from "../components/DraftProtection";
import { lessonMarkdown, saveMarkdown } from "../components/contentExport";
import { Empty, ErrorNotice, Icon, QueryState } from "../components/ui";
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
  useStudyMinutes(id, current?.id);
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
                <Lesson
                  key={current.id}
                  node={current}
                  next={nodes.data.items[nodes.data.items.indexOf(current) + 1]}
                />
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

function Lesson({ node, next }: { node: KNode; next?: KNode }) {
  const confirmDiscard = useConfirmDiscard();
  const { id } = useProject();
  const client = useQueryClient();
  const [tab, setTab] = useState("内容");
  const tasks = useQuery({
    queryKey: key("tasks", id),
    queryFn: ({ signal }) => endpoints.tasks(id, signal),
    enabled: tab === "练习",
  });
  const progress = useMutation({
    mutationFn: () => endpoints.patchNode(node.id, { status: "done" }),
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
            onClick={() => {
              if (t !== tab) confirmDiscard(() => setTab(t));
            }}
          >
            {t}
          </button>
        ))}
      </div>
      <div role="tabpanel" id="lesson-tabpanel" aria-labelledby={`tab-${tab}`}>
        {tab === "内容" && (
          <>
            <ReadingTools
              actions={
                <button
                  type="button"
                  onClick={() =>
                    saveMarkdown(
                      lessonMarkdown(node),
                      `${node.code}-${node.title}`,
                    )
                  }
                >
                  导出本节课文
                </button>
              }
            >
              <LessonAnnotations
                key={`${node.id}:${node.contentVersion}`}
                projectId={id}
                nodeId={node.id}
              >
                <Suspense fallback={<p>正在加载内容…</p>}>
                  <Markdown key={node.description} hideExerciseAnswers>
                    {node.description || "本章节暂无内容。"}
                  </Markdown>
                </Suspense>
              </LessonAnnotations>
            </ReadingTools>
            <GenerationAction
              projectId={id}
              nodeId={node.id}
              ready={node.contentVersion > 0 && node.description.length >= 100}
            />
            <div className="content-actions lesson-completion">
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
              {(node.status === "done" || progress.isSuccess) &&
                (next ? (
                  <Link
                    className="button primary"
                    to={`/study?project=${id}&chapter=${next.id}`}
                  >
                    前往下一节 <Icon name="arrow" size={16} />
                  </Link>
                ) : (
                  <Link className="button" to={`/study?project=${id}`}>
                    已完成最后一节，返回目录
                  </Link>
                ))}
              <Link
                className="button study-ask"
                to={`/chat?project=${id}&chapter=${node.id}`}
              >
                向助教提问 <Icon name="chat" size={16} />
              </Link>
            </div>
            <ErrorNotice error={progress.error} />
          </>
        )}
        {tab === "笔记" && <NotesManager node={node} />}
        {tab === "练习" && (
          <>
            <div className="section-title spread">
              <h2>本节练习</h2>
              <AssessmentGenerator
                projectId={id}
                kind="quiz"
                nodeId={node.id}
                practice
              />
            </div>
            <p className="muted small">
              生成的练习保存在查漏测验，可作答、查看批改并再次回顾。
            </p>
            <Link className="button" to={`/quiz?project=${id}`}>
              查看已有测验与练习
            </Link>
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
                <p className="muted">
                  本章节暂无学习任务。新生成的练习请通过“查看已有测验与练习”打开。
                </p>
              )}
            <ErrorNotice error={completeTask.error} />
          </>
        )}
      </div>
    </article>
  );
}
