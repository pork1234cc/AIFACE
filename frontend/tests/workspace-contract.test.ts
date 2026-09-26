import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
const read = (name: string) => readFileSync(new URL(`../src/${name}`, import.meta.url), "utf8");

test("公共导航只由根布局装配一次", () => {
  assert.match(read("app/layout.tsx"), /<WorkspaceShell>/);
  assert.doesNotMatch(read("app/orders/layout.tsx"), /<aside|className=\"sidebar/);
  assert.doesNotMatch(read("app/page.tsx"), /<aside|className=\"sidebar/);
});
test("导航去除重复流程并提供风格页面", () => {
  const shell = read("components/workspace/workspace-shell.tsx");
  assert.doesNotMatch(shell, /text: "创作流程"/); assert.match(shell, /href: "\/styles", text: "成图风格"/); assert.match(shell, /aria-current=/);
  assert.match(shell, /href: "\/orders\/new", text: "新建订单"/);
  assert.match(shell, /href: "\/model-settings", text: "模型设置"/);
  assert.doesNotMatch(shell, /sidebar-create/);
});
test("订单工作区不再包含额外 ready 动作", () => {
  const page = read("app/orders/[id]/page.tsx");
  assert.match(page, /className="order-workbench"/); assert.match(page, /className="order-result"/);
  assert.doesNotMatch(page, /\/ready`/);
});
test("窄屏恢复导航而不是继续隐藏", () => assert.match(read("app/workspace.css"), /\.app-sidebar nav \{ display: grid/));
test("操作错误与轮询错误是独立状态", () => {
  const code = read("components/orders/generation-panel.tsx");
  assert.match(code, /setActionError/); assert.match(code, /setDeliveryError/); assert.match(code, /setTaskError/);
  const polling = code.slice(code.indexOf("async function loadDelivery()"), code.indexOf("async function send("));
  assert.doesNotMatch(polling, /setActionError/);
});
