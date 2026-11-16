import { useQuery } from "@tanstack/react-query";
import { endpoints } from "../api";
import { key } from "../query";
import Dialog from "./Dialog";
import { QueryState } from "./ui";

export default function MaterialPreview({
  file,
  onClose,
}: {
  file: { fileId: string; name: string };
  onClose: () => void;
}) {
  const preview = useQuery({
    queryKey: key("material-preview", file.fileId),
    queryFn: ({ signal }) => endpoints.materialPreview(file.fileId, signal),
  });
  return (
    <Dialog title={file.name} onClose={onClose}>
      <QueryState query={preview} />
      {preview.data && (
        <>
          <p className="muted small">
            以下为提取的文字；原始排版请下载原件查看。
          </p>
          <pre className="material-preview-text">{preview.data.text}</pre>
          {preview.data.truncated && (
            <p className="muted">当前仅展示前部分内容，完整内容请下载原件。</p>
          )}
        </>
      )}
    </Dialog>
  );
}
