/** Pure UI policy. Server-side validation remains authoritative. */
export const OPEN_BATCH_STATUSES = new Set(["pending", "running", "needs_attention"]);
export type WorkspaceRuntime = {
  loaded: boolean;
  hasOpen: boolean;
  hasResult: boolean;
  needsAttention: boolean;
  pending: boolean;
};
export const INITIAL_RUNTIME: WorkspaceRuntime = {
  loaded: false, hasOpen: false, hasResult: false, needsAttention: false, pending: false,
};
export function workspaceStage(status: string, ready: boolean, runtime: WorkspaceRuntime) {
  if (status === "completed" || status === "closed") return 4;
  if (runtime.hasOpen || runtime.pending || runtime.needsAttention) return 2;
  if (runtime.hasResult) return 3;
  return ready ? 2 : 1;
}
export function workspaceLabel(status: string, ready: boolean, runtime: WorkspaceRuntime) {
  if (status === "completed") return "已完成";
  if (status === "closed") return "已关闭";
  if (runtime.pending || runtime.needsAttention) return "待核对提交";
  if (runtime.hasOpen) return "任务处理中";
  if (!runtime.loaded) return "正在核对任务状态";
  if (runtime.hasResult) return "检查与交付";
  return ready ? "可以生成" : "整理素材与要求";
}
export function canSwitchFinal(options: {
  readonly: boolean; busy: boolean; loaded: boolean; hasOpen: boolean; pending: boolean; dirty: boolean;
}) {
  return options.loaded && !options.readonly && !options.busy && !options.hasOpen && !options.pending && !options.dirty;
}
export function versionDeliveryAction(assetId: string, currentAssetId: string | null): "current" | "switch" {
  return assetId === currentAssetId ? "current" : "switch";
}
export function pollDelay(hasOpen: boolean, readonly: boolean, failures = 0): number | null {
  if (failures) return Math.min(60000, 4000 * 2 ** Math.min(failures, 4));
  if (hasOpen) return 4000;
  return readonly ? null : 30000;
}
export function activeNavigation(pathname: string, hash = "") {
  if (pathname === "/orders/new") return "new";
  if (pathname === "/orders" || pathname.startsWith("/orders/")) return "orders";
  if (pathname === "/model-settings") return "model";
  if (pathname === "/" && hash === "#workflow") return "home";
  if (pathname === "/styles" || (pathname === "/" && hash === "#style")) return "style";
  return pathname === "/" ? "home" : "";
}
export type PendingRequest = { path: string; body: unknown; key: string };
export function parsePending(raw: string | null, orderId: string): PendingRequest | null {
  if (raw === null) return null;
  const value: unknown = JSON.parse(raw);
  if (!value || typeof value !== "object") throw new Error("待核对记录格式错误");
  const item = value as Record<string, unknown>;
  const orderPaths = [`/orders/${orderId}/generate`, `/orders/${orderId}/revise`];
  const recoveryPath = typeof item.path === "string" && /^\/(batches\/[A-Za-z0-9_-]+\/retry|tasks\/[A-Za-z0-9_-]+\/reconcile)$/.test(item.path);
  if (typeof item.path !== "string" || (!orderPaths.includes(item.path) && !recoveryPath)
    || typeof item.key !== "string" || !/^[A-Za-z0-9_-]{8,128}$/.test(item.key)
    || !item.body || typeof item.body !== "object" || Array.isArray(item.body)) {
    throw new Error("待核对记录无效；请核对服务端记录，不要直接重新生成");
  }
  return { path: item.path, key: item.key, body: item.body };
}
export function definiteRejection(status: number, code?: string) {
  // Keep uncertain failures and idempotency conflicts for reconciliation.
  return [404, 413, 415, 422].includes(status)
    || (status === 409 && ["generation_in_progress", "order_readonly", "order_not_ready"].includes(code ?? ""));
}
