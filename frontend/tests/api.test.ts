import assert from "node:assert/strict";
import { afterEach, test } from "node:test";
import { ApiError, apiGet, apiRequest } from "../src/lib/api.ts";

const originalFetch = globalThis.fetch;
afterEach(() => { globalThis.fetch = originalFetch; });

test("生成重发沿用调用方提供的幂等编号", async () => {
  const keys: (string | null)[] = [];
  globalThis.fetch = async (_url, options) => {
    keys.push(new Headers(options?.headers).get("Idempotency-Key"));
    return Response.json({ batch_id: "batch" });
  };
  for (let attempt = 0; attempt < 2; attempt++) {
    await apiRequest("/orders/id/generate", { method: "POST", body: {}, idempotencyKey: "stable-key" });
  }
  assert.deepEqual(keys, ["stable-key", "stable-key"]);
});

test("API 使用同源路径，支持取消请求", async () => {
  const controller = new AbortController();
  globalThis.fetch = async (url, options) => {
    assert.equal(url, "/api/health");
    assert.equal(options?.signal, controller.signal);
    return Response.json({ status: "ok" });
  };
  assert.deepEqual(await apiGet("/health", controller.signal), { status: "ok" });
});

test("JSON 写入保留中文和 false 参数", async () => {
  globalThis.fetch = async (url, options) => {
    assert.equal(url, "/api/orders/id/params");
    assert.equal(options?.method, "PATCH");
    assert.equal(new Headers(options?.headers).get("Content-Type"), "application/json");
    assert.deepEqual(JSON.parse(options?.body as string), { glasses_keep: false, extra_requirement: "中文" });
    return Response.json({ status: "ready" });
  };
  await apiRequest("/orders/id/params", { method: "PATCH", body: { glasses_keep: false, extra_requirement: "中文" } });
});

test("上传由浏览器生成 multipart boundary", async () => {
  const data = new FormData();
  data.set("file", new Blob(["test"]), "照片.png");
  globalThis.fetch = async (_url, options) => {
    assert.equal(options?.body, data);
    assert.equal(new Headers(options?.headers).has("Content-Type"), false);
    return Response.json({ id: "image-id" });
  };
  await apiRequest("/orders/id/images", { method: "POST", body: data });
});

test("保留后端错误提示和关联 ID", async () => {
  globalThis.fetch = async () => Response.json(
    { error: { message: "数据库尚未就绪" }, request_id: "test-request" },
    { status: 503 },
  );
  await assert.rejects(apiGet("/health"), (error: unknown) => {
    assert.ok(error instanceof ApiError);
    assert.equal(error.message, "数据库尚未就绪");
    assert.equal(error.requestId, "test-request");
    assert.equal(error.status, 503);
    return true;
  });
});

test("代理非 JSON 错误提供可理解的提示", async () => {
  globalThis.fetch = async () => new Response("Bad gateway", { status: 502 });
  await assert.rejects(apiGet("/health"), /服务暂时无法连接/);
});

test("拒绝外部地址和损坏的成功响应", async () => {
  await assert.rejects(apiGet("https://example.com"), /站内相对路径/);
  await assert.rejects(apiGet("//example.com"), /站内相对路径/);
  globalThis.fetch = async () => new Response("invalid");
  await assert.rejects(apiGet("/health"), /无法识别的数据/);
});
