"use client";

import Image from "next/image";
import { useEffect, useRef, useState } from "react";
import { apiRequest, errorMessage } from "@/lib/api";
import { addDetectedRegion } from "@/lib/region-prompts";
import type { Asset, DetectedRegion, OrderParams, RegionDetection, RegionPrompt } from "@/types/orders";

function RegionPhoto({ base, detection, selected, disabled, onSelect }: {
  base: Asset; detection: RegionDetection | null; selected: string; disabled: boolean;
  onSelect: (region: DetectedRegion) => void;
}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const mask = useRef<ImageData | null>(null);
  const value = detection?.regions.find((region) => region.id === selected)?.mask_value;
  useEffect(() => {
    mask.current = null;
    const context = canvas.current?.getContext("2d");
    if (!context) return;
    context.clearRect(0, 0, 512, 512);
    if (!detection) return;
    let active = true;
    const image = new window.Image();
    image.onload = () => {
      if (!active) return;
      context.drawImage(image, 0, 0, 512, 512);
      const pixels = context.getImageData(0, 0, 512, 512);
      mask.current = pixels;
      const overlay = context.createImageData(512, 512);
      for (let offset = 0; offset < pixels.data.length; offset += 4) {
        if (pixels.data[offset] !== value) continue;
        overlay.data.set([76, 145, 90, 125], offset);
      }
      context.putImageData(overlay, 0, 0);
    };
    image.src = detection.mask_url;
    return () => { active = false; };
  }, [detection, value]);

  return <button type="button" className="region-photo" disabled={disabled || !detection}
    style={{ aspectRatio: `${base.width} / ${base.height}` }} aria-label="点击照片选择区域，也可使用下方区域按钮"
    onClick={(event) => {
      if (!mask.current || !detection) return;
      const rect = event.currentTarget.getBoundingClientRect();
      const x = Math.max(0, Math.min(511, Math.floor((event.clientX - rect.left) / rect.width * 512)));
      const y = Math.max(0, Math.min(511, Math.floor((event.clientY - rect.top) / rect.height * 512)));
      const index = mask.current.data[(y * 512 + x) * 4];
      const region = detection.regions.find((item) => item.mask_value === index);
      if (region) onSelect(region);
    }}>
    <Image src={base.content_url} alt={base.kind === "generated" ? "当前编辑结果" : "主照片区域预览"} fill unoptimized sizes="280px" />
    <canvas ref={canvas} width={512} height={512} aria-hidden="true" />
  </button>;
}

