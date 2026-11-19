import { expect, it } from "vitest";
import { mapLabel, mindmapTree } from "../src/components/mindmapTree";

it("keeps only text labels, discarding model HTML, links, assets, notes and options", () => {
  const tree = mindmapTree(
    [
      "---",
      "markmap:",
      "  color: red",
      "---",
      "# 主題",
      "## [链接](javascript:alert(1))",
      "## ![图片文字](https://example.org/a.png)",
      "## <img src=x onerror=alert(1)>安全文字",
      "一段不进入导图的正文。",
    ].join("\n"),
  );
  expect(mapLabel(tree)).toBe("主題");
  expect(tree.children.map(mapLabel)).toEqual(["链接", "图片文字", "安全文字"]);
  function inspect(node: typeof tree) {
    expect(node.data).toEqual({});
    expect(node.notes).toEqual([]);
    expect(node.content).toEqual([{ type: "text", value: mapLabel(node) }]);
    node.children.forEach(inspect);
  }
  inspect(tree);
  expect(JSON.stringify(tree)).not.toMatch(/javascript:|https:|onerror|color/);
});

it("rejects oversized and deeply nested maps before SVG layout", () => {
  expect(() => mindmapTree("x".repeat(50_001))).toThrow("内容过长");
  expect(() => mindmapTree(" ")).toThrow("暂无");
  expect(() =>
    mindmapTree(
      "# 根\n" + Array.from({ length: 251 }, (_, i) => `## ${i}`).join("\n"),
    ),
  ).toThrow("结构过大");
  expect(() =>
    mindmapTree(
      "# 根\n" +
        Array.from({ length: 15 }, (_, i) => `${"  ".repeat(i)}- 层级`).join(
          "\n",
        ),
    ),
  ).toThrow("结构过大");
});
