import { useMutation, useQuery } from "@tanstack/react-query";
import { lazy, Suspense, useId, useState } from "react";
import { endpoints } from "../api";
import { key } from "../query";
import Dialog from "./Dialog";
import { ErrorNotice, QueryState } from "./ui";
import { saveBlob } from "./download";

const PdfPreview = lazy(() => import("./PdfPreview"));

export default function MaterialPreview({
  file,
  onClose,
}: {
  file: { fileId: string; name: string; sizeBytes?: number };
  onClose: () => void;
}) {
  const [mode, setMode] = useState<"text" | "pdf">("text");
  const panel = useId();
  const isPdf = /\.pdf$/i.test(file.name);
  const download = useMutation({
    mutationFn: () => endpoints.downloadMaterial(file.fileId),
    onSuccess: (blob) => saveBlob(blob, file.name),
  });
  const preview = useQuery({
    queryKey: key("material-preview", file.fileId),
    queryFn: ({ signal }) => endpoints.materialPreview(file.fileId, signal),
    enabled: mode === "text",
  });
  return (
    <Dialog title={file.name} onClose={onClose}>
      <div className="material-preview-toolbar">
        <div className="content-actions" role="group" aria-label="预览方式">
          <button
            type="button"
            aria-pressed={mode === "text"}
            aria-controls={panel}
            onClick={() => setMode("text")}
          >
            提取文字
          </button>
          {isPdf && (
            <button
              type="button"
              aria-pressed={mode === "pdf"}
              aria-controls={panel}
              onClick={() => setMode("pdf")}
            >
              PDF 原件
            </button>
          )}
        </div>
        <button
          type="button"
          disabled={download.isPending}
          onClick={() => download.mutate()}
        >
          {download.isPending ? "正在下载…" : "下载原件"}
        </button>
      </div>
      <ErrorNotice error={download.error} />
      <div id={panel}>
        {mode === "pdf" ? (
          <Suspense fallback={<p role="status">正在加载 PDF 阅读器…</p>}>
            <PdfPreview file={file} />
          </Suspense>
        ) : (
          <>
            <QueryState query={preview} />
            {preview.data && (
              <>
                <p className="muted small">
                  以下为提取的文字；原始排版请下载原件查看。
                </p>
                <pre className="material-preview-text">{preview.data.text}</pre>
                {preview.data.truncated && (
                  <p className="muted">
                    当前仅展示前部分内容，完整内容请下载原件。
                  </p>
                )}
              </>
            )}
          </>
        )}
      </div>
    </Dialog>
  );
}
