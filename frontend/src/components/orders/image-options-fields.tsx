"use client";

import { useState, type ReactNode } from "react";
import { aspectSizes, type OrderParams } from "@/types/orders";

export function ImageOptionsFields({ config, disabled, onChange, onBusy, children }: {
  config: OrderParams; disabled: boolean; onChange: (config: OrderParams) => void; onBusy: (busy: boolean) => void;
  children?: ReactNode;
}) {
  const [error, setError] = useState("");
  const [reading, setReading] = useState(false);
  const [selection, setSelection] = useState<string | null>(null);
  const patch = (value: Partial<OrderParams>) => onChange({ ...config, ...value });
  const sizeMode = selection ?? (!config.aspect_ratio ? "size" : Object.hasOwn(aspectSizes, config.aspect_ratio) ? config.aspect_ratio : "custom");
  return <fieldset className="order-form" disabled={disabled || reading}>
    <div className="style-output-row">
    <label>输出比例<select value={sizeMode} onChange={(event) => {
      const value = event.target.value;
      setSelection(value);
      patch(value === "size" ? { aspect_ratio: "", size: config.size || "1024x1024" }
        : { aspect_ratio: value === "custom" ? "7:5" : value, size: null });
    }}>{Object.keys(aspectSizes).map((ratio) => <option key={ratio}>{ratio}</option>)}
      <option value="custom">自定义比例</option><option value="size">指定像素尺寸</option>
    </select></label>
    {children}
    </div>
    {sizeMode === "custom" && <label>自定义比例<input aria-label="自定义比例" value={config.aspect_ratio} placeholder="7:5" onChange={(event) => patch({ aspect_ratio: event.target.value })} /><small>使用正整数 n:m，长短边比不超过 3:1。</small></label>}
    {sizeMode === "size" && <label>像素尺寸<input aria-label="像素尺寸" value={config.size ?? ""} placeholder="1024x1024" onChange={(event) => patch({ size: event.target.value })} /><small>宽x高，使用16的倍数。Sunburst 单边最多3840，总像素最多3686400。</small></label>}
    <details><summary>返回方式与局部重绘</summary>
      <label>结果传输<select value={config.response_format ?? "url"} onChange={(event) => patch({ response_format: event.target.value as "url" | "b64_json" })}>
        <option value="url">图片链接</option><option value="b64_json">Base64 图片数据</option>
      </select></label>
      <label>执行方式<select value={config.async_mode === false ? "sync" : "async"} onChange={(event) => patch({ async_mode: event.target.value === "async" })}>
        <option value="async">异步任务（推荐）</option><option value="sync">同步等待结果</option>
      </select></label>
      {config.mode !== "generate" && <>
        <label>上传重绘遮罩<input type="file" accept="image/png,image/webp" disabled={!config.base_asset_id || disabled || reading} onChange={async (event) => {
          const file = event.currentTarget.files?.[0]; event.currentTarget.value = "";
          if (!file) return;
          if (file.size > 20 * 1024 * 1024) { setError("遮罩不能超过20 MiB"); return; }
          setReading(true); onBusy(true); setError("");
          try {
            const mask = await new Promise<string>((resolve, reject) => {
              const reader = new FileReader();
              reader.onload = () => resolve(String(reader.result));
              reader.onerror = () => reject(new Error("无法读取遮罩图片"));
              reader.readAsDataURL(file);
            });
            patch({ mask, mask_base_asset_id: config.base_asset_id });
          } catch { setError("无法读取遮罩图片，请重试"); }
          finally { setReading(false); onBusy(false); }
        }} /></label>
        <label>或填写遮罩地址<input type="url" placeholder="https://…/mask.png" disabled={!config.base_asset_id || disabled || reading}
          value={config.mask?.startsWith("https://") ? config.mask : ""}
          onChange={(event) => patch({ mask: event.target.value || null, mask_base_asset_id: event.target.value ? config.base_asset_id : null })} /></label>
        <p className="muted">遮罩须与底图尺寸一致；完全透明区域重绘，不透明区域保留。</p>
        {config.mask && <p role="status">已设置重绘遮罩。{config.mask_base_asset_id !== config.base_asset_id && <span className="order-alert">底图已变化，请重新设置遮罩。</span>}
          <button type="button" className="text-button" onClick={() => patch({ mask: null, mask_base_asset_id: null })}>取消遮罩</button></p>}
      </>}
    </details>
    {error && <p role="alert" className="order-alert">{error}</p>}
  </fieldset>;
}
