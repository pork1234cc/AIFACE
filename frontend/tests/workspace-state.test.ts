import assert from "node:assert/strict";
import { test } from "node:test";
import { activeNavigation, canSwitchFinal, definiteRejection, INITIAL_RUNTIME, parsePending, pollDelay, versionDeliveryAction, workspaceLabel, workspaceStage } from "../src/lib/workspace-state.ts";

for (const path of ["/orders", "/orders/customer-id"]) test(`统一订单导航：${path}`, () => assert.equal(activeNavigation(path), "orders"));
test("新建订单与模型设置单独高亮", () => {
  assert.equal(activeNavigation("/orders/new"), "new");
  assert.equal(activeNavigation("/model-settings"), "model");
});
test("首页与首页锚点各自高亮", () => {
  assert.equal(activeNavigation("/"), "home"); assert.equal(activeNavigation("/", "#workflow"), "home");
  assert.equal(activeNavigation("/", "#style"), "style"); assert.equal(activeNavigation("/other"), "");
  assert.equal(activeNavigation("/orders", "#style"), "orders");
});
const ready = { ...INITIAL_RUNTIME, loaded: true };
test("素材不足、就绪和有结果的阶段", () => {
  assert.equal(workspaceStage("draft", false, ready), 1); assert.equal(workspaceStage("draft", true, ready), 2);
  assert.equal(workspaceStage("review", false, { ...ready, hasResult: true }), 3);
});
test("有旧图时仍优先显示当前运行任务", () => {
  const runtime = { ...ready, hasResult: true, hasOpen: true };
  assert.equal(workspaceStage("review", true, runtime), 2);
  assert.equal(workspaceLabel("review", true, runtime), "任务处理中");
});
test("提交不明不可伪装为空闲", () => {
  assert.equal(workspaceLabel("generating", true, { ...ready, pending: true }), "待核对提交");
  assert.equal(workspaceLabel("generating", true, { ...ready, hasOpen: true, needsAttention: true }), "待核对提交");
});
for (const status of ["completed", "closed"]) test(`终态优先：${status}`, () => assert.equal(workspaceStage(status, false, { ...ready, hasOpen: true }), 4));
test("未加载状态不显示可以生成", () => assert.equal(workspaceLabel("draft", true, INITIAL_RUNTIME), "正在核对任务状态"));
const permissions = { readonly: false, busy: false, loaded: true, hasOpen: false, pending: false, dirty: false };
test("空闲且已加载才可切换版本", () => assert.equal(canSwitchFinal(permissions), true));
for (const key of ["readonly", "busy", "hasOpen", "pending", "dirty"] as const) test(`版本切换禁止：${key}`, () => assert.equal(canSwitchFinal({ ...permissions, [key]: true }), false));
test("断网保留图片但禁止切换", () => assert.equal(canSwitchFinal({ ...permissions, loaded: false }), false));
test("已自动选中的生成图显示当前交付，其他版本可切换", () => {
  assert.equal(versionDeliveryAction("result-a", "result-a"), "current");
  assert.equal(versionDeliveryAction("result-b", "result-a"), "switch");
  assert.equal(versionDeliveryAction("result-a", null), "switch");
});
test("活动快轮询、空闲低频、终态停止", () => {
  assert.equal(pollDelay(true, false), 4000); assert.equal(pollDelay(false, false), 30000);
  assert.equal(pollDelay(false, true), null); assert.equal(pollDelay(true, true), 4000);
});
test("错误退避存在上限", () => { assert.equal(pollDelay(false, false, 1), 8000); assert.equal(pollDelay(false, false, 100), 60000); });
test("待核对请求保留 key 与原正文", () => {
  const request = { path: "/orders/order-123/generate", body: { inputs: [] }, key: "stable-key" };
  assert.deepEqual(parsePending(JSON.stringify(request), "order-123"), request);
  assert.equal(parsePending(null, "order-123"), null);
});
for (const value of ["not-json", "null", "[]", JSON.stringify({ path: "https://evil.invalid", body: {}, key: "stable-key" }), JSON.stringify({ path: "/orders/other/generate", body: {}, key: "stable-key" }), JSON.stringify({ path: "/orders/order-123/generate", body: {}, key: "short" }), JSON.stringify({ path: "/orders/order-123/generate", body: null, key: "stable-key" })]) test(`损坏或跨订单的存储拒绝：${value}`, () => assert.throws(() => parsePending(value, "order-123")));
test("只允许已知的恢复 API 路径", () => {
  assert.ok(parsePending(JSON.stringify({ path: "/tasks/task-id/reconcile", body: {}, key: "stable-key" }), "order-123"));
  assert.ok(parsePending(JSON.stringify({ path: "/batches/batch-id/retry", body: {}, key: "stable-key" }), "order-123"));
  assert.throws(() => parsePending(JSON.stringify({ path: "/tasks/../reconcile", body: {}, key: "stable-key" }), "order-123"));
});
test("网络与幂等冲突保留待核对记录", () => {
  for (const status of [408, 429, 500, 502, 503, 504]) assert.equal(definiteRejection(status), false);
  assert.equal(definiteRejection(409, "idempotency_conflict"), false);
  assert.equal(definiteRejection(409, "data_conflict"), false);
});
test("明确拒绝与事务校验失败可清理本次待核对", () => {
  for (const status of [404, 413, 415, 422]) assert.equal(definiteRejection(status), true);
  assert.equal(definiteRejection(409, "generation_in_progress"), true);
});
