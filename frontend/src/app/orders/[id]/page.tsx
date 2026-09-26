"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useRef, useState } from "react";
import { AssetPanel } from "@/components/orders/asset-panel";
import { GenerationPanel } from "@/components/orders/generation-panel";
import { ParamsPanel } from "@/components/orders/params-panel";
import { apiGet, apiRequest, errorMessage } from "@/lib/api";
import { INITIAL_RUNTIME, type WorkspaceRuntime } from "@/lib/workspace-state";
import type { Asset, OrderDetail, OrderParams, OrderStatus } from "@/types/orders";

function BasicInfo({ order, actionTarget }: { order: OrderDetail; actionTarget: (node: HTMLDivElement | null) => void }) {
  return <section className="order-panel metadata-panel" aria-label="订单信息">
    <div className="metadata-item"><span className="metadata-label">客户：</span><span className="metadata-value" title={order.customer_name}>{order.customer_name}</span></div>
    <div className="metadata-item"><span className="metadata-label">订单备注：</span><span className="metadata-value" title={order.note}>{order.note || "—"}</span></div>
    <div className="metadata-lifecycle" ref={actionTarget} />
  </section>;
}

function OrderWorkspace({ initial }: { initial: OrderDetail }) {
  const [order, setOrder] = useState(initial);
  const [busyCount, setBusyCount] = useState(0);
  const [dirty, setDirty] = useState(false);
  const [baseError, setBaseError] = useState("");
  const selectingBase = useRef(false);
  const [runtime, setRuntime] = useState<WorkspaceRuntime>(INITIAL_RUNTIME);
  const [actionTarget, setActionTarget] = useState<HTMLDivElement | null>(null);
  const onBusy = useCallback((busy: boolean) => setBusyCount((n) => Math.max(0, n + (busy ? 1 : -1))), []);
  const onStatus = useCallback((status: OrderStatus) => setOrder((current) => current.status === status ? current : { ...current, status }), []);
  const onRuntime = useCallback((next: WorkspaceRuntime) => setRuntime((old) => JSON.stringify(old) === JSON.stringify(next) ? old : next), []);
  const updated = useCallback((data: OrderDetail) => { setOrder(data); }, []);
  const readonly = order.status === "completed" || order.status === "closed";
  const busy = busyCount > 0;
  const taskLocked = runtime.hasOpen || runtime.pending || !runtime.loaded;
  return <>
    <Link className="back-link" href="/orders">← 我的订单</Link>
    <BasicInfo order={order} actionTarget={setActionTarget} />
    <div className="order-workbench">
      <div className="order-config">
        {order.params.mode !== "generate" && <AssetPanel kind="main" order={order} disabled={busy || readonly || taskLocked} onBusy={onBusy} onChange={updated} />}
        <ParamsPanel key={`${order.id}:${JSON.stringify(order.params)}`} order={order} archived={readonly} disabled={busy || readonly || taskLocked} onBusy={onBusy} onDirty={setDirty} onSave={updated}
          materialsPanel={<AssetPanel order={order} disabled={busy || readonly || taskLocked} onBusy={onBusy} onChange={updated} />} />
      </div>
      <div className="order-result" id="order-result">
        <GenerationPanel order={order} actionTarget={actionTarget} disabled={busy || readonly || dirty} dirty={dirty} baseError={baseError} onBusy={onBusy} onStatus={onStatus} onRuntime={onRuntime} onBase={async (asset: Asset, config?: OrderParams) => {
          if (selectingBase.current || busy || readonly || taskLocked || dirty) return;
          selectingBase.current = true; onBusy(true); setBaseError("");
          try {
            updated(await apiRequest<OrderDetail>(`/orders/${order.id}/params`, { method: "PATCH", body: {
              ...order.params, changes: [], extra_requirement: "", style_id: null,
              region_asset_id: null, region_prompts: [], ...config, base_asset_id: asset.id,
              mode: "edit", mask: null, mask_base_asset_id: null,
            } }));
          } catch (cause) { setBaseError(errorMessage(cause)); }
          finally { selectingBase.current = false; onBusy(false); }
        }} />
      </div>
    </div>
  </>;
}

export default function OrderDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [data, setData] = useState<{ order: OrderDetail } | null>(null);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    const signal = AbortSignal.any([controller.signal, AbortSignal.timeout(15000)]);
    void apiGet<OrderDetail>(`/orders/${id}`, signal)
      .then((order) => { if (!controller.signal.aborted) { setData({ order }); setError(""); } })
      .catch((cause) => { if (!controller.signal.aborted) setError(errorMessage(cause)); });
    return () => controller.abort();
  }, [id, retry]);
  if (error) return <div className="order-alert" role="alert">{error} <button className="text-button" onClick={() => { setError(""); setRetry((n) => n + 1); }}>重新加载</button></div>;
  if (!data || data.order.id !== id) return <p className="muted" role="status">正在读取订单…</p>;
  return <OrderWorkspace key={`${id}:${retry}`} initial={data.order} />;
}
