import assert from "node:assert/strict";
import { test } from "node:test";
import { latestBatchLog } from "../src/lib/generation-log.ts";
import type { BatchSummary, GenerationBatch } from "../src/types/generation.ts";

test("订单首次加载且没有任务时日志保持空状态", () => {
  assert.deepEqual(latestBatchLog([], null), { summary: null, error: null });
});

test("查看旧记录时日志仍展示最新任务", () => {
  const latest: BatchSummary = {
    batch_id: "latest", operation: "initial", base_asset_id: null,
    revision_instruction: null, status: "succeeded", target_count: 1,
    created_at: "2026-09-21T10:00:00Z",
  };
  const selectedOld = { ...latest, batch_id: "older", status: "failed", tasks: [{ error_message: "旧错误" }] } as GenerationBatch;
  assert.deepEqual(latestBatchLog([latest], selectedOld), { summary: latest, error: null });
});
