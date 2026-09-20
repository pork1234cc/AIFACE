"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { apiRequest, errorMessage } from "@/lib/api";
import type { OrderDetail } from "@/types/orders";

export default function NewOrderPage() {
  const router = useRouter();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  return <>
    <Link href="/orders" className="back-link">← 我的订单</Link>
    <div className="page-heading"><div><p className="eyebrow">A NEW LITTLE STORY</p><h1>新建一份委托</h1><p className="muted">先记下客人，再慢慢整理照片与要求。</p></div></div>
    {error && <div className="order-alert" role="alert">{error}</div>}
    <div className="detail-grid"><section className="order-panel"><form onSubmit={async (event) => {
      event.preventDefault();
      if (saving) return;
      const form = new FormData(event.currentTarget);
      setSaving(true); setError("");
      try {
        const order = await apiRequest<OrderDetail>("/orders", { method: "POST", body: { customer_name: String(form.get("customer_name")).trim(), note: String(form.get("note")).trim() } });
        router.push(`/orders/${order.id}`);
      } catch (cause) { setError(errorMessage(cause)); setSaving(false); }
    }}><fieldset className="order-form" disabled={saving}>
      <label>客户备注名<input name="customer_name" required maxLength={100} placeholder="例如：小红 / 尾号 0321" autoComplete="off" /></label>
      <label>订单备注<textarea name="note" maxLength={2000} rows={5} placeholder="记录沟通信息、交付约定等。具体出图要求在下一步填写。" /></label>
      <div className="order-actions"><button className="order-button primary">{saving ? "正在创建…" : "创建订单，整理素材 →"}</button><Link className="muted" href="/orders">返回列表</Link></div>
    </fieldset></form></section>
    <aside className="style-summary"><h3>蜡笔小像 · 固定风格</h3><p>软糯 Q 版、柔和腮红、蜡笔颗粒。<br />纯白背景 · 1:1 方形<br /><br />每单最多 4 张素材，参考图最多 1 张。<br />整理完素材与参数后，可保存为待生成订单。</p></aside></div>
  </>;
}
