import assert from "node:assert/strict";
import { test } from "node:test";
import { addDetectedRegion, regionBindingError, validRegionPrompts } from "../src/lib/region-prompts.ts";
import { compactConfig } from "../src/lib/creation-config.ts";
import { validParamsDraft } from "../src/lib/order-drafts.ts";
import type { DetectedRegion, OrderDetail, OrderParams } from "../src/types/orders.ts";

const config: OrderParams = { schema_version: 2, base_asset_id: "main", style_id: null,
  changes: [], material_slots: [null, "material", null], extra_requirement: "保持构图", aspect_ratio: "1:1", output_format: "png" };
const hair: DetectedRegion = { id: "hair", label: "头发", target_description: "头发", origin: "detected", mask_value: 1 };

test("颗粒化对象可保存超过二十项独立要求", () => {
  let value = config;
  for (let i = 0; i < 97; i++) value = addDetectedRegion(value, { ...hair, id: `detail_${i}` });
  assert.equal(value.region_prompts?.length, 97);
  assert.equal(validRegionPrompts(value.region_prompts), true);
});

test("识别区域仅选中后加入配置，重复选择不覆盖已写要求", () => {
  const added = addDetectedRegion(config, hair);
  assert.equal(added.region_asset_id, "main");
  assert.equal(added.region_prompts?.length, 1);
  added.region_prompts![0].instruction = "参考发色";
  added.region_prompts![0].source_asset_ids = ["material"];
  assert.equal(addDetectedRegion(added, hair), added);
  assert.equal(added.extra_requirement, "保持构图");
  assert.equal(regionBindingError(added), null);
});

test("区域草稿保存后不会再转入完整提示词造成重复", () => {
  const added = addDetectedRegion(config, hair);
  added.region_prompts![0].instruction = "换成黑色";
  assert.equal(validParamsDraft(JSON.parse(JSON.stringify(added))), true);
  const compact = compactConfig({ params: added, assets: [] } as unknown as OrderDetail);
  assert.equal(compact.extra_requirement, "保持构图");
  assert.deepEqual(compact.region_prompts, added.region_prompts);
});

test("换底图和同号素材替换要求重新核对，不静默串图", () => {
  const added = addDetectedRegion(config, hair);
  added.region_prompts![0].instruction = "参考发色";
  added.region_prompts![0].source_asset_ids = ["material"];
  assert.match(regionBindingError({ ...added, base_asset_id: "new" })!, /底图已变化/);
  assert.match(regionBindingError({ ...added, material_slots: [null, "replacement", null] })!, /已移出或替换/);
  added.region_prompts![0].instruction = " ";
  assert.match(regionBindingError(added)!, /素材用途/);
});

test("空区域可保留，损坏或超长区域草稿不恢复", () => {
  const added = addDetectedRegion(config, hair);
  assert.equal(regionBindingError(added), null);
  assert.equal(validRegionPrompts(added.region_prompts), true);
  assert.equal(validRegionPrompts([added.region_prompts![0], added.region_prompts![0]]), false);
  assert.equal(validParamsDraft({ ...added, region_prompts: null }), false);
  assert.equal(validRegionPrompts([{ ...added.region_prompts![0], instruction: "长".repeat(2001) }]), false);
});
