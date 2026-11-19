import { parse } from "@markmap/parse";
import type { PhrasingContent } from "mdast";

type MapNode = ReturnType<typeof parse>["root"];

function labelText(items: PhrasingContent[]): string {
  return items
    .map((item): string => {
      if (item.type === "html") return "";
      if ("children" in item) return labelText(item.children);
      if (item.type === "image" || item.type === "imageReference")
        return item.alt || "";
      return "value" in item ? String(item.value) : "";
    })
    .join("");
}

// Model output never controls renderer options, links, assets or note popovers.
// Bounds apply before parsing and before any SVG layout work.
export function mindmapTree(source: string): MapNode {
  if (source.length > 50_000)
    throw new Error("内容过长，请缩短到 5 万字以内再查看导图。");
  if (!source.trim()) throw new Error("暂无可显示的思维导图内容。");
  const { root } = parse(source);
  let count = 0;
  function normalize(node: MapNode, depth: number): MapNode {
    if (++count > 250 || depth > 12)
      throw new Error(
        "结构过大，请拆分为更小的思维导图（最多 250 个节点、12 层）。",
      );
    const label = labelText(node.content).trim().slice(0, 240) || "未命名节点";
    return {
      id: `node-${count}`,
      type: node.type,
      content: [{ type: "text", value: label }],
      notes: [],
      data: {},
      children: node.children.map((child) => normalize(child, depth + 1)),
    };
  }
  return normalize(root, 0);
}

export function mapLabel(node: MapNode) {
  return labelText(node.content);
}
