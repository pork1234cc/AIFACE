"use client";

import { useEffect, useRef, useState } from "react";
import { apiGet, apiRequest, errorMessage } from "@/lib/api";
import { compactConfig, materialSlots } from "@/lib/creation-config";
import { validParamsDraft } from "@/lib/order-drafts";
import { useSessionDraft } from "@/hooks/use-session-draft";
import { useLeaveGuard } from "@/hooks/use-leave-guard";
import { aspectSizes, type OrderDetail, type Style } from "@/types/orders";

export function ParamsPanel({ order, disabled, archived = false, onSave, onBusy, onDirty, materialsPanel }: {
  order: OrderDetail; disabled: boolean; archived?: boolean; onSave: (order: OrderDetail) => void;
  onBusy: (busy: boolean) => void; onDirty: (dirty: boolean) => void;
  materialsPanel?: React.ReactNode;
}) {
  const draft = useSessionDraft(`aiface:v2:draft:params:${order.id}`, compactConfig(order), validParamsDraft);
  const [error, setError] = useState("");
  const [styles, setStyles] = useState<Style[]>([]);
  const [styleError, setStyleError] = useState("");
  const [reload, setReload] = useState(0);
  const running = useRef(false);
  const dirty = draft.dirty && !archived;
  useLeaveGuard(dirty);
  useEffect(() => { onDirty(dirty); return () => onDirty(false); }, [dirty, onDirty]);
  useEffect(() => {
    const controller = new AbortController();
    void apiGet<{ items: Style[] }>("/styles", controller.signal).then((data) => { setStyles(data.items); setStyleError(""); })
      .catch((cause) => { if (!controller.signal.aborted) setStyleError(errorMessage(cause)); });
    return () => controller.abort();
  }, [reload]);
  const locked = disabled || archived || !draft.restored;
  const config = compactConfig({ ...order, params: archived ? order.params : {
    ...draft.value, material_slots: materialSlots(order), base_asset_id: order.params.base_asset_id,
  } });
  return <>
    <section className="order-panel compact-style">
      {styleError && <p className="order-alert" role="alert">{styleError} <button className="text-button" onClick={() => setReload((n) => n + 1)}>重试</button></p>}
      <div className="style-output-row">
        <label>风格<select disabled={locked} value={config.style_id ?? ""} onChange={(event) => draft.change({ ...config, style_id: event.target.value || null })}>
          <option value="">保持原图风格</option>
          {!styles.some((style) => style.style_id === config.style_id) && config.style_id && <option value={config.style_id}>{config.style_id === "q_crayon_001" ? "柔彩蜡笔" : "当前自定义风格"}</option>}
          {styles.map((style) => <option key={style.style_id} value={style.style_id}>{style.style_name}</option>)}
        </select></label>
        <label>生图尺寸<select disabled={locked} value={config.aspect_ratio} onChange={(event) => draft.change({ ...config, aspect_ratio: event.target.value })}>{Object.keys(aspectSizes).map((ratio) => <option key={ratio}>{ratio}</option>)}</select></label>
        <label>生图格式<select disabled={locked} value={config.output_format} onChange={(event) => draft.change({ ...config, output_format: event.target.value as "png" | "jpeg" | "webp" })}>
          <option value="png">PNG</option><option value="jpeg">JPEG</option><option value="webp">WebP</option>
        </select></label>
      </div>
    </section>
    {materialsPanel}
    <section className="order-panel params-panel" id="order-requirements"><h2>完整提示词</h2>
      {error && <p className="order-alert" role="alert">{error}</p>}
      {draft.storageWarning && <p className="order-alert">{draft.storageWarning}</p>}
      <form onSubmit={async (event) => {
        event.preventDefault();
        if (running.current || locked) return;
        if (draft.value.changes.some((change) => change.source_asset_ids.some((id) => !config.material_slots?.includes(id)))) {
          setError("原修改项引用了已移出的素材，请在完整提示词中重新指定素材后保存"); return;
        }
        if (config.extra_requirement.length > 2000) { setError("完整提示词不能超过2000字，请精简后保存"); return; }
        running.current = true; onBusy(true); setError("");
        try {
          const updated = await apiRequest<OrderDetail>(`/orders/${order.id}/params`, { method: "PATCH", body: config });
          draft.reset(compactConfig(updated)); onDirty(false); onSave(updated);
        } catch (cause) { setError(errorMessage(cause)); }
        finally { running.current = false; onBusy(false); }
      }}>
        <textarea aria-label="完整提示词" rows={5} maxLength={2000} disabled={locked} value={config.extra_requirement} onChange={(event) => draft.change({ ...config, extra_requirement: event.target.value })} />
        {!archived && <div className="order-actions"><button className="order-button" disabled={locked}>{dirty ? "保存修改" : "保存配置"}</button>{dirty && <button type="button" disabled={locked} className="text-button" onClick={() => draft.reset(compactConfig(order))}>撤销修改</button>}</div>}
      </form>
    </section>
  </>;
}
