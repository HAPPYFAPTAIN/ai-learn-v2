import { useLayoutEffect, useState, type RefObject } from "react";
type Box = { left: number; top: number; width: number; height: number };
export default function RangePaint({
  ranges,
  host,
  name,
}: {
  ranges: Range[];
  host: RefObject<HTMLDivElement | null>;
  name: "le-annotations" | "le-search" | "le-search-current";
}) {
  const [boxes, setBoxes] = useState<Box[]>([]);
  useLayoutEffect(() => {
    if (
      typeof Highlight !== "undefined" &&
      typeof CSS !== "undefined" &&
      CSS.highlights
    ) {
      const highlight = new Highlight(...ranges);
      highlight.priority =
        name === "le-search-current" ? 3 : name === "le-search" ? 2 : 1;
      CSS.highlights.set(name, highlight);
      setBoxes([]);
      return () => {
        CSS.highlights.delete(name);
      };
    }
    // Older browsers paint transparent rectangles, without changing React text nodes.
    const root = host.current;
    if (!root) return;
    let frame = 0;
    const paint = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const base = root.getBoundingClientRect();
        setBoxes(
          ranges
            .flatMap((range) =>
              Array.from(range.getClientRects()).map((rect) => ({
                left: rect.left - base.left + root.scrollLeft,
                top: rect.top - base.top + root.scrollTop,
                width: rect.width,
                height: rect.height,
              })),
            )
            .filter((rect) => rect.width > 0 && rect.height > 0),
        );
      });
    };
    const resize = new ResizeObserver(paint);
    resize.observe(root);
    window.addEventListener("resize", paint);
    paint();
    return () => {
      cancelAnimationFrame(frame);
      resize.disconnect();
      window.removeEventListener("resize", paint);
    };
  }, [ranges, host, name]);
  return boxes.length ? (
    <div aria-hidden="true" className={`range-paint ${name}`}>
      {boxes.map((box, index) => (
        <span key={index} style={box} />
      ))}
    </div>
  ) : null;
}
