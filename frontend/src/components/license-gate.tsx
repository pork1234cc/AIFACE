"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { requestLicense, type LicenseStatus } from "@/lib/licensing";
import styles from "./license-gate.module.css";

export function LicenseGate({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<LicenseStatus | null>(null);
  const [code, setCode] = useState("");
  const [message, setMessage] = useState("正在检查软件授权…");
  const [busy, setBusy] = useState(true);
  const pending = useRef(false);
  const sequence = useRef(0);

  const check = useCallback(async (action: "status" | "activate" | "verify", value?: string) => {
    if (pending.current) return;
    pending.current = true;
    const current = ++sequence.current;
    try {
      const result = await requestLicense(action, value, AbortSignal.timeout(65000));
      if (current !== sequence.current) return;
      setStatus(result);
      setMessage(result.message);
      if (result.authorized) setCode("");
    } catch {
      if (current !== sequence.current) return;
      setStatus(null);
      setMessage("无法读取授权状态，请检查服务是否启动后重试。");
    } finally {
      if (current === sequence.current) {
        pending.current = false;
        setBusy(false);
      }
    }
  }, []);

  useEffect(() => {
    const initial = window.setTimeout(() => { void check("status"); }, 0);
    const timer = window.setInterval(() => { void check("status"); }, 60000);
    return () => {
      window.clearInterval(timer);
      window.clearTimeout(initial);
      sequence.current += 1;
      pending.current = false;
    };
  }, [check]);

  if (status?.authorized) return <>{children}</>;

  return <main className={styles.screen}>
    <section className={styles.card} aria-labelledby="license-title">
      <p className={styles.brand}>AIFACE</p>
      <h1 id="license-title">激活软件</h1>
      <p>{status?.name || "小红书笔记图片生成器"}</p>
      <form onSubmit={(event) => {
        event.preventDefault();
        if (code.trim() && !pending.current) {
          setBusy(true);
          void check("activate", code);
        }
      }}>
        <label htmlFor="license-code">卡密</label>
        <input id="license-code" type="password" autoComplete="off" maxLength={256}
          placeholder="请输入卡密" value={code} disabled={busy}
          onChange={(event) => setCode(event.target.value)} required />
        <p className={styles.message} role="status" aria-live="polite">{message}</p>
        <div className={styles.actions}>
          <button type="submit" disabled={busy || !code.trim()}>{busy ? "正在验证…" : "激活并进入"}</button>
          <button type="button" className={styles.secondary} disabled={busy}
            onClick={() => {
              if (!pending.current) { setBusy(true); void check("verify"); }
            }}>重新验证</button>
        </div>
      </form>
    </section>
  </main>;
}