export function RegionPromptEditor({ orderId, config, assets, disabled, enabled, archived, onChange }: {
  orderId: string; config: OrderParams; assets: Asset[]; disabled: boolean;
  enabled: boolean; archived: boolean; onChange: (config: OrderParams) => void;
}) {
  const [detection, setDetection] = useState<RegionDetection | null>(null);
  const [selected, setSelected] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [retry, setRetry] = useState(0);
  const [customName, setCustomName] = useState("");
  const baseId = config.base_asset_id;
  const base = assets.find((asset) => asset.id === baseId);
  const regions = config.region_prompts ?? [];
  const stale = regions.length > 0 && config.region_asset_id !== baseId;
  const currentDetection = detection?.asset_id === baseId ? detection : null;
  const current = regions.find((region) => region.id === selected);
  const locked = disabled || stale || !base;
  const materials = (config.material_slots ?? []).flatMap((id, index) => {
    const asset = assets.find((item) => item.id === id && item.kind === "input" && item.is_active_input && item.input_role === "material");
    return asset ? [{ asset, number: index + 1 }] : [];
  });

  useEffect(() => {
    if (!baseId || !enabled || archived) return;
    const controller = new AbortController();
    void Promise.resolve().then(async () => {
      if (controller.signal.aborted) return;
      setLoading(true); setError("");
      try {
        const result = await apiRequest<RegionDetection>(`/orders/${orderId}/images/${baseId}/regions`, {
          method: "POST", signal: AbortSignal.any([controller.signal, AbortSignal.timeout(30000)]),
        });
        if (!controller.signal.aborted && result.asset_id === baseId) setDetection(result);
      } catch (cause) {
        if (!controller.signal.aborted) setError(errorMessage(cause));
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    });
    return () => controller.abort();
  }, [baseId, orderId, enabled, archived, retry]);

  const choose = (region: DetectedRegion) => {
    if (regions.some((item) => item.id === region.id)) { setSelected(region.id); return; }
    if (locked) return;
    onChange(addDetectedRegion(config, region));
    setSelected(region.id);
  };
  const patch = (value: Partial<RegionPrompt>) => onChange({ ...config,
    region_prompts: regions.map((region) => region.id === selected ? { ...region, ...value } : region),
  });

  return <div className="region-editor">
    <div className="region-heading"><h3>按区域编写</h3>{base && !archived && <button type="button" className="text-button" disabled={disabled || loading} onClick={() => setRetry((n) => n + 1)}>{loading ? "正在本地识别…" : "重新识别"}</button>}</div>
    {!base && <p className="muted">上传主照片后，识别可编辑区域。</p>}
    {base && <><p className="muted">点击照片或区域，填写修改要求并选择参考素材。未填写的区域默认保留。</p>
      <RegionPhoto base={base} detection={currentDetection} selected={current?.id ?? ""} disabled={locked} onSelect={choose} />
      {error && <p className="order-alert" role="alert">{error}。可在下方手动添加区域。</p>}
      {stale && <div className="order-alert" role="alert">底图已更换，原区域要求需重新核对。
        <div className="order-actions"><button type="button" className="order-button" disabled={disabled} onClick={() => onChange({ ...config, region_asset_id: baseId,
          region_prompts: regions.map((region) => ({ ...region, origin: "manual" })),
        })}>已核对，沿用文字要求</button><button type="button" className="text-button" disabled={disabled} onClick={() => onChange({ ...config, region_asset_id: baseId, region_prompts: [] })}>清空区域要求</button></div>
      </div>}
      <div className="region-chips" aria-label="照片区域">
        {currentDetection?.regions.map((region) => {
          const saved = regions.find((item) => item.id === region.id);
          return <button type="button" className="region-chip" key={region.id} disabled={!saved && (locked || regions.length >= 20)}
            aria-pressed={current?.id === region.id} onClick={() => choose(region)}>{saved?.label || region.label}{saved && (saved.instruction || saved.preserve_instruction) ? " · 已填写" : ""}</button>;
        })}
        {regions.filter((region) => !currentDetection?.regions.some((item) => item.id === region.id)).map((region) => <button type="button" key={region.id} className="region-chip"
          aria-pressed={selected === region.id} onClick={() => setSelected(region.id)}>{region.label || "未命名区域"}{region.instruction || region.preserve_instruction ? " · 已填写" : ""}</button>)}
      </div>
      {!archived && <div className="region-add"><input aria-label="自定义区域名称" maxLength={100} disabled={locked || regions.length >= 20} value={customName} onChange={(event) => setCustomName(event.target.value)} placeholder="补充区域，如左侧人物的上衣" />
        <button type="button" className="order-button" disabled={locked || !customName.trim() || regions.length >= 20} onClick={() => {
          const label = customName.trim();
          const id = `manual_${crypto.randomUUID()}`;
          onChange({ ...config, region_asset_id: baseId, region_prompts: [...regions, {
            id, label, target_description: label, origin: "manual", source_asset_ids: [], instruction: "", preserve_instruction: "",
          }] });
          setSelected(id); setCustomName("");
        }}>添加区域</button></div>}
      {current && <fieldset className="region-fields order-form" disabled={locked}>
        <legend>{current.label || "区域要求"}</legend>
        <label>区域名称<input maxLength={100} value={current.label} onChange={(event) => patch({ label: event.target.value })} /></label>
        <label>对应照片中的哪里<input maxLength={100} value={current.target_description} onChange={(event) => patch({ target_description: event.target.value })} placeholder="如画面左侧人物的头发" /></label>
        <label>修改要求<textarea rows={3} maxLength={2000} value={current.instruction} onChange={(event) => patch({ instruction: event.target.value })} placeholder="如只参考素材的发色，保留原来的发型" /></label>
        <div className="region-materials"><span>参考素材（可多选）</span>
          {!materials.length && <p className="muted">可先填写文字要求，或在上方上传素材。</p>}
          <div className="region-material-options">{materials.map(({ asset, number }) => <label className="region-material" key={asset.id}>
            <input type="checkbox" checked={current.source_asset_ids.includes(asset.id)} onChange={(event) => patch({ source_asset_ids: event.target.checked ? [...current.source_asset_ids, asset.id] : current.source_asset_ids.filter((id) => id !== asset.id) })} />
            <Image src={asset.content_url} alt={`素材${number}`} width={40} height={40} unoptimized /><span>素材{number}</span>
          </label>)}</div>
          {current.source_asset_ids.filter((id) => !materials.some(({ asset }) => asset.id === id)).map((id) => <p className="order-alert" key={id}>原素材已移出或替换，请重新选择。<button type="button" className="text-button" onClick={() => patch({ source_asset_ids: current.source_asset_ids.filter((key) => key !== id) })}>解除失效引用</button></p>)}
        </div>
        <label>保留要求<textarea rows={2} maxLength={2000} value={current.preserve_instruction} onChange={(event) => patch({ preserve_instruction: event.target.value })} placeholder="如保留头发长度、人物身份与表情" /></label>
        {!archived && <button type="button" className="text-button" onClick={() => {
          onChange({ ...config, region_prompts: regions.filter((region) => region.id !== selected) }); setSelected("");
        }}>移除此区域要求</button>}
      </fieldset>}
      {currentDetection && <p className="region-note">自动识别适合清晰人像；服饰为整体区域。可修正目标描述，多人照片请注明人物位置。</p>}
    </>}
  </div>;
}
