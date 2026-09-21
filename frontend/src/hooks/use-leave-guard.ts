"use client";

import { useEffect, useId } from "react";

const guardedForms = new Set<string>();
export function hasUnsavedChanges() { return guardedForms.size > 0; }

export function useLeaveGuard(dirty: boolean) {
  const id = useId();
  useEffect(() => {
    if (dirty) guardedForms.add(id);
    else guardedForms.delete(id);
    return () => { guardedForms.delete(id); };
  }, [dirty, id]);
}

/** Native back/forward is not monkey-patched. Session drafts cover that route. */
export function useWorkspaceLeaveGuard() {
  useEffect(() => {
    const beforeUnload = (event: BeforeUnloadEvent) => {
      if (!hasUnsavedChanges()) return;
      event.preventDefault(); event.returnValue = "";
    };
    const click = (event: MouseEvent) => {
      if (!hasUnsavedChanges() || event.defaultPrevented || event.button !== 0
        || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      const link = event.target instanceof Element ? event.target.closest("a[href]") : null;
      if (!(link instanceof HTMLAnchorElement) || link.target === "_blank" || link.hasAttribute("download")) return;
      const target = new URL(link.href, window.location.href);
      if (target.origin === location.origin && target.pathname === location.pathname && target.search === location.search) return;
      if (!window.confirm("有未保存的修改。离开后将保留本标签页草稿，但不会保存到订单。确认离开？")) {
        event.preventDefault(); event.stopPropagation();
      }
    };
    window.addEventListener("beforeunload", beforeUnload);
    document.addEventListener("click", click, true);
    return () => {
      window.removeEventListener("beforeunload", beforeUnload);
      document.removeEventListener("click", click, true);
    };
  }, []);
}
