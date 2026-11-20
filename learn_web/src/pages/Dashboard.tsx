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
  const data = id
    ? summary.data
    : {
        totalNodes: 0,
        nodesByStatus: {},
        completedNodes: 0,
        completionRatio: 0,
        masteredNodes: 0,
        masteryRatio: 0,
        studyMinutes: 0,
      };
  const reportItems = id ? reports.data?.items : [];
  return (
    <>
      <PageHeading
        title="学习看板"
        description="看见每一点积累，找到属于你的学习节奏。"
      />
      {!id && (
        <p className="muted" role="status">
          暂无学习记录
        </p>
      )}
      {!!id && <QueryState query={summary} />}
      {data && (
        <>
          <div className="stat-grid">
            {[
              [
                "累计学习",
                `${Math.round(data.studyMinutes)}`,
                "分钟",
                "review",
              ],
              [
                "已完成章节",
                `${data.completedNodes}`,
                `/ ${data.totalNodes} 章`,
                "book",
              ],
              [
                "章节完成率",
                `${Math.round(data.completionRatio * 100)}`,
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
              完成 {data.completedNodes} 个章节，还剩{" "}
              {Math.max(0, data.totalNodes - data.completedNodes)} 个。
            </p>
            <progress
              className="mastery-progress"
              aria-label="章节完成率"
              max={1}
              value={data.completionRatio}
            />
            <ChapterDistribution summary={data} />
          </section>
        </>
      )}
      {reportItems && (
        <LearningTrend key={`trend-${id}`} reports={reportItems} />
      )}
      {!!id && <QueryState query={reports} />}
      {reportItems && (
        <ReportWorkspace
          key={`reports-${id}`}
          projectId={id}
          title={project?.title || "我的学习"}
          reports={reportItems}
          building={build.isPending}
          error={build.error}
          onBuild={() => {
            if (id) build.mutate();
          }}
        />
      )}
    </>
  );
}
