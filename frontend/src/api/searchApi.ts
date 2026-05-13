import { httpClient } from "@/api/httpClient";
import type { SearchRequest, SearchResponse } from "@/types/search";
import type { SearchDataSourceListResponse } from "@/types/searchDataSource";

export async function searchRequest(body: SearchRequest): Promise<SearchResponse> {
  const { data } = await httpClient.post<SearchResponse>("/api/search", body);
  return data;
}

/** 검색·AI 질문 화면용 활성 데이터 소스 목록 (비밀·URL 미포함) */
export async function getSearchDataSources(): Promise<SearchDataSourceListResponse> {
  const { data } = await httpClient.get<SearchDataSourceListResponse>("/api/search/data-sources");
  return data;
}
