import { expect, it } from "vitest";
import { csvCell } from "../src/components/contentExport";
import { reportRange, validDate } from "../src/components/reportData";
it("neutralizes spreadsheet formulas and preserves CSV quoting and multiline content", () => {
  for (const input of [
    "=1+1",
    "  +SUM(1)",
    "\t@cmd",
    "\rtest",
    "-10",
    "\n=NOW()",
  ])
    expect(csvCell(input)).toMatch(/^"'/);
  expect(csvCell('正常,带"引号\n下一行')).toBe('"正常,带""引号\n下一行"');
});
it("rejects impossible dates and reversed ranges, and keeps the latest report for each day", () => {
  expect(validDate("2024-02-29")).toBe(true);
  expect(validDate("2026-02-29")).toBe(false);
  expect(validDate("2026-04-31")).toBe(false);
  const rows = [
    { id: 1, date: "2026-11-15" },
    { id: 3, date: "2026-11-15" },
    { id: 4, date: "2026-11-17" },
  ] as Parameters<typeof reportRange>[0];
  expect(
    reportRange(rows, "2026-11-15", "2026-11-15")?.map((r) => r.id),
  ).toEqual([3]);
  expect(reportRange(rows, "2026-11-18", "2026-11-17")).toBeUndefined();
});
