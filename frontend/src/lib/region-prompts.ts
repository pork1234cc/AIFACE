import type { DetectedRegion, OrderParams, RegionPrompt } from "../types/orders.ts";

export function validRegionPrompts(value: unknown): value is RegionPrompt[] {
  if (!Array.isArray(value) || value.length > 100) return false;
  const ids = new Set<string>();
  return value.every((region) => {
    if (!region || typeof region !== "object") return false;
    if (typeof region.id !== "string" || !/^[a-zA-Z0-9_-]{1,64}$/.test(region.id) || ids.has(region.id)) return false;
    ids.add(region.id);
    return typeof region.label === "string" && region.label.length <= 100
      && typeof region.target_description === "string" && region.target_description.length <= 100
      && ["manual", "detected"].includes(region.origin)
      && typeof region.instruction === "string" && region.instruction.length <= 2000
      && typeof region.preserve_instruction === "string" && region.preserve_instruction.length <= 2000
      && Array.isArray(region.source_asset_ids) && region.source_asset_ids.length <= 100
      && region.source_asset_ids.every((id: unknown) => typeof id === "string" && id.length > 0 && id.length <= 36);
  });
}

export function addDetectedRegion(config: OrderParams, region: DetectedRegion): OrderParams {
  const current = config.region_prompts ?? [];
  if (current.some((item) => item.id === region.id) || current.length >= 100) return config;
  return { ...config, region_asset_id: config.base_asset_id, region_prompts: [...current, {
    id: region.id, label: region.label, target_description: region.target_description,
    origin: "detected", source_asset_ids: [], instruction: "", preserve_instruction: "",
  }] };
}

export function regionBindingError(config: OrderParams): string | null {
  const regions = config.region_prompts ?? [];
  if (regions.length && (!config.base_asset_id || config.region_asset_id !== config.base_asset_id)) {
    return "底图已变化，请先核对区域要求";
  }
  for (const region of regions) {
    if (!region.label.trim() || !region.target_description.trim()) return "请填写区域名称和目标描述";
    if (config.material_slots && region.source_asset_ids.some((id) => !config.material_slots?.includes(id))) {
      return `${region.label}引用的素材已移出或替换，请重新选择`;
    }
    if (region.source_asset_ids.length && !region.instruction.trim()) return `请填写${region.label}的素材用途`;
  }
  return null;
}
