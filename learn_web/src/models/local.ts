import { request } from "../api/client";
import type { ModelConnection } from "./preview";

// The official app never registers these endpoints. Production bundles cannot
// enable them through a query parameter or a server-supplied capability flag.
export const localProvidersAllowed =
  import.meta.env.DEV && !__DEMO__ && location.hostname === "127.0.0.1";

export type LocalProviderInput = Omit<ModelConnection, "id"> & {
  apiKey: string;
};
export type LocalProviderResult = {
  connection: ModelConnection;
  verifiedMs: number;
};
export function localProviders(signal?: AbortSignal) {
  return request<{ enabled: boolean; connections: ModelConnection[] }>(
    "/local-providers",
    {},
    signal,
  );
}
export function addLocalProvider(
  body: LocalProviderInput,
  signal: AbortSignal,
) {
  if (!localProvidersAllowed) throw new Error("当前页面不是本地测试入口。");
  return request<LocalProviderResult>(
    "/local-providers",
    { method: "POST", body: JSON.stringify(body) },
    signal,
  );
}
export function localModelLabel(model: string) {
  return model.replace(/^local\.[a-f0-9]{12}\./, "");
}
