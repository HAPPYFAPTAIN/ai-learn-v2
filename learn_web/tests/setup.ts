import { vi } from "vitest";
function memoryStorage() {
  const values = new Map<string, string>();
  return {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value),
    removeItem: (key: string) => values.delete(key),
    clear: () => values.clear(),
  };
}
vi.stubGlobal("location", { origin: "http://localhost", search: "" });
vi.stubGlobal("sessionStorage", memoryStorage());
vi.stubGlobal("localStorage", memoryStorage());
vi.stubGlobal("document", { hidden: false });
