"use client";

import Image from "next/image";
import { useRef, useState } from "react";
import { apiRequest, errorMessage } from "@/lib/api";
import { fetchDelivery } from "@/lib/delivery";
import type { DeliveryState } from "@/types/deliveries";
import type { Asset, OrderDetail, OrderStatus } from "@/types/orders";

export function DeliveryPanel({ data, disabled, onBusy, onChange, onStatus, onRevise }: {
  data: DeliveryState; disabled: boolean; onBusy: (busy: boolean) => void;
  onChange: (value: DeliveryState) => void; onStatus: (status: OrderStatus) => void;
  onRevise: (asset: Asset) => void;
}) {
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [working, setWorking] = useState(false);
  const [confirm, setConfirm] = useState<"complete" | "close" | null>(null);
  const running = useRef(false);
  const current = data.versions.find((asset) => asset.id === data.items[0]?.asset_id);
  const readonly = data.order_status === "completed" || data.order_status === "closed";
  async function run(action: () => Promise<void>) {
    if (running.current) return;
    running.current = true; setWorking(true); onBusy(true); setError(""); setNotice("");
    try { await action(); }
    catch (cause) { setError(errorMessage(cause)); }
    finally { running.current = false; setWorking(false); onBusy(false); }
  }
  return <div className="delivery-panel">
    <h3>当前交付图</h3>
    <p className="muted">每次生成 1 张。修改成功自动更新当前交付图，旧版本保留，可随时切回。</p>
    {error && <div className="order-alert" role="alert">{error}</div>}
    {notice && <p className="order-notice" role="status">{notice}</p>}
    {current ? <div className="current-delivery">
      <a className="asset-preview" href={current.content_url} target="_blank" rel="noreferrer"><Image src={current.content_url} alt="当前交付图" fill unoptimized sizes="(max-width: 560px) 85vw, 440px" /></a>
      <div className="order-actions">
        <button className="order-button primary" disabled={working} onClick={() => void run(async () => {
          const file = await fetchDelivery(data.order_id);
          const url = URL.createObjectURL(file.blob);
          const link = document.createElement("a"); link.href = url; link.download = file.filename;
          link.click(); setTimeout(() => URL.revokeObjectURL(url), 60000);
          setNotice("下载已发起，订单状态未改变。");
        })}>下载当前交付图</button>
        {!readonly && <button className="order-button" disabled={disabled || working || data.has_open_tasks} onClick={() => onRevise(current)}>修改这张图</button>}
      </div>
    </div> : <p className="order-notice">{data.versions.length ? "该历史订单尚未指定交付图，请在版本历史中选择一张。" : "素材与要求准备好后，生成一张交付图。"}</p>}
    {data.versions.length > 0 && <details className="removed-list"><summary>版本历史（{data.versions.length}）</summary>
      <div className="delivery-versions">{data.versions.map((asset, index) => <article className="asset-card" key={asset.id}>
        <a className="asset-preview" href={asset.content_url} target="_blank" rel="noreferrer"><Image src={asset.content_url} alt={`版本 ${index + 1}`} fill unoptimized sizes="160px" /></a>
        <div className="asset-info"><strong>版本 {index + 1}{asset.id === current?.id ? " · 当前交付" : ""}</strong>
          {asset.review_status === "discarded" ? <p>已作废</p> : <button className="order-button small" disabled={disabled || working || readonly || asset.id === current?.id} onClick={() => void run(async () => {
            const updated = await apiRequest<DeliveryState>(`/orders/${data.order_id}/finals`, { method: "PUT", body: { asset_ids: [asset.id] } });
            onChange(updated); setNotice(`已使用版本 ${index + 1} 作为当前交付图。`);
          })}>使用此版本交付</button>}
        </div>
      </article>)}</div>
    </details>}
    {readonly ? <p className="muted">订单已{data.order_status === "completed" ? "完成" : "关闭"}，可查看历史和下载交付图。</p> : <div className="delivery-finish">
      <p className="muted">下载与完成订单是两个动作。完成或关闭后订单只读。</p>
      <div className="order-actions"><button className="order-button" disabled={disabled || working || data.has_open_tasks || !current} onClick={() => setConfirm("complete")}>完成订单</button>
        <button className="order-button" disabled={disabled || working || data.has_open_tasks} onClick={() => setConfirm("close")}>关闭订单</button></div>
      {data.has_open_tasks && <p className="muted">仍有生成中或待核对任务，暂不能完成或关闭。</p>}
      {confirm && <div className="order-notice"><p>{confirm === "complete" ? "确认以当前交付图完成订单？" : "确认关闭此订单？"}记录和图片会保留，之后不能编辑。</p>
        <div className="order-actions"><button className="order-button" disabled={disabled || working || data.has_open_tasks} onClick={() => void run(async () => {
          const order = await apiRequest<OrderDetail>(`/orders/${data.order_id}/${confirm}`, { method: "POST" });
          onStatus(order.status); onChange({ ...data, order_status: order.status }); setConfirm(null);
        })}>{confirm === "complete" ? "确认完成" : "确认关闭"}</button><button className="order-button" disabled={working} onClick={() => setConfirm(null)}>暂不操作</button></div>
      </div>}
    </div>}
  </div>;
}
