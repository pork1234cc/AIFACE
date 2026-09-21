import assert from "node:assert/strict";
import { test } from "node:test";
import { validInfoDraft, validParamsDraft, validRevisionDraft } from "../src/lib/order-drafts.ts";

test("客户草稿校验", () => {
  assert.equal(validInfoDraft({ customer_name: "阿九", note: "备注" }), true);
  assert.equal(validInfoDraft({ customer_name: 1, note: "" }), false);
  assert.equal(validInfoDraft({ customer_name: "x".repeat(101), note: "" }), false);
  assert.equal(validInfoDraft(null), false);
});
test("参数草稿保留 false 与中文", () => {
  assert.equal(validParamsDraft({ schema_version: 2, base_asset_id: null, style_id: null, changes: [], aspect_ratio: "1:1", extra_requirement: "去掉眼镜" }), true);
});
test("拒绝旧格式或损坏参数草稿", () => {
  assert.equal(validParamsDraft({}), false); assert.equal(validParamsDraft(null), false);
  assert.equal(validParamsDraft({ hair_source_asset_id: "../../bad", glasses_keep: false, clothes_mode: "other", clothes_source_asset_id: null, background: "white", aspect_ratio: "1:1", extra_requirement: "" }), false);
});
test("自定义风格草稿可恢复，拒绝损坏的风格编号", () => {
  const draft = { schema_version: 2, base_asset_id: null, changes: [], aspect_ratio: "1:1", extra_requirement: "" };
  assert.equal(validParamsDraft({ ...draft, style_id: `custom_${"a".repeat(32)}` }), true);
  for (const style_id of ["custom_", "../../style", "unknown", 1]) {
    assert.equal(validParamsDraft({ ...draft, style_id }), false);
  }
});
test("修改草稿支持多张不同附加素材", () => {
  assert.equal(validRevisionDraft({ instruction: "修改", selected: ["a", "b", "c"] }), true);
  assert.equal(validRevisionDraft({ instruction: "", selected: [] }), true);
  assert.equal(validRevisionDraft({ instruction: "", selected: ["a", "a"] }), false);
  assert.equal(validRevisionDraft({ instruction: "", selected: ["a", "b", "c", "d"] }), true);
  assert.equal(validRevisionDraft({ instruction: "", selected: ["../bad"] }), false);
});
test("多素材位置和生图格式草稿可恢复", () => {
  const draft = { schema_version: 2, base_asset_id: null, style_id: null, changes: [],
    material_slots: [null, null, null, "fourth", "fifth"], aspect_ratio: "1:1", output_format: "webp", extra_requirement: "" };
  assert.equal(validParamsDraft(draft), true);
  assert.equal(validParamsDraft({ ...draft, output_format: "gif" }), false);
});
