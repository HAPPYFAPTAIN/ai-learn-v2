import { useEffect, useState } from "react";
import type { Model } from "../api/client";
import { Input } from "./fields";
import { ErrorNotice } from "./ui";
import { saveBlob } from "./download";
import { fileLabel, reportsCsv } from "./contentExport";
import { dateLabel, reportRange } from "./reportData";
import { metricValue } from "./dashboardData";
export default function ReportWorkspace({
  reports,
  title,
  projectId,
  building,
  error,
  onBuild,
}: {
  reports: Model<"ReportOut">[];
  title: string;
  projectId: number;
  building: boolean;
  error: Error | null;
  onBuild: () => void;
}) {
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [printError, setPrintError] = useState("");
  const visible = reportRange(reports, from, to);
  const totals = (visible || []).reduce(
    (sum, r) => ({
      minutes: sum.minutes + metricValue(r, "studyMinutes"),
      cards: sum.cards + metricValue(r, "cardsReviewed"),
      chapters: sum.chapters + metricValue(r, "nodesProgressed"),
    }),
    { minutes: 0, cards: 0, chapters: 0 },
  );
  useEffect(() => {
    const clear = () => {
      delete document.body.dataset.printLearning;
    };
    window.addEventListener("afterprint", clear);
    return () => {
      clear();
      window.removeEventListener("afterprint", clear);
    };
  }, []);
  function preset(days?: number) {
    if (!days) {
      setFrom("");
      setTo("");
      return;
    }
    const now = new Date();
    setTo(dateLabel(now));
    setFrom(dateLabel(new Date(now.getTime() - (days - 1) * 86_400_000)));
  }
  function download(format: "json" | "csv") {
    if (!visible?.length) return;
    saveBlob(
      new Blob(
        [
          format === "csv"
            ? reportsCsv(visible)
            : JSON.stringify(
                {
                  project: title,
                  from: from || null,
                  to: to || null,
                  reports: visible,
                },
                null,
                2,
              ),
        ],
        {
          type:
            format === "csv" ? "text/csv;charset=utf-8" : "application/json",
        },
      ),
      format === "csv"
        ? `${fileLabel(title)}-学习记录.csv`
        : `learning-report-${projectId}.json`,
    );
  }
  return (
    <section className="panel section-space report-print-host">
      <div className="section-title spread no-print">
        <div>
          <h2>学习记录</h2>
          <p className="muted">为今天的学习，留一份小结。</p>
        </div>
        <div className="button-row">
          <button disabled={!visible?.length} onClick={() => download("json")}>
            导出记录
          </button>
          <button
            className="primary"
            disabled={building || !projectId}
            onClick={onBuild}
          >
            {building ? "整理中…" : "整理今日报告"}
          </button>
        </div>
      </div>
      <ErrorNotice error={error} />
      <div className="feature-toolbar report-filters no-print">
        <label>
          开始日期
          <Input
            aria-label="记录开始日期"
            placeholder="YYYY-MM-DD"
            value={from}
            onChange={(e) => setFrom(e.target.value)}
            maxLength={10}
          />
        </label>
        <label>
          结束日期
          <Input
            aria-label="记录结束日期"
            placeholder="YYYY-MM-DD"
            value={to}
            onChange={(e) => setTo(e.target.value)}
            maxLength={10}
          />
        </label>
        <div className="content-actions">
          <button onClick={() => preset(7)}>近7天记录</button>
          <button onClick={() => preset(30)}>近30天记录</button>
          <button onClick={() => preset()}>全部记录</button>
        </div>
      </div>
      {!visible && (
        <p role="alert" className="notice no-print">
          请输入有效日期（YYYY-MM-DD），开始日期不能晚于结束日期。
        </p>
      )}
      {visible && (
        <>
          <div className="learning-report" aria-label="阶段学习报告">
            <h3>{title} · 阶段学习报告</h3>
            <p className="muted small">
              {from || "最早记录"} 至 {to || "最新记录"} · {visible.length}{" "}
              天有日报记录
            </p>
            <dl className="report-totals">
              <div>
                <dt>学习时长</dt>
                <dd>{totals.minutes} 分钟</dd>
              </div>
              <div>
                <dt>复习卡片</dt>
                <dd>{totals.cards} 张</dd>
              </div>
              <div>
                <dt>推进章节次数</dt>
                <dd>{totals.chapters} 次</dd>
              </div>
            </dl>
            <p className="muted small">
              按北京时间汇总已加载的日报；缺失日期不计为零，推进次数不等于不同章节数。
            </p>
          </div>
          <div className="content-actions no-print">
            <button disabled={!visible.length} onClick={() => download("csv")}>
              导出 CSV
            </button>
            <button
              disabled={!visible.length}
              onClick={() => {
                setPrintError("");
                document.body.dataset.printLearning = "true";
                // Keep Safari's user activation: the print scope is a direct
                // DOM attribute, so no React render or animation frame is needed.
                try {
                  window.print();
                } catch {
                  delete document.body.dataset.printLearning;
                  setPrintError("无法打开打印窗口，可使用浏览器的打印功能。");
                }
              }}
            >
              打印学习报告
            </button>
          </div>
          {printError && (
            <p role="status" className="no-print">
              {printError}
            </p>
          )}
          {visible.length ? (
            visible.map((r) => (
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
            <p className="empty-inline">
              {reports.length
                ? "此日期范围暂无学习记录。"
                : "暂无学习记录，完成学习后会在这里展示。"}
            </p>
          )}
        </>
      )}
    </section>
  );
}
