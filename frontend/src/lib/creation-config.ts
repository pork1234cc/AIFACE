import type { OrderDetail, OrderParams } from "../types/orders.ts";

export function materialSlots(order: OrderDetail): (string | null)[] {
  if (order.params.material_slots) return [...order.params.material_slots];
  const ids = order.assets.filter((asset) => asset.kind === "input" && asset.is_active_input && asset.input_role === "material").map((asset) => asset.id);
  return [...ids, ...Array<null>(Math.max(0, 3 - ids.length)).fill(null)];
}

export function nextMaterialSlot(order: OrderDetail): string {
  const active = new Set(order.assets.filter((asset) => asset.kind === "input" && asset.is_active_input && asset.input_role === "material").map((asset) => asset.id));
  const slots = materialSlots(order);
  const vacant = slots.findIndex((id) => id === null || !active.has(id));
  return String(vacant < 0 ? slots.length + 1 : vacant + 1);
}

export function compactConfig(order: OrderDetail): OrderParams {
  const slots = materialSlots(order);
  const legacy = order.params.changes.map((change) => {
    const sources = change.source_asset_ids.map((id) => {
      const slot = slots.indexOf(id);
      return slot < 0 ? `已失效素材（${id}）` : `素材${slot + 1}`;
    }).join("、");
    return `${change.target_description}：${change.change_type}；${sources ? `使用${sources}；` : ""}${change.instruction}${change.preserve_instruction ? `；保留：${change.preserve_instruction}` : ""}`;
  });
  return { ...order.params, output_format: order.params.output_format ?? "png", material_slots: slots, changes: [],
    extra_requirement: [...legacy, order.params.extra_requirement].filter(Boolean).join("\n") };
}
