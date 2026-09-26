import type { OrderDetail, OrderParams } from "../types/orders.ts";

export const IMAGE_MODELS = ["gpt-image-2.0-4k", "gpt-image-2", "gpt-image-2.5-sunburst"] as const;

export function validAspectRatio(value: unknown): boolean {
  if (typeof value !== "string" || !/^[1-9][0-9]{0,11}:[1-9][0-9]{0,11}$/.test(value)) return false;
  const [width, height] = value.split(":").map(Number);
  return Math.max(width, height) <= 3 * Math.min(width, height);
}

export function changeCreationMode(config: OrderParams, mode: "edit" | "generate", order: OrderDetail): OrderParams {
  return { ...config, mode, base_asset_id: mode === "generate" ? null
    : order.assets.find((asset) => asset.kind === "input" && asset.is_active_input && asset.input_role === "main")?.id ?? null,
  changes: [], region_asset_id: null, region_prompts: [], mask: null, mask_base_asset_id: null,
  material_slots: mode === "generate" ? [null, null, null] : order.params.material_slots ?? [null, null, null] };
}
