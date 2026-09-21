"use client";

import { useEffect, useState } from "react";
import { apiGet } from "@/lib/api";

type Status = { state: "checking" | "ready" | "error"; message: string };
export function ServiceStatus() {
  const [attempt, setAttempt] = useState(0);
  const [status, setStatus] = useState<Status>({ state: "checking", message: "正在连接本地 API" });
  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    async function check() {
      if (controller.signal.aborted || document.hidden) return;
      try {
        const result = await apiGet<{ status: string }>("/health", AbortSignal.any([controller.signal, AbortSignal.timeout(8000)]));
        if (!controller.signal.aborted) setStatus(result.status === "ok" ? { state: "ready", message: "本地 API 已连接" } : { state: "error", message: "本地 API 未就绪" });
      } catch {
        if (!controller.signal.aborted) setStatus({ state: "error", message: "本地 API 连接失败" });
      } finally { if (!controller.signal.aborted) timer = setTimeout(() => void check(), 30000); }
    }
    const wake = () => { if (!document.hidden) setAttempt((n) => n + 1); };
    document.addEventListener("visibilitychange", wake);
    void check();
    return () => { controller.abort(); if (timer) clearTimeout(timer); document.removeEventListener("visibilitychange", wake); };
  }, [attempt]);
  return <div className="service-status" title="仅表示 API 与数据库可连接，不表示独立生成 Worker 或供应商在线。">
    <p role="status" className={`status-label ${status.state}`}><span aria-hidden="true" className="status-dot" />{status.message}</p>
    {status.state === "error" && <button className="text-button" onClick={() => { setStatus({ state: "checking", message: "正在连接本地 API" }); setAttempt((n) => n + 1); }}>重连</button>}
  </div>;
}
