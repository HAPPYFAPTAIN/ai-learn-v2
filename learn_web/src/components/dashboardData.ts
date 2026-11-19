import type { Model } from "../api/client";
import { dateLabel } from "./reportData";
export type DailyPoint = { date: string; report?: Model<"ReportOut"> };
export function dailyReports(
  reports: Model<"ReportOut">[],
  days: number,
  now = new Date(),
): DailyPoint[] {
  // Date-only report keys are calendar dates, not timestamps in the browser timezone.
  const end = Date.parse(`${dateLabel(now)}T00:00:00Z`);
  const byDate = new Map<string, Model<"ReportOut">>();
  for (const report of reports) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(report.date)) continue;
    const previous = byDate.get(report.date);
    if (!previous || previous.id < report.id) byDate.set(report.date, report);
  }
  return Array.from({ length: days }, (_, i) => {
    const date = new Date(end - (days - 1 - i) * 86_400_000)
      .toISOString()
      .slice(0, 10);
    return { date, report: byDate.get(date) };
  });
}
export function metricValue(
  report: Model<"ReportOut">,
  field: "studyMinutes" | "cardsReviewed" | "nodesProgressed",
) {
  const value = report[field];
  return Number.isFinite(value) ? Math.max(0, value) : 0;
}
