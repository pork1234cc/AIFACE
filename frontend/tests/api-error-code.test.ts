import assert from "node:assert/strict";
import { test } from "node:test";
import { ApiError, apiRequest, errorMessage } from "../src/lib/api.ts";

test("保留服务端错误码以识别幂等冲突", async (context) => {
  context.mock.method(globalThis, "fetch", async () => Response.json({ error: { code: "idempotency_conflict", message: "请求编号冲突" }, request_id: "request-id" }, { status: 409 }));
  await assert.rejects(apiRequest("/orders/id/generate", { method: "POST", body: {} }), (error: unknown) => {
    assert.ok(error instanceof ApiError); assert.equal(error.code, "idempotency_conflict");
    assert.equal(error.status, 409); assert.match(errorMessage(error), /request-id/); return true;
  });
});
test("保留旧的三参数 ApiError 构造兼容性", () => {
  const error = new ApiError("错误", 500, "id"); assert.equal(error.code, undefined); assert.equal(error.requestId, "id");
});
