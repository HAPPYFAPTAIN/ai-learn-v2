import {
  Children,
  isValidElement,
  lazy,
  Suspense,
  useState,
  type ReactNode,
} from "react";

const MindMap = lazy(() => import("./MindMap"));
const LearningDiagram = lazy(() => import("./LearningDiagram"));

function plainText(value: ReactNode): string {
  return Children.toArray(value)
    .map((child) => {
      if (typeof child === "string" || typeof child === "number")
        return String(child);
      return isValidElement<{ children?: ReactNode }>(child)
        ? plainText(child.props.children)
        : "";
    })
    .join("");
}

export default function CodeBlock({ children }: { children?: ReactNode }) {
  const code = Children.toArray(children).find((child) =>
    isValidElement(child),
  );
  const className = isValidElement<{ className?: string }>(code)
    ? code.props.className || ""
    : "";
  const language = /(?:^|\s)language-([^\s]+)/.exec(className)?.[1] || "text";
  const source = plainText(children).replace(/\n$/, "");
  const [copyResult, setCopyResult] = useState({ source: "", message: "" });
  const [mapSource, setMapSource] = useState<string>();
  const copied = copyResult.source === source ? copyResult.message : "";
  const showMap = mapSource === source;
  const isMap = language === "markmap" || language === "mindmap";
  if (language === "learning-diagram")
    return (
      <Suspense fallback={<p role="status">正在加载知识结构图…</p>}>
        <LearningDiagram source={source} />
      </Suspense>
    );
  async function copy() {
    try {
      await navigator.clipboard.writeText(source);
      setCopyResult({ source, message: "已复制" });
    } catch {
      setCopyResult({ source, message: "复制失败，请选中代码手动复制" });
    }
  }
  return (
    <div className="code-block">
      <div className="code-block-toolbar">
        <span className="code-language">{isMap ? "思维导图" : language}</span>
        <div className="content-actions">
          {isMap && (
            <button
              type="button"
              aria-expanded={showMap}
              onClick={() => setMapSource(showMap ? undefined : source)}
            >
              {showMap ? "查看源码" : "查看思维导图"}
            </button>
          )}
          <button
            type="button"
            aria-label="复制代码"
            onClick={() => void copy()}
          >
            复制代码
          </button>
        </div>
      </div>
      {isMap && showMap ? (
        <Suspense fallback={<p role="status">正在加载思维导图…</p>}>
          <MindMap source={source} />
        </Suspense>
      ) : (
        <pre>{children}</pre>
      )}
      {copied && (
        <p className="copy-feedback" role="status">
          {copied}
        </p>
      )}
    </div>
  );
}
