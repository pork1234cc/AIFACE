export class ApiError extends Error {
  readonly status: number;
  readonly requestId?: string;
  readonly code?: string;
  constructor(message: string, status: number, requestId?: string, code?: string) {
    super(message); this.name = "ApiError";
    this.status = status; this.requestId = requestId; this.code = code;
  }
}
export async function apiGet<T>(path: string, signal?: AbortSignal): Promise<T> {
  return apiRequest<T>(path, { signal });
}
export async function apiRequest<T>(
  path: string,
  options: { method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE"; body?: unknown; signal?: AbortSignal; idempotencyKey?: string } = {},
): Promise<T> {
  if (!path.startsWith("/") || path.startsWith("//")) throw new Error("API 路径必须为站内相对路径");
  const response = await fetch(`/api${path}`, {
    method: options.method ?? "GET", signal: options.signal ?? AbortSignal.timeout(30000),
    headers: {
      Accept: "application/json",
      ...(options.idempotencyKey ? { "Idempotency-Key": options.idempotencyKey } : {}),
      ...(options.body !== undefined && !(options.body instanceof FormData) ? { "Content-Type": "application/json" } : {}),
    },
    body: options.body instanceof FormData ? options.body : options.body === undefined ? undefined : JSON.stringify(options.body),
    cache: "no-store",
  });
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const errorBody = body as { error?: { message?: unknown; code?: unknown }; request_id?: string } | null;
    throw new ApiError(
      typeof errorBody?.error?.message === "string" ? errorBody.error.message : "服务暂时无法连接，请稍后重试",
      response.status, errorBody?.request_id,
      typeof errorBody?.error?.code === "string" ? errorBody.error.code : undefined,
    );
  }
  if (body === null) throw new ApiError("服务返回了无法识别的数据", response.status);
  return body as T;
}
export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message + (error.requestId ? `（请求编号：${error.requestId}）` : "");
  return "连接中断或请求超时，请刷新核对保存结果后再操作";
}
