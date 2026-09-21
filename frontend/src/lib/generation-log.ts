import type { BatchSummary, GenerationBatch } from "../types/generation";

export function latestBatchLog(history: BatchSummary[], batch: GenerationBatch | null): {
  summary: BatchSummary | null; error: string | null;
} {
  const summary = history[0] ?? batch;
  const error = batch && summary && batch.batch_id === summary.batch_id
    ? batch.tasks.at(-1)?.error_message ?? null : null;
  return { summary, error };
}
