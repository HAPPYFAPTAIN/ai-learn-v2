import { expect, it } from "vitest";
import { generationEstimate } from "../src/api/generation";
import type { JobProgress } from "../src/api";

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
