import { httpClient } from "@/api/httpClient";
import type {
  AdminJobDetailResponse,
  AdminJobFailuresResponse,
  AdminJobListResponse,
  AdminJobFailuresParams,
  AdminJobsListParams,
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
