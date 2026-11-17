import {
  useEffect,
  useRef,
  useState,
  type Dispatch,
  type SetStateAction,
} from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ApiError, endpoints } from "../api";
import type { Model } from "../api/client";
import { session } from "../session/store";
import Dialog from "./Dialog";
import { formatBytes } from "./ui";

type Material = Model<"MaterialOut">;
type Result = { state: "deleted" | "failed" | "skipped"; message?: string };

export default function MaterialBatchActions({
  files,
  visible,
  selected,
  onSelectionChange,
  onBusy,
}: {
  files: Material[];
  visible: Material[];
  selected: Set<string>;
  onSelectionChange: Dispatch<SetStateAction<Set<string>>>;
  onBusy: (busy: boolean) => void;
}) {
  const client = useQueryClient();
  const all = useRef<HTMLInputElement>(null);
  const mounted = useRef(false);
  const running = useRef(false);
  const stop = useRef(false);
  const [batch, setBatch] = useState<Material[]>();
  const [results, setResults] = useState<Record<string, Result>>({});
  const [busy, setBusy] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [processed, setProcessed] = useState(0);
  const [total, setTotal] = useState(0);
  const chosen = files.filter((file) => selected.has(file.fileId));
  const visibleChosen = visible.filter((file) =>
    selected.has(file.fileId),
  ).length;
  const allVisible = !!visible.length && visibleChosen === visible.length;
  const tooMany = chosen.length > 50;
  const deleted =
    batch?.filter((file) => results[file.fileId]?.state === "deleted").length ||
    0;
  const remaining =
    batch?.filter((file) => results[file.fileId]?.state !== "deleted") || [];
  const finished = !!batch && Object.keys(results).length === batch.length;

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      stop.current = true;
    };
  }, []);
  useEffect(() => {
    if (all.current)
      all.current.indeterminate = visibleChosen > 0 && !allVisible;
  }, [visibleChosen, allVisible]);

  function selectVisible() {
    onSelectionChange((previous) => {
      const next = new Set(previous);
      visible.forEach((file) => {
        if (allVisible) next.delete(file.fileId);
        else next.add(file.fileId);
      });
      return next;
    });
  }

  // Serial requests reuse the current DELETE contract, with no paid/model work.
  // Do not retry automatically: a disconnected delete may already have committed.
  async function remove(targets: Material[]) {
    if (running.current || !targets.length) return;
    running.current = true;
    stop.current = false;
    setStopping(false);
    setBusy(true);
    onBusy(true);
    setProcessed(0);
    setTotal(targets.length);
    const owner = session.get().owner;
    const materialKey = [owner, "materials"];
    const removed = new Set<string>();
    const updates: Record<string, Result> = {};
    try {
      for (let i = 0; i < targets.length; i++) {
        const file = targets[i];
        if (
          stop.current ||
          !mounted.current ||
          session.get().status !== "ready" ||
          session.get().owner !== owner
        ) {
          targets.slice(i).forEach((item) => {
            updates[item.fileId] = {
              state: "skipped",
              message: "尚未处理，可稍后重试",
            };
          });
          break;
        }
        try {
          await endpoints.deleteMaterial(file.fileId);
          updates[file.fileId] = { state: "deleted" };
          removed.add(file.fileId);
        } catch (error) {
          if (error instanceof ApiError && error.status === 404) {
            updates[file.fileId] = {
              state: "deleted",
              message: "资料已不存在",
            };
            removed.add(file.fileId);
          } else {
            updates[file.fileId] = {
              state: "failed",
              message:
                error instanceof Error && error.name !== "AbortError"
                  ? error.message
                  : "未确认删除结果，请稍后重试",
            };
            if (
              !(error instanceof ApiError) ||
              error.status === 429 ||
              error.status >= 500
            )
              stop.current = true;
          }
        }
        if (mounted.current) {
          setResults((previous) => ({ ...previous, ...updates }));
          setProcessed(i + 1);
        }
      }
    } finally {
      running.current = false;
      if (
        mounted.current &&
        session.get().status === "ready" &&
        session.get().owner === owner
      ) {
        setResults((previous) => ({ ...previous, ...updates }));
        await client.cancelQueries({ queryKey: materialKey });
        if (mounted.current && session.get().owner === owner) {
          client.setQueriesData<{ items: Material[] }>(
            { queryKey: materialKey },
            (previous) =>
              previous && {
                ...previous,
                items: previous.items.filter(
                  (file) => !removed.has(file.fileId),
                ),
              },
          );
          removed.forEach((fileId) =>
            client.removeQueries({
              queryKey: [owner, "material-preview", fileId],
            }),
          );
          onSelectionChange(
            (previous) =>
              new Set([...previous].filter((fileId) => !removed.has(fileId))),
          );
          void client.invalidateQueries({ queryKey: materialKey });
        }
        setBusy(false);
        onBusy(false);
      }
    }
  }

  return (
    <>
      {!!files.length && (
        <div className="material-batch-bar" aria-label="资料批量操作">
          <label className="material-select-all">
            <input
              ref={all}
              type="checkbox"
              checked={allVisible}
              disabled={busy || !visible.length}
              onChange={selectVisible}
            />
            选择当前结果
          </label>
          <span className="muted small">
            已选 {chosen.length} 份
            {chosen.length
              ? ` · ${formatBytes(chosen.reduce((sum, file) => sum + file.sizeBytes, 0))}`
              : ""}
          </span>
          <div className="content-actions">
            <button
              type="button"
              disabled={!chosen.length || busy}
              onClick={() => onSelectionChange(new Set())}
            >
              清除选择
            </button>
            <button
              type="button"
              disabled={!chosen.length || tooMany || busy}
              onClick={() => {
                setBatch([...chosen]);
                setResults({});
              }}
            >
              批量删除
            </button>
          </div>
          {tooMany && (
            <p className="muted small">每批最多删除 50 份资料，请减少选择。</p>
          )}
          {chosen.length > visibleChosen && (
            <p className="muted small">
              已选资料中有 {chosen.length - visibleChosen}{" "}
              份不在当前筛选结果中，删除前可核对完整清单。
            </p>
          )}
        </div>
      )}
      {batch && (
        <Dialog
          title="批量删除资料"
          dismissible={!busy}
          onClose={() => setBatch(undefined)}
        >
          <p>
            以下 {batch.length}{" "}
            份资料将从当前账号的资料库及检索结果中移除。删除后无法从本页面撤回，请先确认清单。
          </p>
          <ol className="material-batch-list">
            {batch.map((file) => (
              <li key={file.fileId}>
                <span>{file.name}</span>
                {results[file.fileId] && (
                  <span
                    className={`small ${results[file.fileId].state === "failed" ? "batch-failure" : "muted"}`}
                  >
                    {results[file.fileId].state === "deleted"
                      ? "已删除"
                      : results[file.fileId].state === "failed"
                        ? "删除未完成"
                        : "未处理"}
                    {results[file.fileId].message &&
                      `：${results[file.fileId].message}`}
                  </span>
                )}
              </li>
            ))}
          </ol>
          {busy && (
            <div role="status">
              <p>
                {stopping
                  ? "正在停止后续删除，等待当前文件返回结果…"
                  : `正在删除：${processed} / ${total}`}
              </p>
              <progress
                aria-label="批量删除进度"
                value={processed}
                max={total || 1}
              />
            </div>
          )}
          {finished && !busy && (
            <p role="status">
              已删除 {deleted} 份资料
              {remaining.length
                ? `，${remaining.length} 份未完成。可重试未完成的资料。`
                : "。"}
            </p>
          )}
          <div className="content-actions">
            {busy ? (
              <button
                type="button"
                disabled={stopping}
                onClick={() => {
                  stop.current = true;
                  setStopping(true);
                }}
              >
                停止后续删除
              </button>
            ) : (
              <>
                <button type="button" onClick={() => setBatch(undefined)}>
                  {finished ? "完成" : "取消"}
                </button>
                {remaining.length > 0 && (
                  <button
                    type="button"
                    className="primary"
                    onClick={() => void remove(remaining)}
                  >
                    {finished
                      ? `重试未完成的 ${remaining.length} 份`
                      : `确认删除 ${remaining.length} 份资料`}
                  </button>
                )}
              </>
            )}
          </div>
        </Dialog>
      )}
    </>
  );
}
