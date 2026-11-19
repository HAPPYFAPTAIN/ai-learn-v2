import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { endpoints } from "../api";
import {
  localProvidersAllowed,
  localProviders,
  localModelLabel,
  type LocalProviderResult,
} from "../models/local";
import { key } from "../query";
import { SearchField } from "../components/fields";
import ProviderDialog from "../components/ProviderDialog";
import ProviderLogo from "../components/ProviderLogo";
import Select from "../components/Select";
import { Icon, PageHeading, QueryState, ErrorNotice } from "../components/ui";
import { providerPresets, type ProviderPreset } from "../models/presets";
import {
  modelPreview,
  useModelPreview,
  type ModelConnection,
} from "../models/preview";

export default function Models() {
  return __DEMO__ ? <PreviewModels /> : <GatewayModels />;
}

function GatewayModels() {
  const client = useQueryClient();
  const catalog = useQuery({
    queryKey: key("models"),
    queryFn: ({ signal }) => endpoints.models(signal),
  });
  const local = useQuery({
    queryKey: key("local-providers"),
    queryFn: ({ signal }) => localProviders(signal),
    enabled: localProvidersAllowed,
  });
  const localEnabled = localProvidersAllowed && local.data?.enabled === true;
  const modelLabel = (model: string) =>
    localEnabled ? localModelLabel(model) : model;
  const [draft, setDraft] = useState("");
  const [message, setMessage] = useState("");
  const [filter, setFilter] = useState("");
  const [provider, setProvider] = useState("");
  const selected = catalog.data?.selectedModel || "";
  const viewed = draft || selected;
  const items = catalog.data?.items || [];
  const providers = [
    ...new Set(items.map((item) => item.provider || "官网网关")),
  ];
  const providerItems =
    provider && providers.includes(provider)
      ? items.filter((item) => (item.provider || "官网网关") === provider)
      : items;
  const save = useMutation({
    mutationFn: () => endpoints.selectModel(viewed),
    onSuccess: (result) => {
      // Only the server-confirmed preference is shown as saved.
      client.setQueryData(key("models"), (previous: typeof catalog.data) =>
        previous
          ? {
              ...previous,
              selectedModel: result.selectedModel,
              selectedAvailable: true,
            }
          : previous,
      );
      setMessage(
        `已将主模型设置为 ${modelLabel(result.selectedModel)}，后续新请求将使用它。`,
      );
    },
  });
  return (
    <>
      <PageHeading
        title="模型设置"
        description="选择学习使用的主模型，所有学习功能统一使用这份设置。"
      />
      <section
        className="panel imported-models"
        aria-labelledby="gateway-model-title"
      >
        <div className="section-title spread">
          <div>
            <h2 id="gateway-model-title">可用模型</h2>
            <p className="muted">
              {localEnabled
                ? "本机测试供应商 · 生成内容会消耗对应供应商额度。"
                : "模型由官网提供，使用当前账号的可用积分。"}
            </p>
          </div>
          <button
            disabled={catalog.isFetching || save.isPending}
            onClick={() => {
              setMessage("");
              void catalog.refetch();
              if (localEnabled) void local.refetch();
            }}
          >
            刷新可用模型
          </button>
        </div>
        <QueryState query={catalog} />
        {catalog.data && (
          <>
            <div className="primary-model-summary">
              <span className="primary-model-icon">
                <Icon name="settings" />
              </span>
              <div>
                <span className="muted">当前主模型</span>
                <strong>{modelLabel(selected) || "尚未设置主模型"}</strong>
              </div>
            </div>
            {selected && !catalog.data.selectedAvailable && (
              <p className="error-notice" role="status">
                原主模型当前不可用，请重新选择。已有学习内容仍保留。
              </p>
            )}
            {items.length ? (
              <>
                <div
                  className="connected-providers"
                  role="group"
                  aria-label="可用供应商"
                >
                  <button
                    type="button"
                    aria-pressed={!provider || !providers.includes(provider)}
                    onClick={() => setProvider("")}
                  >
                    全部供应商
                  </button>
                  {providers.map((name) => {
                    const connection = local.data?.connections.find(
                      (c) => c.id === name,
                    );
                    const preset = providerPresets.find(
                      (p) =>
                        p.id === (connection?.provider || name).toLowerCase() ||
                        p.name.toLowerCase() === name.toLowerCase(),
                    );
                    return (
                      <button
                        type="button"
                        key={name}
                        aria-pressed={provider === name}
                        onClick={() => setProvider(name)}
                      >
                        <ProviderLogo
                          provider={preset?.id || name.toLowerCase()}
                          customMark={name.slice(0, 1).toUpperCase()}
                        />
                        <span>
                          {connection?.name || preset?.name || name}
                          <small>
                            {
                              items.filter(
                                (item) =>
                                  (item.provider || "官网网关") === name,
                              ).length
                            }{" "}
                            个模型
                          </small>
                        </span>
                        {provider === name && <Icon name="check" size={16} />}
                      </button>
                    );
                  })}
                </div>
                <SearchField
                  label="搜索可用模型"
                  placeholder="输入模型名称"
                  value={filter}
                  onChange={setFilter}
                />
                <div className="model-choice">
                  <div className="model-choice-field">
                    <label htmlFor="gateway-primary-model">主模型</label>
                    <Select
                      id="gateway-primary-model"
                      label="主模型"
                      listLabel="可选主模型"
                      value={viewed}
                      placeholder="选择一个可用模型"
                      options={providerItems
                        .filter((m) =>
                          `${m.id} ${m.provider}`
                            .toLowerCase()
                            .includes(filter.trim().toLowerCase()),
                        )
                        .map((m) => ({ value: m.id, label: modelLabel(m.id) }))}
                      onChange={(value) => {
                        setDraft(value);
                        setMessage("");
                        save.reset();
                      }}
                    />
                  </div>
                  <button
                    className="primary"
                    disabled={
                      save.isPending ||
                      !viewed ||
                      viewed === selected ||
                      !items.some((m) => m.id === viewed)
                    }
                    onClick={() => save.mutate()}
                  >
                    {save.isPending ? "正在保存…" : "设为主模型"}
                  </button>
                </div>
                {filter &&
                  !providerItems.some((m) =>
                    `${m.id} ${m.provider}`
                      .toLowerCase()
                      .includes(filter.trim().toLowerCase()),
                  ) && (
                    <p className="muted">
                      没有找到匹配的模型，请修改搜索条件。
                    </p>
                  )}
              </>
            ) : (
              <div className="models-empty">
                <h3>暂无可用模型</h3>
                <p className="muted">
                  {localEnabled
                    ? "从下方添加测试供应商，再选择主模型。"
                    : "请在官网确认模型使用资格后，刷新列表。"}
                </p>
              </div>
            )}
            <p className="field-hint">
              保存后，学习路线、教材、问答、测验和复习卡的新请求将使用此模型；进行中的任务继续使用提交时的模型。
            </p>
          </>
        )}
        <ErrorNotice error={save.error} />
        <p role="status" className="model-status">
          {message}
        </p>
      </section>
      <ProviderCatalog
        localEnabled={localEnabled}
        onLocalAdded={(result) => {
          client.setQueryData(
            key("local-providers"),
            (previous: typeof local.data) =>
              previous
                ? {
                    ...previous,
                    connections: [...previous.connections, result.connection],
                  }
                : previous,
          );
          void client.invalidateQueries({ queryKey: key("models") });
          setProvider(result.connection.id);
          setDraft(result.connection.models[0] || "");
          setFilter("");
          save.reset();
          setMessage(
            `已添加「${result.connection.name}」，目录验证耗时 ${(result.verifiedMs / 1000).toFixed(2)} 秒。请点击“设为主模型”后开始学习。`,
          );
          document
            .getElementById("gateway-model-title")
            ?.scrollIntoView({ block: "start", behavior: "smooth" });
        }}
      />
    </>
  );
}

