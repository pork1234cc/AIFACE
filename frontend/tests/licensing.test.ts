import assert from "node:assert/strict";
import { test } from "node:test";
import { requestLicense } from "../src/lib/licensing.ts";

test("卡密只在 POST 请求体发送，状态读取禁止缓存", async (t) => {
  const requests: { url: string; init: RequestInit }[] = [];
  t.mock.method(globalThis, "fetch", async (url: string, init: RequestInit) => {
    requests.push({ url, init });
    return Response.json({ authorized: true, name: "测试软件", message: "有效" });
  });
  assert.equal((await requestLicense("activate", " test-code ")).authorized, true);
  assert.equal(requests[0].url, "/api/license/activate");
  assert.equal(requests[0].init.method, "POST");
  assert.equal(requests[0].init.body, '{"code":"test-code"}');
  await requestLicense("status");
  assert.equal(requests[1].init.cache, "no-store");
  assert.equal(requests[1].init.body, undefined);
});

test("授权拒绝和伪真值不能放行业务", async (t) => {
  t.mock.method(globalThis, "fetch", async () => Response.json(
    { authorized: true, message: "拒绝" }, { status: 403 },
  ));
  assert.equal((await requestLicense("verify")).authorized, false);
  t.mock.method(globalThis, "fetch", async () => Response.json({ authorized: "true", message: "错误" }));
  await assert.rejects(requestLicense("status"), /授权状态无效/);
});

test("服务错误与失联不会复用授权状态", async (t) => {
  t.mock.method(globalThis, "fetch", async () => new Response("错误", { status: 500 }));
  await assert.rejects(requestLicense("status"), /无法连接/);
  t.mock.method(globalThis, "fetch", async () => { throw new Error("模拟失联"); });
  await assert.rejects(requestLicense("status"), /模拟失联/);
});
