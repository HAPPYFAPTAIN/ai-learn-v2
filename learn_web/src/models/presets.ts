import catalog from "./provider-catalog.json";

export type ProviderPreset = {
  id: string;
  name: string;
  mark: string;
  subtitle: string;
  group: string;
  baseUrl: string;
  profiles: { label: string; value: string }[];
  models: string[];
  note: string;
  website: string;
  docs: string;
};

// Independent snapshot of all legacy presets. Refresh with
// python scripts/learn_web/sync_providers.py; model IDs remain editable hints.
export const providerPresets: ProviderPreset[] = catalog.map((p) =>
  p.id === "custom" ? { ...p, name: "自定义添加新模型" } : p,
);
