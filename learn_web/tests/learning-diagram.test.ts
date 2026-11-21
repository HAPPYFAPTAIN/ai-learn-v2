import { expect, it } from "vitest";
import { learningDiagram } from "../src/components/diagramLayout";

const example = {
  title: "从计数到进位",
  nodes: [
    { id: "zero", label: "0 表示没有" },
    { id: "ones", label: "逐个计数" },
    { id: "tens", label: "十个一合成一个十" },
  ],
  edges: [
    ["zero", "ones"],
    ["ones", "tens"],
  ],
};
it("lays out knowledge points along directed relationships", () => {
  const diagram = learningDiagram(JSON.stringify(example));
  expect(diagram.nodes.map((n) => n.level)).toEqual([0, 1, 2]);
  expect(
    diagram.nodes.every(
      (n) => n.x > 0 && n.x < diagram.width && n.y < diagram.height,
    ),
  ).toBe(true);
  expect(diagram.title).toBe(example.title);
});
it("rejects cycles, unknown endpoints, duplicate IDs and unbounded input", () => {
  const parse = (extra: object) =>
    learningDiagram(JSON.stringify({ ...example, ...extra }));
  expect(() =>
    parse({
      edges: [
        ["zero", "ones"],
        ["ones", "zero"],
      ],
    }),
  ).toThrow("循环");
  expect(() => parse({ edges: [["zero", "missing"]] })).toThrow("不存在");
  expect(() => parse({ nodes: [example.nodes[0], example.nodes[0]] })).toThrow(
    "格式",
  );
  expect(() => learningDiagram("x".repeat(20_001))).toThrow("过长");
  expect(() => parse({ nodes: null })).toThrow("2–10");
});
it("treats model HTML and prototype names only as text labels and IDs", () => {
  const diagram = learningDiagram(
    JSON.stringify({
      nodes: [
        { id: "__proto__", label: "<img src=x onerror=alert(1)>" },
        { id: "toString", label: "安全文字" },
      ],
      edges: [["__proto__", "toString"]],
    }),
  );
  expect(diagram.nodes[0].label).toContain("<img");
  expect(diagram.nodes[1].level).toBe(1);
});
