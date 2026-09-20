"use client";

import { useEffect, useRef, useState } from "react";
import { RevisionForm } from "./revision-form";
import { DeliveryPanel } from "./delivery-panel";
import type { DeliveryState } from "@/types/deliveries";
import { ApiError, apiGet, apiRequest, errorMessage } from "@/lib/api";
import { type BatchSummary, type GenerationBatch, type GenerationTask, type GenerationStats, generationLabels } from "@/types/generation";
import { type Asset, type OrderDetail, type OrderStatus, roleLabels } from "@/types/orders";

type PendingRequest = { path: string; body: unknown; key: string };

function ReconcileForm({ task, disabled, onSubmit }: {
  task: GenerationTask; disabled: boolean; onSubmit: (path: string, body: unknown) => void;
}) {
  const [action, setAction] = useState("link_remote_task");
  const [remote, setRemote] = useState("");
  const [note, setNote] = useState("");
  const [risk, setRisk] = useState(false);
  return <details className="reconcile-form"><summary>核对这次提交</summary>
    <p className="muted">先在供应商后台核对。超时本身不能证明请求未受理。</p>
    <form onSubmit={(event) => {
      event.preventDefault();
      onSubmit(`/tasks/${task.id}/reconcile`, {
        action, note: note.trim(), provider_task_id: action === "link_remote_task" ? remote.trim() : null,
        acknowledge_possible_duplicate_charge: action === "resubmit_with_risk" && risk,
      });
    }}><fieldset disabled={disabled} className="order-form">
      <label>核对结果<select value={action} onChange={(e) => { setAction(e.target.value); setRisk(false); }}>
        <option value="link_remote_task">关联已找到的远端任务</option>
        <option value="confirm_not_accepted">已确认供应商未受理</option>
        <option value="resubmit_with_risk">接受可能重复计费，重新生成</option>
      </select></label>
      {action === "link_remote_task" && <label>供应商任务编号<input required maxLength={128} pattern="[a-zA-Z0-9_-]+" value={remote} onChange={(e) => setRemote(e.target.value)} /></label>}
      <label>核对依据<textarea required minLength={5} maxLength={1000} placeholder="记录后台查询结果或客服确认依据" value={note} onChange={(e) => setNote(e.target.value)} /></label>
      {action === "resubmit_with_risk" && <label className="risk-check"><input type="checkbox" required checked={risk} onChange={(e) => setRisk(e.target.checked)} />我接受旧请求可能已受理，重新生成可能重复计费</label>}
      <button className="order-button" disabled={note.trim().length < 5 || (action === "resubmit_with_risk" && !risk)}>记录核对结果</button>
    </fieldset></form>
  </details>;
}

