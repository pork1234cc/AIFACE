import type { Style } from "../types/orders.ts";

export function previewBusy(style: Style): boolean {
  return ["pending", "submitting", "queued", "running", "downloading"].includes(style.preview?.status ?? "");
}

export function previewLabel(style: Style): string {
  if (previewBusy(style)) return style.preview?.status === "downloading" ? "下载中…" : "生成中…";
  if (style.preview?.status === "submission_unknown") return "核对任务";
  if (style.preview?.can_resume_download) return "恢复下载";
  if (style.preview?.status === "failed") return "重试生成";
  return style.cover_image ? "重新生成示意图" : "生成示意图";
}

export function parsePreviewPending(value: string | null): { key: string; version: number } | null {
  if (!value) return null;
  try {
    const item: unknown = JSON.parse(value);
    if (!item || typeof item !== "object") return null;
    const record = item as Record<string, unknown>;
    return typeof record.key === "string" && /^[a-zA-Z0-9_-]{8,128}$/.test(record.key)
      && typeof record.version === "number" && Number.isSafeInteger(record.version) && record.version > 0
      ? { key: record.key, version: record.version } : null;
  } catch { return null; }
}
