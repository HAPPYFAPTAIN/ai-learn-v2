import { useEffect, useId, useRef, useState } from "react";
import type { Model } from "../api/client";
import { dailyReports, metricValue } from "./dashboardData";

const metrics = {
  studyMinutes: { label: "学习时长", unit: "分钟" },
  cardsReviewed: { label: "复习卡片", unit: "张" },
  nodesProgressed: { label: "推进章节", unit: "章" },
};
type Metric = keyof typeof metrics;
const statusLabels: Record<string, string> = {
  new: "未开始",
  pending: "未开始",
  learning: "学习中",
  reviewing: "复习中",
  weak: "需巩固",
  done: "已完成",
  mastered: "已掌握",
  skipped: "已跳过",
  other: "其他章节",
};

export function LearningTrend({ reports }: { reports: Model<"ReportOut">[] }) {
  const [days, setDays] = useState(7);
  const [metric, setMetric] = useState<Metric>("studyMinutes");
  const [selected, setSelected] = useState<string>();
  const figure = useRef<HTMLElement>(null);
  const [chartWidth, setChartWidth] = useState(640);
  const titleId = useId();
  const series = dailyReports(reports, days);
  const known = series.filter((point) => point.report);
  useEffect(() => {
    const element = figure.current;
    if (!element) return;
    const resize = () =>
      setChartWidth(Math.max(260, Math.round(element.clientWidth)));
    const observer = new ResizeObserver(resize);
    observer.observe(element);
    resize();
    return () => observer.disconnect();
  }, [!!known.length]);
  const total = known.reduce(
    (sum, point) => sum + metricValue(point.report!, metric),
    0,
  );
  const max = Math.max(
    1,
    ...known.map((point) => metricValue(point.report!, metric)),
  );
  const ceiling = Math.max(1, Math.ceil(max / 4) * 4);
  const current = series.find((point) => point.date === selected);
  const unit = metrics[metric].unit;
  const step = (chartWidth - 80) / days;
  return (
    <section
      className="panel section-space learning-trend"
      aria-labelledby={titleId}
    >
      <div className="section-title spread">
        <div>
          <h2 id={titleId}>学习趋势</h2>
          <p className="muted">回看每天的积累，找到适合自己的节奏。</p>
        </div>
        <div className="chart-switch" role="group" aria-label="趋势时间范围">
          {[7, 30].map((value) => (
            <button
              key={value}
              type="button"
              aria-pressed={days === value}
              onClick={() => {
                setDays(value);
                setSelected(undefined);
              }}
            >
              近 {value} 天
            </button>
          ))}
        </div>
      </div>
      <div className="chart-metrics" role="group" aria-label="趋势指标">
        {(Object.keys(metrics) as Metric[]).map((field) => (
          <button
            key={field}
            type="button"
            aria-pressed={metric === field}
            onClick={() => {
              setMetric(field);
              setSelected(undefined);
            }}
          >
            {metrics[field].label}
          </button>
        ))}
      </div>
      <div className="chart-summary">
        <strong>
          {total.toLocaleString("zh-CN")}
          <small>{unit}</small>
        </strong>
        <span className="muted small">
          近 {days} 天已有日报记录的合计 · {known.length} 天有记录
        </span>
      </div>
      {!known.length ? (
        <p className="empty-inline">
          此时间范围暂无学习记录，整理今日报告后即可查看趋势。
        </p>
      ) : (
        <figure className="trend-figure" ref={figure}>
          <svg
            viewBox={`0 0 ${chartWidth} 230`}
            role="group"
            aria-label={`近 ${days} 天${metrics[metric].label}图表`}
          >
            {[0, 1, 2, 3, 4].map((tick) => {
              const y = 180 - tick * 40;
              return (
                <g key={tick}>
                  <line
                    x1="50"
                    y1={y}
                    x2={chartWidth - 30}
                    y2={y}
                    className="chart-gridline"
                  />
                  <text
                    x="40"
                    y={y + 4}
                    textAnchor="end"
                    className="chart-axis"
                  >
                    {(ceiling * tick) / 4}
                  </text>
                </g>
              );
            })}
            {series.map((point, i) => {
              const value = point.report
                ? metricValue(point.report, metric)
                : undefined;
              const height = value == null ? 0 : (value / ceiling) * 160;
              const x = 50 + i * step + step * 0.17;
              const label = `${point.date}，${value == null ? "暂无日报记录" : `${value} ${unit}`}`;
              return (
                <g
                  key={point.date}
                  role="button"
                  tabIndex={0}
                  aria-label={label}
                  aria-pressed={selected === point.date}
                  onClick={() => setSelected(point.date)}
                  onFocus={() => setSelected(point.date)}
                  onMouseEnter={() => setSelected(point.date)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      setSelected(point.date);
                    }
                  }}
                >
                  <title>{label}</title>
                  <rect
                    x={50 + i * step}
                    y="16"
                    width={step}
                    height="166"
                    fill="transparent"
                  />
                  <rect
                    className={value == null ? "chart-missing" : "chart-bar"}
                    x={x}
                    y={value == null ? 177 : 180 - Math.max(2, height)}
                    width={step * 0.66}
                    height={value == null ? 3 : Math.max(2, height)}
                    rx="3"
                  />
                  {(i % Math.ceil(days / 5) === 0 || i === days - 1) && (
                    <text
                      x={50 + i * step + step / 2}
                      y="204"
                      textAnchor="middle"
                      className="chart-axis"
                    >
                      {point.date.slice(5).replace("-", "/")}
                    </text>
                  )}
                </g>
              );
            })}
          </svg>
          <figcaption className="chart-detail" role="status">
            {current
              ? `${current.date}：${current.report ? `${metrics[metric].label} ${metricValue(current.report, metric)} ${unit}` : "暂无日报记录"}`
              : "点击或用 Tab 选择某一天，查看当天数据。"}
          </figcaption>
        </figure>
      )}
      <p className="muted small">
        图表来自已保存的日报；灰色短线表示尚无记录，不等于当天学习量为零。
      </p>
      {!!known.length && (
        <details className="chart-data">
          <summary>查看每日数据</summary>
          <div className="chart-table-scroll">
            <table>
              <thead>
                <tr>
                  <th>日期</th>
                  <th>学习分钟</th>
                  <th>复习卡片</th>
                  <th>推进章节</th>
                </tr>
              </thead>
              <tbody>
                {series.map((point) => (
                  <tr key={point.date}>
                    <th scope="row">{point.date}</th>
                    {(Object.keys(metrics) as Metric[]).map((field) => (
                      <td key={field}>
                        {point.report
                          ? metricValue(point.report, field)
                          : "无记录"}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
    </section>
  );
}

export function ChapterDistribution({
  summary,
}: {
  summary: Model<"SummaryOut">;
}) {
  const rows = Object.entries(summary.nodesByStatus).filter(
    ([, count]) => count > 0,
  );
  const counted = rows.reduce((sum, [, count]) => sum + count, 0);
  if (counted < summary.totalNodes)
    rows.push(["other", summary.totalNodes - counted]);
  const total = rows.reduce((sum, [, count]) => sum + count, 0);
  return (
    <div className="chapter-distribution">
      {!total ? (
        <p className="muted">暂无章节数据，生成学习路线后即可查看分布。</p>
      ) : (
        <>
          <div
            className="chapter-distribution-track"
            role="img"
            aria-label={`章节状态分布：${rows.map(([status, count]) => `${statusLabels[status] || status} ${count} 章`).join("，")}`}
          >
            {rows.map(([status, count], i) => (
              <span
                key={status}
                data-tone={i % 4}
                style={{ width: `${(count / total) * 100}%` }}
              />
            ))}
          </div>
          <ul className="chapter-distribution-legend">
            {rows.map(([status, count], i) => (
              <li key={status}>
                <span className="chart-dot" data-tone={i % 4} />
                <span>{statusLabels[status] || status}</span>
                <strong>{count} 章</strong>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
