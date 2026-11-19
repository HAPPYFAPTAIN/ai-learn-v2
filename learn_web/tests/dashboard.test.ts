import { expect, it } from "vitest";
import { dailyReports, metricValue } from "../src/components/dashboardData";
import { dateLabel } from "../src/components/reportData";
const report = {
  id: 1,
  date: "2026-11-17",
  content: "",
  studyMinutes: 0,
  cardsReviewed: 2,
  nodesProgressed: 1,
};
const now = new Date("2026-11-17T02:00:00Z");
it("preserves the distinction between a zero-value report and a missing day", () => {
  const result = dailyReports([report], 7, now);
  expect(result).toHaveLength(7);
  expect(result[0]).toEqual({ date: "2026-11-11", report: undefined });
  expect(result[6].report?.studyMinutes).toBe(0);
});
it("uses only one report per date, takes the latest id and ignores out-of-range dates", () => {
  const result = dailyReports(
    [
      report,
      { ...report, id: 2, studyMinutes: 20 },
      { ...report, id: 3, date: "2026-10-01" },
    ],
    7,
    now,
  );
  expect(result.filter((point) => point.report)).toHaveLength(1);
  expect(result[6].report?.studyMinutes).toBe(20);
});
it("handles month boundaries as calendar days", () => {
  expect(
    dailyReports([], 2, new Date("2026-02-28T16:00:00Z")).map(
      (point) => point.date,
    ),
  ).toEqual(["2026-02-28", "2026-03-01"]);
});
it("uses Beijing midnight regardless of the browser's local timezone", () => {
  expect(dateLabel(new Date("2026-11-17T15:59:59Z"))).toBe("2026-11-17");
  const midnight = new Date("2026-11-17T16:00:00Z");
  expect(dateLabel(midnight)).toBe("2026-11-18");
  expect(dailyReports([], 2, midnight).map((point) => point.date)).toEqual([
    "2026-11-17",
    "2026-11-18",
  ]);
});
it("does not plot invalid or negative metric values", () => {
  expect(metricValue({ ...report, studyMinutes: -5 }, "studyMinutes")).toBe(0);
  expect(metricValue({ ...report, studyMinutes: NaN }, "studyMinutes")).toBe(0);
});
