import { aspectSizes } from "../types/orders.ts";
import type { OrderParams } from "../types/orders.ts";
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
    && typeof item.aspect_ratio === "string" && Object.hasOwn(aspectSizes, item.aspect_ratio)
    && (item.output_format === undefined || ["png", "jpeg", "webp"].includes(item.output_format as string))
    && typeof item.extra_requirement === "string" && item.extra_requirement.length <= 2000
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
