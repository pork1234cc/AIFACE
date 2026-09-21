import { RecentOrders } from "@/components/workspace/recent-orders";

export default function Home() {
  return <div className="studio-home order-workspace">
    <section className="page-heading"><h1>头像创作工作台</h1></section>
    <RecentOrders />
  </div>;
}
