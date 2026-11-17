import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useId,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useBlocker } from "react-router-dom";
import { session } from "../session/store";
import Dialog from "./Dialog";

type Entry = { label: string; dirty: boolean; pending: boolean };
type Confirm = { action: () => void; labels: string[]; pending: boolean };
const Context = createContext<{
  register: (id: string, entry: Entry) => void;
  remove: (id: string) => void;
  confirm: (action: () => void, ids?: string[]) => void;
} | null>(null);

// One router blocker covers all forms, including forms inside dialogs.
export default function DraftProtection({ children }: { children: ReactNode }) {
  const [entries, setEntries] = useState(new Map<string, Entry>());
  const current = useRef(entries);
  current.current = entries;
  const [local, setLocal] = useState<Confirm>();
  const active = [...entries.values()].filter(
    (entry) => entry.dirty || entry.pending,
  );
  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) =>
      session.get().status === "ready" &&
      [...current.current.values()].some(
        (entry) => entry.dirty || entry.pending,
      ) &&
      (currentLocation.pathname !== nextLocation.pathname ||
        currentLocation.search !== nextLocation.search),
  );
  const register = useCallback((id: string, entry: Entry) => {
    setEntries((old) => {
      const previous = old.get(id);
      if (
        previous?.label === entry.label &&
        previous.dirty === entry.dirty &&
        previous.pending === entry.pending
      )
        return old;
      return new Map(old).set(id, entry);
    });
  }, []);
  const remove = useCallback((id: string) => {
    setEntries((old) => {
      if (!old.has(id)) return old;
      const next = new Map(old);
      next.delete(id);
      return next;
    });
  }, []);
  const confirm = useCallback((action: () => void, ids?: string[]) => {
    const affected = [...current.current]
      .filter(
        ([id, entry]) =>
          (!ids || ids.includes(id)) && (entry.dirty || entry.pending),
      )
      .map(([, entry]) => entry);
    if (!affected.length) return action();
    setLocal({
      action,
      labels: [...new Set(affected.map((entry) => entry.label))],
      pending: affected.some((entry) => entry.pending),
    });
  }, []);
  useEffect(() => {
    if (!active.length) return;
    const warn = (event: BeforeUnloadEvent) => {
      if (session.get().status !== "ready") return;
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [active.length]);
  useEffect(() => {
    if (blocker.state === "blocked" && !active.length) blocker.proceed();
  }, [blocker, active.length]);
  const value = useMemo(
    () => ({ register, remove, confirm }),
    [register, remove, confirm],
  );
  const routeBlocked = blocker.state === "blocked";
  const confirmation = routeBlocked
    ? {
        labels: [...new Set(active.map((entry) => entry.label))],
        pending: active.some((entry) => entry.pending),
      }
    : local;
  function stay() {
    if (blocker.state === "blocked") blocker.reset();
    setLocal(undefined);
  }
  return (
    <Context.Provider value={value}>
      {children}
      {confirmation && (
        <Dialog title="有内容尚未保存" onClose={stay}>
          <p>
            {confirmation.labels.join("、")}
            尚未确认保存。离开后，未保存的输入将被丢弃。
          </p>
          {confirmation.pending && (
            <p className="muted">
              保存请求仍在进行，服务器可能已经接收。离开后请先核对记录，避免重复提交。
            </p>
          )}
          <div className="content-actions">
            <button autoFocus onClick={stay}>
              继续编辑
            </button>
            <button
              onClick={() => {
                const action = local?.action;
                setLocal(undefined);
                if (blocker.state === "blocked") blocker.proceed();
                else action?.();
              }}
            >
              放弃未保存内容
            </button>
          </div>
        </Dialog>
      )}
    </Context.Provider>
  );
}

export function useConfirmDiscard() {
  const context = useContext(Context);
  if (!context) throw new Error("DraftProtection is required");
  return context.confirm;
}
export function useDraftGuard(label: string, dirty: boolean, pending = false) {
  const context = useContext(Context);
  if (!context) throw new Error("DraftProtection is required");
  const id = useId();
  const { register, remove, confirm } = context;
  useLayoutEffect(() => {
    register(id, { label, dirty, pending });
  }, [id, label, dirty, pending, register]);
  useLayoutEffect(() => () => remove(id), [id, remove]);
  return (action: () => void) => confirm(action, [id]);
}
