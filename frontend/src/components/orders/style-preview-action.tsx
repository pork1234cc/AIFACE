"use client";

import { useRef, useState, type FormEvent } from "react";
import { ApiError, apiGet, apiRequest, errorMessage } from "@/lib/api";
import { parsePreviewPending, previewBusy, previewLabel } from "@/lib/style-previews";
import type { Style } from "@/types/orders";

export function StylePreviewAction({ style, onUpdated, onMessage }: {
  style: Style; onUpdated: (style: Style) => void; onMessage: (message: string) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [reconcile, setReconcile] = useState(false);
  const [action, setAction] = useState("link_remote_task");
  const [remoteId, setRemoteId] = useState("");
  const [note, setNote] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [error, setError] = useState("");
  const sending = useRef(false);

  async function generate() {
    if (style.preview?.status === "submission_unknown") { setReconcile(true); return; }
    if (sending.current || previewBusy(style)) return;
    sending.current = true; setBusy(true);
    const storageKey = `aiface:style-preview:${style.style_id}`;
    try {
      let result: Style;
      if (style.preview?.can_resume_download) {
        result = await apiRequest<Style>(`/styles/${style.style_id}/previews/${style.preview.task_id}/resume`, { method: "POST" });
      } else {
        let pending = parsePreviewPending(sessionStorage.getItem(storageKey));
        if (pending?.key === style.preview?.request_key) pending = null;
        if (!pending) {
          if (!window.confirm("生成示意图会调用模型并产生费用。确定生成吗？")) return;
          pending = { key: crypto.randomUUID(), version: Number(style.version) };
        }
        // 先保存请求编号，网络中断时仍复用同一次提交，避免重复付费。
        sessionStorage.setItem(storageKey, JSON.stringify(pending));
        result = await apiRequest<Style>(`/styles/${style.style_id}/previews`, {
          method: "POST", body: { expected_version: pending.version }, idempotencyKey: pending.key,
        });
        sessionStorage.removeItem(storageKey);
      }
      onUpdated(result); onMessage("示意图任务已提交，完成后自动更新封面。可以离开页面，后台会继续处理。");
    } catch (cause) {
      if (cause instanceof ApiError && cause.status >= 400 && cause.status < 500) {
        sessionStorage.removeItem(storageKey);
      }
      onMessage(errorMessage(cause));
      try { onUpdated(await apiGet<Style>(`/styles/${style.style_id}`)); }
      catch { /* 保留提交编号，下一次点击继续核对同一请求。 */ }
    } finally { sending.current = false; setBusy(false); }
  }

  async function submitReconcile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!style.preview || sending.current) return;
    sending.current = true; setBusy(true); setError("");
    try {
      const result = await apiRequest<Style>(`/styles/${style.style_id}/previews/${style.preview.task_id}/reconcile`, {
        method: "POST", body: { action, note: note.trim(),
          provider_task_id: action === "link_remote_task" ? remoteId.trim() : null,
          confirmed_not_accepted: confirmed },
      });
      onUpdated(result); setReconcile(false); onMessage("核对结果已保存。");
    } catch (cause) { setError(errorMessage(cause)); }
    finally { sending.current = false; setBusy(false); }
  }

  return <>
    <button className="style-preview-action" type="button" disabled={busy || previewBusy(style)} onClick={() => void generate()} title="使用统一示例底图生成；调用模型会产生费用">
      {busy ? "提交中…" : previewLabel(style)}
    </button>
    {reconcile && <dialog open className="style-dialog" aria-label="核对示意图任务">
      <form className="order-form" onSubmit={submitReconcile}>
        <h3>核对示意图任务</h3>
        <p>提交结果不明。请先检查供应商记录，避免重复生成和计费。</p>
        <label>核对方式<select value={action} disabled={busy} onChange={(event) => setAction(event.target.value)}>
          <option value="link_remote_task">关联已受理的供应商任务</option>
          <option value="confirm_not_accepted">确认供应商未受理</option>
        </select></label>
        {action === "link_remote_task" ? <label>供应商任务编号<input required maxLength={128} pattern="[a-zA-Z0-9_-]+" value={remoteId} disabled={busy} onChange={(event) => setRemoteId(event.target.value)} /></label>
          : <label className="check-label"><input type="checkbox" required checked={confirmed} disabled={busy} onChange={(event) => setConfirmed(event.target.checked)} />我已核对供应商记录，确认此任务未受理</label>}
        <label>核对说明<textarea required minLength={5} maxLength={1000} value={note} disabled={busy} onChange={(event) => setNote(event.target.value)} /></label>
        {error && <p role="alert">{error}</p>}
        <div className="style-editor-actions"><button className="order-button" type="submit" disabled={busy}>保存核对结果</button><button className="order-button" type="button" disabled={busy} onClick={() => setReconcile(false)}>取消</button></div>
      </form>
    </dialog>}
  </>;
}
