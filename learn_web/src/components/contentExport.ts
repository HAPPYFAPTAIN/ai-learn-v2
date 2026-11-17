import type { KNode } from "../api";
import type { Model } from "../api/client";
import { outlineLabel } from "./roadmapContent";
import { saveBlob } from "./download";

export const fileLabel = (name: string) =>
  name.replace(/[\\/:*?"<>|\u0000-\u001f]/g, "_").slice(0, 90) || "学习内容";
export function saveMarkdown(content: string, name: string) {
  saveBlob(
    new Blob([content], { type: "text/markdown;charset=utf-8" }),
    `${fileLabel(name)}.md`,
  );
}
export function lessonMarkdown(node: KNode) {
  return `# ${outlineLabel(`${node.code} ${node.title}`)}\n\n${node.description || "本章节暂无内容。"}\n`;
}
export function notesMarkdown(
  notes: Model<"NoteOut">[],
  nodes: KNode[],
  title: string,
) {
  return (
    [
      `# ${outlineLabel(title)} · 笔记与批注`,
      ...notes.map((note) => {
        const node = nodes.find((item) => item.id === note.nodeId);
        return [
          `## ${outlineLabel(node ? `${node.code} ${node.title}` : "原章节已不可用")}`,
          `更新时间：${outlineLabel(note.updatedAt)}`,
          note.selection
            ? note.selection
                .split(/\r?\n/)
                .map((line) => `> ${line}`)
                .join("\n")
            : "",
          note.content,
        ]
          .filter(Boolean)
          .join("\n\n");
      }),
    ].join("\n\n") + "\n"
  );
}
// Quote all fields and neutralize spreadsheet formulas, including whitespace-prefixed formulas.
export function csvCell(value: unknown) {
  let text = String(value ?? "");
  if (/^[\s\uFEFF]*[=+@-]/.test(text) || /^[\t\r\n]/.test(text))
    text = `'${text}`;
  return `"${text.replace(/"/g, '""')}"`;
}
export function reportsCsv(reports: Model<"ReportOut">[]) {
  return (
    "\uFEFF" +
    [
      ["日期", "学习分钟", "复习卡片", "推进章节", "学习记录"],
      ...reports.map((r) => [
        r.date,
        r.studyMinutes,
        r.cardsReviewed,
        r.nodesProgressed,
        r.content,
      ]),
    ]
      .map((row) => row.map(csvCell).join(","))
      .join("\r\n") +
    "\r\n"
  );
}
