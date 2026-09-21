"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { apiGet, apiRequest, errorMessage } from "@/lib/api";
import { type OrderList, statusLabels } from "@/types/orders";

export default function OrdersPage() {
  const [data, setData] = useState<OrderList | null>(null);
  const [error, setError] = useState("");
  const [actionError, setActionError] = useState("");
  const [actionNotice, setActionNotice] = useState("");
  const [loading, setLoading] = useState(true);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [filter, setFilter] = useState({ page: 1, q: "", status: "", retry: 0 });
  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    let running = false;
    async function load() {
      if (running || controller.signal.aborted || document.hidden) return;
      running = true;
      let delay = 15000;
      try {
        const query = new URLSearchParams({ page: String(filter.page), page_size: "20", q: filter.q });
        if (filter.status) query.set("status", filter.status);
        const result = await apiGet<OrderList>(`/orders?${query}`, AbortSignal.any([controller.signal, AbortSignal.timeout(15000)]));
        if (controller.signal.aborted) return;
        if (result.items.length === 0 && result.total > 0 && filter.page > 1) {
          setLoading(true);
          setFilter((current) => ({ ...current, page: current.page - 1 }));
          return;
        }
        setData(result); setError("");
        if (["generating", "modifying"].includes(filter.status) || result.items.some((item) => ["generating", "modifying"].includes(item.status))) delay = 4000;
      } catch (cause) {
        if (!controller.signal.aborted) setError(errorMessage(cause));
      } finally {
        running = false;
        if (!controller.signal.aborted) {
          setLoading(false);
          timer = setTimeout(() => void load(), delay);
        }
      }
    }
    const wake = () => { if (!document.hidden) { if (timer) clearTimeout(timer); void load(); } };
    window.addEventListener("focus", wake);
    document.addEventListener("visibilitychange", wake);
    void load();
    return () => { controller.abort(); if (timer) clearTimeout(timer); window.removeEventListener("focus", wake); document.removeEventListener("visibilitychange", wake); };
  }, [filter]);
  function changePage(page: number) { setLoading(true); setFilter((current) => ({ ...current, page })); }
  function applyFilters(form: HTMLFormElement) {
    const values = new FormData(form);
    setLoading(true);
    setFilter((current) => ({ ...current, page: 1, q: String(values.get("q") ?? ""), status: String(values.get("status") ?? ""), retry: current.retry + 1 }));
  }
  async function deleteOrder(id: string, customerName: string) {
    if (deletingId || !window.confirm(`确定删除「${customerName}」的订单吗？订单、照片和生成记录将被永久清除。`)) return;
    setDeletingId(id);
    setActionError("");
    setActionNotice("");
    try {
      const result = await apiRequest<{ deleted: boolean; files_removed: boolean }>(`/orders/${id}`, { method: "DELETE" });
      if (!result.deleted) {
        setActionError("订单删除结果无法确认，请刷新列表核对。");
        return;
      }
      if (!result.files_removed) setActionNotice("订单已删除，但照片文件清理失败，请联系管理员处理。");
      setLoading(true);
      setFilter((current) => ({
        ...current,
        page: data?.items.length === 1 && current.page > 1 ? current.page - 1 : current.page,
        retry: current.retry + 1,
      }));
    } catch (cause) {
      setActionError(errorMessage(cause));
    } finally {
      setDeletingId(null);
    }
  }

  return <>
    <Link href="/" className="back-link">← 工作台</Link>
    <div className="page-heading"><div><p className="eyebrow">EVERY LITTLE COMMISSION</p><h1>我的订单</h1><p className="muted">收好每一份委托，从整理照片开始。</p></div><Link className="order-button primary" href="/orders/new">＋ 新建订单</Link></div>
    <section className="order-panel">
      <form className="order-filters" onSubmit={(event) => { event.preventDefault(); applyFilters(event.currentTarget); }}>
        <label>搜索订单<input name="q" placeholder="客户名称" maxLength={100} /></label>
        <label>订单状态<select name="status" onChange={(event) => { if (event.currentTarget.form) applyFilters(event.currentTarget.form); }}><option value="">全部状态</option>{Object.entries(statusLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <button className="order-button" disabled={loading}>搜索</button>
      </form>
      {error && <div className="order-alert" role="alert">{error}<div><button className="text-button" onClick={() => { setLoading(true); setFilter((current) => ({ ...current, retry: current.retry + 1 })); }}>重新加载</button></div></div>}
      {actionError && <div className="order-alert" role="alert">{actionError}</div>}
      {actionNotice && <div className="order-alert" role="status">{actionNotice}</div>}
      {loading ? <p className="muted" role="status">正在读取订单…</p> : !error && data && <>
        {data.items.length === 0 ? <div className="empty-state"><div className="empty-icon" aria-hidden="true">▤</div><h3>{filter.q || filter.status ? "没有符合条件的订单" : "从第一份委托开始"}</h3><p>新建订单，填写客户备注，再整理照片。</p><Link className="primary-link" href="/orders/new">新建订单 →</Link></div> :
          <div className="order-table-wrap"><table className="order-table"><thead><tr><th>客户</th><th>状态</th><th className="date-column">创建时间</th><th>操作</th></tr></thead><tbody>{data.items.map((order) => <tr key={order.id}>
            <td><Link className="order-client" href={`/orders/${order.id}`}>{order.customer_name}</Link><small className="order-mobile-date">{new Date(order.created_at).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", hour12: false })}</small></td>
            <td><span className={`order-status ${order.status}`}>{statusLabels[order.status]}</span>{order.last_batch_status === "failed" && <small className="order-task-alert">上次生成失败</small>}{order.last_batch_status === "needs_attention" && <small className="order-task-alert">任务待核对</small>}</td>
            <td className="muted date-column">{new Date(order.created_at).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", hour12: false })}</td>
            <td><div className="order-row-actions"><Link className="order-button small" href={`/orders/${order.id}`}>打开</Link><button type="button" className="order-button small danger" disabled={deletingId !== null} aria-label={`删除订单：${order.customer_name}`} onClick={() => void deleteOrder(order.id, order.customer_name)}>{deletingId === order.id ? "删除中…" : "删除订单"}</button></div></td>
          </tr>)}</tbody></table></div>}
        <div className="order-pagination"><span className="muted">共 {data.total} 单 · 第 {data.page} 页</span><div className="order-actions"><button className="order-button small" disabled={filter.page <= 1} onClick={() => changePage(filter.page - 1)}>上一页</button><button className="order-button small" disabled={filter.page * data.page_size >= data.total} onClick={() => changePage(filter.page + 1)}>下一页</button></div></div>
      </>}
    </section>
  </>;
}
