import { Fragment, useEffect, useState } from "react";
import { getApiErrorMessage } from "@/api/httpClient";
import * as adminApi from "@/api/adminApi";
import { ErrorMessage } from "@/components/ErrorMessage";
import { Loading } from "@/components/Loading";
import {
  Badge,
  Button,
  DataTable,
  FilterBar,
  FilterField,
  Input,
  PageHeader,
  SectionCard,
  Select,
} from "@/components/ui";
import type { ActionLogItem } from "@/types/admin";
import { formatDateTime } from "@/utils/format";

function resultVariant(r: string): "success" | "danger" | "neutral" {
  if (r === "SUCCESS") return "success";
  if (r === "FAIL") return "danger";
  return "neutral";
}

export function ActionLogsPage() {
  const [items, setItems] = useState<ActionLogItem[]>([]);
  const [total, setTotal] = useState(0);
  const [actionType, setActionType] = useState("");
  const [result, setResult] = useState("");
  const [keyword, setKeyword] = useState("");
  const [appliedKeyword, setAppliedKeyword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  async function load() {
    setLoading(true);
    setError("");
    try {
      const res = await adminApi.listActionLogs({
        action_type: actionType || undefined,
        result: result || undefined,
        keyword: appliedKeyword || undefined,
        limit: 50,
        offset: 0,
      });
      setItems(res.items);
      setTotal(res.total);
    } catch (e) {
      setError(getApiErrorMessage(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [actionType, result, appliedKeyword]);

  function toggle(id: string) {
    setExpanded((prev) => ({ ...prev, [id]: !prev[id] }));
  }

  if (loading) return <Loading />;

  return (
    <div>
      <PageHeader
        title="작업 로그"
        description="주요 API 작업에 대한 감사 로그입니다. detail에는 비밀·전체 본문이 포함되지 않도록 백엔드에서 제한됩니다."
      />
      <ErrorMessage message={error} />

      <SectionCard title="필터">
        <FilterBar>
          <FilterField label="action_type">
            <Input
              value={actionType}
              onChange={(e) => setActionType(e.target.value)}
              placeholder="예: SEARCH"
            />
          </FilterField>
          <FilterField label="result">
            <Select value={result} onChange={(e) => setResult(e.target.value)}>
              <option value="">전체</option>
              <option value="SUCCESS">SUCCESS</option>
              <option value="FAIL">FAIL</option>
            </Select>
          </FilterField>
          <FilterField label="keyword" wide>
            <Input
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              placeholder="로그인·경로 등"
              onKeyDown={(e) => {
                if (e.key === "Enter") setAppliedKeyword(keyword.trim());
              }}
            />
          </FilterField>
          <Button type="button" variant="primary" size="sm" onClick={() => setAppliedKeyword(keyword.trim())}>
            조회
          </Button>
        </FilterBar>
        <p className="muted" style={{ margin: 0 }}>
          총 {total.toLocaleString("ko-KR")}건
        </p>
      </SectionCard>

      <SectionCard title="로그 목록">
        <DataTable>
          <thead>
            <tr>
              <th>시각</th>
              <th>사용자</th>
              <th>유형</th>
              <th>결과</th>
              <th>검색어</th>
              <th>파일 경로</th>
              <th style={{ width: "6rem" }}>상세</th>
            </tr>
          </thead>
          <tbody>
            {items.map((r) => {
              const open = Boolean(expanded[r.id]);
              const detailStr =
                r.detail && Object.keys(r.detail).length > 0
                  ? JSON.stringify(r.detail, null, 2)
                  : r.error_message ?? "—";
              return (
                <Fragment key={r.id}>
                  <tr>
                    <td>{formatDateTime(r.created_at)}</td>
                    <td>{r.user_name ?? r.login_id ?? "—"}</td>
                    <td>
                      <Badge variant="neutral">{r.action_type}</Badge>
                    </td>
                    <td>
                      <Badge variant={resultVariant(r.result)}>{r.result}</Badge>
                    </td>
                    <td className="snippet">{r.search_query ?? "—"}</td>
                    <td className="snippet">{r.target_file_path ?? "—"}</td>
                    <td>
                      <Button type="button" variant="ghost" size="sm" onClick={() => toggle(r.id)}>
                        {open ? "접기" : "펼치기"}
                      </Button>
                    </td>
                  </tr>
                  {open && (
                    <tr className="muted">
                      <td colSpan={7}>
                        <pre
                          style={{
                            margin: 0,
                            maxHeight: "14rem",
                            overflow: "auto",
                            fontSize: "0.75rem",
                            background: "#f8fafc",
                            padding: "0.65rem",
                            borderRadius: "var(--radius-sm)",
                            border: "1px solid var(--color-border)",
                          }}
                        >
                          {detailStr}
                        </pre>
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </DataTable>
      </SectionCard>
    </div>
  );
}
