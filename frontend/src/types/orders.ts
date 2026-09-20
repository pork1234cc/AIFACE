export type Role = "person_main" | "person_aux" | "reference";
export type OrderStatus = "draft" | "ready" | "review" | "revision_requested" | "completed" | "closed";
export const statusLabels: Record<OrderStatus, string> = {
  draft: "待整理", ready: "待生成", review: "待交付", revision_requested: "待修改",
  completed: "已完成", closed: "已关闭",
};
export const roleLabels: Record<Role, string> = {
  person_main: "主照片", person_aux: "辅助照片", reference: "参考图",
};
export interface OrderParams {
  hair_source_asset_id: string | null;
  glasses_keep: boolean;
  clothes_mode: "person" | "reference" | "simplified";
  clothes_source_asset_id: string | null;
  background: "white";
  aspect_ratio: "1:1";
  extra_requirement: string;
}
export interface Asset {
  id: string;
  order_id: string;
  kind: "input" | "generated";
  input_role: Role;
  is_active_input: boolean;
  original_name: string;
  mime_type: string;
  byte_size: number;
  width: number;
  height: number;
  content_url: string;
  review_status: "unreviewed" | "selected" | "discarded";
}
export interface Order {
  id: string;
  order_no: string;
  customer_name: string;
  note: string;
  status: OrderStatus;
  style_id: string;
  created_at: string;
  updated_at: string;
  params: OrderParams;
}
export interface OrderDetail extends Order {
  assets: Asset[];
  readiness: { ready: boolean; errors: string[] };
}
export interface OrderList { items: Order[]; total: number; page: number; page_size: number }
export interface Style {
  style_id: string;
  style_name: string;
  version: string;
  qa_checklist: string[];
}
