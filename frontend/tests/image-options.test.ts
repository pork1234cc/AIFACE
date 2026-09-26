import assert from "node:assert/strict";
import { test } from "node:test";
import { IMAGE_MODELS, changeCreationMode, validAspectRatio } from "../src/lib/image-options.ts";
import { validParamsDraft } from "../src/lib/order-drafts.ts";
import type { OrderDetail, OrderParams } from "../src/types/orders.ts";

test("三模型选项保留，可恢复自定义比例与 Base64 参数", () => {
  assert.deepEqual(IMAGE_MODELS, ["gpt-image-2.0-4k", "gpt-image-2", "gpt-image-2.5-sunburst"]);
  const config = { schema_version: 2, base_asset_id: null, style_id: null, changes: [],
    aspect_ratio: "7:5", extra_requirement: "海边日落", mode: "generate", response_format: "b64_json", async_mode: false };
  assert.equal(validParamsDraft(config), true);
  assert.equal(validParamsDraft({ ...config, response_format: "invalid" }), false);
  for (const ratio of ["3:1", "1:3", "7:5"]) assert.equal(validAspectRatio(ratio), true);
  for (const ratio of ["4:1", "0:1", "1:0", "1.5:1"]) assert.equal(validAspectRatio(ratio), false);
});

test("纯文生图解除图片与遮罩引用，不删除原始资产", () => {
  const config = { schema_version: 2, base_asset_id: "main", style_id: null, changes: [],
    aspect_ratio: "1:1", output_format: "png", extra_requirement: "日落", mask: "mask",
    mask_base_asset_id: "main", material_slots: ["material", null, null] } as OrderParams;
  const order = { params: config, assets: [{ id: "main", kind: "input", is_active_input: true, input_role: "main" }] } as OrderDetail;
  const pure = changeCreationMode(config, "generate", order);
  assert.equal(pure.base_asset_id, null);
  assert.equal(pure.mask, null);
  assert.deepEqual(pure.material_slots, [null, null, null]);
  assert.equal(order.assets.length, 1);
  assert.equal(changeCreationMode(pure, "edit", order).base_asset_id, "main");
});
