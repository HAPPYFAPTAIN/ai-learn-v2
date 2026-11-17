import { Input } from "../components/fields";
import { lazy, Suspense, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { endpoints } from "../api";
import { key } from "../query";
import { useProject } from "../components/ProjectContext";
import GenerationAction from "../components/GenerationAction";
import { roadmapOutline, downloadRoadmap } from "../components/roadmapContent";
import {
  Empty,
  ErrorNotice,
  Icon,
  PageHeading,
  QueryState,
} from "../components/ui";
const MindMap = lazy(() => import("../components/MindMap"));
export default function Roadmap() {
  const { id, project } = useProject();
  const client = useQueryClient();
  const nodes = useQuery({
    queryKey: key("nodes", id),
    queryFn: ({ signal }) => endpoints.nodes(id, signal),
    enabled: !!id,
  });
  const [title, setTitle] = useState("");
  const [code, setCode] = useState("");
  const [hours, setHours] = useState(2);
  const [weeks, setWeeks] = useState(8);
  const [weekly, setWeekly] = useState(5);
  const [mapProject, setMapProject] = useState<number>();
  const [exportError, setExportError] = useState<Error>();
  const add = useMutation({
    mutationFn: () =>
      endpoints.createNode(id, {
        code: code.trim(),
        title: title.trim(),
        estHours: hours,
      }),
    onSuccess: () => {
      setTitle("");
      setCode("");
      void client.invalidateQueries({ queryKey: key("nodes", id) });
    },
  });
  const plan = useMutation({
    mutationFn: () => endpoints.path(id, { weeks, hoursPerWeek: weekly }),
  });
  return (
    <>
      <PageHeading
        title="学习路线"
        description="把大目标拆成小章节，找到适合自己的前进节奏。"
      />
      {!id ? (
        <Empty title="暂无学习路线" />
      ) : (
        <>
          <QueryState query={nodes} />
          {nodes.data && (
            <>
              <div className="panel">
                <div className="section-title spread">
                  <h2>我的知识章节</h2>
                  <div className="content-actions">
                    <span className="badge">
                      {nodes.data.items.length} 个章节
                    </span>
                    <button
                      type="button"
                      disabled={!nodes.data.items.length}
                      aria-expanded={mapProject === id}
                      onClick={() =>
                        setMapProject(mapProject === id ? undefined : id)
                      }
                    >
                      {mapProject === id ? "收起思维导图" : "思维导图"}
                    </button>
                    <button
                      type="button"
                      disabled={!nodes.data.items.length}
                      onClick={() => {
                        try {
                          downloadRoadmap(project, nodes.data.items);
                          setExportError(undefined);
                        } catch {
                          setExportError(new Error("导出未完成，请重试"));
                        }
                      }}
                    >
                      导出路线
                    </button>
                  </div>
                </div>
                <ErrorNotice error={exportError} />
                {mapProject === id && !!nodes.data.items.length && (
                  <Suspense fallback={<p role="status">正在加载思维导图…</p>}>
                    <MindMap
                      key={id}
                      source={roadmapOutline(project, nodes.data.items)}
                    />
                  </Suspense>
                )}
                <GenerationAction
                  key={id}
                  projectId={id}
                  hideCompleted
                  ready={!!nodes.data.items.length}
                />
                {!nodes.data.items.length ? (
                  <div className="empty-inline">
                    暂无学习路线，可以用 AI 生成，或手动添加章节。
                  </div>
                ) : (
                  <ol className="roadmap-list">
                    {nodes.data.items.map((n) => (
                      <li key={n.id}>
                        <span
                          className={`roadmap-dot ${n.mastery === 1 ? "done" : ""}`}
                        >
                          <Icon
                            name={n.mastery === 1 ? "check" : "book"}
                            size={17}
                          />
                        </span>
                        <div>
                          <span className="eyebrow">
                            {n.code} · {n.stage || "基础学习"}
                          </span>
                          <h3>
                            <Link to={`/study?project=${id}&chapter=${n.id}`}>
                              {n.title}
                            </Link>
                          </h3>
                          <p className="muted">
                            预计 {n.estHours} 小时 · 掌握度{" "}
                            {Math.round(n.mastery * 100)}%
                          </p>
                        </div>
                      </li>
                    ))}
                  </ol>
                )}
                <details className="add-chapter">
                  <summary>
                    <Icon name="plus" size={18} />
                    手动添加章节
                    <svg
                      className="disclosure-chevron"
                      width="16"
                      height="16"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.7"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      aria-hidden="true"
                    >
                      <path d="m6 9 6 6 6-6" />
                    </svg>
                  </summary>
                  <form
                    className="form-grid"
                    onSubmit={(e) => {
                      e.preventDefault();
                      if (!add.isPending) add.mutate();
                    }}
                  >
                    <label>
                      章节编号
                      <Input
                        value={code}
                        onChange={(e) => setCode(e.target.value)}
                        required
                        maxLength={64}
                        placeholder="如 A1"
                      />
                    </label>
                    <label>
                      章节名称
                      <Input
                        value={title}
                        onChange={(e) => setTitle(e.target.value)}
                        required
                        maxLength={200}
                        placeholder="如 变量与数据类型"
                      />
                    </label>
                    <label>
                      预计学时
                      <Input
                        type="number"
                        min={0.5}
                        max={1000}
                        step={0.5}
                        value={hours}
                        onChange={(e) => setHours(Number(e.target.value))}
                        required
                      />
                    </label>
                    <button disabled={add.isPending} className="primary">
                      {add.isPending ? "添加中…" : "添加章节"}
                    </button>
                  </form>
                  <ErrorNotice error={add.error} />
                </details>
              </div>
              <section className="panel section-space">
                <h2>安排学习节奏</h2>
                <p className="muted">根据已有章节和学时排出周计划。</p>
                <form
                  className="form-grid"
                  onSubmit={(e) => {
                    e.preventDefault();
                    if (!plan.isPending) plan.mutate();
                  }}
                >
                  <label>
                    计划周数
                    <Input
                      type="number"
                      min={1}
                      max={52}
                      value={weeks}
                      onChange={(e) => setWeeks(Number(e.target.value))}
                      required
                    />
                  </label>
                  <label>
                    每周学时
                    <Input
                      type="number"
                      min={0.5}
                      max={80}
                      step={0.5}
                      value={weekly}
                      onChange={(e) => setWeekly(Number(e.target.value))}
                      required
                    />
                  </label>
                  <button
                    className="primary"
                    disabled={plan.isPending || !nodes.data.items.length}
                  >
                    {plan.isPending ? "正在排期…" : "生成周计划"}
                  </button>
                </form>
                <ErrorNotice error={plan.error} />
                {plan.data && (
                  <div className="week-grid">
                    {plan.data.weeks.map((w) => (
                      <div className="week-card" key={w.index}>
                        <span className="eyebrow">
                          第 {w.index} 周 · {w.hours} 小时
                        </span>
                        {w.items.length ? (
                          w.items.map((n) => <p key={n.nodeId}>{n.title}</p>)
                        ) : (
                          <p className="muted">留白与巩固</p>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </section>
            </>
          )}
        </>
      )}
    </>
  );
}
