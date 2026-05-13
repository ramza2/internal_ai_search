import type { AnswerResponse } from "@/types/answer";
import type { SearchMode } from "@/types/search";

const KEY = "internal_ai_search_rag_session_v1";

export type RagSessionPayload = {
  query: string;
  searchMode: SearchMode;
  data: AnswerResponse;
};

export function saveRagSession(payload: RagSessionPayload): void {
  try {
    sessionStorage.setItem(KEY, JSON.stringify(payload));
  } catch {
    /* ignore quota / private mode */
  }
}

export function loadRagSession(): RagSessionPayload | null {
  try {
    const raw = sessionStorage.getItem(KEY);
    if (!raw) return null;
    const p = JSON.parse(raw) as Partial<RagSessionPayload>;
    if (!p || typeof p.query !== "string" || !p.data || typeof p.data !== "object") return null;
    if (!Array.isArray(p.data.citations)) return null;
    return {
      query: p.query,
      searchMode: (p.searchMode as SearchMode) ?? "vector",
      data: p.data as AnswerResponse,
    };
  } catch {
    return null;
  }
}

export function clearRagSession(): void {
  try {
    sessionStorage.removeItem(KEY);
  } catch {
    /* ignore */
  }
}
