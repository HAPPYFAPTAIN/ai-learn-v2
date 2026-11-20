import { jobFailure } from "../api/jobError";
import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { useLocation, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { endpoints, type JobProgress } from "../api";
import type { Model } from "../api/client";
import { key } from "../query";
import { watchJob } from "../api/jobs";
import { useProject } from "./ProjectContext";
import { AutoTextarea, ErrorNotice, Icon, QueryState } from "./ui";
import { uncertainWrite } from "./WriteRecovery";
import Dialog from "./Dialog";
import type { AssistantPageContext } from "./AssistantContext";
const Markdown = lazy(() => import("./Markdown"));
const pageNames: Record<string, Model<"AssistantContext">["page"]> = {
  "/": "学习首页",
  "/roadmap": "学习路线",
  "/study": "学习工作台",
  "/review": "间隔复习",
  "/quiz": "查漏测验",
  "/dashboard": "学习看板",
  "/chat": "知识问答",
  "/library": "资料库",
  "/tools": "学习工具",
  "/models": "模型设置",
};
export default function GlobalAssistant({
  context,
}: {
  context: AssistantPageContext;
}) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const [jobId, setJobId] = useState("");
  const [job, setJob] = useState<JobProgress>();
  const [watchError, setWatchError] = useState<Error>();
  const [reconnecting, setReconnecting] = useState(false);
  const [confirm, setConfirm] = useState<"clear" | "append">();
  const [notice, setNotice] = useState("");
  const [params] = useSearchParams();
  const { pathname } = useLocation();
  const { id, project } = useProject();
  const client = useQueryClient();
  const launcher = useRef<HTMLButtonElement>(null);
  const input = useRef<HTMLFormElement>(null);
  const log = useRef<HTMLDivElement>(null);
  const request = useRef<{ signature: string; id: string } | undefined>(
    undefined,
  );
  const page = pageNames[pathname] || "学习首页";
  const nodeId =
    pathname === "/study"
      ? Number(params.get("chapter")) || undefined
      : undefined;
  const nodes = useQuery({
    queryKey: key("nodes", id),
    queryFn: ({ signal }) => endpoints.nodes(id, signal),
    enabled: open && !!nodeId && !!id,
  });
  const node = nodes.data?.items.find((n) => n.id === nodeId);
  const history = useQuery({
    queryKey: key("assistant"),
    queryFn: ({ signal }) => endpoints.assistantHistory(signal),
    enabled: open || !!jobId,
  });
  const activeId = jobId || history.data?.activeJob?.jobId || "";
  const busy =
    !!activeId &&
    !watchError &&
    (!job ||
      job.jobId !== activeId ||
      ["queued", "running"].includes(job.state));
  const send = useMutation({
    mutationFn: () => {
      const body = {
        content: draft.trim(),
        projectId: id || undefined,
        nodeId,
        context: {
          page,
          cardId: context.cardId,
          questionId: context.questionId,
        },
      };
      const signature = JSON.stringify(body);
      if (request.current?.signature !== signature)
        request.current = { signature, id: crypto.randomUUID() };
      return endpoints.askAssistant({
        ...body,
        requestId: request.current!.id,
      });
    },
    onSuccess: (result) => {
      setDraft("");
      setWatchError(undefined);
      setJob(undefined);
      setJobId(result.jobId);
      request.current = undefined;
      void history.refetch();
    },
    onError: () => {
      void history.refetch();
    },
  });
  const pending = busy || send.isPending;
  useEffect(() => {
    if (!activeId) return;
    return watchJob(
      activeId,
      (next) => {
        setJob(next);
        if (["done", "failed", "cancelled"].includes(next.state))
          void history.refetch();
      },
      (state) => setReconnecting(state === "reconnecting"),
      setWatchError,
    );
  }, [activeId, client]);
  useEffect(() => {
    if (open) input.current?.querySelector("textarea")?.focus();
  }, [open]);
  useEffect(() => {
    log.current?.scrollTo({ top: log.current.scrollHeight });
  }, [history.data, pending, open]);
  useEffect(() => {
    if (!open) return;
    const close = (event: KeyboardEvent) => {
      if (
        event.key === "Escape" &&
        !document.querySelector('[aria-modal="true"]')
      ) {
        setOpen(false);
        launcher.current?.focus();
      }
    };
    document.addEventListener("keydown", close);
    return () => document.removeEventListener("keydown", close);
  }, [open]);
  useEffect(() => {
    if (!draft) return;
    const beforeUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", beforeUnload);
    return () => window.removeEventListener("beforeunload", beforeUnload);
  }, [draft, open]);
  const clear = useMutation({
    mutationFn: endpoints.clearAssistant,
    onSuccess: () => {
      setJobId("");
      setJob(undefined);
      setNotice("对话已清空");
      setConfirm(undefined);
      void history.refetch();
    },
  });
  const append = useMutation({
    mutationFn: () =>
      endpoints.appendAssistant({
        nodeId: node!.id,
        expectedVersion: node!.contentVersion,
      }),
    onSuccess: () => {
      setConfirm(undefined);
      setNotice("最近回复已加入当前课程");
      void client.invalidateQueries({ queryKey: key("nodes", id) });
    },
  });
  const messages = history.data?.messages || [];
  const title =
    node?.title ||
    context.title ||
    project?.title ||
    (page === "学习工作台" ? "还没有选择课程" : "学习规划、理解与复习");
  const suggestions =
    page === "学习工作台"
      ? [
          "用简单的例子解释这一节",
          "这一节最需要记住什么？",
          "出一个问题检查我的理解",
        ]
      : page === "间隔复习"
        ? [
            "给我一点回忆提示",
            "这张卡容易和什么概念混淆？",
            "帮我用一句话记住它",
          ]
        : page === "查漏测验"
          ? [
              "给我一点解题提示",
              "这道题在考哪个知识点？",
              "我答完后，帮我分析思路",
            ]
          : [
              "帮我拆解一个学习目标",
              "怎样安排今天的学习？",
              "帮我检查自己的理解",
            ];
  function submit() {
    if (draft.trim() && !pending && !uncertainWrite(send.error)) {
      setNotice("");
      send.mutate();
    }
  }
  return (
    <>
      <button
        ref={launcher}
        className="assistant-launcher"
        aria-label={open ? "收起以太小助" : "打开以太小助"}
        aria-expanded={open}
        aria-controls="global-assistant"
        onClick={() => setOpen((v) => !v)}
      >
        <Icon name="chat" size={25} />
        {pending && <span className="assistant-busy" />}
      </button>
      <aside
        id="global-assistant"
        className="assistant-panel"
        aria-label="以太小助"
        role="dialog"
        aria-modal="false"
        hidden={!open}
      >
        <header className="assistant-header">
          <h2>
            <Icon name="chat" /> 以太小助
          </h2>
          <button
            className="icon-button"
            aria-label="关闭以太小助"
            onClick={() => {
              setOpen(false);
              launcher.current?.focus();
            }}
          >
            ×
          </button>
        </header>
        <div className="assistant-log" ref={log} aria-live="polite">
          <div className="assistant-context">
            <span className="muted small">
              {page}
              {nodeId
                ? " · 当前课程"
                : context.cardId
                  ? " · 当前卡片"
                  : context.questionId
                    ? " · 当前题目"
                    : ""}
            </span>
            <strong>{title}</strong>
          </div>
          {!messages.length && (
            <div className="assistant-suggestions">
              {suggestions.map((text) => (
                <button
                  key={text}
                  onClick={() => {
                    setDraft(text);
                    input.current?.querySelector("textarea")?.focus();
                  }}
                >
                  {text}
                </button>
              ))}
            </div>
          )}
          {open && <QueryState query={history} />}
          {messages.map((m, i) => (
            <div className={`message ${m.role}`} key={i}>
              <span className="message-role">
                {m.role === "user" ? "我" : "以太小助"}
              </span>
              <Suspense fallback={<p>{m.content}</p>}>
                <Markdown>{m.content}</Markdown>
              </Suspense>
              {m.truncated && <p className="muted">回答可能不完整</p>}
            </div>
          ))}
          {pending && (
            <p role="status">
              {job?.state === "running"
                ? "小助正在思考…"
                : "问题已提交，等待回复…"}
              {reconnecting && " 正在恢复任务连接"}
            </p>
          )}
          <ErrorNotice error={send.error || watchError || jobFailure(job)} />
          {uncertainWrite(send.error) && (
            <button
              onClick={() => {
                send.reset();
                void history.refetch();
              }}
            >
              检查任务状态后重试
            </button>
          )}
          {notice && <p role="status">{notice}</p>}
        </div>
        <form
          className="assistant-composer"
          onSubmit={(e) => {
            e.preventDefault();
            submit();
          }}
          ref={input}
        >
          <AutoTextarea
            aria-label="向以太小助提问"
            placeholder="回车发送 · Shift 换行"
            maxLength={16000}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (
                e.key === "Enter" &&
                !e.shiftKey &&
                !e.nativeEvent.isComposing
              ) {
                e.preventDefault();
                submit();
              }
            }}
          />
          <div className="assistant-actions">
            <button
              type="button"
              disabled={pending || !messages.length}
              onClick={() => setConfirm("clear")}
            >
              清空对话
            </button>
            <button
              type="button"
              disabled={
                !node ||
                pending ||
                !messages.some((m) => m.role === "assistant")
              }
              onClick={() => setConfirm("append")}
            >
              加入课程
            </button>
            <button
              className="primary"
              disabled={pending || !draft.trim() || uncertainWrite(send.error)}
            >
              发送
            </button>
          </div>
          <p className="muted small">使用当前主模型，发送后消耗模型额度。</p>
        </form>
      </aside>
      {confirm && (
        <Dialog
          title={
            confirm === "clear" ? "清空小助对话？" : "将最近回复加入课程？"
          }
          onClose={() => {
            setConfirm(undefined);
            clear.reset();
            append.reset();
          }}
          dismissible={!clear.isPending && !append.isPending}
        >
          <p>
            {confirm === "clear"
              ? "此操作清除本账号的小助对话，无法撤销。"
              : `追加到「${node?.title || "当前课程"}」末尾，保留已有正文。`}
          </p>
          <ErrorNotice error={clear.error || append.error} />
          <button
            className="primary"
            disabled={
              clear.isPending ||
              append.isPending ||
              uncertainWrite(clear.error) ||
              uncertainWrite(append.error)
            }
            onClick={() =>
              confirm === "clear" ? clear.mutate() : append.mutate()
            }
          >
            确认{confirm === "clear" ? "清空" : "加入"}
          </button>
        </Dialog>
      )}
    </>
  );
}
