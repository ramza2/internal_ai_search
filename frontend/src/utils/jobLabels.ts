import type { BadgeVariant } from "@/components/ui";

const JOB_TYPE_LABELS: Record<string, string> = {
  MANUAL_SCAN: "수동 작업",
  WEBDAV_SYNC_ROOT: "루트 동기화",
  WEBDAV_SYNC_TREE: "재귀 동기화",
  PROCESS_PENDING_TEXT: "텍스트 처리",
  PROCESS_PENDING_DOCUMENTS: "문서 처리",
  CHUNK_COMPLETED_TEXT: "Chunk 생성",
  EMBED_PENDING_CHUNKS: "Embedding 생성",
  PIPELINE: "파이프라인",
};

/** Korean label for dashboard / jobs table; unknown codes pass through. */
export function getJobTypeLabel(jobType: string): string {
  const k = (jobType || "").trim().toUpperCase();
  if (!k) return "—";
  return JOB_TYPE_LABELS[k] ?? jobType;
}

/** Badge variant for scan_job / job list status (defensive for future states). */
export function getJobStatusBadgeVariant(status: string): BadgeVariant {
  const u = (status || "").toUpperCase();
  if (u === "COMPLETED") return "success";
  if (u === "FAILED") return "danger";
  if (u === "RUNNING") return "warning";
  if (u === "PENDING") return "primary";
  if (u === "PARTIAL") return "warning";
  if (u === "CANCELLING") return "warning";
  if (u === "CANCELLED" || u === "STOPPED") return "neutral";
  return "neutral";
}
