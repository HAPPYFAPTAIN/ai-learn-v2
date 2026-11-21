export function learningDiagram(source: string) {
  if (source.length > 20_000) throw new Error("结构图内容过长");
  const data = JSON.parse(source);
  if (
    !data ||
    !Array.isArray(data.nodes) ||
    data.nodes.length < 2 ||
    data.nodes.length > 10
  )
    throw new Error("结构图需要 2–10 个知识点");
  const nodes: { id: string; label: string; level: number }[] = [];
  const ids = new Set<string>();
  for (const node of data.nodes) {
    if (
      !node ||
      typeof node.id !== "string" ||
      !node.id.trim() ||
      node.id.length > 80 ||
      ids.has(node.id) ||
      typeof node.label !== "string" ||
      !node.label.trim() ||
      node.label.length > 60
    )
      throw new Error("结构图知识点格式不完整");
    ids.add(node.id);
    nodes.push({ id: node.id, label: node.label, level: 0 });
  }
  const rawEdges: unknown = data.edges ?? [];
  if (!Array.isArray(rawEdges) || rawEdges.length > 18)
    throw new Error("结构图最多支持 18 条关系");
  const edges: [string, string][] = [];
  for (const edge of rawEdges) {
    if (
      !Array.isArray(edge) ||
      edge.length !== 2 ||
      !ids.has(edge[0]) ||
      !ids.has(edge[1])
    )
      throw new Error("结构图关系引用了不存在的知识点");
    edges.push([edge[0], edge[1]]);
  }
  const byId = new Map(nodes.map((node) => [node.id, node]));
  let changed = false;
  for (let pass = 0; pass < nodes.length; pass++) {
    changed = false;
    for (const [a, b] of edges) {
      const from = byId.get(a)!,
        to = byId.get(b)!;
      if (to.level <= from.level) {
        to.level = from.level + 1;
        changed = true;
      }
    }
    if (!changed) break;
  }
  if (changed) throw new Error("结构图包含循环，请将流程拆成顺序步骤");
  const depth = Math.max(...nodes.map((node) => node.level)) + 1;
  if (depth > 6) throw new Error("结构图层次过多");
  const rows = Array.from({ length: depth }, (_, level) =>
    nodes.filter((n) => n.level === level),
  );
  const width = Math.max(360, ...rows.map((row) => row.length * 200));
  const nodeHeight = Math.max(
    64,
    ...nodes.map(
      (node) => Math.ceil(Array.from(node.label).length / 10) * 20 + 24,
    ),
  );
  const rowHeight = nodeHeight + 48;
  return {
    title:
      typeof data.title === "string" ? data.title.slice(0, 160) : "知识结构图",
    nodes: rows.flatMap((row, level) =>
      row.map((node, index) => ({
        ...node,
        x: ((index + 0.5) * width) / row.length,
        y: 20 + level * rowHeight,
      })),
    ),
    edges,
    width,
    nodeHeight,
    height: depth * rowHeight - 48 + 40,
  };
}
