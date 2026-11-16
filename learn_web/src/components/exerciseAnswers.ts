import type { Heading, Root, RootContent } from "mdast";

function headingText(heading: Heading): string {
  // Headings may contain emphasis, inline code, links or decorative emoji.
  const text = (node: { value?: string; children?: unknown[] }): string =>
    node.value ??
    (node.children || []).map((child) => text(child as typeof node)).join("");
  return text(heading).replace(/[\s\p{P}\p{S}]/gu, "");
}

// Work on the Markdown tree so code fences and ordinary text remain untouched.
// Only lesson reference-answer sections are grouped, never standalone quiz data.
export function remarkExerciseAnswers() {
  return (tree: Root) => {
    const grouped: RootContent[] = [];
    let exerciseDepth = 0;
    for (let i = 0; i < tree.children.length; i++) {
      const node = tree.children[i];
      if (node.type !== "heading") {
        grouped.push(node);
        continue;
      }
      const title = headingText(node);
      const answer =
        /^(?:自测|练习|自测练习)(?:参考)?答案(?:与?解析)?$/.test(title) ||
        (!!exerciseDepth && /^(?:参考)?答案(?:与?解析)?$/.test(title));
      if (answer) {
        let end = i + 1;
        while (end < tree.children.length) {
          const next = tree.children[end];
          if (next.type === "heading" && next.depth <= node.depth) break;
          end++;
        }
        grouped.push({
          type: "blockquote",
          data: {
            hName: "section",
            hProperties: { "data-exercise-answers": true },
          },
          children: tree.children.slice(i, end) as Extract<
            RootContent,
            { type: "blockquote" }
          >["children"],
        });
        i = end - 1;
      } else {
        if (exerciseDepth && node.depth <= exerciseDepth) exerciseDepth = 0;
        if (/自测练习|自我测验|自测题|课后练习/.test(title))
          exerciseDepth = node.depth;
        grouped.push(node);
      }
    }
    tree.children = grouped;
  };
}
