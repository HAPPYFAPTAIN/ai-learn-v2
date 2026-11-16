import { useSyncExternalStore } from "react";
import { session } from "../session/store";

export type ModelConnection = {
  id: string;
  provider: string;
  name: string;
  baseUrl: string;
  models: string[];
  remark?: string;
  website?: string;
};
type PreviewState = {
  connections: ModelConnection[];
  primary: { connectionId: string; model: string } | null;
};
const empty: PreviewState = { connections: [], primary: null };
let state = empty;
let sequence = 0;
const listeners = new Set<() => void>();
function update(next: PreviewState) {
  state = next;
  listeners.forEach((fn) => fn());
}
// Metadata only. No credential is accepted, stored, or sent by this preview.
export const modelPreview = {
  seed(connections: ModelConnection[]) {
    if (!__DEMO__) return;
    const first = connections[0];
    update({
      connections,
      primary: first
        ? { connectionId: first.id, model: first.models[0] }
        : null,
    });
  },
  add(connection: Omit<ModelConnection, "id">) {
    if (!__DEMO__) throw new Error("模型保存接口尚未接入。");
    const created = { ...connection, id: `preview-${++sequence}` };
    update({ ...state, connections: [...state.connections, created] });
    return created;
  },
  choose(connectionId: string, model: string) {
    if (!__DEMO__) return;
    const connection = state.connections.find(
      (item) => item.id === connectionId,
    );
    if (connection?.models.includes(model))
      update({ ...state, primary: { connectionId, model } });
  },
};
session.onStop(() => update(empty));
export function useModelPreview() {
  return useSyncExternalStore(
    (fn) => {
      listeners.add(fn);
      return () => {
        listeners.delete(fn);
      };
    },
    () => state,
  );
}
