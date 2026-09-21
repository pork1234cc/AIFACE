"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { DeliveryPanel } from "./delivery-panel";
import { ReconcileForm } from "./reconcile-form";
import type { DeliveryState } from "@/types/deliveries";
import { ApiError, apiGet, apiRequest, errorMessage } from "@/lib/api";
import { latestBatchLog } from "@/lib/generation-log";
import { definiteRejection, OPEN_BATCH_STATUSES, parsePending, pollDelay, type PendingRequest, type WorkspaceRuntime } from "@/lib/workspace-state";
import { type BatchSummary, type GenerationBatch, type GenerationTask, generationLabels } from "@/types/generation";
import { type Asset, type OrderDetail, type OrderParams, type OrderStatus } from "@/types/orders";

export function GenerationPanel({ order, actionTarget, disabled, dirty, baseError, onBusy, onStatus, onRuntime, onBase }: {
  order: OrderDetail; actionTarget: HTMLDivElement | null; disabled: boolean; dirty: boolean; baseError?: string;
  onBusy: (busy: boolean) => void; onStatus: (status: OrderStatus) => void;
  onRuntime: (runtime: WorkspaceRuntime) => void;
  onBase: (asset: Asset, config?: OrderParams) => void;
}) {
  const [history, setHistory] = useState<BatchSummary[]>([]);
  const [batch, setBatch] = useState<GenerationBatch | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [readError, setReadError] = useState("");
  const [actionError, setActionError] = useState("");
  const [storageError, setStorageError] = useState("");
  const [storageReady, setStorageReady] = useState(false);
  const [pending, setPending] = useState<PendingRequest | null>(null);
  const [refresh, setRefresh] = useState(0);
  const [messages, setMessages] = useState<{ id: number; message: string; level: "info" | "error"; time: string }[]>([]);
  const nextMessageId = useRef(0);
  const onLog = useCallback((message: string, level: "info" | "error" = "info") => {
    if (level !== "error") return;
    const time = new Date().toLocaleTimeString("zh-CN", { timeZone: "Asia/Shanghai", hour12: false });
    setMessages((current) => [{ id: ++nextMessageId.current, message, level, time }, ...current].slice(0, 20));
  }, []);

  const revisionDirty = dirty;
  const [delivery, setDelivery] = useState<DeliveryState | null>(null);
  const submitting = useRef(false);
  const mounted = useRef(false);
  const epoch = useRef(0);
  const pendingRef = useRef<PendingRequest | null>(null);
  const statusCallback = useRef(onStatus);
  const storageKey = `aiface:v2:pending:${order.id}`;
  const readonly = order.status === "completed" || order.status === "closed";

  const hasOpen = delivery?.has_open_tasks ?? false;
  const hasResult = !!delivery?.versions.length;
  const needsAttention = hasOpen && (history.some((item) => item.status === "needs_attention") || batch?.status === "needs_attention");
  useEffect(() => { statusCallback.current = onStatus; }, [onStatus]);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => {
    onRuntime({ loaded: loaded && storageReady, hasOpen, hasResult, needsAttention, pending: !!pending || !!storageError });
  }, [loaded, storageReady, hasOpen, hasResult, needsAttention, pending, storageError, onRuntime]);

  useEffect(() => {
    const wake = () => { if (!document.hidden) setRefresh((n) => n + 1); };
    window.addEventListener("focus", wake);
    document.addEventListener("visibilitychange", wake);
    return () => { window.removeEventListener("focus", wake); document.removeEventListener("visibilitychange", wake); };
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    let failures = 0;
    async function load() {
      await Promise.resolve(); // Keep restoration updates outside the synchronous effect body.
      if (controller.signal.aborted) return;
      if (document.hidden) return; // Visibility/focus starts a new cycle.
      const version = epoch.current;
      let next: number | null = 30000;
      try {
        try {
          const restored = parsePending(sessionStorage.getItem(storageKey), order.id);
          if (!submitting.current) { pendingRef.current = restored; setPending(restored); }
          setStorageError(""); setStorageReady(true);
        } catch {
          setStorageError("本地待核对记录无法读取或格式损坏。已暂停新提交；请保留记录并核对服务端任务，不要直接重新生成。");
          setStorageReady(false);
        }
        const signal = AbortSignal.any([controller.signal, AbortSignal.timeout(15000)]);
        const [list, finals] = await Promise.all([
          apiGet<{ items: BatchSummary[] }>(`/orders/${order.id}/batches?page=1&page_size=1`, signal),
          apiGet<DeliveryState>(`/orders/${order.id}/finals`, signal),
        ]);
        const currentId = list.items[0]?.batch_id;
        const detail = currentId ? await apiGet<GenerationBatch>(`/batches/${currentId}`, signal) : null;
        if (controller.signal.aborted || version !== epoch.current) return;
        setHistory(list.items); setBatch(detail);
        setDelivery(finals); setLoaded(true); setReadError("");
        statusCallback.current(finals.order_status);
        failures = 0;
        next = pollDelay(finals.has_open_tasks || !!pendingRef.current, finals.order_status === "completed" || finals.order_status === "closed");
      } catch (cause) {
        if (!controller.signal.aborted && version === epoch.current) {
          setReadError(errorMessage(cause)); setLoaded(false); failures += 1;
          next = pollDelay(false, false, failures);
        }
      } finally {
        if (!controller.signal.aborted && next !== null) timer = setTimeout(() => void load(), next);
      }
    }
    void load();
    return () => { controller.abort(); if (timer) clearTimeout(timer); };
  }, [order.id, refresh, storageKey]);

  async function send(path: string, body: unknown, retry?: PendingRequest): Promise<boolean> {
    if (submitting.current || disabled || !storageReady || (!retry && (pending || !loaded))) return false;
    submitting.current = true; epoch.current += 1; onBusy(true); setActionError("");
    const request = retry ?? { path, body, key: "" };
    try {
      if (!retry) {
        if (typeof globalThis.crypto?.randomUUID !== "function") {
          setActionError("当前浏览器无法创建安全请求编号。请使用 localhost 或安全连接后再提交。");
          return false;
        }
        request.key = crypto.randomUUID();
      }
      // Persist BEFORE the POST. Retrying an uncertain request must reuse its key AND body.
      try { sessionStorage.setItem(storageKey, JSON.stringify(request)); }
      catch { setStorageError("浏览器无法保存待核对请求，未发送本次生成。请检查会话存储权限。"); setStorageReady(false); return false; }
      pendingRef.current = request; setPending(request);
      const result = await apiRequest<GenerationBatch>(request.path, { method: "POST", body: request.body, idempotencyKey: request.key });
      // Even if the user left the page, a confirmed response can clear its own stored receipt.
      try { sessionStorage.removeItem(storageKey); }
      catch { if (mounted.current) { setStorageError("服务端已接收，但本地核对记录未能清理。请恢复存储后使用原请求核对。"); setStorageReady(false); } return false; }
      pendingRef.current = null;
      if (!mounted.current) return true;
      epoch.current += 1; setPending(null); setBatch(result); setLoaded(false);
      // Do not reopen controls during the interval before the next GET snapshot.
      setDelivery((current) => current ? { ...current, has_open_tasks: OPEN_BATCH_STATUSES.has(result.status) } : current);
      setRefresh((n) => n + 1);
      return true;
    } catch (cause) {
      if (cause instanceof ApiError && definiteRejection(cause.status, cause.code)) {
        try { sessionStorage.removeItem(storageKey); pendingRef.current = null; if (mounted.current) setPending(null); }
        catch { if (mounted.current) { setStorageError("本地待核对记录清理失败，请刷新核对。"); setStorageReady(false); } }
      }
      if (mounted.current) setActionError(errorMessage(cause));
      return false;
    } finally {
      submitting.current = false;
      if (mounted.current) { epoch.current += 1; onBusy(false); setRefresh((n) => n + 1); }
    }
  }
  function finalsChanged(value: DeliveryState) {
    epoch.current += 1; setDelivery(value);
    setRefresh((n) => n + 1);
  }
  const blocked = disabled || !!pending || !loaded || !storageReady;
  const latestTasks = new Map<number, GenerationTask>();
  batch?.tasks.forEach((task) => {
    if ((latestTasks.get(task.slot_index)?.attempt_no ?? 0) < task.attempt_no) latestTasks.set(task.slot_index, task);
  });
  function retryTask(task: GenerationTask) {
    if (batch) void send(`/batches/${batch.batch_id}/retry`, { slot_indices: [task.slot_index] });
  }
  function reconcileTask(path: string, body: unknown) { void send(path, body); }
  const { summary: latestLog, error: latestError } = latestBatchLog(history, batch);
  const failedLog = latestLog && ["failed", "partial_failed", "needs_attention"].includes(latestLog.status) ? latestLog : null;
  const attentionTasks = !readonly ? Array.from(latestTasks.values()).filter((task) => task.status === "failed" || task.status === "submission_unknown") : [];
  const showAttention = !!(baseError || readError || actionError || storageError || pending ||
    (delivery && !delivery.items.length && delivery.versions.length > 0) || messages.length || failedLog || attentionTasks.length || needsAttention);
  return <section className="order-panel generation-panel">
    <div className="section-heading"><h2>{hasResult ? "检查与交付" : "生成头像"}</h2><button type="button" className="text-button" onClick={() => setRefresh((n) => n + 1)}>刷新状态</button></div>
    {!hasResult && <div className="generation-start">
      <div className="result-placeholder" aria-hidden="true"><span>◫</span></div>
      {!readonly && <><button className="order-button primary generate-cta" disabled={blocked || hasOpen || !order.readiness.ready} onClick={() => void send(`/orders/${order.id}/generate`, { config: order.params })}>{hasOpen ? "生成中…" : "生成 1 张头像"}</button></>}
    </div>}
    {hasResult && !readonly && <div className="generation-start">
      <button className="order-button primary" disabled={blocked || hasOpen || !delivery?.items.some((item) => item.asset_id === order.params.base_asset_id)} onClick={() => void send(`/orders/${order.id}/revise`, { config: order.params })}>{hasOpen ? "生成中…" : "生成修改图"}</button></div>}
    {delivery && <DeliveryPanel data={delivery} actionTarget={actionTarget} disabled={blocked} loaded={loaded && storageReady} pending={!!pending || !!storageError} revisionDirty={revisionDirty}
      onBusy={onBusy} onStatus={onStatus} onChange={finalsChanged}
      onRevise={onBase} onLog={onLog} />}

    {showAttention && <section className="generation-log" aria-label="需要处理的状态">
      <h3>需要处理</h3>
      <ul className="generation-log-list" aria-live="polite">
        {baseError && <li className="error" role="alert">{baseError}</li>}
        {readError && <li className="error" role="alert">状态读取失败：{readError} 已保留最近结果，恢复连接前暂停写操作。</li>}
        {actionError && <li className="error" role="alert">{actionError}</li>}
        {storageError && <li className="error" role="alert">{storageError}</li>}
        {pending && <li className="error">上次提交尚未确认。使用原请求核对，不会更换请求编号。<button type="button" className="order-button small" disabled={disabled || !storageReady} onClick={() => void send(pending.path, pending.body, pending)}>核对上次提交</button></li>}
        {delivery && !delivery.items.length && delivery.versions.length > 0 && <li>当前尚未指定交付图，请在版本历史中选择一张。</li>}
        {messages.map((item) => <li className="error" key={item.id}><time>{item.time}</time>{item.message}</li>)}
        {failedLog && <li className="error"><time>{new Date(failedLog.created_at).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai" })}</time>{failedLog.operation === "revision" ? "修改" : "生成"}：{generationLabels[failedLog.status] ?? failedLog.status}{latestError ? ` · ${latestError}` : ""}</li>}
        {batch && attentionTasks.map((task) => {
          // 点击事件才读取提交状态；此处只创建处理函数。
          // eslint-disable-next-line react-hooks/refs
          if (task.status === "failed") return <li className="error" key={task.id}>任务失败。<button type="button" className="order-button small" disabled={blocked || hasOpen || revisionDirty} onClick={() => retryTask(task)}>{["download", "persist", "protocol"].includes(task.failure_stage ?? "") ? "恢复原任务（不重新生成）" : "重试生成"}</button></li>;
          if (task.status === "submission_unknown") return <li className="error" key={task.id}>提交结果不明，请先核对供应商是否已受理。<ReconcileForm task={task} disabled={blocked || revisionDirty} onSubmit={reconcileTask} /></li>;
          return null;
        })}
        {needsAttention && !attentionTasks.length && <li className="error">需要核对提交。</li>}
      </ul>
    </section>}
  </section>;
}
