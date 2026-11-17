import type { KNode, Project } from "../api";

// Titles are text, never extra Markdown headings, links or embedded HTML.
export function outlineLabel(value: string) {
  return value
    .replace(/[\r\n\t]+/g, " ")
    .replace(/[\\`*{}\[\]<>()!#|_]/g, "\\$&");
}

export function roadmapOutline(project: Project | undefined, nodes: KNode[]) {
  return [
    `# ${outlineLabel(project?.title || "学习路线")}`,
    ...nodes.map(
      (node) =>
        `## ${outlineLabel(`${node.code} ${node.title}`)}\n\n- ${outlineLabel(node.stage || "基础学习")}\n- 预计 ${node.estHours} 小时`,
    ),
  ].join("\n\n");
}

export function roadmapMarkdown(project: Project | undefined, nodes: KNode[]) {
  return (
    [
      `# ${outlineLabel(project?.title || "学习路线")}`,
      project?.goal ? `学习目标：${outlineLabel(project.goal)}` : "",
      "此文件为章节目录与当前学习进度快照，不包含教材正文、笔记或完整账号数据。",
      ...nodes.map((node) =>
        [
          `## ${outlineLabel(`${node.code} ${node.title}`)}`,
          `- 阶段：${outlineLabel(node.stage || "基础学习")}`,
          `- 预计学时：${node.estHours} 小时`,
          `- 掌握度：${Math.round(node.mastery * 100)}%`,
          `- 状态：${node.status === "done" ? "已完成" : node.status === "learning" ? "学习中" : "待学习"}`,
        ].join("\n"),
      ),
    ]
      .filter(Boolean)
      .join("\n\n") + "\n"
  );
}

export function downloadRoadmap(project: Project | undefined, nodes: KNode[]) {
  const blob = new Blob([roadmapMarkdown(project, nodes)], {
    type: "text/markdown;charset=utf-8",
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${(project?.title || "学习路线").replace(/[\\/:*?"<>|\u0000-\u001f]/g, "_").slice(0, 100)}-学习路线.md`;
  anchor.style.display = "none";
  document.body.append(anchor);
  try {
    anchor.click();
  } finally {
    anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
}
