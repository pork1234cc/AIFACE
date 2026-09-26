"use client";

import { useEffect, useState } from "react";
import { apiGet, apiRequest, errorMessage } from "@/lib/api";
import styles from "./codex-settings.module.css";

type CodexStatus = {
  configured_path: string;
  resolved_path: string;
  source: string;
  available: boolean;
  version: string;
  message: string;
};

const SOURCES: Record<string, string> = {
  manual: "手动指定", PATH: "系统 PATH", desktop: "桌面版安装目录", npm: "npm 安装目录",
};

export default function CodexSettings() {
  const [path, setPath] = useState("");
  const [result, setResult] = useState<CodexStatus | null>(null);
  const [busy, setBusy] = useState("读取中");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    void apiGet<CodexStatus>("/model-settings/codex", controller.signal)
      .then((value) => {
        if (!controller.signal.aborted) { setResult(value); setPath(value.configured_path); }
      })
      .catch((cause) => { if (!controller.signal.aborted) setError(errorMessage(cause)); })
      .finally(() => { if (!controller.signal.aborted) setBusy(""); });
    return () => controller.abort();
  }, []);

  async function browse() {
    setBusy("请选择文件"); setError(""); setNotice("");
    try {
      const value = await apiRequest<{ path: string | null }>("/model-settings/codex/browse", { method: "POST", body: {} });
      if (value.path) { setPath(value.path); setResult(null); setNotice("已选择，点击保存后生效。"); }
      else setNotice("已取消选择，原设置保持不变。");
    } catch (cause) { setError(errorMessage(cause)); }
    finally { setBusy(""); }
  }

  async function detect() {
    setBusy("检测中"); setError(""); setNotice("");
    try {
      const value = await apiRequest<CodexStatus>("/model-settings/codex/detect", { method: "POST", body: { path: "" } });
      setPath(""); setResult(value); setNotice("已切换为自动检测，点击保存后生效。");
    } catch (cause) { setError(errorMessage(cause)); }
    finally { setBusy(""); }
  }

  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setBusy("保存中"); setError(""); setNotice("");
    try {
      const value = await apiRequest<CodexStatus>("/model-settings/codex", { method: "PUT", body: { path } });
      setResult(value); setPath(value.configured_path); setNotice("Codex 设置已保存，下次识别立即使用。");
    } catch (cause) { setError(errorMessage(cause)); }
    finally { setBusy(""); }
  }

  return <form className={`order-panel ${styles.panel}`} onSubmit={(event) => void save(event)}>
    <div><h2>图片元素识别 · Codex</h2><p className="muted">自动查找本机 Codex CLI，也可选择桌面版附带的 codex.exe。请使用当前 Windows 用户登录 Codex。</p></div>
    <div>
      <label htmlFor="codex-program-path">Codex 程序路径</label>
      <div className={styles.pathRow}>
        <input id="codex-program-path" value={path} maxLength={4096} disabled={Boolean(busy)} placeholder="留空自动检测，或选择 codex.exe" onChange={(event) => { setPath(event.target.value); setResult(null); setNotice(""); setError(""); }} />
        <button className="order-button" type="button" disabled={Boolean(busy)} onClick={() => void browse()}>浏览…</button>
        <button className="order-button" type="button" disabled={Boolean(busy)} onClick={() => void detect()}>自动检测</button>
      </div>
    </div>
    {result && <div className={styles.detection} role="status">
      <strong>{result.available ? "已检测到可用 Codex" : "Codex 尚不可用"}</strong>
      {result.available ? <><span>{result.version} · {SOURCES[result.source] || result.source}</span><code>{result.resolved_path}</code></> : <span>{result.message}</span>}
    </div>}
    <p className="muted">“浏览”会打开本机文件选择窗口；也可直接粘贴完整路径。清空路径并保存可恢复自动检测。检测仅验证程序可运行，图片识别还需要有效登录和模型权限。</p>
    {error && <p className="order-alert" role="alert">{error}</p>}
    <div className="order-actions"><button className="order-button primary" type="submit" disabled={Boolean(busy)}>保存 Codex 设置</button><span role="status">{busy ? `${busy}…` : notice}</span></div>
  </form>;
}
