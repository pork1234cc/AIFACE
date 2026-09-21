"use client";

import { useEffect, useState } from "react";

/** A tab-local draft; no photos or credentials are written to browser storage. */
export function useSessionDraft<T>(key: string, initial: T, validate: (value: unknown) => value is T) {
  const [seed] = useState(initial);
  const [value, setValue] = useState(initial);
  const [baseline, setBaseline] = useState(initial);
  const [restored, setRestored] = useState(false);
  const [storageWarning, setStorageWarning] = useState("");
  useEffect(() => {
    let active = true;
    // Restore after hydration. Fields remain disabled until this completes.
    void Promise.resolve().then(() => {
      if (!active) return;
      try {
        const raw = sessionStorage.getItem(key);
        if (raw !== null) {
          const candidate: unknown = JSON.parse(raw);
          if (validate(candidate)) setValue(candidate);
          else setStorageWarning("本地草稿格式不匹配，未自动恢复；请核对后重新填写。");
        } else setValue(seed);
      } catch {
        setStorageWarning("无法读取会话草稿；离开前请保存，浏览器返回可能无法恢复。");
      }
      setRestored(true);
    });
    return () => { active = false; };
  }, [key, seed, validate]);
  const dirty = JSON.stringify(value) !== JSON.stringify(baseline);
  function change(next: T) {
    setValue(next);
    try {
      if (JSON.stringify(next) === JSON.stringify(baseline)) sessionStorage.removeItem(key);
      else sessionStorage.setItem(key, JSON.stringify(next));
      setStorageWarning("");
    } catch { setStorageWarning("会话草稿未能保存；离开前请保存到订单。"); }
  }
  function reset(next: T) {
    setValue(next); setBaseline(next);
    try { sessionStorage.removeItem(key); setStorageWarning(""); }
    catch { setStorageWarning("服务端已更新，但本地旧草稿未能清理；再次打开请以服务端记录为准。"); }
  }
  return { value, change, reset, dirty, restored, storageWarning };
}
