export type Role = "main" | "material";
export type OrderStatus = "draft" | "generating" | "modifying" | "review" | "completed" | "closed";
export const statusLabels: Record<OrderStatus, string> = {
  draft: "待整理", generating: "生成中", modifying: "修改中", review: "待交付",
  completed: "已完成", closed: "已关闭",
};
export const roleLabels: Record<Role, string> = {
  main: "主照片", material: "素材图",
};
export interface ChangeItem {
  target_description: string;
  change_type: string;
  source_asset_ids: string[];
  instruction: string;
  preserve_instruction: string;
}
export const aspectSizes: Record<string, string> = {
  "16:9": "3840×2160", "21:9": "3840×1648", "4:3": "3264×2448", "3:2": "3504×2336",
  "5:4": "3200×2560", "1:1": "2880×2880", "4:5": "2560×3200", "2:3": "2336×3504",
  "3:4": "2448×3264", "9:16": "2160×3840", "9:21": "1648×3840",
};
export interface RegionPrompt {
  id: string;
  label: string;
  target_description: string;
  origin: "detected" | "manual";
  source_asset_ids: string[];
  instruction: string;
  preserve_instruction: string;
}
export interface DetectedRegion {
  id: string;
  label: string;
  target_description: string;
  origin: "detected";
  mask_value: number;
}
export interface RegionDetection {
  asset_id: string;
  regions: DetectedRegion[];
  mask_url: string;
  width: number;
  height: number;
}
export interface OrderParams {
  schema_version: 2;
  base_asset_id: string | null;
  style_id: string | null;
  changes: ChangeItem[];
  region_asset_id?: string | null;
  region_prompts?: RegionPrompt[];
  material_slots?: (string | null)[] | null;
  aspect_ratio: string;
  output_format: "png" | "jpeg" | "webp";
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
  last_batch_status?: string | null;
}
export interface OrderDetail extends Order {
  assets: Asset[];
  readiness: { ready: boolean; errors: string[] };
}
export interface OrderList { items: Order[]; total: number; page: number; page_size: number }
export interface Style {
  style_id: string;
  is_builtin: boolean;
  style_name: string;
  version: string;
  qa_checklist: string[];
  description: string;
  cover_image: string | null;
  cover_stale?: boolean;
  preview?: {
    task_id: string;
    request_key: string;
    status: "pending" | "submitting" | "queued" | "running" | "downloading" | "succeeded" | "failed" | "submission_unknown";
    error_message: string | null;
    can_resume_download: boolean;
  } | null;
  prompt_template: Record<string, string>;
}
