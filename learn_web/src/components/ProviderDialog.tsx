import { useEffect, useRef, useState, type FormEvent } from "react";
import { Input } from "./fields";
import Select from "./Select";
import ProviderLogo from "./ProviderLogo";
import { AutoTextarea, Icon } from "./ui";
import { addLocalProvider, type LocalProviderResult } from "../models/local";
import type { ProviderPreset } from "../models/presets";
import {
  modelPreview,
  useModelPreview,
  type ModelConnection,
} from "../models/preview";

type Props = {
  preset: ProviderPreset;
  localEnabled?: boolean;
  onLocalAdded?: (result: LocalProviderResult) => void;
  onClose: () => void;
  onAdded: (connection: ModelConnection) => void;
};

export default function ProviderDialog({
  preset,
  onClose,
  onAdded,
  localEnabled = false,
  onLocalAdded,
}: Props) {
  const { connections } = useModelPreview();
  const dialog = useRef<HTMLDialogElement>(null);
  const nameInput = useRef<HTMLInputElement>(null);
  const [name, setName] = useState(preset.id === "custom" ? "" : preset.name);
  const [remark, setRemark] = useState("");
  const [website, setWebsite] = useState(preset.website);
  const [baseUrl, setBaseUrl] = useState(preset.baseUrl);
  const [models, setModels] = useState(preset.models.join("\n"));
  const [error, setError] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [saving, setSaving] = useState(false);
  const inFlight = useRef<AbortController | null>(null);
  const currentProfile =
    preset.profiles.find((p) => p.value === baseUrl)?.value || "__custom__";

  useEffect(() => {
    const element = dialog.current!;
    const previous = document.activeElement as HTMLElement | null;
    const overflow = document.body.style.overflow;
    element.showModal();
    document.body.style.overflow = "hidden";
    nameInput.current?.focus({ preventScroll: true });
    return () => {
      inFlight.current?.abort();
      element.close();
      document.body.style.overflow = overflow;
      if (previous?.isConnected) previous.focus({ preventScroll: true });
    };
  }, []);

  async function add(event: FormEvent) {
    event.preventDefault();
    if ((!__DEMO__ && !localEnabled) || inFlight.current) return;
    let url: URL;
    try {
      url = new URL(baseUrl.trim());
      if (
        !["http:", "https:"].includes(url.protocol) ||
        url.username ||
        url.password ||
        url.search ||
        url.hash
      )
        throw new Error();
    } catch {
      setError("请填写有效的 API 根地址，不包含账号密码、查询参数或密钥。");
      return;
    }
    if (website.trim()) {
      try {
        const site = new URL(website.trim());
        if (
          !["http:", "https:"].includes(site.protocol) ||
          site.username ||
          site.password
        )
          throw new Error();
      } catch {
        setError("请填写有效的官网链接，或留空。");
        return;
      }
    }
    const ids = [
      ...new Set(
        models
          .split(/[\n,，]+/)
          .map((m) => m.trim())
          .filter(Boolean),
      ),
    ];
    if (!name.trim() || !ids.length) {
      setError("请填写供应商名称和至少一个模型 ID。");
      return;
    }
    if (__DEMO__ && connections.some((c) => c.name === name.trim())) {
      setError("这个供应商名称已存在，请添加一个不同的备注名称。");
      return;
    }
    if (localEnabled) {
      if (!apiKey.trim()) {
        setError("请填写 API Key。");
        return;
      }
      const controller = new AbortController();
      inFlight.current = controller;
      setSaving(true);
      setError("");
      try {
        const result = await addLocalProvider(
          {
            provider: preset.id,
            name: name.trim(),
            remark: remark.trim(),
            website: website.trim(),
            baseUrl: url.href.replace(/\/$/, ""),
            models: ids,
            apiKey: apiKey.trim(),
          },
          controller.signal,
        );
        if (!controller.signal.aborted) {
          setApiKey("");
          onLocalAdded?.(result);
        }
      } catch (cause) {
        if (!controller.signal.aborted)
          setError(
            cause instanceof Error
              ? cause.message
              : "添加失败，请检查连接后重试。",
          );
      } finally {
        inFlight.current = null;
        if (!controller.signal.aborted) setSaving(false);
      }
      return;
    }
    const added = modelPreview.add({
      provider: preset.id,
      name: name.trim(),
      remark: remark.trim(),
      website: website.trim(),
      baseUrl: url.href.replace(/\/$/, ""),
      models: ids,
    });
    onAdded(added);
  }

  return (
    <dialog
      ref={dialog}
      className="provider-dialog"
      aria-labelledby="provider-dialog-title"
      aria-describedby="provider-dialog-description"
      onKeyDown={(event) => {
        if (event.key !== "Tab") return;
        const fields = Array.from(
          event.currentTarget.querySelectorAll<HTMLElement>(
            'button:not(:disabled), input:not(:disabled), textarea:not(:disabled), a[href], [tabindex]:not([tabindex="-1"])',
          ),
        ).filter((element) => element.getClientRects().length > 0);
        const first = fields[0];
        const last = fields[fields.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last?.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first?.focus();
        }
      }}
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onClick={(event) => {
        if (event.target !== event.currentTarget) return;
        const box = event.currentTarget.getBoundingClientRect();
        if (
          event.clientX < box.left ||
          event.clientX > box.right ||
          event.clientY < box.top ||
          event.clientY > box.bottom
        )
          onClose();
      }}
    >
      <form
        id="provider-form"
        className="provider-form"
        aria-label={`${preset.name}连接设置`}
        onSubmit={add}
      >
        <header className="provider-dialog-header">
          <button
            type="button"
            className="icon-button provider-dialog-back"
            aria-label="返回模型设置"
            onClick={onClose}
          >
            <span aria-hidden="true">←</span>
          </button>
          <div>
            <h2 id="provider-dialog-title">添加新供应商</h2>
            <p className="muted">
              {preset.id === "custom" ? "自定义配置" : preset.name}
            </p>
          </div>
          <button
            type="button"
            className="icon-button provider-dialog-close"
            aria-label="关闭添加模型"
            onClick={onClose}
          >
            <span aria-hidden="true">×</span>
          </button>
        </header>
        <div className="provider-dialog-body">
          <p className="field-hint" id="provider-dialog-description">
            {preset.note}
          </p>
          <div className="provider-dialog-emblem" aria-hidden="true">
            <ProviderLogo
              provider={preset.id}
              customMark={name.trim().slice(0, 1).toUpperCase() || "P"}
            />
          </div>
          <div className="provider-fields">
            <label>
              供应商名称
              <Input
                ref={nameInput}
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="例如：我的模型服务"
                required
                maxLength={80}
              />
            </label>
            <label>
              备注
              <Input
                value={remark}
                onChange={(e) => setRemark(e.target.value)}
                placeholder="例如：学习专用账号（可选）"
                maxLength={200}
              />
            </label>
            <label className="provider-wide-field">
              官网链接
              <Input
                value={website}
                onChange={(e) => setWebsite(e.target.value)}
                placeholder="https://example.com（可选）"
                type="url"
                maxLength={500}
              />
            </label>
            <div className="provider-wide-field">
              <label htmlFor="provider-key">API Key</label>
              <Input
                id="provider-key"
                type="password"
                value={apiKey}
                onChange={(event) => setApiKey(event.target.value)}
                autoComplete="off"
                maxLength={4096}
                required={localEnabled}
                disabled={!localEnabled || saving}
                placeholder={
                  localEnabled
                    ? "粘贴该供应商的 API Key"
                    : __DEMO__
                      ? "演示模式无需填写真实 API Key"
                      : "API Key 由官网网关统一管理"
                }
              />
              <p className="field-hint">
                {localEnabled
                  ? "仅用于本机测试，Key 保留在本次服务内存中，重启后需重新添加。"
                  : __DEMO__
                    ? "本页仅演示配置流程，请勿填写真实密钥。"
                    : "当前学习使用官网网关，无需在此填写个人密钥。"}
              </p>
            </div>
            {preset.profiles.length > 1 && (
              <div className="provider-wide-field provider-profile">
                <label htmlFor="provider-profile">接口区域 / 服务方案</label>
                <Select
                  id="provider-profile"
                  label="接口区域 / 服务方案"
                  value={currentProfile}
                  options={[
                    ...preset.profiles,
                    { label: "自定义地址", value: "__custom__" },
                  ]}
                  onChange={(value) =>
                    setBaseUrl(value === "__custom__" ? "" : value)
                  }
                />
              </div>
            )}
            <label className="provider-wide-field">
              API 地址
              <Input
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
                placeholder="https://api.example.com/v1"
                type="url"
                required
                maxLength={500}
              />
            </label>
            <div className="provider-wide-field">
              <label htmlFor="provider-model-ids">模型 ID</label>
              <AutoTextarea
                id="provider-model-ids"
                value={models}
                onChange={(e) => setModels(e.target.value)}
                placeholder="填写完整模型 ID，每行一个"
                required
                maxLength={8000}
              />
              <p className="field-hint">
                每行一个，也可用逗号分隔。预设仅供参考，以供应商实际提供的模型为准。
              </p>
            </div>
          </div>
        </div>
        <footer className="provider-dialog-footer">
          {error && (
            <p className="error-notice" role="alert">
              {error}
            </p>
          )}
          <p className="field-hint">
            {localEnabled
              ? "验证模型目录后添加，不发起付费生成请求。暂支持公开 HTTPS OpenAI 兼容服务。"
              : __DEMO__
                ? "本地交互演示 · 配置刷新后重置"
                : "配置预览 · 不保存、不改变当前网关"}
          </p>
          <div className="provider-form-actions">
            <button type="button" onClick={onClose}>
              取消
            </button>
            <button
              className="primary"
              disabled={saving || (!__DEMO__ && !localEnabled)}
            >
              <Icon name="plus" size={18} />
              {saving
                ? "正在验证…"
                : localEnabled
                  ? "验证并添加"
                  : __DEMO__
                    ? "添加到演示列表"
                    : "由官网网关管理"}
            </button>
          </div>
        </footer>
      </form>
    </dialog>
  );
}
