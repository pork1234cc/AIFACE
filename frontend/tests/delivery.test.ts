import assert from "node:assert/strict";
import { test } from "node:test";
import { fetchDelivery } from "../src/lib/delivery.ts";

test("下载保留图片字节和后端交付文件名", async (context) => {
  context.mock.method(globalThis, "fetch", async (url: string) => {
    assert.equal(url, "/api/orders/order-123/delivery");
    return new Response(new Uint8Array([1, 2, 3]), { headers: {
      "Content-Type": "image/png", "Content-Disposition": 'attachment; filename="AF-order_123.png"',
    } });
  });
  const result = await fetchDelivery("order-123");
  assert.equal(result.filename, "AF-order_123.png");
  assert.equal(result.blob.size, 3);
});

test("下载错误保留业务提示，不把 JSON 当作图片", async (context) => {
  context.mock.method(globalThis, "fetch", async () => new Response(JSON.stringify({error:{message:"尚无当前交付图"}}), {status:409}));
  await assert.rejects(fetchDelivery("order-123"), /尚无当前交付图/);
});

test("拒绝损坏的下载响应和危险文件名", async (context) => {
  context.mock.method(globalThis, "fetch", async () => new Response("bad", {headers:{"Content-Type":"text/html"}}));
  await assert.rejects(fetchDelivery("order-123"), /格式无效/);
  await assert.rejects(fetchDelivery("../other"), /订单信息无效/);
  context.mock.method(globalThis, "fetch", async () => new Response("image", { headers: {
    "Content-Type": "image/png", "Content-Disposition": 'attachment; filename="../outside.png"',
  } }));
  await assert.rejects(fetchDelivery("order-123"), /文件名无效/);
});