function PreviewModels() {
  const { connections, primary } = useModelPreview();
  const [viewed, setViewed] = useState(
    primary?.connectionId || connections[0]?.id || "",
  );
  const connection = connections.find((c) => c.id === viewed);
  const [model, setModel] = useState(
    primary?.model || connection?.models[0] || "",
  );
  const [message, setMessage] = useState("");
  const primaryConnection = connections.find(
    (c) => c.id === primary?.connectionId,
  );
  const isPrimary =
    primary?.connectionId === viewed && primary?.model === model;

  function added(connection: ModelConnection) {
    setViewed(connection.id);
    setModel(connection.models[0]);
    setMessage(`已添加「${connection.name}」到演示列表，可在上方选择主模型。`);
    document
      .getElementById("imported-models")
      ?.scrollIntoView({ block: "start", behavior: "smooth" });
    requestAnimationFrame(() =>
      document.getElementById("imported-title")?.focus({ preventScroll: true }),
    );
  }
  return (
    <>
      <PageHeading
        title="模型设置"
        description="管理你的模型供应商，为学习选择一个合适的主模型。"
      />
      <section
        className="panel imported-models"
        id="imported-models"
        aria-labelledby="imported-title"
      >
        <div className="section-title spread">
          <div>
            <h2 id="imported-title" tabIndex={-1}>
              已导入的模型
            </h2>
            <p className="muted">选择供应商，再选择该供应商下的主模型。</p>
          </div>
          <span className="badge">
            {connections.length} 个供应商{__DEMO__ ? " · 示例" : ""}
          </span>
        </div>
        {connections.length ? (
          <>
            <div
              className="connected-providers"
              role="group"
              aria-label="已导入的供应商"
            >
              {connections.map((c) => (
                <button
                  type="button"
                  key={c.id}
                  aria-pressed={viewed === c.id}
                  onClick={() => {
                    setViewed(c.id);
                    setModel(
                      primary?.connectionId === c.id
                        ? primary.model
                        : c.models[0],
                    );
                    setMessage("");
                  }}
                >
                  <ProviderLogo provider={c.provider} />
                  <span>
                    {c.name}
                    <small>{c.models.length} 个模型</small>
                  </span>
                  {viewed === c.id && <Icon name="check" size={16} />}
                </button>
              ))}
            </div>
            {connection && (
              <div className="model-choice">
                <div className="model-choice-field">
                  <label htmlFor="primary-model-picker">主模型</label>
                  <Select
                    id="primary-model-picker"
                    label="主模型"
                    listLabel="可选主模型"
                    value={model}
                    options={connection.models.map((value) => ({
                      value,
                      label: value,
                    }))}
                    onChange={(value) => {
                      setModel(value);
                      setMessage("");
                    }}
                  />
                  <p className="field-hint">{connection.baseUrl}</p>
                </div>
                <button
                  type="button"
                  className="primary"
                  disabled={isPrimary || !__DEMO__}
                  onClick={() => {
                    modelPreview.choose(connection.id, model);
                    setMessage("已更新演示主模型，未发起模型调用。");
                  }}
                >
                  {isPrimary ? "当前主模型" : "设为主模型"}
                </button>
              </div>
            )}
            <div className="primary-model-summary">
              <span className="primary-model-icon">
                <Icon name="check" size={18} />
              </span>
              <div>
                <span className="muted">
                  {__DEMO__ ? "演示主模型" : "当前主模型"}
                </span>
                <strong>
                  {primary
                    ? `${primaryConnection?.name} / ${primary.model}`
                    : "尚未设置主模型"}
                </strong>
              </div>
            </div>
          </>
        ) : (
          <div className="models-empty">
            <span className="empty-icon">
              <Icon name="settings" size={25} />
            </span>
            <h3>暂无已导入的模型</h3>
            <p className="muted">从下方选择一个供应商，或自定义添加模型。</p>
          </div>
        )}
        <p className="field-hint model-preview-note">
          {__DEMO__
            ? "当前为交互演示，配置仅在本次页面会话中保留；刷新后重置，不保存 API Key，也不调用模型。"
            : "供应商导入与主模型保存尚未接入。当前学习仍使用官网服务端配置；下方可预览添加界面。"}
        </p>
      </section>
      <p role="status" className="model-status">
        {message}
      </p>
      <ProviderCatalog onAdded={added} />
    </>
  );
}

