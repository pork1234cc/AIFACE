import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  poweredByHeader: false,
  // 隔离验收可使用独立构建目录和后端端口；这些变量仅在服务端读取。
  distDir: process.env.AIFACE_NEXT_DIST_DIR || ".next",
  // 素材上限 20 MiB，额外预留 multipart 表单开销。
  experimental: { proxyClientMaxBodySize: 22 * 1024 * 1024 },
  async rewrites() {
    const origin = process.env.AIFACE_BACKEND_ORIGIN || "http://127.0.0.1:8000";
    return [{ source: "/api/:path*", destination: `${origin}/api/:path*` }];
  },
};

export default nextConfig;
