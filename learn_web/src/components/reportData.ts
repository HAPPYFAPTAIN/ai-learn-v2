import type { Model } from "../api/client";
export function validDate(value: string) {
  return (
    /^\d{4}-\d{2}-\d{2}$/.test(value) &&
    Number.isFinite(Date.parse(`${value}T00:00:00Z`)) &&
    new Date(`${value}T00:00:00Z`).toISOString().slice(0, 10) === value
  );
}
export function dateLabel(date = new Date()) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}
export function reportRange(
  reports: Model<"ReportOut">[],
  from: string,
  to: string,
) {
  if (
    (from && !validDate(from)) ||
    (to && !validDate(to)) ||
    (from && to && from > to)
  )
    return undefined;
  const unique = new Map<string, Model<"ReportOut">>();
  for (const r of reports) {
    if (!validDate(r.date) || (from && r.date < from) || (to && r.date > to))
      continue;
    if (!unique.has(r.date) || unique.get(r.date)!.id < r.id)
      unique.set(r.date, r);
  }
  return [...unique.values()].sort((a, b) => b.date.localeCompare(a.date));
}
