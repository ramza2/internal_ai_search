import type { SearchMode, SearchRequest, SearchResponse } from "@/types/search";

const KEY = "internal_ai_search_search_session_v1";

export type SearchSessionPayload = {
  query: string;
  searchMode: SearchMode;
  dataSourceId: string;
  extensionsRaw: string;
  fileType: string;
  limit: number;
  minScoreStr: string;
  vectorW: string;
  keywordW: string;
  lastRequest: SearchRequest;
  data: SearchResponse;
};

function isSearchResponse(v: unknown): v is SearchResponse {
  if (!v || typeof v !== "object") return false;
  const o = v as Record<string, unknown>;
  return (
    typeof o.status === "string" &&
    typeof o.query === "string" &&
    typeof o.total_results === "number" &&
    Array.isArray(o.results)
  );
}

function isSearchRequest(v: unknown): v is SearchRequest {
  if (!v || typeof v !== "object") return false;
  const o = v as Record<string, unknown>;
  return typeof o.query === "string";
}

export function saveSearchSession(payload: SearchSessionPayload): void {
  try {
    sessionStorage.setItem(KEY, JSON.stringify(payload));
  } catch {
    /* ignore quota / private mode */
  }
}

export function loadSearchSession(): SearchSessionPayload | null {
  try {
    const raw = sessionStorage.getItem(KEY);
    if (!raw) return null;
    const p = JSON.parse(raw) as Partial<SearchSessionPayload>;
    if (!p || typeof p.query !== "string") return null;
    if (!isSearchRequest(p.lastRequest) || !isSearchResponse(p.data)) return null;
    return {
      query: p.query,
      searchMode: (p.searchMode as SearchMode) ?? "vector",
      dataSourceId: typeof p.dataSourceId === "string" ? p.dataSourceId : "",
      extensionsRaw: typeof p.extensionsRaw === "string" ? p.extensionsRaw : "",
      fileType: typeof p.fileType === "string" ? p.fileType : "",
      limit: typeof p.limit === "number" && Number.isFinite(p.limit) ? p.limit : 20,
      minScoreStr: typeof p.minScoreStr === "string" ? p.minScoreStr : "0",
      vectorW: typeof p.vectorW === "string" ? p.vectorW : "0.7",
      keywordW: typeof p.keywordW === "string" ? p.keywordW : "0.3",
      lastRequest: p.lastRequest,
      data: p.data,
    };
  } catch {
    return null;
  }
}

export function clearSearchSession(): void {
  try {
    sessionStorage.removeItem(KEY);
  } catch {
    /* ignore */
  }
}
