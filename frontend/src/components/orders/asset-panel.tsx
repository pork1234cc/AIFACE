"use client";

import Image from "next/image";
import { useRef, useState } from "react";
import { apiRequest, errorMessage } from "@/lib/api";
import { materialSlots, nextMaterialSlot } from "@/lib/creation-config";
import type { OrderDetail } from "@/types/orders";

export function AssetPanel({ order, kind = "materials", disabled, onChange, onBusy }: {
  order: OrderDetail; kind?: "main" | "materials"; disabled: boolean;
  onChange: (order: OrderDetail) => void; onBusy: (busy: boolean) => void;
}) {
  const [error, setError] = useState("");
  const running = useRef(false);
  const active = order.assets.filter((asset) => asset.kind === "input" && asset.is_active_input);
  const main = active.find((asset) => asset.input_role === "main");
  const materials = materialSlots(order).flatMap((id, index) => {
    const asset = active.find((item) => item.id === id && item.input_role === "material");
    return asset ? [{ asset, number: index + 1 }] : [];
  });
  const nextSlot = nextMaterialSlot(order);
  async function update(slot: string, file?: File) {
    if (running.current || disabled) return;
    if (file && file.size > 20 * 1024 * 1024) { setError("单张图片不能超过 20 MiB"); return; }
    running.current = true; onBusy(true); setError("");
    const body = new FormData();
    if (file) body.set("file", file);
    try {
      onChange(await apiRequest<OrderDetail>(`/orders/${order.id}/image-slots/${slot}${file ? "" : "/clear"}`, { method: "POST", ...(file ? { body } : {}) }));
    } catch (cause) { setError(errorMessage(cause)); }
    finally { running.current = false; onBusy(false); }
  }
  return <section className={`order-panel slot-panel ${kind}`} id={kind === "main" ? "order-assets" : undefined}>
    <h2>{kind === "main" ? "主图片" : "素材上传"}</h2>
    {error && <p className="order-alert" role="alert">{error}</p>}
    <div className="input-slots">
      {kind === "main" ? <div className="input-slot" key="main">
        {main && <a className="asset-preview" href={main.content_url} target="_blank" rel="noreferrer" aria-label="查看主图片"><Image src={main.content_url} alt="主图片" fill unoptimized sizes="120px" /></a>}
        <div className={main ? "input-slot-footer main-slot-actions" : undefined}>
          <label className={`slot-upload ${disabled ? "disabled" : ""}`}>
            {main ? "替换" : "上传图片"}
            <input type="file" aria-label={main ? "替换主图片" : "上传主图片"} accept="image/jpeg,image/png,image/webp" disabled={disabled} onChange={(event) => {
              const file = event.currentTarget.files?.[0]; event.currentTarget.value = "";
              if (file) void update("main", file);
            }} />
          </label>
          {main && <button type="button" className="text-button" disabled={disabled} onClick={() => void update("main")}>移出</button>}
        </div>
      </div> : <>
        {materials.map(({ asset, number }) => <div className="input-slot material-card" key={asset.id}>
          <a className="asset-preview" href={asset.content_url} target="_blank" rel="noreferrer" aria-label={`查看素材${number}`}><Image src={asset.content_url} alt={`素材${number}`} fill unoptimized sizes="120px" /></a>
          <div className="input-slot-footer"><span title={asset.original_name}>素材{number}</span><button type="button" className="text-button" disabled={disabled} onClick={() => void update(String(number))}>移出</button></div>
        </div>)}
        <label className={`slot-upload material-upload ${disabled ? "disabled" : ""}`}>
          <span aria-hidden="true" className="material-upload-icon">＋</span><span>上传素材图</span>
          <input type="file" aria-label="上传素材图" accept="image/jpeg,image/png,image/webp" disabled={disabled} onChange={(event) => {
            const file = event.currentTarget.files?.[0]; event.currentTarget.value = "";
            if (file) void update(nextSlot, file);
          }} />
        </label>
      </>}
    </div>
  </section>;
}
