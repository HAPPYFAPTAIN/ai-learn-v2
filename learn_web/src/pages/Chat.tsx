import { jobFailure } from "../api/jobError";
import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { endpoints, type JobProgress } from "../api";
import { key } from "../query";
import { generationStorageKey } from "../api/generation";
import { watchJob } from "../api/jobs";
import { useProject } from "../components/ProjectContext";
import MaterialPreview from "../components/MaterialPreview";
import { useDraftGuard } from "../components/DraftProtection";
import WriteRecovery, { uncertainWrite } from "../components/WriteRecovery";
import {
  AutoTextarea,
  ErrorNotice,
  Icon,
  PageHeading,
  QueryState,
} from "../components/ui";
const Markdown = lazy(() => import("../components/Markdown"));

export default function Chat() {
  const { id } = useProject();
  return (
    <>
      <PageHeading
        title="知识问答"
        description="结合课程与参考资料，把不理解的地方问清楚。"
      />
      <ChatRoom key={id} id={id} />
    </>
  );
}

export function ChatRoom({
  id,
  mode = "chat",
}: {
  id: number;
  mode?: "chat" | "coach";
}) {
  const coach = mode === "coach";
  const client = useQueryClient();
  const [params] = useSearchParams();
  const chapter = Number(params.get("chapter")) || undefined;
  const history = useQuery({
    queryKey: key(`conversation-${mode}`, id),
    queryFn: ({ signal }) => endpoints.conversation(id, signal, mode),
    enabled: !!id,
  });
  const files = useQuery({
    queryKey: key("materials", id),
    queryFn: ({ signal }) => endpoints.materials(id, signal),
    enabled: !!id,
  });
  const [draft, setDraft] = useState("");
  const [useMaterials, setUseMaterials] = useState(true);
  const [materialIds, setMaterialIds] = useState<string[]>([]);
  const [preview, setPreview] = useState<{ fileId: string; name: string }>();
  const storageKey = generationStorageKey(id, mode);
  const [jobId, setJobId] = useState(
    () => sessionStorage.getItem(storageKey) || "",
  );
  const [job, setJob] = useState<JobProgress>();
  const [watchError, setWatchError] = useState<Error>();
  const [reconnecting, setReconnecting] = useState(false);
  const requestId = useRef(crypto.randomUUID());
  const submittedContent = useRef("");
  const activeId = jobId || history.data?.activeJob?.jobId || "";
  useEffect(() => {
    if (!activeId) return;
    sessionStorage.setItem(storageKey, activeId);
    return watchJob(
      activeId,
      (next) => {
        setJob(next);
        if (["done", "failed", "cancelled"].includes(next.state)) {
          sessionStorage.removeItem(storageKey);
          void client.invalidateQueries({
            queryKey: key(`conversation-${mode}`, id),
          });
        }
      },
      (state) => setReconnecting(state === "reconnecting"),
      (e) => {
        setWatchError(e);
        sessionStorage.removeItem(storageKey);
      },
    );
  }, [activeId, id, client, storageKey, mode]);
  const send = useMutation({
    mutationFn: () => {
      const signature = JSON.stringify({
        content: draft.trim(),
        chapter,
        useMaterials,
        materialIds,
        mode,
      });
      if (submittedContent.current !== signature)
        requestId.current = crypto.randomUUID();
      submittedContent.current = signature;
      return endpoints.ask(id, {
        content: draft.trim(),
        requestId: requestId.current,
        nodeId: chapter,
        useMaterials,
        materialIds,
        mode,
      });
    },
    onSuccess: (result) => {
      setJob(undefined);
      setWatchError(undefined);
      setJobId(result.jobId);
      setDraft("");
      requestId.current = crypto.randomUUID();
      sessionStorage.setItem(storageKey, result.jobId);
      void client.invalidateQueries({
        queryKey: key(`conversation-${mode}`, id),
      });
    },
    onError: () => {
      setJobId("");
      setJob(undefined);
      void history.refetch();
    },
  });
  useDraftGuard(coach ? "教练反馈" : "问答输入", !!draft, send.isPending);
  const pending =
    send.isPending ||
    (!!activeId &&
      !watchError &&
      (!job ||
        job.jobId !== activeId ||
        ["queued", "running"].includes(job.state)));
  const messages = history.data?.messages || [];
  return (
    <section className="panel chat-panel">
      {!!id && <QueryState query={history} />}
      <div className="chat-log" aria-live="polite" aria-busy={pending}>
        {(!id || history.data) && !messages.length && !pending && (
          <div className="chat-welcome">
            <div className="empty-icon">
              <Icon name="chat" size={28} />
            </div>
            <h2>
              {coach ? "从一个小步骤开始练习" : "今天，有什么想弄明白的？"}
            </h2>
            <p className="muted">
              {coach
                ? "告诉教练你的起点，完成一步后反馈结果，再继续下一步。"
                : "试着问一个概念，或者聊聊你卡住的地方。"}
            </p>
            <div className="suggestions">
              {(coach
                ? [
                    "根据当前章节带我做一个小练习",
                    "这一步遇到报错，我应该怎么排查？",
                    "请帮我检查这一步的完成标准",
                  ]
                : [
                    "用一个例子解释这个概念",
                    "帮我梳理今天的学习重点",
                    "我该如何检验自己是否理解了？",
                  ]
              ).map((t) => (
                <button key={t} disabled={!id} onClick={() => setDraft(t)}>
                  {t}
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map((m, i) => (
          <div className={`message ${m.role}`} key={i}>
            <span className="message-role">
              {m.role === "user" ? "我" : coach ? "练习教练" : "学习助教"}
            </span>
            <Suspense fallback={<p>{m.content}</p>}>
              <Markdown>{m.content}</Markdown>
            </Suspense>
            {m.truncated && (
              <p role="status" className="muted">
                回答可能不完整
              </p>
            )}
            {!!m.references.length && (
              <div className="file-actions" aria-label="回答参考资料">
                {m.references.map((ref, j) => (
                  <button key={j} onClick={() => setPreview(ref)}>
                    [{ref.label}] {ref.name}
                  </button>
                ))}
              </div>
            )}
          </div>
        ))}
        {pending && (
          <div className="job-status" role="status">
            <strong>
              {job?.state === "running"
                ? "助教正在结合课程与资料回答…"
                : "问题已提交，正在等待助教回答…"}
            </strong>
            {!!history.data?.pendingQuestion && (
              <p>{history.data.pendingQuestion}</p>
            )}
            {reconnecting && (
              <p>连接中断，正在恢复任务状态；刷新后会继续查看同一问题。</p>
            )}
          </div>
        )}
        {job?.state === "done" && job.progress.degradedSearch === true && (
          <p className="muted small">
            本次向量检索暂不可用，已使用文字检索查找资料。
          </p>
        )}
        <ErrorNotice error={watchError || jobFailure(job)} />
      </div>
      <form
        className="chat-composer"
        onSubmit={(e) => {
          e.preventDefault();
          if (id && draft.trim() && !pending && !uncertainWrite(send.error))
            send.mutate();
        }}
      >
        {!id && (
          <p className="muted small">暂无学习计划，关联课程的问答暂不可用。</p>
        )}
        <label htmlFor="question" className="sr-only">
          {coach ? "向教练反馈" : "向助教提问"}
        </label>
        <AutoTextarea
          id="question"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="写下你的问题…"
          maxLength={16000}
          disabled={pending || !history.data}
        />
        <label className="inline-label">
          <input
            type="checkbox"
            checked={useMaterials}
            disabled={pending || !id}
            onChange={(e) => setUseMaterials(e.target.checked)}
          />
          结合资料库回答
        </label>
        {chapter && (
          <p className="muted small">本次提问将带上当前章节的学习内容。</p>
        )}
        {useMaterials && !!files.data?.items.length && (
          <details className="chat-materials">
            <summary>选择参考资料（默认全部）</summary>
            <p className="muted small">
              不勾选时检索全部资料；也可以指定最多 20 份。
            </p>
            {files.data.items.map((f) => (
              <label key={f.fileId} className="inline-label">
                <input
                  type="checkbox"
                  checked={materialIds.includes(f.fileId)}
                  disabled={
                    pending ||
                    (!materialIds.includes(f.fileId) &&
                      materialIds.length >= 20)
                  }
                  onChange={(e) =>
                    setMaterialIds((ids) =>
                      e.target.checked
                        ? [...ids, f.fileId]
                        : ids.filter((i) => i !== f.fileId),
                    )
                  }
                />
                {f.name}
              </label>
            ))}
          </details>
        )}
        <ErrorNotice error={useMaterials ? files.error : null} />
        <div className="form-footer">
          <span className="muted small">
            {coach
              ? "由你自行操作并反馈，教练不会自动控制电脑或标记掌握。"
              : "回答仅供学习参考，请结合资料核实。"}
          </span>
          <button
            className="primary"
            disabled={
              !draft.trim() ||
              pending ||
              !history.data ||
              uncertainWrite(send.error)
            }
          >
            发送 <Icon name="arrow" />
          </button>
        </div>
        <ErrorNotice error={send.error} />
        <WriteRecovery
          error={send.error}
          onCheck={async () => {
            const fresh = await history.refetch();
            if (fresh.error) throw fresh.error;
            return fresh.data?.activeJob
              ? "已找到进行中的问答任务，请等待结果，不必再次发送。"
              : "已更新问答历史，请核对本次问题和回答。同一内容重发仍使用原请求编号。";
          }}
          onAllowRetry={() => send.reset()}
        />
      </form>
      {preview && (
        <MaterialPreview file={preview} onClose={() => setPreview(undefined)} />
      )}
    </section>
  );
}
