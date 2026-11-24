import { Input } from "../components/fields";
import { lazy, Suspense, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { endpoints } from "../api";
import { key } from "../query";
import { useProject } from "../components/ProjectContext";
import GenerationAction from "../components/GenerationAction";
import DeleteLearningButton from "../components/DeleteLearningButton";
import { roadmapOutline, downloadRoadmap } from "../components/roadmapContent";
import { Empty, ErrorNotice, Icon, QueryState } from "../components/ui";
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
  const items = nodes.data?.items || [];
  const totalHours = items.reduce((sum, node) => sum + node.estHours, 0);
  const averageMastery = items.length
    ? Math.round(
        (items.reduce((sum, node) => sum + node.mastery, 0) / items.length) *
          100,
      )
    : 0;
  return (
    <>
      <header className="roadmap-hero">
        <p className="eyebrow">
          LEARNING PATH
          {project?.title ? ` / ${project.title}` : ""}
        </p>
        <div className="roadmap-hero-row">
          <div>
            <h1>学习路线</h1>
            <p>从目标到章节，再到每周可以完成的一小步。</p>
          </div>
          {nodes.data && (
            <dl className="roadmap-metrics" aria-label="学习路线概览">
              <div>
                <dt>章节</dt>
                <dd>{items.length}</dd>
              </div>
              <div>
                <dt>预计学时</dt>
                <dd>{Math.round(totalHours * 10) / 10}</dd>
              </div>
              <div>
                <dt>平均掌握</dt>
                <dd>{averageMastery}%</dd>
              </div>
            </dl>
          )}
        </div>
      </header>
      {!id ? (
        <Empty title="暂无学习路线" />
      ) : (
        <>
          <QueryState query={nodes} />
          {nodes.data && (
            <>
              <section
                className="roadmap-section roadmap-chapters"
                aria-labelledby="roadmap-chapters-title"
              >
                <div className="roadmap-section-head">
                  <div>
                    <p className="eyebrow">CHAPTERS</p>
                    <h2 id="roadmap-chapters-title">章节目录</h2>
                  </div>
                  <div className="roadmap-actions">
                    <span>{items.length} 个章节</span>
                    {project && !!items.length && (
                      <DeleteLearningButton
                        project={project}
                        scope="roadmap"
                        onDeleted={() => {
                          plan.reset();
                          setMapProject(undefined);
                          setExportError(undefined);
                        }}
                      />
                    )}
                    <button
                      type="button"
                      disabled={!items.length}
                      aria-expanded={mapProject === id}
                      onClick={() =>
                        setMapProject(mapProject === id ? undefined : id)
                      }
                    >
                      {mapProject === id ? "收起思维导图" : "思维导图"}
                    </button>
                    <button
                      type="button"
                      disabled={!items.length}
                      onClick={() => {
                        try {
                          downloadRoadmap(project, items);
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
                {mapProject === id && !!items.length && (
                  <div className="roadmap-reveal">
                    <Suspense fallback={<p role="status">正在加载思维导图…</p>}>
                      <MindMap
                        key={id}
                        source={roadmapOutline(project, items)}
                      />
                    </Suspense>
                  </div>
                )}
                <GenerationAction
                  key={`${id}:${!!items.length}`}
                  projectId={id}
                  hideCompleted
                  ready={!!items.length}
                />
                {!items.length ? (
                  <div className="roadmap-empty">
                    <p>还没有章节。</p>
                    <span>用 AI 生成一条路线，或手动添加第一课。</span>
                  </div>
                ) : (
                  <ol className="roadmap-list">
                    {items.map((n, index) => (
                      <li key={n.id}>
                        <span className="roadmap-index" aria-hidden="true">
                          {String(index + 1).padStart(2, "0")}
                        </span>
                        <span
                          className={`roadmap-dot ${n.status === "done" ? "done" : ""}`}
                          aria-label={
                            n.status === "done" ? "已完成" : "尚未完成"
                          }
                        >
                          <Icon
                            name={n.status === "done" ? "check" : "book"}
                            size={14}
                          />
                        </span>
                        <div className="roadmap-item-body">
                          <span className="eyebrow">
                            {n.code} · {n.stage || "基础学习"}
                          </span>
                          <h3>
                            <Link to={`/study?project=${id}&chapter=${n.id}`}>
                              {n.title}
                            </Link>
                          </h3>
                          <div className="roadmap-item-progress">
                            <span
                              style={{
                                width: `${Math.min(100, Math.max(0, n.mastery * 100))}%`,
                              }}
                            />
                          </div>
                        </div>
                        <div className="roadmap-item-meta">
                          <strong>{n.estHours}</strong>
                          <span>小时</span>
                          <small>{Math.round(n.mastery * 100)}%</small>
                        </div>
                        <Link
                          className="roadmap-enter"
                          to={`/study?project=${id}&chapter=${n.id}`}
                          aria-label={`进入章节：${n.title}`}
                        >
                          <Icon name="arrow" size={18} />
                        </Link>
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
              </section>

              <section
                className="roadmap-section roadmap-schedule"
                aria-labelledby="roadmap-schedule-title"
              >
                <div className="roadmap-section-head roadmap-schedule-head">
                  <div>
                    <p className="eyebrow">CADENCE</p>
                    <h2 id="roadmap-schedule-title">安排学习节奏</h2>
                    <p>把章节放进几周里，给每周一个清楚的范围。</p>
                  </div>
                  <form
                    className="roadmap-schedule-form"
                    onSubmit={(e) => {
                      e.preventDefault();
                      if (!plan.isPending) plan.mutate();
                    }}
                  >
                    <label>
                      周数
                      <Input
                        type="number"
                        min={1}
                        max={52}
                        value={weeks}
                        onChange={(e) => setWeeks(Number(e.target.value))}
                        aria-label="计划周数"
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
                        aria-label="每周学时"
                        required
                      />
                    </label>
                    <button
                      className="primary"
                      disabled={plan.isPending || !items.length}
                    >
                      {plan.isPending ? "正在排期…" : "生成周计划"}
                    </button>
                  </form>
                </div>
                <ErrorNotice error={plan.error} />
                {plan.data && (
                  <div className="week-grid">
                    {plan.data.weeks.map((w) => (
                      <article className="week-card" key={w.index}>
                        <header>
                          <span>WEEK</span>
                          <strong>{String(w.index).padStart(2, "0")}</strong>
                          <small>{w.hours} 小时</small>
                        </header>
                        <div>
                          {w.items.length ? (
                            w.items.map((n) => <p key={n.nodeId}>{n.title}</p>)
                          ) : (
                            <p className="week-rest">留白与巩固</p>
                          )}
                        </div>
                      </article>
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
