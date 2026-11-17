import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";

export type SelectOption<T extends string | number> = {
  value: T;
  label: string;
};
type Props<T extends string | number> = {
  id?: string;
  options: SelectOption<T>[];
  value: T | undefined;
  onChange: (value: T) => void;
  label: string;
  listLabel?: string;
  placeholder?: string;
  disabled?: boolean;
  className?: string;
};

export default function Select<T extends string | number>({
  id,
  options,
  value,
  onChange,
  label,
  listLabel = label,
  placeholder = "请选择",
  disabled = false,
  className = "",
}: Props<T>) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const listId = useId();
  const search = useRef({ text: "", time: 0 });
  const selected = options.findIndex((option) => option.value === value);

  useEffect(() => {
    if (!open) return;
    const dismiss = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", dismiss);
    return () => document.removeEventListener("pointerdown", dismiss);
  }, [open]);

  useEffect(() => {
    if (open)
      document
        .getElementById(`${listId}-${active}`)
        ?.scrollIntoView({ block: "nearest" });
  }, [open, active, listId]);

  function expand() {
    setActive(Math.max(0, selected));
    setOpen(true);
  }

  function choose(index: number) {
    const option = options[index];
    if (!option) return;
    setOpen(false);
    trigger.current?.focus();
    onChange(option.value);
  }

  function handleKey(event: KeyboardEvent<HTMLButtonElement>) {
    if (disabled || !options.length || event.nativeEvent.isComposing) return;
    switch (event.key) {
      case "ArrowDown":
      case "ArrowUp":
        event.preventDefault();
        if (!open) expand();
        else
          setActive(
            (index) =>
              (index + (event.key === "ArrowDown" ? 1 : -1) + options.length) %
              options.length,
          );
        break;
      case "Home":
      case "End":
        event.preventDefault();
        setOpen(true);
        setActive(event.key === "Home" ? 0 : options.length - 1);
        break;
      case "Enter":
      case " ":
        event.preventDefault();
        if (open) choose(active);
        else expand();
        break;
      case "Escape":
        if (open) event.preventDefault();
        setOpen(false);
        break;
      case "Tab":
        setOpen(false);
        break;
      default:
        if (
          event.key.length !== 1 ||
          event.ctrlKey ||
          event.metaKey ||
          event.altKey
        )
          return;
        event.preventDefault();
        const now = Date.now();
        search.current = {
          text:
            (now - search.current.time < 700 ? search.current.text : "") +
            event.key.toLocaleLowerCase(),
          time: now,
        };
        const match = options.findIndex((option) =>
          option.label.toLocaleLowerCase().startsWith(search.current.text),
        );
        if (match >= 0) {
          setOpen(true);
          setActive(match);
        }
    }
  }

  return (
    <div className={`ui-select ${className}`} ref={root}>
      <button
        id={id}
        ref={trigger}
        className="ui-select-trigger"
        type="button"
        role="combobox"
        aria-label={label}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? listId : undefined}
        aria-activedescendant={open ? `${listId}-${active}` : undefined}
        disabled={disabled || !options.length}
        onClick={() => (open ? setOpen(false) : expand())}
        onKeyDown={handleKey}
        onBlur={(event) => {
          if (
            !event.currentTarget.parentElement?.contains(
              event.relatedTarget as Node | null,
            )
          )
            setOpen(false);
        }}
      >
        <span>{options[selected]?.label || placeholder}</span>
        <svg
          className={open ? "is-open" : ""}
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.7"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="m6 9 6 6 6-6" />
        </svg>
      </button>
      {open && (
        <ul
          id={listId}
          className="ui-select-menu"
          role="listbox"
          aria-label={listLabel}
        >
          {options.map((option, index) => (
            <li
              id={`${listId}-${index}`}
              key={option.value}
              role="option"
              aria-selected={option.value === value}
              className={index === active ? "is-active" : ""}
              onMouseDown={(event) => event.preventDefault()}
              onMouseMove={() => setActive(index)}
              onClick={() => choose(index)}
            >
              <svg
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.7"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
                className={option.value === value ? "" : "is-hidden"}
              >
                <path d="m5 12 4 4L19 6" />
              </svg>
              <span>{option.label}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
