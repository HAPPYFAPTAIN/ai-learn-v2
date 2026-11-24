import {
  useEffect,
  useId,
  useRef,
  useState,
  type ReactNode,
  type CSSProperties,
} from "react";
import { Input, SearchField } from "./fields";
import { matchingRanges, readingIndex } from "./quoteRange";
import RangePaint from "./RangePaint";
export default function ReadingTools({
  children,
  actions,
}: {
  children: ReactNode;
  actions?: ReactNode;
}) {
  const body = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState(() => {
    const saved = Number(localStorage.getItem("learn.reading.size"));
    // Wide screens open at the chapter reading size; phones start smaller.
    return saved >= 16 && saved <= 24
      ? saved
      : window.matchMedia("(min-width: 768px)").matches
        ? 22
        : 18;
  });
  const [search, setSearch] = useState("");
  const [current, setCurrent] = useState(0);
  const [found, setFound] = useState<{ ranges: Range[]; truncated: boolean }>({
    ranges: [],
    truncated: false,
  });
  const [headings, setHeadings] = useState<
    { element: HTMLElement; text: string; depth: number }[]
  >([]);
  const id = useId();
  useEffect(() => {
    const root = body.current;
    if (!root) return;
    let frame = 0;
    const scan = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const reading = root.querySelector<HTMLElement>(".lesson-reading");
        setHeadings(
          Array.from(
            root.querySelectorAll<HTMLElement>(
              ".lesson-reading .prose h1, .lesson-reading .prose h2, .lesson-reading .prose h3, .lesson-reading .prose h4",
            ),
          ).map((element) => ({
            element,
            text: element.textContent || "未命名标题",
            depth: Number(element.tagName.slice(1)),
          })),
        );
        setFound(
          reading && search.trim()
            ? matchingRanges(readingIndex(reading), search, 200, true)
            : { ranges: [], truncated: false },
        );
      });
    };
    const observer = new MutationObserver((mutations) => {
      if (
        mutations.some((m) => {
          const target =
            m.target instanceof Element ? m.target : m.target.parentElement;
          if (target?.closest(".range-paint")) return false;
          const changed = [...m.addedNodes, ...m.removedNodes];
          return (
            !changed.length ||
            !changed.every(
              (n) =>
                n instanceof Element && n.classList.contains("range-paint"),
            )
          );
        })
      )
        scan();
    });
    observer.observe(root, {
      childList: true,
      subtree: true,
      characterData: true,
    });
    scan();
    return () => {
      observer.disconnect();
      cancelAnimationFrame(frame);
    };
  }, [search]);
  const position = found.ranges.length ? current % found.ranges.length : 0;
  const active = found.ranges[position];
  function jump(next: number) {
    if (!found.ranges.length) return;
    const index = (next + found.ranges.length) % found.ranges.length;
    setCurrent(index);
    const element = found.ranges[index].startContainer.parentElement;
    element?.scrollIntoView({ block: "center", behavior: "smooth" });
  }
  return (
    <section className="reading-tools" aria-label="课文阅读工具">
      <div className="feature-toolbar reading-toolbar">
        <SearchField
          label="搜索课文"
          placeholder="在本节正文中查找"
          value={search}
          onChange={(value) => {
            setSearch(value.slice(0, 200));
            setCurrent(0);
          }}
        />
        <div className="content-actions">
          <button
            type="button"
            disabled={!found.ranges.length}
            onClick={() => jump(position - 1)}
          >
            上一处
          </button>
          <button
            type="button"
            disabled={!found.ranges.length}
            onClick={() => jump(position + 1)}
          >
            下一处
          </button>
        </div>
        <label htmlFor={id} className="reading-size">
          <span>
            字号 <output htmlFor={id}>{size}px</output>
          </span>
          <Input
            id={id}
            type="range"
            min={16}
            max={24}
            step={1}
            value={size}
            onChange={(e) => {
              const value = Number(e.target.value);
              setSize(value);
              localStorage.setItem("learn.reading.size", String(value));
            }}
            aria-label="课文字号"
          />
        </label>
        {actions && (
          <div className="content-actions reading-actions">{actions}</div>
        )}
      </div>
      {search.trim() && (
        <p role="status" className="muted small">
          {found.ranges.length
            ? `第 ${position + 1} / ${found.ranges.length} 处${found.truncated ? "（仅显示前200处）" : ""}`
            : "本节正文未找到匹配文字。"}
        </p>
      )}
      {headings.length > 0 && (
        <details className="lesson-outline">
          <summary>课文目录（{headings.length}）</summary>
          <nav aria-label="课文目录">
            <ol>
              {headings.map(({ element, text, depth }, index) => (
                <li
                  key={index}
                  style={{ paddingInlineStart: Math.max(0, depth - 2) * 12 }}
                >
                  <button
                    type="button"
                    onClick={() => {
                      element.tabIndex = -1;
                      element.focus({ preventScroll: true });
                      element.scrollIntoView({
                        block: "start",
                        behavior: "smooth",
                      });
                    }}
                  >
                    {text}
                  </button>
                </li>
              ))}
            </ol>
          </nav>
        </details>
      )}
      <div
        className="reading-body"
        ref={body}
        style={{ "--reading-size": `${size}px` } as CSSProperties}
      >
        {children}
        <RangePaint ranges={found.ranges} host={body} name="le-search" />
        <RangePaint
          ranges={active ? [active] : []}
          host={body}
          name="le-search-current"
        />
      </div>
    </section>
  );
}
