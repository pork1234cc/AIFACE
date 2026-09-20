import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AIFACE · 头像工作台",
  description: "从一张照片开始，认真完成每一份头像委托。",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="zh-CN" data-scroll-behavior="smooth"><body>{children}</body></html>;
}
