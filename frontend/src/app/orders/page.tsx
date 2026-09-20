"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { apiGet, errorMessage } from "@/lib/api";
import { type OrderList, statusLabels } from "@/types/orders";

export default function OrdersPage() {
  const [data, setData] = useState<OrderList | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState({ page: 1, q: "", status: "", retry: 0 });
  useEffect(() => {
    const controller = new AbortController();
    const query = new URLSearchParams({ page: String(filter.page), page_size: "20", q: filter.q });
    if (filter.status) query.set("status", filter.status);
    apiGet<OrderList>(`/orders?${query}`, AbortSignal.any([controller.signal, AbortSignal.timeout(15000)]))
      .then((result) => { if (!controller.signal.aborted) { setData(result); setError(""); } })
      .catch((cause) => { if (!controller.signal.aborted) setError(errorMessage(cause)); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [filter]);
  function changePage(page: number) { setLoading(true); setFilter({ ...filter, page }); }

  return <>
    <Link href="/" className="back-link">← 工作台</Link>
    <div className="page-heading"><div><p className="eyebrow">EVERY LITTLE COMMISSION</p><h1>我的订单</h1><p className="muted">收好每一份委托，从整理照片开始。</p></div><Link className="order-button primary" href="/orders/new">＋ 新建订单</Link></div>
    <section className="order-panel">
      <form className="order-filters" onSubmit={(event) => {
        event.preventDefault(); const form = new FormData(event.currentTarget);
        setLoading(true); setFilter({ page: 1, q: String(form.get("q") ?? ""), status: String(form.get("status") ?? ""), retry: filter.retry + 1 });
      }}>
        <label>搜索订单<input name="q" placeholder="客户备注名或订单编号" maxLength={100} /></label>
        <label>订单状态<select name="status"><option value="">全部状态</option>{Object.entries(statusLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <button className="order-button" disabled={loading}>搜索</button>
      </form>
      {error && <div className="order-alert" role="alert">{error}<div><button className="text-button" onClick={() => { setLoading(true); setFilter({ ...filter, retry: filter.retry + 1 }); }}>重新加载</button></div></div>}
      {loading ? <p className="muted" role="status">正在读取订单…</p> : !error && data && <>
        {data.items.length === 0 ? <div className="empty-state"><div className="empty-icon" aria-hidden="true">▤</div><h3>{filter.q || filter.status ? "没有符合条件的订单" : "从第一份委托开始"}</h3><p>新建订单，填写客户备注，再整理照片。</p><Link className="primary-link" href="/orders/new">新建订单 →</Link></div> :
          <div className="order-table-wrap"><table className="order-table"><thead><tr><th>客户 / 订单编号</th><th>状态</th><th className="date-column">创建时间</th><th>操作</th></tr></thead><tbody>{data.items.map((order) => <tr key={order.id}>
            <td><Link className="order-client" href={`/orders/${order.id}`}>{order.customer_name}</Link><div className="order-code">{order.order_no}</div></td>
            <td><span className={`order-status ${order.status}`}>{statusLabels[order.status]}</span></td>
            <td className="muted date-column">{new Date(order.created_at).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", hour12: false })}</td>
            <td><Link className="order-button small" href={`/orders/${order.id}`}>打开</Link></td>
          </tr>)}</tbody></table></div>}
        <div className="order-pagination"><span className="muted">共 {data.total} 单 · 第 {data.page} 页</span><div className="order-actions"><button className="order-button small" disabled={filter.page <= 1} onClick={() => changePage(filter.page - 1)}>上一页</button><button className="order-button small" disabled={filter.page * data.page_size >= data.total} onClick={() => changePage(filter.page + 1)}>下一页</button></div></div>
      </>}
    </section>
  </>;
}
