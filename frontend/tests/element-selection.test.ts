import assert from "node:assert/strict";
import { test } from "node:test";
import { containsPixel, hitElements, imagePoint } from "../src/lib/element-selection.ts";
import type { DetectedRegion } from "../src/types/orders.ts";

const node = (id: string, depth: number, runs: number[], area: number): DetectedRegion => ({
  id, label: id, target_description: id, origin: "detected", depth,
  mask_runs: runs, mask_area: area, location_status: "located",
});

test("独立蒙版保留空洞，不使用矩形框命中", () => {
  assert.equal(containsPixel([1, 2, 5, 1], 3), false);
  assert.equal(containsPixel([1, 2, 5, 1], 5), true);
  assert.equal(containsPixel([], 1), false);
});
test("细节优先但保留父级候选，相邻人物不串选", () => {
  const regions = [node("person", 0, [0, 9], 9), node("bow", 2, [4, 1], 1), node("other", 0, [9, 3], 3)];
  assert.deepEqual(hitElements(regions, 4).map((r) => r.id), ["bow", "person"]);
  assert.deepEqual(hitElements(regions, 10).map((r) => r.id), ["other"]);
  assert.deepEqual(hitElements(regions, 12), []);
});
test("未定位候选不参与图片点选", () => {
  assert.deepEqual(hitElements([{ ...node("unknown", 1, [0, 5], 5), location_status: "unlocated" }], 2), []);
});
test("缩放点选映射原图，边界外及零尺寸不误选", () => {
  const rect = { left: 20, top: 40, width: 200, height: 300 };
  assert.deepEqual(imagePoint(120, 190, rect, 1000, 1500), { x: 500, y: 750 });
  assert.equal(imagePoint(220, 100, rect, 1000, 1500), null);
  assert.equal(imagePoint(19, 100, rect, 1000, 1500), null);
  assert.equal(imagePoint(20, 40, { ...rect, width: 0 }, 1000, 1500), null);
});
