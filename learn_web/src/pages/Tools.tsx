import { jobFailure } from "../api/jobError";
import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { endpoints, type JobProgress } from "../api";
import { key } from "../query";
import { watchJob } from "../api/jobs";
import { useProject } from "../components/ProjectContext";
import {
  AutoTextarea,
  ErrorNotice,
  Icon,
  PageHeading,
  QueryState,
} from "../components/ui";
import Select from "../components/Select";
import { ChatRoom } from "./Chat";

const purposes = [
  { value: "note", label: "学习笔记" },
  { value: "goal", label: "学习目标" },
  { value: "background", label: "学习背景" },
  { value: "question", label: "提问" },
  { value: "answer", label: "自己的答案" },
  { value: "title", label: "标题" },
  { value: "feedback", label: "反馈" },
  { value: "instruction", label: "说明" },
  { value: "general", label: "一般文本" },
];

export default function Tools() {
  const { id } = useProject();
  const [params, setParams] = useSearchParams();
  const tool = params.get("tool") === "polish" ? "polish" : "coach";
  const chapter = Number(params.get("chapter")) || 0;
  const nodes = useQuery({
    queryKey: key("nodes", id),
    queryFn: ({ signal }) => endpoints.nodes(id!, signal),
    enabled: !!id,
  });
  return (
    <>
      <PageHeading
        title="学习工具"
        description="把理解变成实践，把想法表达得更清楚。"
      />
      <div className="tool-grid">
        {(
          [
            [
              "coach",
              "tool",
              "分步练习教练",
              "每次练习一个步骤，反馈结果后再继续。",
            ],
            [
              "polish",
              "book",
              "文本润色",
              "保留原意，改善目标、笔记和提问的表达。",
            ],
          ] as const
        ).map(([value, icon, title, description]) => (
          <button
            className="panel tool-card"
            key={value}
            aria-pressed={tool === value}
            onClick={() =>
              setParams((p) => {
                p.set("tool", value);
                return p;
              })
            }
          >
            <Icon name={icon} size={28} />
            <h2>{title}</h2>
            <p className="muted">{description}</p>
          </button>
        ))}
      </div>
      {tool === "polish" ? (
        <Polish key={id} id={id} />
      ) : (
        <>
          <section className="panel form-panel">
            <h2>选择练习内容</h2>
            <Select
              label="练习章节"
              disabled={!id}
              value={chapter}
              options={[
                { value: 0, label: "围绕当前学习目标" },
                ...(nodes.data?.items.map((n) => ({
                  value: n.id,
                  label: `${n.code} ${n.title}`,
                })) || []),
              ]}
              onChange={(value) =>
                setParams((p) => {
                  if (value) p.set("chapter", String(value));
                  else p.delete("chapter");
                  return p;
                })
              }
            />
            <ErrorNotice error={nodes.error} />
          </section>
          <ChatRoom key={id} id={id} mode="coach" />
        </>
      )}
    </>
  );
}

function Polish({ id }: { id: number }) {
  const latest = useQuery({
    queryKey: key("polish-job", id),
    queryFn: ({ signal }) => endpoints.polishJob(id, signal),
    enabled: !!id,
  });
  const [draft, setDraft] = useState("");
  const [purpose, setPurpose] = useState("note");
  const [jobId, setJobId] = useState("");
  const [job, setJob] = useState<JobProgress>();
  const [watchError, setWatchError] = useState<Error>();
  const [reconnecting, setReconnecting] = useState(false);
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState<Error>();
  const recovered = useRef(false);
  const submitted = useRef({ signature: "", requestId: crypto.randomUUID() });
  const activeId = jobId || latest.data?.jobId || "";
  useEffect(() => {
    if (!activeId) return;
    return watchJob(
      activeId,
      (next) => {
        setJob(next);
        if (!recovered.current) {
          recovered.current = true;
          if (typeof next.progress.source === "string")
            setDraft((current) => current || (next.progress.source as string));
          if (typeof next.progress.purpose === "string")
            setPurpose(next.progress.purpose);
        }
      },
      (state) => setReconnecting(state === "reconnecting"),
      setWatchError,
    );
  }, [activeId]);
  const send = useMutation({
    mutationFn: () => {
      const signature = JSON.stringify({ source: draft, purpose });
      if (signature !== submitted.current.signature)
        submitted.current = { signature, requestId: crypto.randomUUID() };
      return endpoints.polish(id, {
        source: draft,
        purpose,
        requestId: submitted.current.requestId,
      });
    },
    onSuccess: (result) => {
      recovered.current = true;
      setJob(undefined);
      setWatchError(undefined);
      setCopied(false);
      setCopyError(undefined);
      setJobId(result.jobId);
      submitted.current = { signature: "", requestId: crypto.randomUUID() };
    },
    onError: () => {
      setJobId("");
      setJob(undefined);
      void latest.refetch();
    },
  });
  const pending =
    send.isPending ||
    (!!activeId &&
      !watchError &&
      (!job ||
        job.jobId !== activeId ||
        ["queued", "running"].includes(job.state)));
  const result =
    job?.state === "done" && typeof job.progress.result === "string"
      ? job.progress.result
      : "";
  return (
    <section className="panel form-panel polish-panel">
      <h2>文本润色</h2>
      <p className="muted">
        只改善表达，保留代码、链接、数字与原意。润色结果单独展示，由你决定是否采用。
      </p>
      {!!id && <QueryState query={latest} />}
      {!id && (
        <p className="muted small">暂无学习计划，关联计划的润色暂不可用。</p>
      )}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (id && draft.trim() && !pending) send.mutate();
        }}
      >
        <Select
          label="润色用途"
          value={purpose}
          options={purposes}
          disabled={pending || !id}
          onChange={setPurpose}
        />
        <label htmlFor="polish-source">原文</label>
        <AutoTextarea
          id="polish-source"
          value={draft}
          maxLength={12000}
          disabled={!id || pending || latest.isPending}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="粘贴要润色的学习目标、笔记或问题…"
        />
        <div className="form-footer">
          <span className="muted small">{draft.length} / 12000 字</span>
          <button
            className="primary"
            disabled={!id || !draft.trim() || pending || latest.isPending}
          >
            {pending ? "正在润色…" : "开始润色"}
          </button>
        </div>
        {pending && (
          <p role="status">
            {job?.state === "running"
              ? "正在改善表达，原文会保留。"
              : "润色任务正在排队。"}
            {reconnecting ? " 正在恢复连接，可刷新后查看同一任务。" : ""}
          </p>
        )}
        <ErrorNotice error={send.error || watchError || jobFailure(job)} />
      </form>
      {result && (
        <section className="polish-result" aria-label="润色结果">
          <h3>润色结果</h3>
          {job?.progress.truncated === true && (
            <p role="status" className="muted">
              回答可能不完整
            </p>
          )}
          <p className="material-text">{result}</p>
          {job?.progress.source !== draft && (
            <p className="muted small">
              这是上一份原文的结果；当前原文有修改，请重新润色。
            </p>
          )}
          <button
            onClick={async () => {
              try {
                await navigator.clipboard.writeText(result);
                setCopied(true);
                setCopyError(undefined);
              } catch {
                setCopyError(new Error("复制失败，请选中文字后手动复制。"));
              }
            }}
          >
            {copied ? "已复制" : "复制结果"}
          </button>
          <ErrorNotice error={copyError} />
        </section>
      )}
    </section>
  );
}
