import type { JobProgress } from "../api";

const messages: Record<string, string> = {
  INSUFFICIENT_CREDITS: "官网积分不足，请充值后重试",
  RESULT_UNCONFIRMED:
    "模型请求结果未确认，已停止自动重试。请核对任务与用量记录",
  OUTPUT_TRUNCATED: "生成内容超出长度上限，未能保存。可以缩小章节范围后重试。",
  GATEWAY_REJECTED: "模型网关拒绝了请求，请检查模型设置后重试",
};

export function jobFailure(job?: JobProgress): Error | null {
  if (!job) return null;
  const code = String(job.progress.errorCode || "");
  const message =
    code === "GATEWAY_REJECTED"
      ? job.error || messages[code]
      : messages[code] || job.error;
  return message
    ? new Error(message)
    : job.state === "failed"
      ? new Error("任务未完成，请核对任务状态后重试")
      : null;
}
