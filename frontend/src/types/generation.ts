import type { Asset } from "./orders";

export interface GenerationTask {
  id: string;
  slot_index: number;
  attempt_no: number;
  status: string;
  failure_stage: string | null;
  error_message: string | null;
  next_poll_at?: string | null;
  provider_task_id: string | null;
  cost_amount: string | null;
}
export interface BatchSummary {
  batch_id: string;
  operation: "initial" | "revision";
  base_asset_id: string | null;
  revision_instruction: string | null;
  status: string;
  target_count: number;
  created_at: string;
}
export interface GenerationBatch extends BatchSummary {
  config: import("./orders").OrderParams;
  prompt: string;
  style_version: string;
  inputs: { asset_id: string; role: string }[];
  tasks: GenerationTask[];
  outputs: (Asset & { generation_task_id: string })[];
}
export interface GenerationStats {
  revision_count: number;
  successful_revision_count: number;
  generation_attempt_count: number;
  submitted_attempt_count: number;
}
export const generationLabels: Record<string, string> = {
  pending: "等待执行", submitting: "正在提交", queued: "远端排队中", running: "生成中",
  downloading: "正在保存图片", succeeded: "已完成", failed: "明确失败",
  partial_failed: "部分完成", needs_attention: "需要人工核对",
  submission_unknown: "提交结果不明", superseded_unknown: "已另开尝试，旧结果仍未知",
};
