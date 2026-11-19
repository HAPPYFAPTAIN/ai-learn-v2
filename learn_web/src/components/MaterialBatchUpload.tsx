import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { endpoints } from "../api";
import { watchJob } from "../api/jobs";
import { key } from "../query";
import { session } from "../session/store";
import Dialog from "./Dialog";
import { formatBytes } from "./ui";

type Entry = {
  file: File;
  state:
    | "pending"
    | "sending"
    | "indexing"
    | "done"
    | "failed"
    | "index-failed";
  loaded: number;
  total?: number;
  accepted?: boolean;
  message?: string;
};
const bytes = (value: number) =>
  value < 1024 ? `${value} B` : formatBytes(value);

// Keep at most one upload AND one indexing job in flight for this batch.
function awaitIndex(id: string, signal: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    let stop = () => {};
    let settled = false;
    const finish = (error?: Error) => {
      if (settled) return;
      settled = true;
      signal.removeEventListener("abort", cancel);
      stop();
      if (error) reject(error);
      else resolve();
    };
    const cancel = () => finish(new DOMException("Aborted", "AbortError"));
    if (signal.aborted) return cancel();
    signal.addEventListener("abort", cancel, { once: true });
    stop = watchJob(
      id,
      (job) => {
        if (job.state === "done") finish();
        else if (["failed", "cancelled"].includes(job.state))
          finish(new Error("文件已接收，但索引未完成；请在资料列表重试索引。"));
      },
      (connection) => {
        if (connection === "closed" && !settled)
          finish(new Error("索引进度连接已结束，请重新打开资料库确认状态。"));
      },
      finish,
    );
    if (settled) stop();
  });
}

