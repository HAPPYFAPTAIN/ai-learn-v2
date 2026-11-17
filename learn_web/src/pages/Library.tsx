import { SearchField } from "../components/fields";
import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { endpoints, type JobProgress } from "../api";
import { key } from "../query";
import { watchJob, type Connection } from "../api/jobs";
import { session } from "../session/store";
import type { UploadProgress } from "../api/upload";
import { useProject } from "../components/ProjectContext";
import Dialog from "../components/Dialog";
import MaterialPreview from "../components/MaterialPreview";
import MaterialBatchActions from "../components/MaterialBatchActions";
import MaterialBatchUpload from "../components/MaterialBatchUpload";
import { validateUpload } from "../components/uploadValidation";
import Select from "../components/Select";
import { saveBlob } from "../components/download";
import {
  Empty,
  ErrorNotice,
  formatBytes,
  Icon,
  PageHeading,
  QueryState,
} from "../components/ui";
export default function Library() {
  const { id } = useProject();
  return <LibraryContent key={id} />;
}
type UploadDisplay = UploadProgress & {
  name: string;
  state: "sending" | "saved" | "cancelled" | "failed";
  message?: string;
};
function LibraryContent() {
  const { id } = useProject();
  const client = useQueryClient();
  const jobKey = `learn.v2.job.${session.get().owner}.${id}`;
  const savedJob = sessionStorage.getItem(jobKey) || "";
  const [filter, setFilter] = useState("");
  const [fileType, setFileType] = useState("all");
  const [sort, setSort] = useState("newest");
  const [selected, setSelected] = useState(new Set<string>());
  const [batchBusy, setBatchBusy] = useState(false);
  const [batchFiles, setBatchFiles] = useState<File[]>();
  const [batchUploading, setBatchUploading] = useState(false);
  const [validation, setValidation] = useState("");
  const [job, setJob] = useState(savedJob);
  const [active, setActive] = useState(!!savedJob);
  const input = useRef<HTMLInputElement>(null);
  const uploadController = useRef<AbortController | undefined>(undefined);
  const lastFile = useRef<File | undefined>(undefined);
  const alive = useRef(false);
  const owner = useRef(session.get().owner);
  const [transfer, setTransfer] = useState<UploadDisplay>();
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
      uploadController.current?.abort();
    };
  }, []);
  const [preview, setPreview] = useState<{
    fileId: string;
    name: string;
    sizeBytes: number;
  }>();
  const [deleting, setDeleting] = useState<{ fileId: string; name: string }>();
  const remove = useMutation({
    mutationFn: (fileId: string) => endpoints.deleteMaterial(fileId),
    onSuccess: (_, fileId) => {
      setDeleting(undefined);
      setSelected(
        (previous) => new Set([...previous].filter((id) => id !== fileId)),
      );
      client.removeQueries({ queryKey: key("material-preview", fileId) });
      void client.invalidateQueries({ queryKey: key("materials") });
    },
  });
  const download = useMutation({
    mutationFn: (file: { fileId: string; name: string }) =>
      endpoints.downloadMaterial(file.fileId),
    onSuccess: (blob, file) => {
      saveBlob(blob, file.name);
    },
  });
  const reindex = useMutation({
    mutationFn: (fileId: string) => endpoints.indexMaterial(fileId),
    onSuccess: (r) => {
      setJob(r.jobId);
      setActive(true);
      sessionStorage.setItem(jobKey, r.jobId);
    },
  });
  const files = useQuery({
    queryKey: key("materials", id),
    queryFn: ({ signal }) => endpoints.materials(id, signal),
    enabled: !!id,
  });
  const visibleFiles = (files.data?.items || [])
    .filter(
      (file) =>
        file.name.toLowerCase().includes(filter.trim().toLowerCase()) &&
        (fileType === "all" ||
          file.name.toLowerCase().endsWith(`.${fileType}`)),
    )
    .sort((a, b) => {
      if (sort === "name")
        return a.name.localeCompare(b.name, "zh-CN", { numeric: true });
      if (sort === "size") return b.sizeBytes - a.sizeBytes;
      const byDate = Date.parse(b.createdAt) - Date.parse(a.createdAt);
      return sort === "oldest" ? -byDate : byDate;
    });
  const upload = useMutation({
    mutationFn: ({
      file,
      controller,
    }: {
      file: File;
      controller: AbortController;
    }) =>
      endpoints.upload(
        id,
        file,
        (progress) => {
          if (alive.current && !controller.signal.aborted)
            setTransfer((previous) => previous && { ...previous, ...progress });
        },
        controller.signal,
      ),
    onSuccess: (r, { controller, file }) => {
      if (
        !alive.current ||
        controller.signal.aborted ||
        session.get().owner !== owner.current
      )
        return;
      setTransfer(
        (previous) =>
          previous && {
            ...previous,
            loaded: previous.total || file.size,
            state: "saved",
          },
      );
      lastFile.current = undefined;
      setJob(r.jobId || "");
      setActive(!!r.jobId);
      if (r.jobId) sessionStorage.setItem(jobKey, r.jobId);
      void client.invalidateQueries({ queryKey: key("materials", id) });
    },
    onError: (error, { controller }) => {
      if (!alive.current || session.get().owner !== owner.current) return;
      setTransfer(
        (previous) =>
          previous && {
            ...previous,
            state: controller.signal.aborted ? "cancelled" : "failed",
            message:
              error.name === "AbortError"
                ? "若文件已传输完成，请刷新资料列表确认结果。"
                : error.message,
          },
      );
      void client.invalidateQueries({ queryKey: key("materials", id) });
    },
  });
  function startUpload(file: File) {
    if (upload.isPending) return;
    const controller = new AbortController();
    uploadController.current = controller;
    lastFile.current = file;
    setValidation("");
    setTransfer({
      name: file.name,
      loaded: 0,
      total: file.size,
      state: "sending",
    });
    upload.mutate({ file, controller });
  }
  const done = () => {
    sessionStorage.removeItem(jobKey);
    setActive(false);
    void client.invalidateQueries({ queryKey: key("materials", id) });
  };
  return (
    <>
      <PageHeading
        title="资料库"
        description="把有用的知识整理在一起，方便随时查阅。"
      />
      {!id ? (
        <Empty title="暂无学习目标" />
      ) : (
        <>
          <section className="panel">
            <div className="section-title spread">
              <div>
                <h2>我的资料</h2>
                <p className="muted">
                  当前账号共享的学习资料，支持 TXT、Markdown、PDF 和
                  DOCX，单个文件最多 50 MB；每批最多 10 份、共 100 MB。
                </p>
              </div>
              <button
                className="primary"
                disabled={
                  upload.isPending || active || batchBusy || batchUploading
                }
                onClick={() => input.current?.click()}
              >
                <Icon name="plus" />
                {upload.isPending ? "上传中…" : "上传资料"}
              </button>
            </div>
            <input
              className="sr-only"
              ref={input}
              type="file"
              multiple
              accept=".txt,.md,.pdf,.docx"
              aria-label="选择上传资料"
              disabled={
                upload.isPending || active || batchBusy || batchUploading
              }
              onChange={(e) => {
                const chosen = Array.from(e.target.files || []);
                e.target.value = "";
                if (!chosen.length) return;
                const error = validateUpload(chosen);
                if (error) {
                  setValidation(error);
                  return;
                }
                setValidation("");
                if (chosen.length === 1) startUpload(chosen[0]);
                else setBatchFiles(chosen);
              }}
            />
            <ErrorNotice error={validation ? new Error(validation) : null} />
            {transfer && (
              <UploadStatus
                value={transfer}
                pending={upload.isPending}
                onCancel={() => uploadController.current?.abort()}
                onRetry={() => {
                  if (lastFile.current) startUpload(lastFile.current);
                }}
              />
            )}
            <ErrorNotice error={download.error || reindex.error} />
            {job && <JobStatus id={job} done={done} />}
            <div className="library-toolbar">
              <SearchField
                label="搜索资料"
                placeholder="搜索资料名称"
                value={filter}
                onChange={setFilter}
              />
              <div className="library-filters">
                <Select
                  label="资料类型"
                  value={fileType}
                  onChange={setFileType}
                  options={[
                    { value: "all", label: "全部类型" },
                    { value: "pdf", label: "PDF" },
                    { value: "md", label: "Markdown" },
                    { value: "txt", label: "TXT" },
                    { value: "docx", label: "DOCX" },
                  ]}
                />
                <Select
                  label="资料排序"
                  value={sort}
                  onChange={setSort}
                  options={[
                    { value: "newest", label: "最新添加" },
                    { value: "oldest", label: "最早添加" },
                    { value: "name", label: "名称顺序" },
                    { value: "size", label: "文件大小" },
                  ]}
                />
              </div>
            </div>
            {files.data && (
              <p className="muted small library-result-count" role="status">
                显示 {visibleFiles.length} / {files.data.items.length} 份资料
              </p>
            )}
            <QueryState query={files} />
            {files.data && (
              <MaterialBatchActions
                files={files.data.items}
                visible={visibleFiles}
                selected={selected}
                onSelectionChange={setSelected}
                onBusy={setBatchBusy}
              />
            )}
            {files.data &&
              (!files.data.items.length ? (
                <Empty
                  title="资料库还是空的"
                  description="上传学习资料，慢慢建立自己的知识库。"
                  action={false}
                />
              ) : (
                <div className="file-list">
                  <div className="file-list-head">
                    <span>资料名称</span>
                    <span>文件大小</span>
                    <span>添加时间</span>
                  </div>
                  {visibleFiles.map((f) => (
                    <div className="file-row library-file-row" key={f.fileId}>
                      <div className="file-name">
                        <input
                          type="checkbox"
                          aria-label={`选择资料：${f.name}`}
                          disabled={batchBusy}
                          checked={selected.has(f.fileId)}
                          onChange={(event) => {
                            const checked = event.target.checked;
                            setSelected((previous) => {
                              const next = new Set(previous);
                              if (checked) next.add(f.fileId);
                              else next.delete(f.fileId);
                              return next;
                            });
                          }}
                        />
                        <span className="file-icon">
                          <Icon name="book" />
                        </span>
                        <div>
                          <strong>{f.name || "未命名资料"}</strong>
                          <small>
                            {f.name.split(".").pop()?.toUpperCase() || "FILE"}
                          </small>
                        </div>
                      </div>
                      <span className="muted">{formatBytes(f.sizeBytes)}</span>
                      <span className="muted">
                        {new Date(f.createdAt).toLocaleDateString("zh-CN")}
                      </span>
                      <div
                        className="file-actions"
                        aria-label={`${f.name}的操作`}
                      >
                        <button
                          onClick={() => {
                            download.reset();
                            setPreview(f);
                          }}
                        >
                          查看
                        </button>
                        <button
                          disabled={download.isPending}
                          onClick={() => download.mutate(f)}
                        >
                          下载
                        </button>
                        <button
                          disabled={active || reindex.isPending || batchBusy}
                          onClick={() => reindex.mutate(f.fileId)}
                        >
                          重新索引
                        </button>
                        <button
                          disabled={batchBusy}
                          onClick={() => {
                            remove.reset();
                            setDeleting(f);
                          }}
                        >
                          删除
                        </button>
                      </div>
                    </div>
                  ))}
                  {!visibleFiles.length && (
                    <div className="empty-inline">
                      <p>没有找到匹配的资料。</p>
                      <button
                        type="button"
                        onClick={() => {
                          setFilter("");
                          setFileType("all");
                        }}
                      >
                        清除筛选
                      </button>
                    </div>
                  )}
                </div>
              ))}
          </section>
          {batchFiles && (
            <MaterialBatchUpload
              files={batchFiles}
              projectId={id}
              jobKey={jobKey}
              onBusy={setBatchUploading}
              onClose={() => {
                setBatchFiles(undefined);
                const recover = sessionStorage.getItem(jobKey);
                if (recover) {
                  setJob(recover);
                  setActive(true);
                }
              }}
            />
          )}
          {preview && (
            <MaterialPreview
              key={preview.fileId}
              file={preview}
              onClose={() => setPreview(undefined)}
            />
          )}
          {deleting && (
            <Dialog
              title="删除资料"
              onClose={() => {
                if (!remove.isPending) setDeleting(undefined);
              }}
            >
              <p>
                确认删除「{deleting.name}
                」？资料会从当前账号的资料库和检索结果中移除。
              </p>
              <ErrorNotice error={remove.error} />
              <div className="file-actions">
                <button
                  disabled={remove.isPending}
                  onClick={() => setDeleting(undefined)}
                >
                  取消
                </button>
                <button
                  className="primary"
                  disabled={remove.isPending}
                  onClick={() => remove.mutate(deleting.fileId)}
                >
                  {remove.isPending ? "正在删除…" : "确认删除"}
                </button>
              </div>
            </Dialog>
          )}
        </>
      )}
    </>
  );
}
function UploadStatus({
  value,
  pending,
  onCancel,
  onRetry,
}: {
  value: UploadDisplay;
  pending: boolean;
  onCancel: () => void;
  onRetry: () => void;
}) {
  const bytes = (value: number) =>
    value < 1024 ? `${value} B` : formatBytes(value);
  const percent = value.total
    ? Math.min(100, Math.floor((value.loaded / value.total) * 100))
    : undefined;
  const waiting = percent === 100 && value.state === "sending";
  const label =
    value.state === "saved"
      ? "上传已确认"
      : value.state === "cancelled"
        ? "上传已停止"
        : value.state === "failed"
          ? "上传未完成"
          : waiting
            ? "文件已传输，等待服务确认…"
            : "正在上传文件";
  return (
    <section className="upload-status" aria-label="文件上传进度">
      <div className="section-title spread">
        <div>
          <strong role="status">{label}</strong>
          <p className="muted small upload-filename">{value.name}</p>
        </div>
        <strong>
          {value.state === "saved"
            ? "100%"
            : percent == null
              ? "传输中"
              : `${percent}%`}
        </strong>
      </div>
      <progress
        aria-label="文件传输进度"
        max={100}
        value={value.state === "saved" ? 100 : percent}
      />
      <div className="upload-status-footer">
        <span className="muted small">
          {bytes(value.loaded)}
          {value.total ? ` / ${bytes(value.total)}` : " · 正在计算总量"}
          {__DEMO__ ? " · 演示进度" : ""}
        </span>
        {pending && (
          <button type="button" onClick={onCancel}>
            停止上传
          </button>
        )}
        {!pending && ["failed", "cancelled"].includes(value.state) && (
          <button type="button" onClick={onRetry}>
            重新上传
          </button>
        )}
      </div>
      {value.state === "saved" && (
        <p className="muted small">
          文件传输已完成，解析与索引状态会单独显示。
        </p>
      )}
      {value.message && (
        <p
          role={value.state === "failed" ? "alert" : "status"}
          className="muted small"
        >
          {value.message}
        </p>
      )}
    </section>
  );
}
function JobStatus({ id, done }: { id: string; done: () => void }) {
  const [job, setJob] = useState<JobProgress>();
  const [connection, setConnection] = useState<Connection>("connecting");
  const [error, setError] = useState<Error>();
  const onDone = useRef(done);
  onDone.current = done;
  useEffect(
    () =>
      watchJob(
        id,
        (data) => {
          setJob(data);
          if (["done", "failed", "cancelled"].includes(data.state))
            onDone.current();
        },
        setConnection,
        (e) => {
          setError(e);
          onDone.current();
        },
      ),
    [id],
  );
  const labels: Record<string, string> = {
    queued: "已排队，等待处理",
    running: "正在建立索引",
    done: "资料索引已完成",
    failed: "索引失败",
    cancelled: "任务已取消",
  };
  const doneCount = Number(job?.progress.done || 0),
    total = Number(job?.progress.total || 0);
  return (
    <div className="job-status" role="status">
      <strong>
        {job ? labels[job.state] || job.state : "正在连接任务进度…"}
      </strong>
      {connection === "reconnecting" && (
        <p>连接中断，正在重新连接并检查任务状态…</p>
      )}
      {total > 0 && (
        <progress aria-label="索引进度" max={total} value={doneCount} />
      )}
      <ErrorNotice
        error={error || (job?.error ? new Error(job.error) : null)}
      />
    </div>
  );
}
