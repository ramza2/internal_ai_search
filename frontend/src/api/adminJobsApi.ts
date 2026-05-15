import { httpClient } from "@/api/httpClient";
import type {
  AdminJobCancelRequest,
  AdminJobCancelResponse,
  AdminJobRetryRequest,
  AdminJobRetryResponse,
  AdminJobDetailResponse,
  AdminJobFailuresResponse,
  AdminJobListResponse,
  AdminJobFailuresParams,
  AdminJobsListParams,
  AdminProcessPendingTextJobRequest,
  AdminProcessPendingTextJobResponse,
  AdminProcessPendingDocumentsJobRequest,
  AdminProcessPendingDocumentsJobResponse,
  AdminChunkCompletedTextJobRequest,
  AdminChunkCompletedTextJobResponse,
  AdminEmbedPendingChunksJobRequest,
  AdminEmbedPendingChunksJobResponse,
  AdminSyncTreeJobRequest,
  AdminSyncTreeJobResponse,
  AdminTestEnqueueBody,
  AdminTestEnqueueResponse,
} from "@/types/adminJobs";

export async function getAdminJobs(params: AdminJobsListParams): Promise<AdminJobListResponse> {
  const { data } = await httpClient.get<AdminJobListResponse>("/api/admin/jobs", { params });
  return data;
}

export async function getAdminJob(jobId: string): Promise<AdminJobDetailResponse> {
  const { data } = await httpClient.get<AdminJobDetailResponse>(`/api/admin/jobs/${jobId}`);
  return data;
}

export async function getAdminJobFailures(
  jobId: string,
  params?: AdminJobFailuresParams
): Promise<AdminJobFailuresResponse> {
  const { data } = await httpClient.get<AdminJobFailuresResponse>(`/api/admin/jobs/${jobId}/failures`, {
    params,
  });
  return data;
}

/** Dev-only: queue a PENDING test job for the DB polling worker skeleton. */
export async function postAdminTestEnqueue(body: AdminTestEnqueueBody): Promise<AdminTestEnqueueResponse> {
  const { data } = await httpClient.post<AdminTestEnqueueResponse>("/api/admin/jobs/test-enqueue", body);
  return data;
}

/** Queue a real WEBDAV_SYNC_TREE PENDING job for the DB worker. */
export async function postAdminSyncTreeJob(body: AdminSyncTreeJobRequest): Promise<AdminSyncTreeJobResponse> {
  const { data } = await httpClient.post<AdminSyncTreeJobResponse>("/api/admin/jobs/sync-tree", body);
  return data;
}

/** Queue a real PROCESS_PENDING_TEXT PENDING job for the DB worker. */
export async function postAdminProcessPendingTextJob(
  body: AdminProcessPendingTextJobRequest
): Promise<AdminProcessPendingTextJobResponse> {
  const { data } = await httpClient.post<AdminProcessPendingTextJobResponse>(
    "/api/admin/jobs/process-pending-text",
    body
  );
  return data;
}

export async function postAdminProcessPendingDocumentsJob(
  body: AdminProcessPendingDocumentsJobRequest
): Promise<AdminProcessPendingDocumentsJobResponse> {
  const { data } = await httpClient.post<AdminProcessPendingDocumentsJobResponse>(
    "/api/admin/jobs/process-pending-documents",
    body
  );
  return data;
}

/** Queue a real CHUNK_COMPLETED_TEXT PENDING job for the DB worker. */
export async function postAdminChunkCompletedTextJob(
  body: AdminChunkCompletedTextJobRequest
): Promise<AdminChunkCompletedTextJobResponse> {
  const { data } = await httpClient.post<AdminChunkCompletedTextJobResponse>(
    "/api/admin/jobs/chunk-completed-text",
    body
  );
  return data;
}

/** Queue a real EMBED_PENDING_CHUNKS PENDING job for the DB worker. */
export async function postAdminEmbedPendingChunksJob(
  body: AdminEmbedPendingChunksJobRequest
): Promise<AdminEmbedPendingChunksJobResponse> {
  const { data } = await httpClient.post<AdminEmbedPendingChunksJobResponse>(
    "/api/admin/jobs/embed-pending-chunks",
    body
  );
  return data;
}

/** Request cancel on a PENDING (immediate) or RUNNING (→ CANCELLING) job. */
export async function cancelAdminJob(
  jobId: string,
  body?: AdminJobCancelRequest
): Promise<AdminJobCancelResponse> {
  const payload =
    body && (body.reason !== undefined && body.reason !== null && String(body.reason).trim() !== "")
      ? { reason: String(body.reason).trim() }
      : {};
  const { data } = await httpClient.post<AdminJobCancelResponse>(`/api/admin/jobs/${jobId}/cancel`, payload);
  return data;
}

/** Clone a terminal job into a new PENDING worker job (manual retry). */
export async function retryAdminJob(
  jobId: string,
  body?: AdminJobRetryRequest
): Promise<AdminJobRetryResponse> {
  const payload: Record<string, unknown> = {};
  if (body?.force === true) payload.force = true;
  if (body?.priority !== undefined && body?.priority !== null) payload.priority = body.priority;
  const { data } = await httpClient.post<AdminJobRetryResponse>(`/api/admin/jobs/${jobId}/retry`, payload);
  return data;
}
