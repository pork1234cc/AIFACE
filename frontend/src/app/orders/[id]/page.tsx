"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";
import { AssetPanel } from "@/components/orders/asset-panel";
import { GenerationPanel } from "@/components/orders/generation-panel";
import { ParamsPanel } from "@/components/orders/params-panel";
import { apiGet, apiRequest, errorMessage } from "@/lib/api";
import { type OrderDetail, type Style, statusLabels } from "@/types/orders";

function BasicInfo({ order, disabled, onSave, onBusy }: {
  order: OrderDetail; disabled: boolean; onSave: (order: OrderDetail) => void; onBusy: (busy: boolean) => void;
}) {
  const [name, setName] = useState(order.customer_name);
  const [note, setNote] = useState(order.note);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  return <section className="order-panel"><h2>订单信息</h2>{error && <div className="order-alert" role="alert">{error}</div>}{message && <p className="order-notice" role="status">{message}</p>}
    <form onSubmit={async (event) => {
      event.preventDefault(); onBusy(true); setError(""); setMessage("");
      try {
        const updated = await apiRequest<OrderDetail>(`/orders/${order.id}`, { method: "PATCH", body: { customer_name: name.trim(), note: note.trim() } });
        setName(updated.customer_name); setNote(updated.note); onSave(updated); setMessage("订单信息已保存");
      } catch (cause) { setError(errorMessage(cause)); }
      finally { onBusy(false); }
    }}><fieldset className="order-form" disabled={disabled}>
      <label>客户备注名<input required maxLength={100} value={name} onChange={(event) => setName(event.target.value)} /></label>
      <label>订单备注<textarea maxLength={2000} value={note} onChange={(event) => setNote(event.target.value)} /></label>
      <div><button className="order-button">保存订单信息</button></div>
    </fieldset></form>
  </section>;
}

export default function OrderDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [order, setOrder] = useState<OrderDetail | null>(null);
  const [style, setStyle] = useState<Style | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [preview, setPreview] = useState("");
  const [reload, setReload] = useState(0);
  const [notice, setNotice] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    const signal = AbortSignal.any([controller.signal, AbortSignal.timeout(15000)]);
    Promise.all([apiGet<OrderDetail>(`/orders/${id}`, signal), apiGet<Style>("/styles/q_crayon_001", signal)])
      .then(([data, styleData]) => { if (!controller.signal.aborted) { setOrder(data); setStyle(styleData); setError(""); } })
      .catch((cause) => { if (!controller.signal.aborted) setError(errorMessage(cause)); });
    return () => controller.abort();
  }, [id, reload]);
  function updated(data: OrderDetail) { setOrder(data); setPreview(""); setNotice(""); }
  const readonly = order?.status === "completed" || order?.status === "closed";
  return <>
    <Link className="back-link" href="/orders">← 我的订单</Link>
    {error && <div className="order-alert" role="alert">{error}<div><button className="text-button" onClick={() => setReload(reload + 1)}>重新加载</button></div></div>}
    {!order && !error && <p role="status" className="muted">正在读取订单…</p>}
    {order && <>
      <div className="page-heading"><div><p className="eyebrow">A PORTRAIT IN THE MAKING</p><h1>{order.customer_name}的委托</h1><p className="order-code">{order.order_no}</p></div><span className={`order-status ${order.status}`}>{statusLabels[order.status]}</span></div>
      {readonly ? <div className="order-notice">该订单已完成或关闭，仅供查看。</div> : <div className="order-notice" role="status">
        {dirty ? "创作要求尚未保存，请先保存再调整素材或检查就绪。" : order.readiness.ready ? "素材与参数已齐备，订单可待生成。" : "还差一点整理，就能准备生成。"}
        {!order.readiness.ready && <ul>{order.readiness.errors.map((item) => <li key={item}>{item}</li>)}</ul>}
      </div>}
      <div className="detail-grid"><div>
        <BasicInfo key={id} order={order} disabled={busy || readonly || dirty} onBusy={setBusy} onSave={updated} />
        <AssetPanel order={order} disabled={busy || readonly || dirty} onBusy={setBusy} onChange={updated} />
      </div><div>
        <div className="style-summary"><h3>{style?.style_name ?? "蜡笔小像"}</h3><p>纯白背景 · 1:1 方形 · 每次生成 1 张<br />{style?.qa_checklist.join(" · ")}</p></div>
        <ParamsPanel key={`${id}:${JSON.stringify(order.params)}`} order={order} disabled={busy || readonly} onBusy={setBusy} onDirty={setDirty} onSave={updated} />
        <section className="order-panel"><h2>准备生成</h2><p className="muted">先保存素材与创作要求，再到下方生成交付图。</p>
          {notice && <p className="order-notice" role="status">{notice}</p>}
          <div className="order-actions"><button className="order-button primary" disabled={busy || readonly || dirty} onClick={async () => {
            setBusy(true); setError("");
            try { updated(await apiRequest<OrderDetail>(`/orders/${id}/ready`, { method: "POST" })); setNotice("订单已准备好，保存为待生成状态。"); }
            catch (cause) { setError(errorMessage(cause)); }
            finally { setBusy(false); }
          }}>检查并保存为待生成</button>
          <button className="order-button" disabled={busy || readonly || dirty || !order.readiness.ready} onClick={async () => {
            setBusy(true); setError("");
            try {
              const result = await apiRequest<{ prompt: string }>(`/orders/${id}/prompt-preview`, { method: "POST", body: { inputs: order.assets.filter((a) => a.kind === "input" && a.is_active_input).map((a) => ({ asset_id: a.id, role: a.input_role })) } });
              setPreview(result.prompt);
            } catch (cause) { setError(errorMessage(cause)); }
            finally { setBusy(false); }
          }}>预览创作要求</button></div>
          {preview && <div className="prompt-preview">{preview}</div>}
        </section>
      </div></div>
      <GenerationPanel key={id} order={order} disabled={busy || readonly || dirty} onBusy={setBusy} onStatus={(status) => setOrder((current) => current && current.status !== status ? { ...current, status } : current)} />
    </>}
  </>;
}
