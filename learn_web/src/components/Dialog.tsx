import { useEffect, useId, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";

const stack: HTMLDivElement[] = [];
let originalOverflow = "";

export default function Dialog({
  title,
  onClose,
  children,
  dismissible = true,
  open = true,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
  dismissible?: boolean;
  open?: boolean;
}) {
  const id = useId();
  const panel = useRef<HTMLDivElement>(null);
  const close = useRef(onClose);
  close.current = () => {
    if (dismissible) onClose();
  };
  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement as HTMLElement | null;
    if (!stack.length) originalOverflow = document.body.style.overflow;
    const root = panel.current!;
    const previousPanel = stack[stack.length - 1];
    if (previousPanel) previousPanel.inert = true;
    stack.push(root);
    document.body.style.overflow = "hidden";
    panel.current?.focus();
    const key = (e: KeyboardEvent) => {
      if (stack[stack.length - 1] !== root || e.defaultPrevented) return;
      if (e.key === "Escape") {
        e.preventDefault();
        close.current();
      }
      if (e.key !== "Tab") return;
      const fields = Array.from(
        panel.current?.querySelectorAll<HTMLElement>(
          'button:not(:disabled), a[href], input:not(:disabled), textarea:not(:disabled), [tabindex="0"]',
        ) || [],
      ).filter((el) => el.getClientRects().length);
      const first = fields[0],
        last = fields[fields.length - 1];
      if (!first) {
        e.preventDefault();
        return;
      }
      if (
        e.shiftKey &&
        (document.activeElement === first ||
          document.activeElement === panel.current)
      ) {
        e.preventDefault();
        last?.focus();
      } else if (
        !e.shiftKey &&
        (document.activeElement === last ||
          document.activeElement === panel.current)
      ) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", key);
    return () => {
      const wasTop = stack[stack.length - 1] === root;
      const index = stack.indexOf(root);
      if (index >= 0) stack.splice(index, 1);
      if (!stack.length) document.body.style.overflow = originalOverflow;
      const next = stack[stack.length - 1];
      if (next) next.inert = false;
      document.removeEventListener("keydown", key);
      if (wasTop && previous?.isConnected) previous.focus();
    };
  }, [open]);
  // Escape transformed/hovered cards: a fixed descendant otherwise uses the
  // card as its containing block in Safari and flashes as hover changes.
  return createPortal(
    <div
      className="provider-dialog-backdrop"
      hidden={!open}
      onClick={(e) => {
        if (dismissible && e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className="provider-dialog"
        role={open ? "dialog" : undefined}
        aria-modal={open ? true : undefined}
        aria-labelledby={id}
        tabIndex={-1}
        ref={panel}
      >
        <header className="provider-dialog-header">
          <h2 id={id}>{title}</h2>
          <button
            onClick={onClose}
            disabled={!dismissible}
            aria-label="关闭对话框"
          >
            关闭
          </button>
        </header>
        <div className="provider-dialog-body">{children}</div>
      </div>
    </div>,
    document.body,
  );
}
