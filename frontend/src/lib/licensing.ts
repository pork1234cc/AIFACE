export type LicenseStatus = {
  authorized: boolean;
  name: string;
  message: string;
  expire_time: string;
};

export async function requestLicense(
  action: "status" | "activate" | "verify",
  code?: string,
  signal?: AbortSignal,
): Promise<LicenseStatus> {
  const response = await fetch(`/api/license/${action}`, {
    method: action === "status" ? "GET" : "POST",
    cache: "no-store",
    signal,
    ...(action === "activate" ? {
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code: code?.trim() ?? "" }),
    } : {}),
  });
  if (!response.ok && response.status !== 403) throw new Error("无法连接授权服务，请稍后重试");
  const data: unknown = await response.json();
  if (!data || typeof data !== "object" || !("authorized" in data)
      || typeof data.authorized !== "boolean" || !("message" in data)
      || typeof data.message !== "string") {
    throw new Error("授权状态无效，请重新验证");
  }
  return {
    authorized: response.ok && data.authorized === true,
    name: "name" in data && typeof data.name === "string" ? data.name : "AIFACE",
    message: data.message,
    expire_time: "expire_time" in data && typeof data.expire_time === "string" ? data.expire_time : "",
  };
}
