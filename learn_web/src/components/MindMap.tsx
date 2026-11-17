import { useEffect, useId, useMemo, useRef, useState } from "react";
import { Markmap, type ViewOptions } from "@markmap/view";
import { mapLabel, mindmapTree } from "./mindmapTree";

type MapNode = ReturnType<typeof mindmapTree>;

function Outline({ node }: { node: MapNode }) {
  return (
    <li>
      {mapLabel(node)}
      {node.children.length > 0 && (
        <ul>
          {node.children.map((child) => (
            <Outline key={child.id} node={child} />
          ))}
        </ul>
      )}
    </li>
  );
}

export default function MindMap({ source }: { source: string }) {
  const svg = useRef<SVGSVGElement>(null);
  const view = useRef<Markmap | null>(null);
  const hint = useId();
  const [renderError, setRenderError] = useState("");
  const tree = useMemo(() => {
    try {
      return { root: mindmapTree(source), error: "" };
    } catch (error) {
      return {
        root: undefined,
        error:
          error instanceof Error
            ? error.message
            : "无法解析导图，请查看章节列表或源码。",
      };
    }
  }, [source]);

  useEffect(() => {
    setRenderError("");
    if (!svg.current || !tree.root) return;
    let map: Markmap | undefined;
    let resize: ResizeObserver | undefined;
    let theme: MutationObserver | undefined;
    try {
      let compact = svg.current.clientWidth < 600;
      const options = (): ViewOptions => ({
        colorScheme:
          document.documentElement.dataset.theme === "dark" ? "dark" : "light",
        zoom: false,
        pan: true,
        duration: 0,
        wrapWidth: compact ? 110 : 220,
        levelGap: compact ? 20 : 60,
        foldLevel: compact ? 1 : undefined,
        fitPadding: compact ? 14 : 24,
        fitMaxScale: 1.2,
        highlight: false,
      });
      map = new Markmap(svg.current, options());
      view.current = map;
      map.setTree(tree.root);
      map.fit();
      resize = new ResizeObserver(([entry]) => {
        const nextCompact = entry.contentRect.width < 600;
        if (compact !== nextCompact) {
          compact = nextCompact;
          map?.setOptions(options());
        }
        map?.fit();
      });
      resize.observe(svg.current);
      theme = new MutationObserver(() => map?.setOptions(options()));
      theme.observe(document.documentElement, {
        attributes: true,
        attributeFilter: ["data-theme"],
      });
    } catch {
      setRenderError("导图暂时无法显示，请使用下方文字大纲。");
    }
    return () => {
      resize?.disconnect();
      theme?.disconnect();
      map?.destroy();
      view.current = null;
    };
  }, [tree]);

  const error = tree.error || renderError;
  return (
    <section className="mindmap" aria-label="思维导图">
      {error && (
        <p role="status" className="muted">
          {error}
        </p>
      )}
      {tree.root && (
        <>
          <div className="mindmap-toolbar">
            <p id={hint} className="muted">
              拖动查看；用按钮缩放，点击分支圆点可折叠。
            </p>
            <div className="content-actions">
              <button
                type="button"
                disabled={!!error}
                aria-label="放大导图"
                onClick={() => view.current?.zoomIn()}
              >
                放大
              </button>
              <button
                type="button"
                disabled={!!error}
                aria-label="缩小导图"
                onClick={() => view.current?.zoomOut()}
              >
                缩小
              </button>
              <button
                type="button"
                disabled={!!error}
                onClick={() => view.current?.fit()}
              >
                适应画布
              </button>
            </div>
          </div>
          <svg
            ref={svg}
            className="mindmap-canvas"
            role="img"
            aria-label={`${mapLabel(tree.root)}思维导图`}
            aria-describedby={hint}
            style={error ? { display: "none" } : undefined}
          />
          <details className="mindmap-outline" open={!!error}>
            <summary>查看文字大纲</summary>
            <ul>
              <Outline node={tree.root} />
            </ul>
          </details>
        </>
      )}
    </section>
  );
}
