import { httpClient } from "@/api/httpClient";
import { getDataSourceFileStats as getDataSourceFileStatsFromFileApi } from "@/api/fileApi";
import type { ChunkCompletedTextParams } from "@/types/chunking";
import type {
  DocumentProcessRequestParams,
  DocumentProcessResponse,
} from "@/types/documentProcessing";
import type { EmbedPendingChunksParams } from "@/types/embedding";
import type { ProcessPendingTextParams } from "@/types/textProcessing";
import type { SyncTreeParams } from "@/types/syncTree";
import type {
  DataSource,
  DataSourceCreateBody,
  DataSourceListResponse,
  DataSourceUpdateBody,
} from "@/types/dataSource";

export async function listDataSources(
  includeInactive = false
): Promise<DataSourceListResponse> {
  const { data } = await httpClient.get<DataSourceListResponse>("/api/data-sources", {
    params: { include_inactive: includeInactive },
  });
  return data;
}

export async function createDataSource(
  body: DataSourceCreateBody
): Promise<DataSource> {
  const { data } = await httpClient.post<DataSource>("/api/data-sources", body);
  return data;
}

export async function updateDataSource(
  id: string,
  body: DataSourceUpdateBody
): Promise<DataSource> {
  const { data } = await httpClient.put<DataSource>(`/api/data-sources/${id}`, body);
  return data;
}

export async function activateDataSource(id: string): Promise<DataSource> {
  const { data } = await httpClient.patch<DataSource>(
    `/api/data-sources/${id}/activate`
  );
  return data;
}

export async function deactivateDataSource(id: string): Promise<DataSource> {
  const { data } = await httpClient.patch<DataSource>(
    `/api/data-sources/${id}/deactivate`
  );
  return data;
}

export async function testDataSourceConnection(
  id: string
): Promise<{ data: Record<string, unknown>; status: number }> {
  const res = await httpClient.post<Record<string, unknown>>(
    `/api/data-sources/${id}/test-connection`,
    {},
    { validateStatus: () => true }
  );
  return { data: res.data, status: res.status };
}

function omitUndefined<T extends Record<string, unknown>>(obj: T): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(obj)) {
    if (v !== undefined) out[k] = v;
  }
  return out;
}

/** Admin: bounded recursive WebDAV sync (PROPFIND BFS). */
export async function syncTree(
  dataSourceId: string,
  params: SyncTreeParams
): Promise<Record<string, unknown>> {
  const q = omitUndefined({
    start_path: params.start_path ?? "/",
    max_depth: params.max_depth ?? 3,
    max_items: params.max_items ?? 5000,
    include_hidden: params.include_hidden ?? false,
    apply_exclusions: params.apply_exclusions ?? true,
    detect_deleted: params.detect_deleted ?? false,
  });
  const { data } = await httpClient.post<Record<string, unknown>>(
    `/api/data-sources/${dataSourceId}/sync-tree`,
    {},
    { params: q }
  );
  return data;
}

/** Admin: download PENDING plain-text files into `file_contents`. */
export async function processPendingText(
  dataSourceId: string,
  params: ProcessPendingTextParams
): Promise<Record<string, unknown>> {
  const q = omitUndefined({
    limit: params.limit,
    max_file_size_bytes: params.max_file_size_bytes,
    dry_run: params.dry_run,
    include_extensions:
      params.include_extensions && params.include_extensions.trim() !== ""
        ? params.include_extensions.trim()
        : undefined,
  });
  const { data } = await httpClient.post<Record<string, unknown>>(
    `/api/data-sources/${dataSourceId}/process-pending-text`,
    {},
    { params: q }
  );
  return data;
}

function buildDocumentProcessParams(p: DocumentProcessRequestParams): Record<string, unknown> {
  const out: Record<string, unknown> = {
    limit: p.limit,
    max_file_size_bytes: p.max_file_size_bytes,
    dry_run: p.dry_run,
    reprocess_skipped: p.reprocess_skipped,
  };
  if (p.include_extensions && p.include_extensions.trim() !== "") {
    out.include_extensions = p.include_extensions.trim();
  }
  return out;
}

/** Admin: extract PDF/DOCX/XLSX/PPTX/HWPX/HWP text into `file_contents`. */
export async function processPendingDocuments(
  dataSourceId: string,
  params: DocumentProcessRequestParams
): Promise<DocumentProcessResponse> {
  const { data } = await httpClient.post<DocumentProcessResponse>(
    `/api/data-sources/${dataSourceId}/process-pending-documents`,
    {},
    { params: buildDocumentProcessParams(params) }
  );
  if (data.status === "error") {
    const err = new Error(data.message || "문서 처리 요청이 실패했습니다.");
    (err as Error & { responseBody?: DocumentProcessResponse }).responseBody = data;
    throw err;
  }
  return data;
}

/** Admin: slice `file_contents` into `document_chunks`. */
export async function chunkCompletedText(
  dataSourceId: string,
  params: ChunkCompletedTextParams
): Promise<Record<string, unknown>> {
  const q = omitUndefined({
    limit: params.limit,
    chunk_size: params.chunk_size,
    chunk_overlap: params.chunk_overlap,
    min_chunk_size: params.min_chunk_size,
    reprocess: params.reprocess,
    dry_run: params.dry_run,
    include_extensions:
      params.include_extensions && params.include_extensions.trim() !== ""
        ? params.include_extensions.trim()
        : undefined,
  });
  const { data } = await httpClient.post<Record<string, unknown>>(
    `/api/data-sources/${dataSourceId}/chunk-completed-text`,
    {},
    { params: q }
  );
  return data;
}

/** Admin: embed pending chunk rows (Ollama). */
export async function embedPendingChunks(
  dataSourceId: string,
  params: EmbedPendingChunksParams
): Promise<Record<string, unknown>> {
  const q = omitUndefined({
    limit: params.limit,
    batch_size: params.batch_size,
    reembed: params.reembed,
    dry_run: params.dry_run,
    include_extensions:
      params.include_extensions && params.include_extensions.trim() !== ""
        ? params.include_extensions.trim()
        : undefined,
    file_id: params.file_id && params.file_id.trim() !== "" ? params.file_id.trim() : undefined,
  });
  const { data } = await httpClient.post<Record<string, unknown>>(
    `/api/data-sources/${dataSourceId}/embed-pending-chunks`,
    {},
    { params: q }
  );
  return data;
}

/** GET /api/data-sources/{id}/file-stats — re-exported for pipeline UI. */
export async function getDataSourceFileStats(
  dataSourceId: string,
  params?: { include_deleted?: boolean }
) {
  return getDataSourceFileStatsFromFileApi(dataSourceId, params);
}
