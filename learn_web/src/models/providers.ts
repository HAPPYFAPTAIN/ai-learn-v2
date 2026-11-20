import { request, type Model } from "../api/client";
import type { LocalProviderInput, LocalProviderResult } from "./local";

export function personalProviders(signal?: AbortSignal) {
  return request<Model<"ProviderListOut">>("/model-providers", {}, signal);
}

export function addPersonalProvider(
  body: LocalProviderInput & { id: string },
  signal: AbortSignal,
) {
  return request<LocalProviderResult>(
    "/model-providers",
    { method: "POST", body: JSON.stringify(body) },
    signal,
  );
}

export function removePersonalProvider(id: string) {
  return request<void>(`/model-providers/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

export function updatePersonalProvider(
  id: string,
  body: Model<"ProviderUpdate">,
  signal: AbortSignal,
) {
  return request<LocalProviderResult>(
    `/model-providers/${encodeURIComponent(id)}`,
    { method: "PUT", body: JSON.stringify(body) },
    signal,
  );
}

export function personalModelLabel(model: string) {
  return model.replace(/^personal\.[a-f0-9]{12}\./, "");
}
