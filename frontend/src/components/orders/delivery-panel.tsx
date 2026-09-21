"use client";

import Image from "next/image";
import { createPortal } from "react-dom";
import { useRef, useState } from "react";
import { apiRequest, errorMessage } from "@/lib/api";
import { fetchDelivery } from "@/lib/delivery";
import { canSwitchFinal, versionDeliveryAction } from "@/lib/workspace-state";
import type { DeliveryState } from "@/types/deliveries";
import type { Asset, OrderDetail, OrderStatus } from "@/types/orders";

export function DeliveryPanel({ data, actionTarget, disabled, loaded, pending, revisionDirty, revision, onBusy, onChange, onStatus, onRevise, onLog }: {
  data: DeliveryState; actionTarget: HTMLDivElement | null; disabled: boolean; loaded: boolean; pending: boolean; revisionDirty: boolean;
  revision?: React.ReactNode; onBusy: (busy: boolean) => void;
  onChange: (value: DeliveryState) => void; onStatus: (status: OrderStatus) => void; onRevise: (asset: Asset) => void;
  onLog: (message: string, level?: "info" | "error") => void;
}) {
  const [working, setWorking] = useState(false);
  const [confirm, setConfirm] = useState<{ kind: "complete" | "close"; assetId: string | null } | null>(null);
  const running = useRef(false);
  const current = data.versions.find((asset) => asset.id === data.items[0]?.asset_id);
  const readonly = data.order_status === "completed" || data.order_status === "closed";
  const mutable = canSwitchFinal({ readonly, busy: disabled || working, loaded, hasOpen: data.has_open_tasks, pending, dirty: revisionDirty });
  const canDownload = !!current && loaded && !working && !pending && !data.has_open_tasks;
  const currentVersion = current ? data.versions.findIndex((asset) => asset.id === current.id) + 1 : 0;
  const selectionChanged = confirm?.kind === "complete" && confirm.assetId !== current?.id;
  async function run(action: () => Promise<void>) {
    if (running.current) return;
    running.current = true; setWorking(true); onBusy(true);
    try { await action(); }
    catch (cause) { onLog(errorMessage(cause), "error"); }
    finally { running.current = false; setWorking(false); onBusy(false); }
  }
  return <>
  {actionTarget && !readonly && createPortal(<>
    <div className="order-actions metadata-actions"><button className="order-button" disabled={!mutable || !!revision || !current} onClick={() => setConfirm({ kind: "complete", assetId: current?.id ?? null })}>完成订单</button>
      <button className="text-button danger-action" disabled={!mutable || !!revision} onClick={() => setConfirm({ kind: "close", assetId: current?.id ?? null })}>关闭订单</button></div>
    {confirm && <div className="order-notice metadata-confirm"><p>{confirm.kind === "complete" ? `确认以版本 ${currentVersion} 完成订单？` : "确认关闭此订单？"}记录和图片保留，之后不能编辑。</p>
      {selectionChanged && <p role="alert">当前交付图已变化，请取消后重新确认。</p>}
      <div className="order-actions"><button className="order-button" disabled={!mutable || !!selectionChanged} onClick={() => void run(async () => {
        const order = await apiRequest<OrderDetail>(`/orders/${data.order_id}/${confirm.kind}`, { method: "POST" });
        onStatus(order.status); onChange({ ...data, order_status: order.status }); setConfirm(null);
        onLog(confirm.kind === "complete" ? "订单已完成。" : "订单已关闭。");
      })}>{confirm.kind === "complete" ? "确认完成" : "确认关闭"}</button><button className="text-button" disabled={working} onClick={() => setConfirm(null)}>取消</button></div>
    </div>}
  </>, actionTarget)}
  <div className="delivery-panel">
    {current ? <div className="current-delivery">
      <a className="asset-preview" href={current.content_url} target="_blank" rel="noreferrer" aria-label="查看当前交付图原图"><Image src={current.content_url} alt="当前交付图" fill unoptimized sizes="(max-width: 380px) 80vw, 320px" /></a>
      <div className="order-actions delivery-primary-actions">
        <button className="order-button primary" disabled={!canDownload} onClick={() => void run(async () => {
          const file = await fetchDelivery(data.order_id);
          const url = URL.createObjectURL(file.blob);
          const link = document.createElement("a"); link.href = url; link.download = file.filename;
          document.body.appendChild(link); link.click(); link.remove();
          setTimeout(() => URL.revokeObjectURL(url), 60000);
          onLog("下载已发起；请确认文件已保存，订单尚未自动完成。");
        })}>下载当前交付图</button>
        {!readonly && <button className="order-button" disabled={!mutable || !!revision} onClick={() => { setConfirm(null); onRevise(current); }}>继续修改</button>}
      </div>
    </div> : null}
    {revision}
    {data.versions.length > 0 && <details className="removed-list"><summary>版本历史（{data.versions.length}）</summary>
      <div className="delivery-versions">{data.versions.map((asset, index) => <article className="asset-card" key={asset.id}>
        <a className="asset-preview" href={asset.content_url} target="_blank" rel="noreferrer"><Image src={asset.content_url} alt={`版本 ${index + 1}`} fill unoptimized sizes="150px" /></a>
        <div className="asset-info"><strong>版本 {index + 1}{asset.id === current?.id ? " · 当前" : ""}</strong>
          {asset.review_status === "discarded" ? <p>已作废</p> : versionDeliveryAction(asset.id, current?.id ?? null) === "current" ? <p>当前交付图，可直接下载或完成订单</p> : !readonly && <button className="order-button small" disabled={!mutable || !!revision} onClick={() => void run(async () => {
            const updated = await apiRequest<DeliveryState>(`/orders/${data.order_id}/finals`, { method: "PUT", body: { asset_ids: [asset.id] } });
            setConfirm(null); onChange(updated); onLog(`已切换为版本 ${index + 1}。`);
          })}>用此版本交付</button>}
        </div></article>)}</div>
    </details>}
  </div></>;
}