export function GenerationPanel({ order, disabled, onBusy, onStatus }: {
  order: OrderDetail; disabled: boolean; onBusy: (busy: boolean) => void; onStatus: (status: OrderStatus) => void;
}) {
  const [history, setHistory] = useState<BatchSummary[]>([]);
  const [batch, setBatch] = useState<GenerationBatch | null>(null);
  const [selected, setSelected] = useState("");
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [hasOpen, setHasOpen] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState("");
  const [pending, setPending] = useState<PendingRequest | null>(null);
  const [refresh, setRefresh] = useState(0);
  const [base, setBase] = useState<Asset | null>(null);
  const [stats, setStats] = useState<GenerationStats | null>(null);
  const [delivery, setDelivery] = useState<DeliveryState | null>(null);
  const submitting = useRef(false);
  const statusCallback = useRef(onStatus);
  const storageKey = `aiface:pending:${order.id}`;
  const active = order.assets.filter((asset) => asset.kind === "input" && asset.is_active_input);
  useEffect(() => { statusCallback.current = onStatus; }, [onStatus]);
  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function load() {
      try {
        const signal = AbortSignal.any([controller.signal, AbortSignal.timeout(15000)]);
        const list = await apiGet<{ items: BatchSummary[]; total: number }>(`/orders/${order.id}/batches?page=${page}&page_size=10`, signal);
        const currentId = selected || list.items[0]?.batch_id;
        const detail = currentId ? await apiGet<GenerationBatch>(`/batches/${currentId}`, signal) : null;
        const statistics = await apiGet<GenerationStats>(`/orders/${order.id}/generation-stats`, signal);
        const finals = await apiGet<DeliveryState>(`/orders/${order.id}/finals`, signal);
        if (controller.signal.aborted) return;
        setHistory(list.items); setTotal(list.total); setBatch(detail);
        setStats(statistics);
        setDelivery(finals); setHasOpen(finals.has_open_tasks); setLoaded(true);
        const stored = sessionStorage.getItem(storageKey);
        setPending(stored ? JSON.parse(stored) as PendingRequest : null);
        statusCallback.current(finals.order_status);
        setError("");
      } catch (cause) {
        if (!controller.signal.aborted) { setError(errorMessage(cause)); setLoaded(false); }
      } finally {
        if (!controller.signal.aborted) timer = setTimeout(() => void load(), 4000);
      }
    }
    void load();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [order.id, page, selected, refresh, storageKey]);

  async function send(path: string, body: unknown, retry?: PendingRequest) {
    if (submitting.current) return;
    submitting.current = true; onBusy(true); setError("");
    const request = retry ?? { path, body, key: crypto.randomUUID() };
    try {
      // 请求编号与原始正文先保存在会话中；刷新后仍可核对同一次提交。
      sessionStorage.setItem(storageKey, JSON.stringify(request)); setPending(request);
      const result = await apiRequest<GenerationBatch>(request.path, {
        method: "POST", body: request.body, idempotencyKey: request.key,
      });
      sessionStorage.removeItem(storageKey); setPending(null); setBatch(result);
      setBase(null);
      setSelected(result.batch_id); setPage(1); setRefresh((value) => value + 1);
    } catch (cause) {
      if (cause instanceof ApiError && [404, 409, 413, 422].includes(cause.status)) {
        sessionStorage.removeItem(storageKey); setPending(null);
      }
      setError(errorMessage(cause));
    } finally { submitting.current = false; onBusy(false); }
  }
  const blocked = disabled || !!pending;
  const latestTasks = new Map<number, GenerationTask>();
  batch?.tasks.forEach((task) => {
    if ((latestTasks.get(task.slot_index)?.attempt_no ?? 0) < task.attempt_no) latestTasks.set(task.slot_index, task);
  });
  return <section className="order-panel generation-panel">
    <div className="section-heading"><h2>生成与交付</h2><span className="pill">每次 1 张</span></div>
    {stats && <p className="muted">修改 {stats.revision_count} 轮 · 成功 {stats.successful_revision_count} 轮 · 生成尝试 {stats.generation_attempt_count} 次 · 已进入提交 {stats.submitted_attempt_count} 次（费用未知）</p>}
    {!delivery?.versions.length && <><p className="muted">按已保存的风格和创作要求生成一张交付图。</p>
    <ol className="generation-inputs">{active.map((asset) => <li key={asset.id}>{roleLabels[asset.input_role]} · {asset.original_name}</li>)}</ol></>}
    {error && <div className="order-alert" role="alert">{error}</div>}
    {pending && <div className="order-alert">上次提交尚未确认结果。请使用原请求核对，避免重复生成。<div><button className="order-button" disabled={disabled} onClick={() => void send(pending.path, pending.body, pending)}>重试确认上次提交</button></div></div>}
    <div className="order-actions">{!delivery?.versions.length && <button className="order-button primary" disabled={blocked || !loaded || !order.readiness.ready || hasOpen} onClick={() => void send(`/orders/${order.id}/generate`, { inputs: active.map((asset) => ({ asset_id: asset.id, role: asset.input_role })) })}>生成交付图</button>}
      <button className="order-button" onClick={() => setRefresh((value) => value + 1)}>刷新状态</button></div>
    {hasOpen && <p className="muted">本单有未结束任务，完成或核对前不能再次生成。</p>}
    {delivery && <DeliveryPanel data={delivery} disabled={blocked || !loaded} onBusy={onBusy} onStatus={onStatus} onRevise={setBase} onChange={(value) => { setDelivery(value); setBase(null); setRefresh((number) => number + 1); }} />}
    {base && <RevisionForm key={base.id} base={base} inputs={active} disabled={blocked || hasOpen || !loaded} onCancel={() => setBase(null)} onSubmit={(body) => void send(`/orders/${order.id}/revise`, body)} />}
    {history.length > 0 && <label className="generation-history">生成记录<select value={selected || history[0].batch_id} onChange={(e) => setSelected(e.target.value)}>
      {history.map((item) => <option key={item.batch_id} value={item.batch_id}>{new Date(item.created_at).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai" })} · {item.operation === "revision" ? "修改" : item.target_count === 2 ? "旧双图记录" : "生成"} · {generationLabels[item.status]}</option>)}
    </select></label>}
    {total > 10 && <div className="order-pagination"><button className="order-button small" disabled={page === 1} onClick={() => { setSelected(""); setPage(page - 1); }}>较新记录</button><span>{page} / {Math.ceil(total / 10)}</span><button className="order-button small" disabled={page * 10 >= total} onClick={() => { setSelected(""); setPage(page + 1); }}>较早记录</button></div>}
    {batch && <>
      {batch.operation === "revision" && <div className="order-notice"><p>修改要求：{batch.revision_instruction}</p><p>基础图：<a href={`/api/images/${batch.base_asset_id}/content`} target="_blank" rel="noreferrer">查看基础版本 ↗</a> · 风格版本 {batch.style_version} · 本次输入 {batch.inputs.length} 张</p></div>}
      <p className="generation-status" role="status">{generationLabels[batch.status]} · {batch.outputs.length} / {batch.target_count} 张已保存</p>
      <div className="task-list">{Array.from(latestTasks.values()).map((task) => {
        const output = batch.outputs.find((asset) => asset.generation_task_id === task.id);
        return <article className="asset-card" key={task.id}>
          <div className="asset-info"><strong>结果 {task.slot_index + 1} · 第 {task.attempt_no} 次尝试</strong><p>{generationLabels[task.status]}</p>
            {output && <a href={output.content_url} target="_blank" rel="noreferrer">查看本次结果（{output.width} × {output.height}）↗</a>}
            <small>费用：{task.cost_amount === null ? "未知" : task.cost_amount}</small>
            {task.error_message && <p className="task-error">{task.error_message}</p>}
            {task.status === "failed" && <button className="order-button" disabled={blocked} onClick={() => void send(`/batches/${batch.batch_id}/retry`, { slot_indices: [task.slot_index] })}>{["download", "persist", "protocol"].includes(task.failure_stage ?? "") ? "恢复原任务" : "重试生成"}</button>}
            {task.status === "submission_unknown" && <ReconcileForm task={task} disabled={blocked} onSubmit={(path, body) => void send(path, body)} />}
          </div>
        </article>;
      })}</div>
      <details className="removed-list"><summary>查看全部尝试（{batch.tasks.length}）</summary>{batch.tasks.map((task) => <p className="muted" key={task.id}>结果 {task.slot_index + 1} / 尝试 {task.attempt_no}：{generationLabels[task.status]}{task.error_message ? ` · ${task.error_message}` : ""}</p>)}</details>
    </>}
    {loaded && total === 0 && <p className="muted">还没有生成记录。</p>}
  </section>;
}
