import {
  useLayoutEffect,
  useRef,
  type ComponentProps,
  type ReactNode,
} from "react";
import { Link } from "react-router-dom";
import { ApiError } from "../api";

export function Icon({ name, size = 20 }: { name: string; size?: number }) {
  const paths: Record<string, ReactNode> = {
    home: (
      <>
        <path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1Z" />
        <path d="M9 21v-8h6v8" />
      </>
    ),
    book: (
      <>
        <path d="M12 5c-3-2-7-2-10-1v15c3-1 7-1 10 1 3-2 7-2 10-1V4c-3-1-7-1-10 1Z" />
        <path d="M12 5v15" />
      </>
    ),
    route: (
      <>
        <circle cx="5" cy="5" r="2" />
        <circle cx="19" cy="19" r="2" />
        <path d="M5 7v7a5 5 0 0 0 10 0V9a4 4 0 0 1 8 0M15 14h4v3" />
      </>
    ),
    chat: (
      <path d="M21 11a8 8 0 0 1-8 8H7l-5 3 1-6a8 8 0 0 1-1-5 9 9 0 0 1 19 0Z" />
    ),
    folder: <path d="M3 5h6l2 3h10v12H3Z" />,
    review: (
      <>
        <path d="M3 10a9 9 0 1 1 1 8M3 4v6h6" />
        <path d="M12 7v5l3 2" />
      </>
    ),
    quiz: (
      <>
        <rect x="4" y="3" width="16" height="19" rx="2" />
        <path d="M8 8h8m-8 5h5m-5 5h3" />
      </>
    ),
    chart: (
      <>
        <path d="M4 3v17h17M8 15v-4m5 4V7m5 8V4" />
      </>
    ),
    tool: (
      <>
        <path d="m4 20 6-6m4-4 6-6M14 3a6 6 0 0 0-6 8L2 17a3 3 0 0 0 5 5l6-6a6 6 0 0 0 8-7l-4 4-4-4 4-4Z" />
      </>
    ),
    settings: (
      <>
        <circle cx="12" cy="12" r="3" />
        <path d="m9 3-1 3-3 1-2 3 2 2-1 4 3 2 2-1 3 4 3-2 1-3 3-1 2-3-2-2 1-4-3-2-2 1-3-4Z" />
      </>
    ),
    arrow: <path d="M4 12h16m-6-6 6 6-6 6" />,
    plus: <path d="M12 4v16M4 12h16" />,
    sun: (
      <>
        <circle cx="12" cy="12" r="4" />
        <path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1 1m12 12 1 1M5 19l1-1M18 6l1-1" />
      </>
    ),
    moon: <path d="M21 13A9 9 0 0 1 11 3a9 9 0 1 0 10 10Z" />,
    check: <path d="m5 12 4 4L19 6" />,
    menu: <path d="M4 6h16M4 12h16M4 18h16" />,
    "chevron-left": <path d="m15 6-6 6 6 6" />,
    "chevron-right": <path d="m9 6 6 6-6 6" />,
  };
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths[name] || paths.book}
    </svg>
  );
}
export function PageHeading({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        <h1>{title}</h1>
        <p className="muted">{description}</p>
      </div>
      {action}
    </div>
  );
}
export function Empty({
  title,
  description,
  action = true,
}: {
  title: string;
  description?: string;
  action?: boolean;
}) {
  return (
    <div className="empty">
      <div className="empty-icon">
        <Icon name="book" size={28} />
      </div>
      <h2>{title}</h2>
      {description && <p className="muted">{description}</p>}
      {action && (
        <Link className="button primary" to="/#goal">
          <Icon name="plus" />
          添加学习计划
        </Link>
      )}
    </div>
  );
}
const errorMessages: Record<string, string> = {
  INSUFFICIENT_CREDITS: "可用积分不足，请到官网补充后继续。",
  TENANT_BUSY: "当前学习任务较多，请稍后再试。",
  STORAGE_FULL: "学习空间已满。你仍可查看已有内容。",
  NOT_FOUND: "内容不存在或当前账号无法访问。",
  JOB_RUNNING: "已有任务正在进行，请等待完成。",
  CONFLICT: "内容已更新，请刷新后重试。",
  MODEL_NOT_SELECTED: "请先到「模型设置」选择主模型",
  MODEL_NOT_CONFIGURED: "请先导入 API Key，并在模型设置中选择主模型。",
};
export function ErrorNotice({
  error,
  retry,
}: {
  error: unknown;
  retry?: () => void;
}) {
  if (!error) return null;
  const text =
    error instanceof ApiError
      ? ["CONFLICT", "JOB_RUNNING", "MODEL_NOT_SELECTED"].includes(error.code)
        ? error.message || errorMessages[error.code]
        : errorMessages[error.code] || error.message
      : error instanceof Error
        ? error.message
        : "操作未完成，请重试。";
  return (
    <div role="alert" className="error-notice">
      <p>
        {text}
        {error instanceof ApiError && error.retryAfterSeconds
          ? ` 建议 ${error.retryAfterSeconds} 秒后重试。`
          : ""}
      </p>
      {error instanceof ApiError &&
        ["MODEL_NOT_CONFIGURED", "MODEL_NOT_SELECTED"].includes(error.code) && (
          <Link className="button" to="/models">
            {error.code === "MODEL_NOT_CONFIGURED"
              ? "导入 API Key"
              : "前往模型设置"}
          </Link>
        )}
      {retry && <button onClick={retry}>重新加载</button>}
    </div>
  );
}
export function QueryState({
  query,
}: {
  query: { isPending: boolean; error: unknown; refetch: () => unknown };
}) {
  if (query.isPending)
    return (
      <p className="loading" role="status">
        正在加载…
      </p>
    );
  return <ErrorNotice error={query.error} retry={() => void query.refetch()} />;
}
export function Unavailable({
  title = "此功能正在迁移",
  children,
}: {
  title?: string;
  children?: ReactNode;
}) {
  return (
    <div className="notice">
      <Icon name="tool" />
      <div>
        <strong>{title}</strong>
        <p>
          {children || "准备就绪后即可在这里使用。已有的学习数据不受影响。"}
        </p>
      </div>
    </div>
  );
}
export function AutoTextarea(props: ComponentProps<"textarea">) {
  const ref = useRef<HTMLTextAreaElement>(null);
  useLayoutEffect(() => {
    const el = ref.current;
    if (el) {
      el.style.height = "auto";
      el.style.height = `${Math.max(110, el.scrollHeight)}px`;
    }
  }, [props.value]);
  return (
    <textarea
      autoComplete="off"
      {...props}
      className={`form-input ${props.className || ""}`}
      ref={ref}
    />
  );
}
export function formatBytes(bytes: number) {
  return bytes < 1024 * 1024
    ? `${(bytes / 1024).toFixed(1)} KB`
    : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
