"use client";

import Image from "next/image";
import { useRef, useState } from "react";
import { apiRequest, errorMessage } from "@/lib/api";
import { type OrderDetail, type Role, roleLabels } from "@/types/orders";

export function AssetPanel({ order, disabled, onChange, onBusy }: {
  order: OrderDetail; disabled: boolean; onChange: (order: OrderDetail) => void; onBusy: (busy: boolean) => void;
}) {
  const [error, setError] = useState("");
  const formRef = useRef<HTMLFormElement>(null);
  const active = order.assets.filter((a) => a.kind === "input" && a.is_active_input);
  const removed = order.assets.filter((a) => a.kind === "input" && !a.is_active_input);
  const base = `/orders/${order.id}`;
  async function update(id: string, action: "role" | "active", body: unknown) {
    onBusy(true); setError("");
    try { onChange(await apiRequest<OrderDetail>(`${base}/images/${id}/${action}`, { method: "PATCH", body })); }
    catch (cause) { setError(errorMessage(cause)); }
    finally { onBusy(false); }
  }
  function roleSelect(id: string, role: Role) {
    return <select aria-label="图片角色" value={role} disabled={disabled} onChange={(event) => void update(id, "role", { role: event.target.value })}>
      {Object.entries(roleLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
    </select>;
  }
  return <section className="order-panel">
    <div className="section-heading"><h2>照片与参考</h2><span className="pill">{active.length} / 4 张</span></div>
    <p className="muted">主照片确定人物，辅助照片补充细节。参考图仅参考局部元素。</p>
    {error && <div className="order-alert" role="alert">{error}</div>}
    <form ref={formRef} onSubmit={async (event) => {
      event.preventDefault();
      const data = new FormData(event.currentTarget);
      const file = data.get("file");
      if (!(file instanceof File) || file.size === 0) { setError("请选择一张图片"); return; }
      if (file.size > 20 * 1024 * 1024) { setError("单张图片不能超过 20 MiB"); return; }
      onBusy(true); setError("");
      try {
        await apiRequest(`${base}/images`, { method: "POST", body: data });
        formRef.current?.reset();
        onChange(await apiRequest<OrderDetail>(base));
      } catch (cause) { setError(errorMessage(cause)); }
      finally { onBusy(false); }
    }}><fieldset disabled={disabled || active.length >= 4} className="order-form">
      <div className="form-columns"><label>添加图片<input name="file" type="file" accept="image/jpeg,image/png,image/webp" required /></label><label>素材角色<select name="role" defaultValue="person_aux"><option value="person_aux">辅助照片</option><option value="person_main" disabled={active.some((a) => a.input_role === "person_main")}>主照片</option><option value="reference" disabled={active.some((a) => a.input_role === "reference")}>参考图</option></select></label></div>
      <div className="order-actions"><button className="order-button">上传图片</button><span className="muted">JPEG / PNG / WebP · ≤ 20 MiB · ≤ 4000 万像素</span></div>
    </fieldset></form>
    {active.length === 0 && <div className="empty-state"><h3>还没有照片</h3><p>上传一张主照片，开始整理这份委托。</p></div>}
    <div className="asset-grid">{active.map((asset, index) => <article className="asset-card" key={asset.id}>
      <a className="asset-preview" href={asset.content_url} target="_blank" rel="noreferrer" aria-label={`查看大图：${asset.original_name}`}><Image src={asset.content_url} alt={asset.original_name} fill unoptimized sizes="(max-width: 560px) 40vw, 260px" /></a>
      <div className="asset-info"><p className="asset-name">{index + 1}. {asset.original_name}</p><small>{asset.width} × {asset.height} · {(asset.byte_size / 1024 / 1024).toFixed(2)} MiB</small>{roleSelect(asset.id, asset.input_role)}<div className="order-actions"><a href={asset.content_url} target="_blank" rel="noreferrer" className="muted">查看大图 ↗</a><button className="order-button small" disabled={disabled} onClick={() => void update(asset.id, "active", { active: false })}>移出素材</button></div></div>
    </article>)}</div>
    {active.length >= 4 && <p className="muted">当前素材已满。移出不需要的图片后，可继续上传。</p>}
    {removed.length > 0 && <details className="removed-list"><summary>已移出的素材（{removed.length}）· 原文件保留</summary>{removed.map((asset) => <div className="removed-row" key={asset.id}>
      <a href={asset.content_url} target="_blank" rel="noreferrer">{asset.original_name}</a>{roleSelect(asset.id, asset.input_role)}<button className="order-button small" disabled={disabled || active.length >= 4} onClick={() => void update(asset.id, "active", { active: true })}>恢复</button>
    </div>)}</details>}
  </section>;
}
