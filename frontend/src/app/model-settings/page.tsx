"use client";

import { useEffect, useState } from "react";
import { apiGet, apiRequest, errorMessage } from "@/lib/api";
import CodexSettings from "@/components/codex-settings";
import { IMAGE_MODELS } from "@/lib/image-options";

type ModelSettings = { api_url: string; model: string; quality: string; has_api_key: boolean };
const MODEL_OPTIONS = IMAGE_MODELS;

export default function ModelSettingsPage() {
  const [settings, setSettings] = useState<ModelSettings | null>(null);
  const [apiKey, setApiKey] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const [modelOpen, setModelOpen] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    void apiGet<ModelSettings>("/model-settings", controller.signal)
      .then((result) => { if (!controller.signal.aborted) setSettings(result); })
      .catch((cause) => { if (!controller.signal.aborted) setError(errorMessage(cause)); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, []);

  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!settings || saving) return;
    setSaving(true); setError(""); setSaved(false);
    try {
      const result = await apiRequest<ModelSettings>("/model-settings", {
        method: "PUT",
        body: { api_url: settings.api_url, model: settings.model, quality: settings.quality, api_key: apiKey },
      });
      setSettings(result); setApiKey(""); setSaved(true);
    } catch (cause) { setError(errorMessage(cause)); }
    finally { setSaving(false); }
  }

  const modelOptions = settings
    ? Array.from(new Set([settings.model, ...MODEL_OPTIONS].filter(Boolean)))
    : [...MODEL_OPTIONS];

  return <section className="model-settings-page">
    <div className="page-heading"><h1>模型设置</h1></div>
    {loading && <p role="status">正在读取模型设置…</p>}
    {error && <p className="order-alert" role="alert">{error}</p>}
    {settings && <form className="order-panel model-settings-form" onSubmit={(event) => void save(event)}>
      <label><span>接口 URL</span><input type="url" required value={settings.api_url} onChange={(event) => { setSettings({ ...settings, api_url: event.target.value }); setSaved(false); }} placeholder="https://ai.apii.cn" /></label>
      <label><span>模型 ID</span><div className="model-combobox">
        <div className="model-combobox-input"><input required maxLength={80} value={settings.model} onFocus={() => setModelOpen(true)} onChange={(event) => { setSettings({ ...settings, model: event.target.value }); setSaved(false); setModelOpen(true); }} aria-label="模型 ID" aria-expanded={modelOpen} aria-controls="model-id-options" role="combobox" /><button type="button" aria-label="展开模型 ID 选项" onMouseDown={(event) => event.preventDefault()} onClick={() => setModelOpen((open) => !open)}>▾</button></div>
        {modelOpen && <ul id="model-id-options" className="model-combobox-options" role="listbox" onMouseDown={(event) => event.preventDefault()}>
          {modelOptions.map((model) => <li key={model} role="option" aria-selected={settings.model === model} onClick={() => { setSettings({ ...settings, model }); setSaved(false); setModelOpen(false); }}>{model}</li>)}
        </ul>}
      </div></label>
      <label><span>质量</span><select value={settings.quality} onChange={(event) => { setSettings({ ...settings, quality: event.target.value }); setSaved(false); }}>
        <option value="auto">自动</option><option value="low">低</option><option value="medium">中</option><option value="high">高</option>
      </select></label>
      <label><span>API Key</span><input type="password" autoComplete="new-password" value={apiKey} onChange={(event) => { setApiKey(event.target.value); setSaved(false); }} placeholder={settings.has_api_key ? "已配置；留空则保持不变" : "输入 API Key"} /></label>
      <p className="muted">API Key 只保存在后端配置中，不会回传到浏览器。接口地址需支持现有的图片编辑与任务查询路径。</p>
      <div className="order-actions"><button className="order-button primary" type="submit" disabled={saving}>{saving ? "保存中…" : "保存模型设置"}</button>{saved && <span role="status">已保存</span>}</div>
    </form>}
    <CodexSettings />
  </section>;
}
