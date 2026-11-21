import { useId } from "react";
import { learningDiagram } from "./diagramLayout";

export default function LearningDiagram({ source }: { source: string }) {
  const marker = `diagram-${useId().replace(/:/g, "")}`;
  try {
    const diagram = learningDiagram(source);
    const byId = new Map(diagram.nodes.map((node) => [node.id, node]));
    return (
      <figure className="learning-diagram">
        <figcaption>{diagram.title}</figcaption>
        <p className="muted small">
          沿箭头阅读知识点之间的关系；也可展开下方文字版。
        </p>
        <div
          className="learning-diagram-scroll"
          tabIndex={0}
          role="region"
          aria-label={`${diagram.title}图示，可横向滚动`}
        >
          <svg
            viewBox={`0 0 ${diagram.width} ${diagram.height}`}
            style={{ minWidth: diagram.width }}
            role="img"
            aria-label={diagram.title}
          >
            <defs>
              <marker
                id={marker}
                markerWidth="8"
                markerHeight="8"
                refX="7"
                refY="4"
                orient="auto"
              >
                <path d="M0 0L8 4L0 8Z" fill="currentColor" />
              </marker>
            </defs>
            {diagram.edges.map(([a, b], index) => {
              const from = byId.get(a)!,
                to = byId.get(b)!;
              return (
                <path
                  key={index}
                  className="diagram-edge"
                  d={`M${from.x} ${from.y + diagram.nodeHeight} C${from.x} ${from.y + diagram.nodeHeight + 22} ${to.x} ${to.y - 22} ${to.x} ${to.y - 3}`}
                  markerEnd={`url(#${marker})`}
                />
              );
            })}
            {diagram.nodes.map((node) => (
              <g key={node.id} className="diagram-node">
                <rect
                  x={node.x - 88}
                  y={node.y}
                  width={176}
                  height={diagram.nodeHeight}
                  rx={12}
                />
                {Array.from(node.label)
                  .reduce<string[]>((lines, letter, index) => {
                    if (index % 10 === 0) lines.push("");
                    lines[lines.length - 1] += letter;
                    return lines;
                  }, [])
                  .map((line, index, lines) => (
                    <text
                      key={index}
                      x={node.x}
                      y={
                        node.y +
                        diagram.nodeHeight / 2 +
                        5 +
                        (index - (lines.length - 1) / 2) * 20
                      }
                      textAnchor="middle"
                    >
                      {line}
                    </text>
                  ))}
              </g>
            ))}
          </svg>
        </div>
        <details>
          <summary>文字版知识关系</summary>
          <ul>
            {diagram.edges.length
              ? diagram.edges.map(([a, b], index) => (
                  <li key={index}>
                    {byId.get(a)!.label} → {byId.get(b)!.label}
                  </li>
                ))
              : diagram.nodes.map((node) => (
                  <li key={node.id}>{node.label}</li>
                ))}
          </ul>
        </details>
      </figure>
    );
  } catch {
    return (
      <div className="notice" role="note">
        <p>
          这张知识结构图格式不完整，暂时无法绘制。可先阅读上下文，已有课文不受影响。
        </p>
        <details>
          <summary>查看结构图原文</summary>
          <pre>{source.slice(0, 20_000)}</pre>
        </details>
      </div>
    );
  }
}
