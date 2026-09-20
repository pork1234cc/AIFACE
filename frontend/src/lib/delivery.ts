import { ApiError } from "./api.ts";

export async function fetchDelivery(orderId: string): Promise<{ blob: Blob; filename: string }> {
  if (!/^[a-zA-Z0-9_-]+$/.test(orderId)) throw new Error("订单编号无效");
  const response = await fetch(`/api/orders/${orderId}/delivery`, {
    cache: "no-store", signal: AbortSignal.timeout(30000),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ApiError(typeof body?.error?.message === "string" ? body.error.message : "下载失败，请稍后重试", response.status, body?.request_id);
  }
  if (!["image/png", "image/jpeg", "image/webp"].includes(response.headers.get("content-type") ?? "")) {
    throw new ApiError("交付文件格式无效，请刷新后重试", response.status);
  }
  const filename = response.headers.get("content-disposition")?.match(/filename="([a-zA-Z0-9_-]+\.(?:png|jpg|webp))"/)?.[1];
  if (!filename) throw new ApiError("交付文件名无效，请刷新后重试", response.status);
  const blob = await response.blob();
  if (!blob.size) throw new ApiError("交付文件为空", response.status);
  return { blob, filename };
}
