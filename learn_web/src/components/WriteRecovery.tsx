import { useEffect, useRef, useState } from "react";
import { ApiError } from "../api/client";
import { ErrorNotice } from "./ui";

export const uncertainWrite = (error: unknown) =>
  error instanceof ApiError && error.outcomeUnknown;

// Reads only. A second write always requires a separate, explicit user action.
export default function WriteRecovery({
  error,
  onCheck,
  onAllowRetry,
}: {
  error: unknown;
  onCheck: () => Promise<string>;
  onAllowRetry: () => void;
}) {
  const [checking, setChecking] = useState(false);
  const [checked, setChecked] = useState("");
  const [failure, setFailure] = useState<unknown>();
  const mounted = useRef(false);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  useEffect(() => {
    setChecked("");
    setFailure(undefined);
  }, [error]);
  if (!uncertainWrite(error)) return null;
  return (
    <section className="notice write-recovery" aria-label="核对保存结果">
      <p>
        暂时无法确认保存结果，服务器可能已经接收。请先核对记录，避免重复提交；当前输入仍保留。
      </p>
      <button
        type="button"
        disabled={checking}
        onClick={async () => {
          setChecking(true);
          setFailure(undefined);
          setChecked("");
          try {
            const message = await onCheck();
            if (mounted.current) setChecked(message);
          } catch (cause) {
            if (mounted.current) setFailure(cause);
          } finally {
            if (mounted.current) setChecking(false);
          }
        }}
      >
        {checking ? "正在核对…" : "核对已保存记录"}
      </button>
      {checked && (
        <>
          <p role="status">{checked}</p>
          <p className="muted small">
            列表暂未出现也不代表服务器一定未保存。确认没有本次内容后，可允许再次提交；新建记录仍有重复风险。
          </p>
          <button type="button" onClick={onAllowRetry}>
            已核对，允许再次提交
          </button>
        </>
      )}
      <ErrorNotice error={failure} />
    </section>
  );
}
