import { httpClient } from "@/api/httpClient";
import type { SearchRequest, SearchResponse } from "@/types/search";

export async function searchRequest(body: SearchRequest): Promise<SearchResponse> {
  const { data } = await httpClient.post<SearchResponse>("/api/search", body);
  return data;
}
