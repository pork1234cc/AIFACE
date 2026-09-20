"use client";

import { useState } from "react";
import { apiRequest, errorMessage } from "@/lib/api";
import type { OrderDetail, OrderParams } from "@/types/orders";

export function ParamsPanel({ order, disabled, onSave, onBusy, onDirty }: {
  order: OrderDetail; disabled: boolean; onSave: (order: OrderDetail) => void;
  onBusy: (busy: boolean) => void; onDirty: (dirty: boolean) => void;
}) {
  const [params, setParams] = useState(order.params);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const active = order.assets.filter((a) => a.kind === "input" && a.is_active_input);
  const people = active.filter((a) => a.input_role !== "reference");
  const clothes = active.filter((a) => params.clothes_mode === "reference" ? a.input_role === "reference" : a.input_role !== "reference");
  function change(patch: Partial<OrderParams>) { setParams({ ...params, ...patch }); onDirty(true); setSaved(false); }
  return <section className="order-panel"><h2>创作要求</h2><p className="muted">人物来自主照片，发型与服装可分别指定来源。</p>
    {error && <div className="order-alert" role="alert">{error}</div>}
    {saved && <p className="order-notice" role="status">创作要求已保存。</p>}
    <form onSubmit={async (event) => {
      event.preventDefault(); onBusy(true); setError("");
      try {
        const updated = await apiRequest<OrderDetail>(`/orders/${order.id}/params`, { method: "PATCH", body: params });
        onDirty(false); setSaved(true); onSave(updated);
      } catch (cause) { setError(errorMessage(cause)); }
      finally { onBusy(false); }
    }}><fieldset className="order-form" disabled={disabled}>
      <label>发型来源<select value={params.hair_source_asset_id ?? ""} onChange={(event) => change({ hair_source_asset_id: event.target.value || null })}><option value="">请选择本人照片</option>{people.map((asset) => <option key={asset.id} value={asset.id}>{asset.original_name}{asset.input_role === "person_main" ? "（主照片）" : "（辅助）"}</option>)}</select></label>
      <label className="check-label"><input type="checkbox" checked={params.glasses_keep} onChange={(event) => change({ glasses_keep: event.target.checked })} />保留原有眼镜（取消勾选则去掉）</label>
      <label>服装处理<select value={params.clothes_mode} onChange={(event) => change({ clothes_mode: event.target.value as OrderParams["clothes_mode"], clothes_source_asset_id: null })}><option value="simplified">简化处理</option><option value="person">跟本人照片</option><option value="reference">跟参考图</option></select></label>
      {params.clothes_mode !== "simplified" && <label>服装来源<select required value={params.clothes_source_asset_id ?? ""} onChange={(event) => change({ clothes_source_asset_id: event.target.value || null })}><option value="">请选择来源图片</option>{clothes.map((asset) => <option key={asset.id} value={asset.id}>{asset.original_name}</option>)}</select>{clothes.length === 0 && <span className="muted">请先上传并设置对应角色的素材。</span>}</label>}
      <label>额外要求<textarea maxLength={2000} rows={4} value={params.extra_requirement} onChange={(event) => change({ extra_requirement: event.target.value })} placeholder="例如：头发蓬松一点，脸不要太尖" /></label>
      <div className="style-tags"><span>固定白底</span><span>1:1 方形</span><span>交付图 1 张</span></div>
      <div className="order-actions"><button className="order-button primary">保存创作要求</button><button type="button" className="order-button" onClick={() => { setParams(order.params); setError(""); setSaved(false); onDirty(false); }}>撤销未保存修改</button></div>
    </fieldset></form>
  </section>;
}
