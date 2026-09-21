"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useSyncExternalStore } from "react";
import { ServiceStatus } from "@/components/service-status";
import { activeNavigation } from "@/lib/workspace-state";
import { useWorkspaceLeaveGuard } from "@/hooks/use-leave-guard";

const links = [
  { id: "home", href: "/", text: "工作台", icon: "◫" },
  { id: "orders", href: "/orders", text: "我的订单", icon: "▤" },
  { id: "new", href: "/orders/new", text: "新建订单", icon: "＋" },
  { id: "style", href: "/styles", text: "成图风格", icon: "✳" },
  { id: "model", href: "/model-settings", text: "模型设置", icon: "⚙" },
];
function subscribeHash(callback: () => void) {
  window.addEventListener("hashchange", callback);
  window.addEventListener("popstate", callback);
  return () => {
    window.removeEventListener("hashchange", callback);
    window.removeEventListener("popstate", callback);
  };
}
function getHash() { return window.location.hash; }
function getServerHash() { return ""; }

export function WorkspaceShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const hash = useSyncExternalStore(subscribeHash, getHash, getServerHash);
  const active = activeNavigation(pathname, hash);
  useWorkspaceLeaveGuard();
  const inOrders = pathname === "/orders" || pathname.startsWith("/orders/");
  const suffix = pathname === "/orders/new" ? "新建订单" : pathname.startsWith("/orders/") ? "订单详情" : "";
  return <div className="workspace app-shell">
    <a className="skip-link" href="#workspace-content">跳到主要内容</a>
    <aside className="sidebar app-sidebar">
      <Link className="brand" href="/" aria-label="AIFACE 工作台">
        <span className="brand-mark" aria-hidden="true">a<span>·</span></span>
        <span>AIFACE<small>头像创作工作台</small></span>
      </Link>
      <div className="nav-label">我的工作室</div>
      <nav aria-label="工作台导航">{links.map((item) => {
        // 跨页面锚点交给浏览器导航，确保地址与首次订阅的 hash 一致。
        // Next.js 的客户端跳转可能在组件订阅后更新 hash，却不发送 hashchange。
        const NavigationLink = item.href.startsWith("/#") ? "a" : Link;
        return <NavigationLink
        key={item.id} href={item.href} className={`nav-item${active === item.id ? " active" : ""}`}
        aria-current={active === item.id ? "page" : undefined}
        onClick={(event) => {
          // 首页内部使用原生 hash 事件，同步高亮且保留浏览器前进后退。
          if (pathname !== "/" || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
          if (item.href.startsWith("/#")) {
            event.preventDefault(); window.location.hash = item.href.slice(1);
          } else if (item.id === "home" && window.location.hash) {
            event.preventDefault(); window.location.hash = ""; window.scrollTo({ top: 0 });
          }
        }}>
        <span aria-hidden="true">{item.icon}</span>{item.text}
      </NavigationLink>;
      })}</nav>
      <div className="sidebar-note"><p>整理素材，生成头像，<br />把每份委托认真交付。</p></div>
      <div className="local-tag">本地工作室 · 单张交付</div>
    </aside>
    <main className="app-main" id="workspace-content" tabIndex={-1}>
      <header className="topbar app-topbar">
        <nav aria-label="当前位置" className="breadcrumbs">
          <Link href="/">工作室</Link><span aria-hidden="true">/</span>
          {inOrders ? <><Link href="/orders">我的订单</Link>{suffix && <><span aria-hidden="true">/</span><span aria-current="page">{suffix}</span></>}</> : <span aria-current="page">{pathname === "/styles" ? "风格" : pathname === "/model-settings" ? "模型设置" : "工作台"}</span>}
        </nav>
        <ServiceStatus />
      </header>
      <div className="main-content app-content">{children}</div>
    </main>
  </div>;
}
