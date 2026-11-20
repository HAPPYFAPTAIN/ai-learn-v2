import { expect, it } from "vitest";
import { generationEstimate } from "../src/api/generation";
import type { JobProgress } from "../src/api";
import { jobFailure } from "../src/api/jobError";

const start = Date.parse("2026-11-15T00:00:00Z");
const job: JobProgress = {
  jobId: "r",
  kind: "roadmap",
  subject: "project:1",
  state: "running",
  error: null,
  updatedAt: new Date(start).toISOString(),
  progress: {
    attemptStartedAt: new Date(start).toISOString(),
    estimatedModelMs: 20_000,
  },
};
it("explains failed job codes even when an older worker omits the message", () => {
  for (const [code, message] of [
    ["INSUFFICIENT_CREDITS", "官网积分不足"],
    ["RESULT_UNCONFIRMED", "已停止自动重试"],
    ["OUTPUT_TRUNCATED", "缩小章节范围"],
    ["GATEWAY_REJECTED", "模型网关拒绝"],
  ]) {
    expect(
      jobFailure({ ...job, state: "failed", progress: { errorCode: code } })
        ?.message,
    ).toContain(message);
  }
  expect(
    jobFailure({ ...job, state: "failed", error: "具体校验失败" })?.message,
  ).toBe("具体校验失败");
  expect(jobFailure(job)).toBeNull();
});
it("estimates the same percentage after a refresh and caps late models below completion", () => {
  const halfway = generationEstimate(job, start + 10_000);
  expect(halfway.percent).toBe(49);
  expect(halfway.remaining).toBe("约 10 秒");
  expect(generationEstimate(structuredClone(job), start + 10_000)).toEqual(
    halfway,
  );
  const late = generationEstimate(job, start + 200_000);
  expect(late.percent).toBe(90);
  expect(late.remaining).toContain("超出预估");
});
it("reserves 100 percent for a committed success, never failures or queue waits", () => {
  expect(
    generationEstimate({ ...job, state: "queued" }, start + 200_000).remaining,
  ).toContain("等待");
  expect(
    generationEstimate(
      { ...job, progress: { ...job.progress, phase: "saving" } },
      start,
    ).percent,
  ).toBe(96);
  expect(generationEstimate({ ...job, state: "done" }, start).percent).toBe(
    100,
  );
  for (const state of ["failed", "cancelled"])
    expect(
      generationEstimate({ ...job, state }, start + 200_000).percent,
    ).toBeLessThan(100);
});
it("uses a finite fallback estimate and resets to the new attempt timestamp on retry", () => {
  const retry = {
    ...job,
    progress: {
      ...job.progress,
      startedAt: new Date(start - 60_000).toISOString(),
      estimatedModelMs: "invalid",
    },
  };
  expect(generationEstimate(retry, start).remaining).toBe("约 45 秒");
  expect(generationEstimate(retry, start).percent).toBe(8);
});
it("describes the generated content for lessons, quizzes and review cards", () => {
  expect(generationEstimate({ ...job, kind: "lesson" }, start).stage).toContain(
    "本节教材",
  );
  expect(generationEstimate({ ...job, kind: "quiz" }, start).stage).toContain(
    "测验题",
  );
  expect(generationEstimate({ ...job, kind: "cards" }, start).stage).toContain(
    "复习卡片",
  );
});