function ProviderCatalog({
  onAdded,
  localEnabled = false,
  onLocalAdded,
}: {
  onAdded?: (connection: ModelConnection) => void;
  localEnabled?: boolean;
  onLocalAdded?: (result: LocalProviderResult) => void;
}) {
  const [preset, setPreset] = useState<ProviderPreset>();
  const [filter, setFilter] = useState("");
  const [group, setGroup] = useState("全部");
  const categories = ["全部", "国内平台", "海外平台", "聚合中转", "本地服务"];
  const filtered = providerPresets.filter(
    (p) =>
      p.id === "custom" ||
      ((group === "全部" || p.group === group) &&
        `${p.name} ${p.subtitle} ${p.id}`
          .toLowerCase()
          .includes(filter.trim().toLowerCase())),
  );
  return (
    <>
      <section className="model-add-section" aria-labelledby="add-model-title">
        <div className="section-title">
          <div>
            <h2 id="add-model-title">添加新模型</h2>
            <p className="muted">
              {localEnabled
                ? "添加本机测试供应商：验证后在上方选择主模型。重启服务会清空添加的配置。"
                : __DEMO__
                  ? "使用自定义接口，或选择预设快速填写连接信息。"
                  : "查看预设或自定义配置；实际可用模型由官网网关统一提供。"}
            </p>
          </div>
        </div>
        <div className="provider-catalog-toolbar">
          <SearchField
            label="搜索模型供应商"
            placeholder="搜索供应商，例如 Kimi、OpenRouter…"
            value={filter}
            onChange={setFilter}
          />
          <span className="muted small">{filtered.length - 1} 个预设</span>
        </div>
        <div
          className="provider-categories"
          role="group"
          aria-label="供应商分类"
        >
          {categories.map((category) => (
            <button
              type="button"
              key={category}
              aria-pressed={group === category}
              onClick={() => setGroup(category)}
            >
              {category}
            </button>
          ))}
        </div>
        <div className="provider-grid">
          {filtered.map((p) => (
            <button
              type="button"
              key={p.id}
              className={`provider-preset ${p.id === "custom" ? "provider-custom" : ""}`}
              aria-label={p.id === "custom" ? p.name : `添加 ${p.name}`}
              aria-pressed={preset?.id === p.id}
              aria-expanded={preset?.id === p.id}
              aria-haspopup="dialog"
              aria-controls={preset?.id === p.id ? "provider-form" : undefined}
              onClick={() => {
                setPreset(p);
              }}
            >
              <ProviderLogo provider={p.id} />
              <span>
                <strong>{p.name}</strong>
                <small>{p.subtitle}</small>
              </span>
              <span className="provider-add-icon" aria-hidden="true">
                <Icon name="plus" size={17} />
              </span>
            </button>
          ))}
        </div>
        {filtered.length === 1 && (
          <p className="empty-inline">
            没有找到匹配的供应商，可以使用自定义添加。
          </p>
        )}
      </section>
      {preset && (
        <ProviderDialog
          key={preset.id}
          preset={preset}
          localEnabled={localEnabled}
          onLocalAdded={(result) => {
            setPreset(undefined);
            onLocalAdded?.(result);
          }}
          onClose={() => setPreset(undefined)}
          onAdded={(connection) => {
            setPreset(undefined);
            onAdded?.(connection);
          }}
        />
      )}
    </>
  );
}
