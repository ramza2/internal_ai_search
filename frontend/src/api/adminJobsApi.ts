import { httpClient } from "@/api/httpClient";
import type {
  AdminJobDetailResponse,
  AdminJobFailuresResponse,
  AdminJobListResponse,
  AdminJobFailuresParams,
  AdminJobsListParams,
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
