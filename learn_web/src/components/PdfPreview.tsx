import { useEffect, useMemo, useRef, useState } from "react";
import {
  getDocument,
  GlobalWorkerOptions,
  version,
  type PDFDocumentProxy,
  type PDFDocumentLoadingTask,
  type RenderTask,
} from "pdfjs-dist/legacy/build/pdf.mjs";
import workerUrl from "pdfjs-dist/legacy/build/pdf.worker.min.mjs?url";
import { endpoints } from "../api";
import { ErrorNotice } from "./ui";
import { Input } from "./fields";

GlobalWorkerOptions.workerSrc = workerUrl;
const MAX_BYTES = 20 * 1024 * 1024;
const resources = `${import.meta.env.BASE_URL}pdfjs-assets/${version}/`;

export default function PdfPreview({
  file,
}: {
  file: { fileId: string; name: string; sizeBytes?: number };
}) {
  const [document, setDocument] = useState<PDFDocumentProxy>();
  const [error, setError] = useState<Error>();
  const [attempt, setAttempt] = useState(0);
  const [page, setPage] = useState(1);
  const [zoom, setZoom] = useState(1);
  const [width, setWidth] = useState(0);
  const renderToken = useMemo(
    () => ({}),
    [document, page, zoom, width, attempt],
  );
  const [renderState, setRenderState] = useState<{
    token?: object;
    error?: Error;
  }>({});
  const renderKey = `${file.fileId}-${!!document}-${page}-${zoom}-${width}-${attempt}`;
  const rendering = renderState.token !== renderToken;
  const pageError =
    renderState.token === renderToken ? renderState.error : undefined;
  const [pageDraft, setPageDraft] = useState("1");
  const container = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    if (!container.current) return;
    const resize = new ResizeObserver(([entry]) =>
      setWidth(Math.floor(entry.contentRect.width)),
    );
    resize.observe(container.current);
    return () => resize.disconnect();
  }, []);

  useEffect(() => {
    const abort = new AbortController();
    let loading: PDFDocumentLoadingTask | undefined;
    setError(undefined);
    setDocument(undefined);
    setPage(1);
    setPageDraft("1");
    setZoom(1);
    async function load() {
      try {
        if ((file.sizeBytes || 0) > MAX_BYTES)
          throw new Error(
            "原件预览支持 20 MB 以内的 PDF，较大文件请下载查看。",
          );
        const blob = await endpoints.downloadMaterial(
          file.fileId,
          abort.signal,
        );
        if (blob.size > MAX_BYTES)
          throw new Error(
            "原件预览支持 20 MB 以内的 PDF，较大文件请下载查看。",
          );
        const data = new Uint8Array(await blob.arrayBuffer());
        if (abort.signal.aborted) return;
        loading = getDocument({
          data,
          cMapUrl: `${resources}cmaps/`,
          cMapPacked: true,
          standardFontDataUrl: `${resources}standard_fonts/`,
          wasmUrl: `${resources}wasm/`,
          iccUrl: `${resources}iccs/`,
          enableXfa: false,
          disableWorkerRendering: true,
          maxImageSize: 16_000_000,
          canvasMaxAreaInBytes: 32_000_000,
        });
        const pdf = await loading.promise;
        if (abort.signal.aborted) return;
        if (pdf.numPages > 200)
          throw new Error("原件预览最多支持 200 页，请下载查看完整文件。");
        setDocument(pdf);
      } catch (cause) {
        if (abort.signal.aborted) return;
        if (loading) void loading.destroy().catch(() => {});
        setError(
          new Error(
            cause instanceof Error && cause.name === "PasswordException"
              ? "这份 PDF 需要密码，请下载原件后打开。"
              : cause instanceof Error && /原件预览/.test(cause.message)
                ? cause.message
                : "PDF 原件暂时无法预览，可以重试、查看提取文字或下载原件。",
          ),
        );
      }
    }
    void load();
    return () => {
      abort.abort();
      if (loading) void loading.destroy().catch(() => {});
    };
  }, [file.fileId, file.sizeBytes, attempt]);

  useEffect(() => {
    if (!document || !canvas.current || !width) return;
    const target = canvas.current;
    let cancelled = false;
    let task: RenderTask | undefined;
    async function render() {
      try {
        const sheet = await document!.getPage(page);
        if (cancelled) return;
        const original = sheet.getViewport({ scale: 1 });
        const viewport = sheet.getViewport({
          scale: (Math.max(1, width - 28) / original.width) * zoom,
        });
        if (
          !Number.isFinite(viewport.width + viewport.height) ||
          viewport.width <= 0 ||
          viewport.height <= 0 ||
          Math.max(viewport.width, viewport.height) > 12_000
        )
          throw new Error("页面尺寸过大，请下载原件查看。");
        const ratio = Math.min(
          window.devicePixelRatio || 1,
          2,
          Math.sqrt(8_000_000 / (viewport.width * viewport.height)),
          8192 / Math.max(viewport.width, viewport.height),
        );
        target.width = Math.max(1, Math.floor(viewport.width * ratio));
        target.height = Math.max(1, Math.floor(viewport.height * ratio));
        target.style.width = `${viewport.width}px`;
        target.style.height = `${viewport.height}px`;
        task = sheet.render({
          canvas: target,
          viewport,
          transform: [ratio, 0, 0, ratio, 0, 0],
          background: "white",
        });
        await task.promise;
        if (!cancelled) setRenderState({ token: renderToken });
        // Retain the document, but release page operator/image caches between pages.
        sheet.cleanup();
      } catch (cause) {
        if (!cancelled) {
          setRenderState({
            token: renderToken,
            error: new Error(
              cause instanceof Error && /页面尺寸/.test(cause.message)
                ? cause.message
                : "这一页暂时无法显示，请切换页面、重试或查看提取文字。",
            ),
          });
        }
      }
    }
    void render();
    return () => {
      cancelled = true;
      task?.cancel();
    };
  }, [document, page, zoom, width, renderToken]);

  function go(next: number) {
    if (
      !document ||
      !Number.isInteger(next) ||
      next < 1 ||
      next > document.numPages
    ) {
      setPageDraft(String(page));
      return;
    }
    setPage(next);
    setPageDraft(String(next));
  }

  return (
    <section className="pdf-preview" aria-label="PDF 原件预览" ref={container}>
      <ErrorNotice error={error} />
      {error ? (
        <button type="button" onClick={() => setAttempt((value) => value + 1)}>
          重试预览
        </button>
      ) : !document ? (
        <p role="status">正在加载 PDF 原件…</p>
      ) : (
        <>
          <div className="pdf-toolbar">
            <div className="content-actions">
              <button
                type="button"
                disabled={page <= 1}
                onClick={() => go(page - 1)}
              >
                上一页
              </button>
              <form
                className="pdf-page-form"
                onSubmit={(event) => {
                  event.preventDefault();
                  go(Number(pageDraft));
                }}
              >
                <Input
                  aria-label="PDF 页码"
                  type="number"
                  min={1}
                  max={document.numPages}
                  value={pageDraft}
                  onChange={(event) => setPageDraft(event.target.value)}
                />
                <span> / {document.numPages} 页</span>
                <button type="submit">跳转</button>
              </form>
              <button
                type="button"
                disabled={page >= document.numPages}
                onClick={() => go(page + 1)}
              >
                下一页
              </button>
            </div>
            <div className="content-actions">
              <button
                type="button"
                aria-label="缩小 PDF"
                disabled={zoom <= 0.5}
                onClick={() => setZoom((value) => Math.max(0.5, value - 0.25))}
              >
                缩小
              </button>
              <span className="small muted">{Math.round(zoom * 100)}%</span>
              <button
                type="button"
                aria-label="放大 PDF"
                disabled={zoom >= 2}
                onClick={() => setZoom((value) => Math.min(2, value + 0.25))}
              >
                放大
              </button>
              <button type="button" onClick={() => setZoom(1)}>
                适应宽度
              </button>
            </div>
          </div>
          <ErrorNotice error={pageError} />
          {pageError && (
            <button
              type="button"
              onClick={() => setAttempt((value) => value + 1)}
            >
              重试预览
            </button>
          )}
          <p role="status" className="small muted">
            {rendering
              ? `正在绘制第 ${page} 页…`
              : `第 ${page} / ${document.numPages} 页`}
          </p>
          <div
            className="pdf-canvas-scroll"
            aria-busy={rendering}
            tabIndex={0}
            role="region"
            aria-label="PDF 页面，可横向滚动"
          >
            <canvas
              key={renderKey}
              ref={canvas}
              role="img"
              aria-label={`${file.name}，第 ${page} 页`}
              style={{
                visibility: rendering || pageError ? "hidden" : "visible",
              }}
            />
          </div>
          <p className="muted small">
            原件保留文档自身配色；需要复制或查找文字时，请切换到“提取文字”。
          </p>
        </>
      )}
    </section>
  );
}
