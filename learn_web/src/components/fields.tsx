import { useId, useRef, type ComponentProps } from "react";

export function Input({
  className = "",
  autoComplete = "off",
  ...props
}: ComponentProps<"input">) {
  return (
    <input
      type="text"
      {...props}
      autoComplete={autoComplete}
      className={`form-input ${className}`}
    />
  );
}

type SearchProps = {
  label: string;
  placeholder?: string;
  value: string;
  onChange: (value: string) => void;
};
export function SearchField({
  label,
  placeholder,
  value,
  onChange,
}: SearchProps) {
  const id = useId();
  const input = useRef<HTMLInputElement>(null);
  function clear() {
    onChange("");
    input.current?.focus();
  }
  return (
    <div className="search-field">
      <label className="sr-only" htmlFor={id}>
        {label}
      </label>
      <svg
        width="18"
        height="18"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
        aria-hidden="true"
      >
        <circle cx="10.5" cy="10.5" r="6.5" />
        <path d="m16 16 4 4" />
      </svg>
      <Input
        id={id}
        ref={input}
        type="search"
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Escape" && value) {
            e.preventDefault();
            clear();
          }
        }}
      />
      {value && (
        <button
          className="search-clear"
          type="button"
          aria-label={`清空${label}`}
          onClick={clear}
        >
          <svg
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.7"
            strokeLinecap="round"
            aria-hidden="true"
          >
            <path d="m6 6 12 12M6 18 18 6" />
          </svg>
        </button>
      )}
    </div>
  );
}
