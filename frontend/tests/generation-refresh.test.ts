import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import vm from "node:vm";
import ts from "typescript";
import { ApiError } from "../src/lib/api.ts";
import * as policy from "../src/lib/workspace-state.ts";

// 执行组件真实轮询 effect，使用可控请求和计时器模拟慢网，不依赖真实时间。
function polling(read: (path: string) => Promise<unknown>) {
  const source = readFileSync(new URL("../src/components/orders/generation-panel.tsx", import.meta.url), "utf8");
  const marker = source.indexOf("    const controller = new AbortController();");
  const end = source.indexOf("  }, [order.id, refresh, storageKey]);", marker);
  assert.ok(marker > 0 && end > marker);
  const body = source.slice(marker, end);
  const pictures: unknown[] = [];
  const timers: { callback: () => void; ms: number }[] = [];
  const flags = { delivery: false, tasks: false };
  const noop = () => {};
  const context = vm.createContext({
    ...policy, ApiError, AbortController, AbortSignal, document: { hidden: false },
    epoch: { current: 0 }, submitting: { current: false }, pendingRef: { current: null },
    order: { id: "test-order" }, storageKey: "test", sessionStorage: { getItem: () => null },
    setPending: noop, setStorageError: noop, setStorageReady: noop,
    setHistory: noop, setBatch: noop, setDelivery: (value: unknown) => pictures.push(value),
    setLoaded: noop, setReadError: noop, setDeliveryError: noop, setTaskError: noop,
    setDeliveryLoaded: (value: boolean) => { flags.delivery = value; },
    setTasksLoaded: (value: boolean) => { flags.tasks = value; },
    statusCallback: { current: noop }, errorMessage: () => "模拟超时",
    setTimeout: (callback: () => void, ms: number) => { timers.push({ callback, ms }); return timers.length; },
    clearTimeout: noop, apiGet: read,
  });
  const stop = vm.runInContext(ts.transpile(`(function () { ${body} })()`), context) as () => void;
  return { pictures, timers, flags, stop, context };
}

const finals = { order_status: "review", has_open_tasks: false, versions: [{ id: "image" }], items: [{ asset_id: "image" }] };
const flush = () => new Promise<void>((resolve) => setImmediate(resolve));

test("任务详情仍挂起时立即显示已读取的交付图", async () => {
  let finish!: (value: unknown) => void;
  const detail = new Promise((resolve) => { finish = resolve; });
  const run = polling(async (path) => path.includes("/finals") ? finals
    : path.startsWith("/orders/") ? { items: [{ batch_id: "batch" }] } : detail);
  try {
    await flush();
    assert.equal(run.pictures.length, 1);
    assert.equal(run.flags.tasks, false);
    finish({ status: "succeeded", tasks: [] });
    await flush();
    assert.equal(run.flags.delivery && run.flags.tasks, true);
  } finally { run.stop(); }
});

test("详情读取失败不阻止后续交付快轮询，仍锁定写操作", async () => {
  let count = 0;
  const run = polling(async (path) => {
    if (path.includes("/finals")) return ++count === 1 ? { ...finals, has_open_tasks: true } : finals;
    if (path.startsWith("/orders/")) return { items: [{ batch_id: "batch" }] };
    throw new Error("模拟详情失败");
  });
  try {
    await flush();
    assert.equal(run.pictures.length, 1);
    const next = run.timers.find((timer) => timer.ms === 4000);
    assert.ok(next);
    next.callback();
    await flush();
    assert.equal(run.pictures.length, 2);
    assert.equal(run.flags.tasks, false);
  } finally { run.stop(); }
});

test("矛盾交付响应保持短轮询，不把图片空列表当成最终状态", async () => {
  const run = polling(async (path) => path.includes("/finals") ? { ...finals, versions: [] }
    : path.startsWith("/orders/") ? { items: [] } : null);
  try {
    await flush();
    assert.equal(run.pictures.length, 0);
    assert.ok(run.timers.some((timer) => timer.ms === 4000));
    assert.equal(run.flags.delivery, false);
  } finally { run.stop(); }
});

test("退出页面后迟到的交付响应不得写入状态", async () => {
  let finish!: (value: unknown) => void;
  const pending = new Promise((resolve) => { finish = resolve; });
  const run = polling(async (path) => path.includes("/finals") ? pending : { items: [] });
  await flush();
  run.stop(); finish(finals);
  await flush();
  assert.equal(run.pictures.length, 0);
});

test("提交新操作后旧请求返回不能覆盖新状态", async () => {
  let finish!: (value: unknown) => void;
  const pending = new Promise((resolve) => { finish = resolve; });
  const run = polling(async (path) => path.includes("/finals") ? pending : { items: [] });
  try {
    await flush();
    run.context.epoch.current += 1;
    finish(finals);
    await flush();
    assert.equal(run.pictures.length, 0);
    assert.ok(run.timers.some((timer) => timer.ms === 4000));
  } finally { run.stop(); }
});

test("页面隐藏时暂停读取，恢复后的新轮询立即加载", async () => {
  let reads = 0;
  const run = polling(async (path) => { reads++; return path.includes("/finals") ? finals : { items: [] }; });
  run.context.document.hidden = true;
  await flush();
  assert.equal(reads, 0);
  run.stop();
  const resumed = polling(async (path) => path.includes("/finals") ? finals : { items: [] });
  try { await flush(); assert.equal(resumed.pictures.length, 1); }
  finally { resumed.stop(); }
});
