/** Global navigation is owned exclusively by the root WorkspaceShell. */
export default function OrdersLayout({ children }: { children: React.ReactNode }) {
  return <div className="order-workspace">{children}</div>;
}
