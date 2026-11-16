import { SearchField } from "../components/fields";
import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { endpoints, type JobProgress } from "../api";
import { key } from "../query";
import { watchJob, type Connection } from "../api/jobs";
import { session } from "../session/store";
import { useProject } from "../components/ProjectContext";
import Dialog from "../components/Dialog";
import MaterialPreview from "../components/MaterialPreview";
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
  const client = useQueryClient();
  const jobKey = `learn.v2.job.${session.get().owner}.${id}`;
  const savedJob = sessionStorage.getItem(jobKey) || "";
  const [filter, setFilter] = useState("");
  const [validation, setValidation] = useState("");
  const [job, setJob] = useState(savedJob);
  const [active, setActive] = useState(!!savedJob);
  const input = useRef<HTMLInputElement>(null);
  const [preview, setPreview] = useState<{ fileId: string; name: string }>();
  const [deleting, setDeleting] = useState<{ fileId: string; name: string }>();
  const remove = useMutation({
    mutationFn: (fileId: string) => endpoints.deleteMaterial(fileId),
    onSuccess: (_, fileId) => {
      setDeleting(undefined);
      client.removeQueries({ queryKey: key("material-preview", fileId) });
      void client.invalidateQueries({ queryKey: key("materials") });
    },
  });
  const download = useMutation({
    mutationFn: (file: { fileId: string; name: string }) =>
      endpoints.downloadMaterial(file.fileId),
    onSuccess: (blob, file) => {
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = file.name;
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 30000);
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
  const upload = useMutation({
    mutationFn: (file: File) => endpoints.upload(id, file),
    onSuccess: (r) => {
      setJob(r.jobId || "");
      setActive(!!r.jobId);
      if (r.jobId) sessionStorage.setItem(jobKey, r.jobId);
      void client.invalidateQueries({ queryKey: key("materials", id) });
    },
  });
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
                  DOCX，单个文件最多 50 MB。
                </p>
              </div>
              <button
                className="primary"
                disabled={upload.isPending || active}
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
              accept=".txt,.md,.pdf,.docx"
              aria-label="选择上传资料"
              disabled={upload.isPending || active}
              onChange={(e) => {
                const file = e.target.files?.[0];
                e.target.value = "";
                if (!file) return;
                if (!file.size || file.size > 50 * 1024 * 1024) {
                  setValidation("请选择非空且不超过 50 MB 的文件。");
                  return;
                }
                setValidation("");
                upload.mutate(file);
              }}
            />
            <ErrorNotice
              error={validation ? new Error(validation) : upload.error}
            />
            <ErrorNotice error={download.error || reindex.error} />
            {job && <JobStatus id={job} done={done} />}
            <div className="library-toolbar">
              <SearchField
                label="搜索资料"
                placeholder="搜索资料名称"
                value={filter}
                onChange={setFilter}
              />
              <span className="muted small">
                {files.data?.items.length || 0} 份资料
              </span>
            </div>
            <QueryState query={files} />
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
                  {files.data.items
                    .filter((f) =>
                      f.name.toLowerCase().includes(filter.toLowerCase()),
                    )
                    .map((f) => (
                      <div className="file-row library-file-row" key={f.fileId}>
                        <div className="file-name">
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
                        <span className="muted">
                          {formatBytes(f.sizeBytes)}
                        </span>
                        <span className="muted">
                          {new Date(f.createdAt).toLocaleDateString("zh-CN")}
                        </span>
                        <div
                          className="file-actions"
                          aria-label={`${f.name}的操作`}
                        >
                          <button onClick={() => setPreview(f)}>查看</button>
                          <button
                            disabled={download.isPending}
                            onClick={() => download.mutate(f)}
                          >
                            下载
                          </button>
                          <button
                            disabled={active || reindex.isPending}
                            onClick={() => reindex.mutate(f.fileId)}
                          >
                            重新索引
                          </button>
                          <button
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
                  {!files.data.items.some((f) =>
                    f.name.toLowerCase().includes(filter.toLowerCase()),
                  ) && <p className="empty-inline">没有找到匹配的资料。</p>}
                </div>
              ))}
          </section>
          {preview && (
            <MaterialPreview
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
