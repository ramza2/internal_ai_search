import axios from "axios";
import { useCallback, useEffect, useState } from "react";
import * as dsApi from "@/api/dataSourceApi";
import type { DataSource } from "@/types/dataSource";

/**
 * 관리자 데이터 소스 CRUD 목록 (`GET /api/data-sources`, ADMIN 전용).
 * 검색·답변 화면은 `useSearchDataSources` + `GET /api/search/data-sources` 사용.
 */
export function useDataSources(includeInactive = false) {
  const [items, setItems] = useState<DataSource[]>([]);
  const [loading, setLoading] = useState(true);
  /** true면 ADMIN 아님 등으로 목록 API가 403 */
  const [forbidden, setForbidden] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await dsApi.listDataSources(includeInactive);
      setItems(res.items);
      setForbidden(false);
    } catch (e) {
      if (axios.isAxiosError(e) && e.response?.status === 403) {
        setForbidden(true);
        setItems([]);
      } else {
        setError(e instanceof Error ? e.message : "데이터 소스 목록을 불러오지 못했습니다.");
        setItems([]);
      }
    } finally {
      setLoading(false);
    }
  }, [includeInactive]);

  useEffect(() => {
    void reload();
  }, [reload]);

  return { items, loading, forbidden, error, reload };
}
