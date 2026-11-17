import { useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { endpoints, type JobProgress } from "../api";
import { watchJob } from "../api/jobs";
import { key } from "../query";
import { ErrorNotice } from "./ui";
import { generationStorageKey } from "../api/generation";
import GenerationProgress from "./GenerationProgress";

export default function GenerationAction({
  projectId,
  nodeId,
  ready = false,
  assessment,
  initialJobId,
  onComplete,
  hideCompleted = false,
}: {
  projectId: number;
  nodeId?: number;
  ready?: boolean;
  initialJobId?: string;
  onComplete?: () => void;
  hideCompleted?: boolean;
  assessment?: {
    kind: "quiz" | "cards";
    nodeIds: number[];
    count: number;
    qtype: "mixed" | "choice" | "fill" | "short" | "practice";
  };
}) {
  const client = useQueryClient();
  const storageKey = generationStorageKey(
    projectId,
    assessment?.kind || nodeId || "roadmap",
  );
  const [jobId, setJobId] = useState(
    () => initialJobId || sessionStorage.getItem(storageKey) || "",
  );
  const [job, setJob] = useState<JobProgress>();
  const [error, setError] = useState<Error>();
  const [reconnecting, setReconnecting] = useState(false);
  const [replace, setReplace] = useState(false);
  const handled = useRef("");
  const submit = useMutation({
    mutationFn: () =>
      assessment
        ? endpoints.generateAssessment(projectId, assessment)
        : nodeId
          ? endpoints.generateLesson(nodeId, ready && replace)
          : endpoints.generateRoadmap(projectId),
    onSuccess: (result) => {
      setError(undefined);
      setJob(undefined);
      handled.current = "";
      sessionStorage.setItem(storageKey, result.jobId);
      setJobId(result.jobId);
    },
  });
  useEffect(() => {
    if (!jobId) return;
    return watchJob(
      jobId,
      (next) => {
        setJob(next);
        if (
          ["done", "failed", "cancelled"].includes(next.state) &&
          handled.current !== jobId
        ) {
          handled.current = jobId;
          if (next.state === "done") {
            void client.invalidateQueries({
              queryKey: key("nodes", projectId),
            });
            void client.invalidateQueries({
              queryKey: key("summary", projectId),
            });
            void client.invalidateQueries({
              queryKey: key("quizzes", projectId),
            });
            void client.invalidateQueries({ queryKey: key("due") });
            void client.invalidateQueries({
              queryKey: key("cards", projectId),
            });
          }
        }
      },
      (state) => setReconnecting(state === "reconnecting"),
      (e) => {
        setError(e);
        sessionStorage.removeItem(storageKey);
      },
    );
  }, [jobId, client, projectId, storageKey]);
  if (hideCompleted && job?.state === "done") return null;
  if (!assessment && !nodeId && ready && !jobId) return null;
  const pending =
    submit.isPending ||
    (!!jobId && !error && (!job || ["queued", "running"].includes(job.state)));
  const labels: Record<string, string> = {
    queued: "已排队，等待生成",
    running: "正在生成学习内容",
    done: "生成已完成",
    failed: "生成失败",
    cancelled: "生成已停止",
  };
  const seconds = (value: unknown) => `${(Number(value) / 1000).toFixed(2)} 秒`;
  return (
    <section className="generation-action">
      {(!ready || !!nodeId || !!assessment) && (
        <>
          <p className="muted small">
            {__DEMO__
              ? "演示模式不调用模型。真实生成需启动后端并配置测试网关。"
              : "使用当前主模型生成，将消耗模型额度。其他章节可按需生成。"}
          </p>
          {nodeId && ready && (
            <label className="inline-label">
              <input
                type="checkbox"
                checked={replace}
                disabled={pending}
                onChange={(e) => setReplace(e.target.checked)}
              />
              重新生成并替换本节教材
            </label>
          )}
          <button
            className="primary"
            disabled={
              __DEMO__ ||
              pending ||
              (!assessment && ready && !replace) ||
              (!!assessment && !assessment.nodeIds.length)
            }
            onClick={() => submit.mutate()}
          >
            {pending
              ? "生成处理中…"
              : assessment
                ? assessment.kind === "quiz"
                  ? "生成测验"
                  : "生成复习卡"
                : nodeId
                  ? ready
                    ? "重新生成本节教材"
                    : "生成本节教材"
                  : "AI 生成学习路线"}
          </button>
        </>
      )}
      {job && (
        <div className="job-status" role="status">
          <strong>{labels[job.state] || job.state}</strong>
          {!nodeId && !assessment && (
            <GenerationProgress job={job} reconnecting={reconnecting} />
          )}
          {reconnecting && <p>连接中断，正在重新检查任务状态…</p>}
          {job.state === "done" && (
            <dl className="generation-timings">
              <div>
                <dt>排队</dt>
                <dd>{seconds(job.progress.queueMs)}</dd>
              </div>
              <div>
                <dt>模型响应</dt>
                <dd>{seconds(job.progress.modelMs)}</dd>
              </div>
              <div>
                <dt>总耗时</dt>
                <dd>{seconds(job.progress.totalMs)}</dd>
              </div>
            </dl>
          )}
          {job.state === "done" && onComplete && (
            <button
              type="button"
              className="primary generation-complete"
              onClick={onComplete}
            >
              完成
            </button>
          )}
          <ErrorNotice error={job.error ? new Error(job.error) : null} />
          {job.state === "done" && assessment && (
            <p>
              已保存 {Number(job.progress.count || 0)}{" "}
              {assessment.kind === "quiz"
                ? "道题，可在下方选择新测验作答。"
                : "张卡片，可在下方开始复习。"}
            </p>
          )}
        </div>
      )}
      <ErrorNotice error={error || submit.error} />
    </section>
  );
}
