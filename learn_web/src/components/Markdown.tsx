import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import rehypeHighlight from "rehype-highlight";
import CodeBlock from "./CodeBlock";
import { useId, useState, type ReactNode } from "react";
import { remarkExerciseAnswers } from "./exerciseAnswers";
import "katex/dist/katex.min.css";
// No raw HTML plugin: user/model content cannot inject scripts, inline handlers or iframes.
export default function RichText({
  children,
  hideExerciseAnswers = false,
}: {
  children: string;
  hideExerciseAnswers?: boolean;
}) {
  return (
    <div className="prose">
      <Markdown
        remarkPlugins={[
          remarkGfm,
          remarkMath,
          ...(hideExerciseAnswers ? [remarkExerciseAnswers] : []),
        ]}
        rehypePlugins={[
          [
            rehypeHighlight,
            {
              detect: false,
              ignoreMissing: true,
              plainText: ["markmap", "mindmap"],
            },
          ],
          [
            rehypeKatex,
            { trust: false, strict: "ignore", maxExpand: 1000, maxSize: 20 },
          ],
        ]}
        components={{
          pre: ({ children }) => <CodeBlock>{children}</CodeBlock>,
          section: ({ node, children, ...props }) =>
            node?.properties["data-exercise-answers"] ? (
              <ExerciseAnswers>{children}</ExerciseAnswers>
            ) : (
              <section {...props}>{children}</section>
            ),
          a: (props) => (
            <a {...props} target="_blank" rel="noopener noreferrer" />
          ),
        }}
      >
        {children}
      </Markdown>
    </div>
  );
}

function ExerciseAnswers({ children }: { children: ReactNode }) {
  const [revealed, setRevealed] = useState(false);
  const id = useId();
  return (
    <section className="exercise-answers">
      <button
        type="button"
        className="exercise-answer-toggle"
        aria-expanded={revealed}
        aria-controls={id}
        onClick={() => setRevealed((value) => !value)}
      >
        {revealed ? "收起答案" : "显示答案"}
      </button>
      {revealed && (
        <div id={id} className="exercise-answer-content">
          {children}
        </div>
      )}
    </section>
  );
}
