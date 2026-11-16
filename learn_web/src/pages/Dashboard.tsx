import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { endpoints } from "../api";
import { key } from "../query";
import { useProject } from "../components/ProjectContext";
import {
  Empty,
  ErrorNotice,
  Icon,
  PageHeading,
  QueryState,
} from "../components/ui";
export default function Dashboard() {
  const { id, project } = useProject();
  const client = useQueryClient();
  const summary = useQuery({
    queryKey: key("summary", id),
    queryFn: ({ signal }) => endpoints.summary(id, signal),
    enabled: !!id,
  });
  const reports = useQuery({
    queryKey: key("reports", id),
    queryFn: ({ signal }) => endpoints.reports(id, signal),
    enabled: !!id,
  });
  const build = useMutation({
    mutationFn: () => endpoints.buildReport(id),
    onSuccess: () =>
      void client.invalidateQueries({ queryKey: key("reports", id) }),
  });
  function download() {
    if (!reports.data?.items.length) return;
    const blob = new Blob(
      [
        JSON.stringify(
          { project: project?.title, reports: reports.data.items },
          null,
          2,
        ),
      ],
      { type: "application/json" },
    );
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `learning-report-${id}.json`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return (
    <>
      <PageHeading
        title="学习看板"
        description="看见每一点积累，找到属于你的学习节奏。"
      />
      {!id ? (
        <div className="panel dashboard-empty">
          <div className="search-field" role="note">
            <Icon name="chart" />
            <span>暂无学习记录，快去新建学习计划吧</span>
          </div>
        </div>
      ) : (
        <>
          <QueryState query={summary} />
          {summary.data && (
            <>
              <div className="stat-grid">
                {[
                  [
                    "累计学习",
                    `${Math.round(summary.data.studyMinutes)}`,
                    "分钟",
                    "review",
                  ],
                  [
                    "已完成章节",
                    `${summary.data.masteredNodes}`,
                    `/ ${summary.data.totalNodes} 章`,
                    "book",
                  ],
                  [
                    "章节完成率",
                    `${Math.round(summary.data.masteryRatio * 100)}`,
                    "%",
                    "chart",
                  ],
                ].map(([label, number, unit, icon]) => (
                  <div className="panel stat-card" key={label}>
                    <div className="stat-top">
                      <span>{label}</span>
                      <Icon name={icon} />
                    </div>
                    <strong>
                      {number}
                      <small>{unit}</small>
                    </strong>
                  </div>
                ))}
              </div>
              <section className="panel section-space">
                <h2>章节完成进度</h2>
                <p className="muted">
                  完成 {summary.data.masteredNodes} 个章节，还剩{" "}
                  {Math.max(
                    0,
                    summary.data.totalNodes - summary.data.masteredNodes,
                  )}{" "}
                  个。
                </p>
                <progress
                  className="mastery-progress"
                  aria-label="章节完成率"
                  max={1}
                  value={summary.data.masteryRatio}
                />
              </section>
            </>
          )}
          <section className="panel section-space">
            <div className="section-title spread">
              <div>
                <h2>学习记录</h2>
                <p className="muted">为今天的学习，留一份小结。</p>
              </div>
              <div className="button-row">
                <button
                  disabled={!reports.data?.items.length}
                  onClick={download}
                >
                  导出记录
                </button>
                <button
                  className="primary"
                  disabled={build.isPending}
                  onClick={() => build.mutate()}
                >
                  {build.isPending ? "整理中…" : "整理今日报告"}
                </button>
              </div>
            </div>
            <ErrorNotice error={build.error} />
            <QueryState query={reports} />
            {reports.data &&
              (reports.data.items.length ? (
                reports.data.items.map((r) => (
                  <div className="report-row" key={r.id}>
                    <div>
                      <strong>{r.date}</strong>
                      <small>
                        {r.studyMinutes} 分钟 · {r.cardsReviewed} 张复习卡
                      </small>
                    </div>
                    <p>{r.content}</p>
                  </div>
                ))
              ) : (
                <p className="empty-inline">暂无学习记录，快去新建学习计划吧</p>
              ))}
          </section>
        </>
      )}
    </>
  );
}
