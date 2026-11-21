import Markdown, { defaultUrlTransform } from "react-markdown";
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
              plainText: ["markmap", "mindmap", "learning-diagram"],
            },
          ],
          [
            rehypeKatex,
            { trust: false, strict: "ignore", maxExpand: 1000, maxSize: 20 },
          ],
        ]}
        urlTransform={(url, key) =>
          key === "src" && url.startsWith("data:image/")
            ? url
            : defaultUrlTransform(url)
        }
        components={{
          img: ({ src, alt }) => {
            const value = typeof src === "string" ? src : "";
            let allowed = value.startsWith("data:image/");
            try {
              allowed ||=
                new URL(value, window.location.href).origin ===
                window.location.origin;
            } catch {
              /* invalid sources are blocked */
            }
            return value && allowed ? (
              <img src={value} alt={alt || ""} loading="lazy" />
            ) : (
              <span className="muted">
                [外部图片已屏蔽] {alt} {value}
              </span>
            );
          },
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
