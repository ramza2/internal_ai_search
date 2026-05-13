import type { AnswerRequest, AnswerResponse } from "@/types/answer";
import type { SearchMode } from "@/types/search";

const KEY = "internal_ai_search_rag_session_v2";

export type RagSessionPayload = {
  query: string;
  searchMode: SearchMode;
  /** 고급 옵션 일부 복원용 */
  answerOptions?: Partial<AnswerRequest>;
  data: AnswerResponse;
};

export function saveRagSession(payload: RagSessionPayload): void {
  try {
    sessionStorage.setItem(KEY, JSON.stringify(payload));
  } catch {
    /* ignore */
  }
}

export function loadRagSession(): RagSessionPayload | null {
  try {
    const raw = sessionStorage.getItem(KEY);
    if (!raw) return _migrateV1();
    const p = JSON.parse(raw) as Partial<RagSessionPayload>;
    if (!p || typeof p.query !== "string" || !p.data || typeof p.data !== "object") return null;
    if (!Array.isArray(p.data.citations)) return null;
    return {
      query: p.query,
      searchMode: (p.searchMode as SearchMode) ?? "vector",
      answerOptions: p.answerOptions,
      data: p.data as AnswerResponse,
    };
  } catch {
    return null;
  }
}

/** v1 세션 키가 남아 있으면 한 번만 승격 */
function _migrateV1(): RagSessionPayload | null {
  try {
    const raw = sessionStorage.getItem("internal_ai_search_rag_session_v1");
    if (!raw) return null;
    const p = JSON.parse(raw) as { query?: string; searchMode?: SearchMode; data?: AnswerResponse };
    if (!p?.query || !p.data) return null;
    const next: RagSessionPayload = {
      query: p.query,
      searchMode: p.searchMode ?? "vector",
      data: p.data,
    };
    saveRagSession(next);
    sessionStorage.removeItem("internal_ai_search_rag_session_v1");
    return next;
  } catch {
    return null;
  }
}

export function clearRagSession(): void {
  try {
    sessionStorage.removeItem(KEY);
    sessionStorage.removeItem("internal_ai_search_rag_session_v1");
  } catch {
    /* ignore */
  }
}
