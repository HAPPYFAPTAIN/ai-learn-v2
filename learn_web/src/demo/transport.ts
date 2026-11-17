import { setTransport } from "../api/client";
import { setStreamFactory, type EventStream } from "../api/jobs";
import { createDemo } from "./data";
import { modelPreview } from "../models/preview";
import { providerPresets } from "../models/presets";
export function enableDemo() {
  const empty = new URLSearchParams(location.search).get("empty") === "1";
  modelPreview.seed(
    empty
      ? []
      : providerPresets
          .filter((p) => ["deepseek", "qwen"].includes(p.id))
          .map((p) => ({
            id: `demo-${p.id}`,
            provider: p.id,
            name: p.name,
            baseUrl: p.baseUrl,
            models: [...p.models],
          })),
  );
  const demo = createDemo(empty);
  setTransport(async (input, init) => {
    if (init?.signal?.aborted) throw new DOMException("Aborted", "AbortError");
    return demo.handle(String(input), init);
  });
  setStreamFactory((url) => {
    const target = new EventTarget();
    const id = new URL(url, location.origin).pathname.split("/").slice(-2)[0];
    let closed = false;
    const stream: EventStream = {
      addEventListener: target.addEventListener.bind(
        target,
      ) as EventStream["addEventListener"],
      onopen: null,
      onerror: null,
      close() {
        closed = true;
        clearTimeout(timer);
      },
    };
    let timer = setTimeout(() => {
      if (closed) return;
      stream.onopen?.call(stream as EventSource, new Event("open"));
      const job = demo.jobs.get(id);
      if (!job) {
        target.dispatchEvent(new MessageEvent("gone", { data: "{}" }));
        return;
      }
      target.dispatchEvent(
        new MessageEvent("progress", { data: JSON.stringify(job) }),
      );
      timer = setTimeout(() => {
        if (!closed) {
          Object.assign(job, {
            state: "done",
            progress: { done: 1, total: 1 },
          });
          target.dispatchEvent(
            new MessageEvent("progress", { data: JSON.stringify(job) }),
          );
        }
      }, 800);
    }, 100);
    return stream;
  });
}
