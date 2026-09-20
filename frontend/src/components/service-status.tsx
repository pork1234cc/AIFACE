"use client";

import { useEffect, useState } from "react";
import { apiGet } from "@/lib/api";

type Status = { state: "checking" | "ready" | "error"; message: string };

export function ServiceStatus() {
  const [attempt, setAttempt] = useState(0);
  const [status, setStatus] = useState<Status>({ state: "checking", message: "正在连接工作台" });

  useEffect(() => {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 8000);
    let active = true;
    apiGet<{ status: string }>("/health", controller.signal)
      .then((result) => {
        if (!active) return;
        setStatus(result.status === "ok"
          ? { state: "ready", message: "工作台已连接" }
          : { state: "error", message: "工作台暂未就绪" });
      })
      .catch((error: unknown) => {
        if (!active) return;
        setStatus({
          state: "error",
          message: controller.signal.aborted
            ? "连接超时，请重试"
            : error instanceof Error && error.name === "ApiError"
              ? error.message
              : "无法连接工作台，请检查本地服务",
        });
      })
      .finally(() => clearTimeout(timeout));
    return () => { active = false; clearTimeout(timeout); controller.abort(); };
  }, [attempt]);

  return (
    <div className="service-status">
      <p role="status" className={`status-label ${status.state}`}>
        <span aria-hidden="true" className="status-dot" />{status.message}
      </p>
      {status.state === "error" && (
        <button className="text-button" onClick={() => {
          setStatus({ state: "checking", message: "正在连接工作台" });
          setAttempt((value) => value + 1);
        }}>重新连接</button>
      )}
    </div>
  );
}
