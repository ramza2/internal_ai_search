import { useCallback, useEffect, useState } from "react";
import { getApiErrorMessage } from "@/api/httpClient";
import * as searchApi from "@/api/searchApi";
import type { SearchDataSource } from "@/types/searchDataSource";

/**
 * 검색·AI 질문용 활성 데이터 소스 (`GET /api/search/data-sources`).
 * 실패 시 목록만 비우고 화면은 계속 동작하도록 `loadError`만 설정합니다.
 */
export function useSearchDataSources() {
  const [items, setItems] = useState<SearchDataSource[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const res = await searchApi.getSearchDataSources();
      setItems(res.items ?? []);
    } catch (e) {
      setItems([]);
      setLoadError(getApiErrorMessage(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  return { items, loading, loadError, reload };
}
