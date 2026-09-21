"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { apiGet, errorMessage } from "@/lib/api";
import { type OrderList, statusLabels } from "@/types/orders";

export function RecentOrders() {
  const [data, setData] = useState<OrderList | null>(null);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    void apiGet<OrderList>("/orders?page=1&page_size=5", AbortSignal.any([controller.signal, AbortSignal.timeout(15000)]))
      .then((result) => { if (!controller.signal.aborted) { setData(result); setError(""); } })
      .catch((cause) => { if (!controller.signal.aborted) setError(errorMessage(cause)); });
    return () => controller.abort();
  }, [retry]);
  return <section className="order-panel recent-orders" aria-labelledby="recent-orders-title">
    <div className="section-heading"><h2 id="recent-orders-title">最近订单</h2><Link href="/orders" className="text-button">查看全部 →</Link></div>
    {error ? <div className="order-alert" role="alert">{error} <button className="text-button" onClick={() => setRetry((n) => n + 1)}>重试</button></div>
      : !data ? <p className="muted" role="status">正在读取订单…</p>
      : data.items.length === 0 ? <div className="empty-state"><h3>还没有订单</h3><p>创建第一份委托，上传素材开始创作。</p><Link className="primary-link" href="/orders/new">新建订单 →</Link></div>
      : <div className="recent-order-list">{data.items.map((order) => <Link className="recent-order-row" key={order.id} href={`/orders/${order.id}`}>
        <span><strong>{order.customer_name}</strong><small className="order-meta">{new Date(order.created_at).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", hour12: false })}</small></span>
        <span className={`order-status ${order.status}`}>{statusLabels[order.status]}</span><span aria-hidden="true">→</span>
      </Link>)}</div>}
  </section>;
}
