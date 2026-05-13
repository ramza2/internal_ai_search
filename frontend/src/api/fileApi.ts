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

export async function getFileStats(): Promise<FileStatsResponse> {
  const { data } = await httpClient.get<FileStatsResponse>("/api/files/stats");
  return data;
}
