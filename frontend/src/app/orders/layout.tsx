import Link from "next/link";
import { ServiceStatus } from "@/components/service-status";
import "./orders.css";

export default function OrdersLayout({ children }: { children: React.ReactNode }) {
  return <div className="workspace">
    <aside className="sidebar">
      <Link className="brand" href="/"><span className="brand-mark" aria-hidden="true">a<span>·</span></span><span>AIFACE<small>头像创作工作台</small></span></Link>
      <div className="nav-label">我的工作室</div>
      <nav aria-label="工作台导航"><Link className="nav-item" href="/">工作台</Link><Link className="nav-item active" href="/orders">我的订单</Link><Link className="nav-item" href="/orders/new">新建订单</Link></nav>
      <div className="sidebar-note"><span className="tiny-flower" aria-hidden="true">✳</span><p>把素材整理好，<br />让每份委托有迹可循。</p></div>
      <div className="local-tag">● 本地工作室</div>
    </aside>
    <main><header className="topbar"><span>工作室 / 我的订单</span><ServiceStatus /></header><div className="main-content order-workspace">{children}</div></main>
  </div>;
}
