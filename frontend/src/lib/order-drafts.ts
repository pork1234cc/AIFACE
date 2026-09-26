import { validAspectRatio } from "./image-options.ts";
import type { OrderParams } from "../types/orders.ts";
import { validRegionPrompts } from "./region-prompts.ts";
export type InfoDraft = { customer_name: string; note: string };
export function validInfoDraft(value: unknown): value is InfoDraft {
  if (!value || typeof value !== "object") return false;
  const item = value as Record<string, unknown>;
  return typeof item.customer_name === "string" && item.customer_name.length <= 100
    && typeof item.note === "string" && item.note.length <= 2000;
}
export function validParamsDraft(value: unknown): value is OrderParams {
  if (!value || typeof value !== "object") return false;
  const item = value as Record<string, unknown>;
  return item.schema_version === 2 && (item.base_asset_id === null || typeof item.base_asset_id === "string")
    && (item.style_id === null || item.style_id === "q_crayon_001"
      || (typeof item.style_id === "string" && /^custom_[0-9a-f]{32}$/.test(item.style_id)))
    && (validAspectRatio(item.aspect_ratio) || (item.aspect_ratio === "" && typeof item.size === "string"))
    && (item.mode === undefined || ["edit", "generate"].includes(item.mode as string))
    && (item.size == null || (typeof item.size === "string" && /^[1-9][0-9]{0,3}x[1-9][0-9]{0,3}$/.test(item.size)))
    && (item.response_format === undefined || ["url", "b64_json"].includes(item.response_format as string))
    && (item.async_mode === undefined || typeof item.async_mode === "boolean")
    && (item.mask == null || (typeof item.mask === "string" && item.mask.length <= 28000000))
    && (item.mask_base_asset_id == null || typeof item.mask_base_asset_id === "string")
    && (item.output_format === undefined || ["png", "jpeg", "webp"].includes(item.output_format as string))
    && typeof item.extra_requirement === "string" && item.extra_requirement.length <= 2000
    && (item.region_asset_id == null || typeof item.region_asset_id === "string")
    && (item.region_prompts === undefined || validRegionPrompts(item.region_prompts))
    && (item.material_slots == null || (Array.isArray(item.material_slots)
      && item.material_slots.length >= 3 && item.material_slots.every((id) => id === null || typeof id === "string")))
    && Array.isArray(item.changes) && item.changes.length <= 20
    && item.changes.every((change) => change && typeof change === "object"
      && typeof change.target_description === "string" && typeof change.change_type === "string"
      && typeof change.instruction === "string" && typeof change.preserve_instruction === "string"
      && Array.isArray(change.source_asset_ids)
      && change.source_asset_ids.every((id: unknown) => typeof id === "string"));
}

export type RevisionDraft = { instruction: string; selected: string[] };
export function validRevisionDraft(value: unknown): value is RevisionDraft {
  if (!value || typeof value !== "object") return false;
  const item = value as Record<string, unknown>;
  return typeof item.instruction === "string" && item.instruction.length <= 2000
    && Array.isArray(item.selected)
    && item.selected.every((id) => typeof id === "string" && /^[A-Za-z0-9_-]{1,128}$/.test(id))
    && new Set(item.selected).size === item.selected.length;
}
