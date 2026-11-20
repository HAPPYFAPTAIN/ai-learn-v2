import { useEffect, useState } from "react";
import type { JobProgress } from "../api";
import { generationEstimate } from "../api/generation";

export default function GenerationProgress({
  job,
  reconnecting,
}: {
  job: JobProgress;
  reconnecting: boolean;
}) {
  const [now, setNow] = useState(Date.now);
  const active = job.state === "queued" || job.state === "running";
  useEffect(() => {
    if (!active) return;
    // Local display updates need no extra network requests; unmount stops the timer.
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [active, job.jobId]);
  const value = generationEstimate(job, now);
  if (!active && job.state !== "done") return null;
  return (
    <div className="generation-progress">
      <div className="generation-progress-heading">
        <span>{value.stage}</span>
        <strong aria-hidden="true">
          {value.estimated ? "约 " : ""}
          {value.percent}%
        </strong>
      </div>
      <div
        className="generation-progress-track"
        role="progressbar"
        aria-label={
          {
            lesson: "学习内容生成进度",
            quiz: "测验生成进度",
            cards: "复习卡生成进度",
          }[job.kind] || "学习路线生成进度"
        }
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={value.percent}
        aria-valuetext={`${value.estimated ? "估算进度" : "已完成"} ${value.percent}%`}
      >
        <span style={{ width: `${value.percent}%` }} />
      </div>
      <p className="generation-progress-remaining">
        {reconnecting ? (
          "连接恢复中，剩余时间暂不可用。任务仍可能继续运行。"
        ) : (
          <>预计剩余：{value.remaining}</>
        )}
      </p>
      {active && (
        <p className="muted small">
          {job.progress.estimateSource === "history"
            ? "根据近期同模型生成耗时估算"
            : "首次使用，按参考耗时估算"}
          ；百分比为估算值，保存成功后显示 100%。
        </p>
      )}
    </div>
  );
}
