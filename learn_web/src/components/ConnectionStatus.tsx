import { useEffect, useState } from "react";

export default function ConnectionStatus() {
  const [status, setStatus] = useState<"offline" | "restored" | "quiet">(() =>
    navigator.onLine ? "quiet" : "offline",
  );
  useEffect(() => {
    const offline = () => setStatus("offline");
    const online = () =>
      setStatus((old) => (old === "offline" ? "restored" : old));
    window.addEventListener("offline", offline);
    window.addEventListener("online", online);
    return () => {
      window.removeEventListener("offline", offline);
      window.removeEventListener("online", online);
    };
  }, []);
  if (status === "quiet") return null;
  return (
    <div className="connection-notice" role="status">
      {status === "offline"
        ? "网络已断开，当前页面的输入仍保留。恢复连接后请先核对保存结果。"
        : "网络连接已恢复。请核对保存结果，未确认的操作不会自动重新提交。"}
      {status === "restored" && (
        <button type="button" onClick={() => setStatus("quiet")}>
          关闭网络提示
        </button>
      )}
    </div>
  );
}
