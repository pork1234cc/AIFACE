import assert from "node:assert/strict";
import { test } from "node:test";
import { parsePreviewPending, previewBusy, previewLabel } from "../src/lib/style-previews.ts";
import type { Style } from "../src/types/orders.ts";

const style = { cover_image: null, preview: null } as Style;
test("封面操作区分生成、重新生成和受理不明核对", () => {
  assert.equal(previewLabel(style), "生成示意图");
  assert.equal(previewLabel({ ...style, cover_image: "/cover.png" }), "重新生成示意图");
  for (const status of ["pending", "submitting", "queued", "running", "downloading"] as const) {
    assert.equal(previewBusy({ ...style, preview: { task_id: "id", request_key: "request-key", status, error_message: null, can_resume_download: false } }), true);
  }
  const unknown: Style = { ...style, preview: { task_id: "id", request_key: "request-key", status: "submission_unknown", error_message: null, can_resume_download: false } };
  assert.equal(previewLabel(unknown), "核对任务");
  assert.equal(previewLabel({ ...unknown, preview: { ...unknown.preview!, status: "failed", can_resume_download: true } }), "恢复下载");
});
test("保存提交编号和版本供超时后重放，拒绝损坏记录", () => {
  assert.deepEqual(parsePreviewPending('{"key":"request-key","version":2}'), { key: "request-key", version: 2 });
  for (const value of [null, "bad", "{}", "null", '{"key":"x","version":2}', '{"key":"request-key","version":0}']) {
    assert.equal(parsePreviewPending(value), null);
  }
});
