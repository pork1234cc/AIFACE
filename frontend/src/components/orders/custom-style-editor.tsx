"use client";

import { useRef, useState, type FormEvent } from "react";
import { apiRequest, errorMessage } from "@/lib/api";
import type { Style } from "@/types/orders";

export function CustomStyleEditor({ style, onSaved, onCancel }: {
  style: Style | null; onSaved: (style: Style) => void; onCancel: () => void;
}) {
  const [name, setName] = useState(style?.style_name ?? "");
  const [description, setDescription] = useState(style?.description ?? "");
  const [prompt, setPrompt] = useState(style?.prompt_template.system_style ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const submitting = useRef(false);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting.current) return;
    if (!name.trim() || !prompt.trim()) { setError("请填写风格名称和提示词，不能只填空格。"); return; }
    submitting.current = true;
    setSaving(true); setError("");
    try {
      const result = await apiRequest<Style>(style ? `/styles/${style.style_id}` : "/styles", {
        method: style ? "PUT" : "POST",
        body: { style_name: name.trim(), description: description.trim(), prompt: prompt.trim(),
          ...(style ? { expected_version: Number(style.version) } : {}) },
      });
      onSaved(result);
    } catch (cause) { setError(errorMessage(cause)); }
    finally { submitting.current = false; setSaving(false); }
  }

  return <dialog open className="style-dialog" aria-label={style ? "编辑自定义风格" : "新建自定义风格"}>
    <form className="order-form" onSubmit={save}>
      <h3>{style ? "编辑自定义风格" : "新建自定义风格"}</h3>
      <p className="muted">描述配色、笔触、质感等表现方式。具体人物、动作或物品修改请填写在订单要求中。</p>
      <label>风格名称<input autoFocus required maxLength={60} value={name} disabled={saving} onChange={(event) => setName(event.target.value)} placeholder="例如：清透水彩" /></label>
      <label>简短说明（可选）<input maxLength={200} value={description} disabled={saving} onChange={(event) => setDescription(event.target.value)} placeholder="用于卡片展示" /></label>
      <label>风格提示词<textarea required rows={8} maxLength={4000} value={prompt} disabled={saving} onChange={(event) => setPrompt(event.target.value)} placeholder="例如：使用清透水彩晕染、柔和配色与细腻纸张纹理。" /></label>
      <small className="muted">{prompt.length} / 4000 字。保存后可在订单中选择；后续修改不影响已有任务和图片。</small>
      {error && <p className="order-alert" role="alert">{error}</p>}
      <div className="style-editor-actions">
        <button type="submit" className="order-button primary" disabled={saving}>{saving ? "保存中…" : "保存自定义风格"}</button>
        <button type="button" className="order-button" disabled={saving} onClick={onCancel}>取消</button>
      </div>
    </form>
  </dialog>;
}
