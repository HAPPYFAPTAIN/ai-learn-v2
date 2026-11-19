import type { JobProgress } from "../api";
import { session } from "../session/store";

export function generationStorageKey(
  projectId: number,
  subject: string | number = "roadmap",
) {
  return `learn.v2.generation.${session.get().owner}.${projectId}.${subject}`;
}

export function generationEstimate(job: JobProgress, now = Date.now()) {
  const timestamp = (value: unknown) =>
    typeof value === "string" ? Date.parse(value) : NaN;
  const start = timestamp(
    job.progress.attemptStartedAt || job.progress.startedAt,
  );
  const elapsed = Number.isFinite(start) ? Math.max(0, now - start) : 0;
  const raw = Number(job.progress.estimatedModelMs);
  const estimate = Number.isFinite(raw) && raw > 0 ? raw : 45_000;
  if (job.state === "done")
    return {
      percent: 100,
      remaining: "已完成",
      stage: "学习内容已保存",
      estimated: false,
    };
  if (job.state === "failed" || job.state === "cancelled")
    return {
      percent: 0,
      remaining: "已停止",
      stage: "任务未完成，可重试",
      estimated: false,
    };
  if (job.state === "queued")
    return {
      percent: 3,
      remaining: "等待开始后估算",
      stage:
        Number(job.progress.attempt) >= 0 && job.error
          ? "等待重试"
          : "排队等待模型",
      estimated: true,
    };
  if (job.progress.phase === "saving")
    return {
      percent: 96,
      remaining: "即将完成",
      stage: "校验并保存学习内容",
      estimated: true,
    };
  const percent = Math.min(
    90,
    Math.round(8 + 82 * Math.min(elapsed / estimate, 1)),
  );
  const remaining =
    elapsed >= estimate
      ? "超出预估，仍在生成…"
      : `约 ${Math.max(1, Math.ceil((estimate - elapsed) / 1000))} 秒`;
  return {
    percent,
    remaining,
    stage: "正在规划章节与学习顺序",
    estimated: true,
  };
}
