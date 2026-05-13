import { httpClient } from "@/api/httpClient";
import type {
  DataSource,
  DataSourceCreateBody,
  DataSourceListResponse,
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