export default function MaterialBatchUpload({
  files,
  projectId,
  jobKey,
  onBusy,
  onClose,
}: {
  files: File[];
  projectId: number;
  jobKey: string;
  onBusy: (busy: boolean) => void;
  onClose: () => void;
}) {
  const [entries, setEntries] = useState<Entry[]>(() =>
    files.map((file) => ({
      file,
      state: "pending",
      loaded: 0,
      total: file.size,
    })),
  );
  const current = useRef(entries);
  const alive = useRef(false);
  const running = useRef(false);
  const stopping = useRef(false);
  const controller = useRef<AbortController | undefined>(undefined);
  const owner = useRef(session.get().owner);
  const [busy, setBusy] = useState(false);
  const [stopped, setStopped] = useState(false);
  const [started, setStarted] = useState(false);
  const client = useQueryClient();
  const validSession = () =>
    alive.current &&
    session.get().status === "ready" &&
    session.get().owner === owner.current;
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
      stopping.current = true;
      controller.current?.abort();
    };
  }, []);
  function update(index: number, value: Partial<Entry>) {
    if (!validSession()) return;
    current.current = current.current.map((entry, i) =>
      i === index ? { ...entry, ...value } : entry,
    );
    setEntries(current.current);
  }
  async function start() {
    if (running.current || !validSession()) return;
    running.current = true;
    stopping.current = false;
    setStopped(false);
    setStarted(true);
    setBusy(true);
    onBusy(true);
    const abort = new AbortController();
    controller.current = abort;
    const off = session.onStop(() => abort.abort());
    try {
      for (let i = 0; i < current.current.length; i++) {
        const entry = current.current[i];
        if (stopping.current || abort.signal.aborted || !validSession()) break;
        if (entry.accepted) continue;
        update(i, { state: "sending", loaded: 0, message: undefined });
        try {
          const result = await endpoints.upload(
            projectId,
            entry.file,
            (progress) => update(i, progress),
            abort.signal,
          );
          if (!validSession() || abort.signal.aborted) break;
          update(i, {
            accepted: true,
            loaded: current.current[i].total || entry.file.size,
            state: result.jobId ? "indexing" : "done",
          });
          void client.invalidateQueries({
            queryKey: key("materials", projectId),
          });
          if (result.jobId) {
            sessionStorage.setItem(jobKey, result.jobId);
            await awaitIndex(result.jobId, abort.signal);
            if (!validSession() || abort.signal.aborted) break;
            if (sessionStorage.getItem(jobKey) === result.jobId)
              sessionStorage.removeItem(jobKey);
          }
          update(i, { state: "done" });
        } catch (cause) {
          if (!validSession() || abort.signal.aborted) break;
          const error =
            cause instanceof Error ? cause : new Error("上传未完成");
          update(i, {
            state: current.current[i].accepted ? "index-failed" : "failed",
            message:
              error.name === "AbortError"
                ? "等待超时或连接中断，文件可能已接收，请先核对资料列表。"
                : error.message,
          });
          // Do not amplify network, quota or indexing failures with more work.
          break;
        }
      }
    } finally {
      off();
      running.current = false;
      if (validSession()) {
        setBusy(false);
        onBusy(false);
        void client.invalidateQueries({
          queryKey: key("materials", projectId),
        });
      }
    }
  }
  const accepted = entries.filter((entry) => entry.accepted).length;
  const completed = entries.filter((entry) => entry.state === "done").length;
  const remaining = entries.filter((entry) => !entry.accepted).length;
  const unresolvedIndex = entries.some(
    (entry) => entry.state === "index-failed",
  );
  const labels: Record<Entry["state"], string> = {
    pending: "等待上传",
    sending: "正在上传",
    indexing: "已接收，正在索引",
    done: "已完成",
    failed: "上传未完成",
    "index-failed": "已接收，索引待确认",
  };
  return (
    <Dialog title="批量上传资料" dismissible={!busy} onClose={onClose}>
      <p className="muted small">
        共 {files.length} 份，
        {bytes(files.reduce((sum, file) => sum + file.size, 0))}。
        每次处理一份，索引结束后再上传下一份。离开页面会停止后续处理，已接收文件继续保留。
      </p>
      <ol className="material-batch-list batch-upload-list">
        {entries.map((entry, index) => (
          <li key={index}>
            <strong>{entry.file.name}</strong>
            <span className="muted small">
              {bytes(entry.file.size)} · {labels[entry.state]}
            </span>
            {entry.state === "sending" && (
              <>
                <progress
                  aria-label={`${entry.file.name}传输进度`}
                  max={100}
                  value={
                    entry.total
                      ? Math.min(
                          100,
                          Math.floor((entry.loaded / entry.total) * 100),
                        )
                      : undefined
                  }
                />
                <span className="muted small">
                  {entry.total && entry.loaded >= entry.total
                    ? "文件已传输，等待服务确认…"
                    : "正在发送文件…"}
                </span>
              </>
            )}
            {entry.message && (
              <span className="small batch-failure">{entry.message}</span>
            )}
          </li>
        ))}
      </ol>
      <p role="status">
        已接收 {accepted} / {files.length} 份，已完成 {completed} 份。
        {stopped && busy ? "正在等待当前文件处理结束，再停止后续上传。" : ""}
      </p>
      {started && !busy && remaining > 0 && (
        <p className="muted small">
          剩余 {remaining}{" "}
          份未确认接收。若发生网络中断，请先核对资料列表，再手动重试；已确认接收的文件不会重复上传。
        </p>
      )}
      {unresolvedIndex && (
        <p className="muted small">
          请先关闭此窗口，在资料列表核对或重试索引，再上传剩余文件。
        </p>
      )}
      <div className="content-actions">
        {busy ? (
          <button
            type="button"
            disabled={stopped}
            onClick={() => {
              stopping.current = true;
              setStopped(true);
            }}
          >
            停止后续上传
          </button>
        ) : (
          <>
            <button type="button" onClick={onClose}>
              {started ? "完成" : "取消"}
            </button>
            {remaining > 0 && !unresolvedIndex && (
              <button
                type="button"
                className="primary"
                onClick={() => void start()}
              >
                {started
                  ? `核对后重试未接收的 ${remaining} 份`
                  : `开始上传 ${remaining} 份资料`}
              </button>
            )}
          </>
        )}
      </div>
    </Dialog>
  );
}
