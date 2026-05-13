/** UI state for a pipeline step card. */
export type PipelineStepStatus = "idle" | "loading" | "success" | "error";

export type PipelineStepKey =
  | "sync_tree"
  | "pending_text"
  | "pending_documents"
  | "chunk"
  | "embed";

/** Normalized outcome after an indexing API call (HTTP 2xx body). */
export type PipelineStepRunMeta = {
  step: PipelineStepKey;
  ok: boolean;
  at: number;
};

/** 권장 순서 자동 실행 모달에서 단계별 진행 표시용 */
export type PipelineAutoStepKey = "sync" | "text" | "document" | "chunk" | "embedding";

export type PipelineAutoRunStepStatus = "idle" | "running" | "success" | "error" | "skipped";

export type PipelineAutoStepState = {
  key: PipelineAutoStepKey;
  label: string;
  status: PipelineAutoRunStepStatus;
  startedAt?: string;
  finishedAt?: string;
  durationMs?: number;
  message?: string;
  errorMessage?: string;
};
