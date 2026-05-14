/** PipelineRunModal — 백그라운드(admin job) 단계 추적 */

export type PipelineBackgroundStepId = "sync" | "text" | "doc" | "chunk" | "embed";

export type BackgroundPipelineStepState = {
  key: PipelineBackgroundStepId;
  label: string;
  jobId?: string;
  jobType?: string;
  status?: string;
  progressPercent?: number | null;
  workerId?: string | null;
  heartbeatAt?: string | null;
  startedAt?: string | null;
  finishedAt?: string | null;
  errorMessage?: string | null;
  lastUpdatedAt?: string;
  /** Job 생성 API 직후 안내 문구 */
  enqueueMessage?: string;
};

export type ExecutionMode = "immediate" | "background";
