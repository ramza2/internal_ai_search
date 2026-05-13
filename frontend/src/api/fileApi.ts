import { httpClient } from "@/api/httpClient";
import type { FilePreviewResponse, FileStatsResponse } from "@/types/file";

export async function getFilePreview(
  fileId: string,
  params: { chunk_id?: string; query?: string }
): Promise<FilePreviewResponse> {
  const { data } = await httpClient.get<FilePreviewResponse>(
    `/api/files/${fileId}/preview`,
    { params }
  );
  return data;
}

/** GET /api/files/stats — 전체 또는 `data_source_id` 범위 */
export async function getFileStats(params?: {
  data_source_id?: string | null;
  include_deleted?: boolean;
}): Promise<FileStatsResponse> {
  const { data } = await httpClient.get<FileStatsResponse>("/api/files/stats", {
    params: {
      data_source_id: params?.data_source_id || undefined,
      include_deleted: params?.include_deleted,
    },
  });
  return data;
}

/** GET /api/data-sources/{id}/file-stats (백엔드 별칭) */
export async function getDataSourceFileStats(
  dataSourceId: string,
  params?: { include_deleted?: boolean }
): Promise<FileStatsResponse> {
  const { data } = await httpClient.get<FileStatsResponse>(
    `/api/data-sources/${dataSourceId}/file-stats`,
    { params }
  );
  return data;
}
