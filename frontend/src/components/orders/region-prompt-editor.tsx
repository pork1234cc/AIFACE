"use client";

import Image from "next/image";
import { useEffect, useRef, useState } from "react";
import { apiRequest, errorMessage } from "@/lib/api";
import { addDetectedRegion } from "@/lib/region-prompts";
import { ElementPhoto } from "./element-photo";
import type { Asset, DetectedRegion, ElementStatus, OrderParams, RegionDetection, RegionPrompt } from "@/types/orders";

export function RegionPromptEditor({ orderId, config, assets, disabled, enabled, archived, onChange }: {
  orderId: string; config: OrderParams; assets: Asset[]; disabled: boolean;
  enabled: boolean; archived: boolean; onChange: (config: OrderParams) => void;
}) {
  const [detection, setDetection] = useState<RegionDetection | null>(null);
  const [selected, setSelected] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState("");
  const [refining, setRefining] = useState(false);
  const [retry, setRetry] = useState(0);
  const [customName, setCustomName] = useState("");
  const baseId = config.base_asset_id;
  const activeBase = useRef(baseId);
  useEffect(() => { activeBase.current = baseId; }, [baseId]);
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
    if (!baseId || !enabled) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    const poll = async () => {
      if (controller.signal.aborted) return;
      try {
        const result = await apiRequest<ElementStatus>(`/orders/${orderId}/images/${baseId}/elements`, {
          signal: AbortSignal.any([controller.signal, AbortSignal.timeout(30000)]),
        });
        if (controller.signal.aborted || result.asset_id !== baseId) return;
        setLoading(result.status === "running");
        setProgress(result.message ?? "");
        if (result.result) setDetection({ ...result.result, asset_id: baseId });
        setError(result.status === "failed" ? result.message || "元素识别失败" : "");
        if (result.status === "running") timer = setTimeout(() => void poll(), 1500);
      } catch (cause) {
        if (!controller.signal.aborted) { setError(errorMessage(cause)); setLoading(false); }
      }
    };
    void poll();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [baseId, orderId, enabled, retry]);

  const recognize = async () => {
    if (!baseId || loading || archived) return;
    const requestedBase = baseId;
    setLoading(true); setError(""); setProgress("Codex 正在分析图片元素…");
    try {
      await apiRequest(`/orders/${orderId}/images/${baseId}/elements`, { method: "POST" });
      if (activeBase.current === requestedBase) setRetry((n) => n + 1);
    } catch (cause) {
      if (activeBase.current === requestedBase) { setError(errorMessage(cause)); setLoading(false); }
    }
  };

  const refine = async (x: number, y: number, label: number) => {
    if (!currentDetection?.version || !current || refining || archived) return;
    const requestedBase = baseId;
    setRefining(true); setError("");
    try {
      const response = await apiRequest<ElementStatus>(`/orders/${orderId}/images/${baseId}/elements/${current.id}/refine`, {
        method: "POST", body: { version: currentDetection.version, points: [{ x, y, label }] },
      });
      if (activeBase.current === requestedBase && response.result) setDetection({ ...response.result, asset_id: response.asset_id });
    } catch (cause) {
      if (activeBase.current === requestedBase) setError(errorMessage(cause));
    } finally { setRefining(false); }
  };

  const choose = (region: DetectedRegion) => {
    if (regions.some((item) => item.id === region.id)) { setSelected(region.id); return; }
    if (locked || archived || regions.length >= 100) return;
    onChange(addDetectedRegion(config, region));
    setSelected(region.id);
  };
  const patch = (value: Partial<RegionPrompt>) => onChange({ ...config,
    region_prompts: regions.map((region) => region.id === selected ? { ...region, ...value } : region),
  });

  return <div className="region-editor">
    <div className="region-heading"><h3>按元素修改</h3>{base && !archived && <button type="button" className="text-button" disabled={disabled || loading || refining} onClick={() => void recognize()}>{loading ? "正在识别…" : currentDetection ? "重新识别元素" : "识别图片元素"}</button>}</div>
    {!base && <p className="muted">上传主照片后，识别可编辑区域。</p>}
    {base && <><p className="muted">点击照片或区域，填写修改要求并选择参考素材。未填写的区域默认保留。</p>
      <ElementPhoto key={base.id} base={base} detection={currentDetection} selected={current?.id ?? ""} disabled={locked || archived || refining || loading} onSelect={choose} onRefine={(x, y, label) => void refine(x, y, label)} />
      {loading && <p className="region-note" role="status">{progress}</p>}
      {refining && <p className="region-note" role="status">正在修正元素轮廓…</p>}
      {error && <p className="order-alert" role="alert">{error}。可在下方手动添加区域。</p>}
      {stale && <div className="order-alert" role="alert">底图已更换，原区域要求需重新核对。
        <div className="order-actions"><button type="button" className="order-button" disabled={disabled} onClick={() => onChange({ ...config, region_asset_id: baseId,
          region_prompts: regions.map((region) => ({ ...region, origin: "manual" })),
        })}>已核对，沿用文字要求</button><button type="button" className="text-button" disabled={disabled} onClick={() => onChange({ ...config, region_asset_id: baseId, region_prompts: [] })}>清空区域要求</button></div>
      </div>}
      <div className="region-chips" aria-label="照片区域">
        {currentDetection?.regions.map((region) => {
          const saved = regions.find((item) => item.id === region.id);
          return <button type="button" className="region-chip element-tree-item" key={region.id} disabled={!saved && (locked || archived || regions.length >= 100)}
            aria-pressed={current?.id === region.id} onClick={() => choose(region)}>{region.depth ? "↳ " : ""}{saved?.label || region.label}{region.location_status === "unlocated" ? " · 待定位" : ""}{saved && (saved.instruction || saved.preserve_instruction) ? " · 已填写" : ""}</button>;
        })}
        {regions.filter((region) => !currentDetection?.regions.some((item) => item.id === region.id)).map((region) => <button type="button" key={region.id} className="region-chip"
          aria-pressed={selected === region.id} onClick={() => setSelected(region.id)}>{region.label || "未命名区域"}{region.instruction || region.preserve_instruction ? " · 已填写" : ""}</button>)}
      </div>
      {!archived && <div className="region-add"><input aria-label="自定义区域名称" maxLength={100} disabled={locked || regions.length >= 100} value={customName} onChange={(event) => setCustomName(event.target.value)} placeholder="补充区域，如左侧人物的上衣" />
        <button type="button" className="order-button" disabled={locked || !customName.trim() || regions.length >= 100} onClick={() => {
          const label = customName.trim();
          const id = `manual_${crypto.randomUUID()}`;
          onChange({ ...config, region_asset_id: baseId, region_prompts: [...regions, {
            id, label, target_description: label, origin: "manual", source_asset_ids: [], instruction: "", preserve_instruction: "",
          }] });
          setSelected(id); setCustomName("");
        }}>添加区域</button></div>}
      {current && <fieldset className="region-fields order-form" disabled={locked || archived}>
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
      {currentDetection && <p className="region-note">已拆解 {currentDetection.regions.length} 个元素。点选优先选择细节，可切换上级对象；选区不准时可补选或排除。重新识别后原有文字要求保留，不自动绑定到新元素。</p>}
    </>}
  </div>;
}
