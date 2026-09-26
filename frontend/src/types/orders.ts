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
  "16:9": "2560×1440", "21:9": "2912×1248", "4:3": "2176×1632", "3:2": "2304×1536",
  "5:4": "2080×1664", "1:1": "1920×1920", "4:5": "1664×2080", "2:3": "1536×2304",
  "3:4": "1632×2176", "9:16": "1440×2560", "9:21": "1248×2912",
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
  mask_value?: number;
  parent_id?: string | null;
  kind?: "object" | "part" | "detail" | "background";
  depth?: number;
  bbox?: number[];
  mask_runs?: number[];
  mask_area?: number;
  mask_score?: number;
  location_status?: "located" | "unlocated";
}
export interface RegionDetection {
  asset_id: string;
  regions: DetectedRegion[];
  mask_url?: string;
  version?: string;
  width: number;
  height: number;
}
export interface ElementStatus {
  asset_id: string;
  status: "idle" | "running" | "ready" | "failed";
  message?: string;
  result?: Omit<RegionDetection, "asset_id"> | null;
}
export interface OrderParams {
  schema_version: 2;
  mode?: "edit" | "generate";
  size?: string | null;
  response_format?: "url" | "b64_json";
  async_mode?: boolean;
  mask?: string | null;
  mask_base_asset_id?: string | null;
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
