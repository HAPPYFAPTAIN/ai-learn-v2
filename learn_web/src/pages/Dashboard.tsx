import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { endpoints } from "../api";
import ReportWorkspace from "../components/ReportWorkspace";
import { key } from "../query";
import { useProject } from "../components/ProjectContext";
import {
  LearningTrend,
  ChapterDistribution,
} from "../components/LearningCharts";
import { Icon, PageHeading, QueryState } from "../components/ui";
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
                <ChapterDistribution summary={summary.data} />
              </section>
            </>
          )}
          {reports.data && (
            <LearningTrend key={id} reports={reports.data.items} />
          )}
          <QueryState query={reports} />
          {reports.data && (
            <ReportWorkspace
              key={id}
              projectId={id}
              title={project?.title || "学习计划"}
              reports={reports.data.items}
              building={build.isPending}
              error={build.error}
              onBuild={() => build.mutate()}
            />
          )}
        </>
      )}
    </>
  );
}
