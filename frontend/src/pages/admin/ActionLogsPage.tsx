import { Fragment, useCallback, useEffect, useState } from "react";
import { getApiErrorMessage } from "@/api/httpClient";
import * as adminApi from "@/api/adminApi";
import { EmptyState } from "@/components/EmptyState";
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
  PaginationBar,
  SectionCard,
  Select,
} from "@/components/ui";
import { COMMON_ACTION_TYPES } from "@/constants/filters";
import { useDataSources } from "@/hooks/useDataSources";
import type { ActionLogItem } from "@/types/admin";
import { formatDateTime } from "@/utils/format";

function resultVariant(r: string): "success" | "danger" | "neutral" {
  if (r === "SUCCESS") return "success";
  if (r === "FAIL") return "danger";
  return "neutral";
}

type Draft = {
  userId: string;
  actionType: string;
  result: string;
  dataSourceId: string;
  targetFileId: string;
  keyword: string;
  fromDate: string;
  toDate: string;
};

const emptyDraft = (): Draft => ({
  userId: "",
  actionType: "",
  result: "",
  dataSourceId: "",
  targetFileId: "",
  keyword: "",
  fromDate: "",
  toDate: "",
});

export function ActionLogsPage() {
  const { items: dataSources } = useDataSources(true);
  const [draft, setDraft] = useState<Draft>(emptyDraft);
  const [applied, setApplied] = useState<Draft>(emptyDraft);
  const [limit, setLimit] = useState(50);
  const [offset, setOffset] = useState(0);
  const [items, setItems] = useState<ActionLogItem[]>([]);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [listBusy, setListBusy] = useState(false);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  const fetchLogs = useCallback(async () => {
    setListBusy(true);
    setError("");
    try {
      const res = await adminApi.listActionLogs({
        user_id: applied.userId.trim() || undefined,
        action_type: applied.actionType.trim() || undefined,
        result: applied.result || undefined,
        data_source_id: applied.dataSourceId.trim() || undefined,
        target_file_id: applied.targetFileId.trim() || undefined,
        keyword: applied.keyword.trim() || undefined,
        from_date: applied.fromDate || undefined,
        to_date: applied.toDate || undefined,
        limit,
        offset,
      });
      setItems(res.items);
      setTotal(res.total);
    } catch (e) {
      setError(getApiErrorMessage(e));
      setItems([]);
      setTotal(0);
    } finally {
      setListBusy(false);
      setLoading(false);
    }
  }, [applied, limit, offset]);

  useEffect(() => {
    void fetchLogs();
  }, [fetchLogs]);

  function onSearch() {
    setApplied({ ...draft });
    setOffset(0);
  }

  function onReset() {
    const z = emptyDraft();
    setDraft(z);
    setApplied(z);
    setLimit(50);
    setOffset(0);
  }

  function toggle(id: string) {
    setExpanded((prev) => ({ ...prev, [id]: !prev[id] }));
  }

  const actionTypeOptions = COMMON_ACTION_TYPES.filter(Boolean);

  const pipelineActionTypes = [
    "WEBDAV_SYNC_TREE",
    "PROCESS_PENDING_TEXT",
    "PROCESS_PENDING_DOCUMENTS",
    "CHUNK_COMPLETED_TEXT",
    "EMBED_PENDING_CHUNKS",
  ] as const;

  function applyPipelineLogPreset() {
    const next = { ...draft, actionType: "WEBDAV_SYNC_TREE" };
    setDraft(next);
    setApplied(next);
    setOffset(0);
  }

  if (loading && items.length === 0) return <Loading />;

  return (
    <div>
      <PageHeader
        title="작업 로그"
        description="주요 API 작업에 대한 감사 로그입니다. detail에는 비밀·전체 본문이 포함되지 않도록 백엔드에서 제한됩니다."
      />
      <ErrorMessage message={error} />

      <SectionCard title="필터">
        <FilterBar>
          <FilterField label="user_id">
            <Input
              value={draft.userId}
              onChange={(e) => setDraft((d) => ({ ...d, userId: e.target.value }))}
              placeholder="UUID"
              disabled={listBusy}
            />
          </FilterField>
          <FilterField label="action_type">
            <Select
              value={draft.actionType}
              onChange={(e) => setDraft((d) => ({ ...d, actionType: e.target.value }))}
              disabled={listBusy}
            >
              <option value="">전체</option>
              {actionTypeOptions.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </Select>
          </FilterField>
          <Button type="button" variant="secondary" size="sm" onClick={applyPipelineLogPreset} disabled={listBusy}>
            파이프라인 작업
          </Button>
          <FilterField label="result">
            <Select
              value={draft.result}
              onChange={(e) => setDraft((d) => ({ ...d, result: e.target.value }))}
              disabled={listBusy}
            >
              <option value="">전체</option>
              <option value="SUCCESS">SUCCESS</option>
              <option value="FAIL">FAIL</option>
            </Select>
          </FilterField>
          <FilterField label="data_source" wide>
            <Select
              value={draft.dataSourceId}
              onChange={(e) => setDraft((d) => ({ ...d, dataSourceId: e.target.value }))}
              disabled={listBusy}
            >
              <option value="">전체</option>
              {dataSources.map((ds) => (
                <option key={ds.id} value={ds.id}>
                  {ds.name}
                  {!ds.is_active ? " (비활성)" : ""}
                </option>
              ))}
            </Select>
          </FilterField>
          <FilterField label="target_file_id">
            <Input
              value={draft.targetFileId}
              onChange={(e) => setDraft((d) => ({ ...d, targetFileId: e.target.value }))}
              placeholder="UUID"
              disabled={listBusy}
            />
          </FilterField>
          <FilterField label="keyword" wide>
            <Input
              value={draft.keyword}
              onChange={(e) => setDraft((d) => ({ ...d, keyword: e.target.value }))}
              placeholder="로그인·경로 등"
              disabled={listBusy}
              onKeyDown={(e) => {
                if (e.key === "Enter") onSearch();
              }}
            />
          </FilterField>
          <FilterField label="from_date">
            <Input
              type="date"
              value={draft.fromDate}
              onChange={(e) => setDraft((d) => ({ ...d, fromDate: e.target.value }))}
              disabled={listBusy}
            />
          </FilterField>
          <FilterField label="to_date">
            <Input
              type="date"
              value={draft.toDate}
              onChange={(e) => setDraft((d) => ({ ...d, toDate: e.target.value }))}
              disabled={listBusy}
            />
          </FilterField>
          <FilterField label="limit">
            <Select
              value={String(limit)}
              onChange={(e) => {
                setLimit(Number(e.target.value));
                setOffset(0);
              }}
              disabled={listBusy}
            >
              <option value={20}>20</option>
              <option value={50}>50</option>
              <option value={100}>100</option>
              <option value={200}>200</option>
            </Select>
          </FilterField>
          <Button type="button" variant="primary" size="sm" onClick={onSearch} disabled={listBusy}>
            조회
          </Button>
          <Button type="button" variant="secondary" size="sm" onClick={onReset} disabled={listBusy}>
            필터 초기화
          </Button>
        </FilterBar>
        <p className="muted" style={{ margin: "0.5rem 0 0", fontSize: "0.8rem" }}>
          <strong>파이프라인 작업</strong> 프리셋은 <code>WEBDAV_SYNC_TREE</code>로 필터를 맞춘 뒤 조회합니다. API는{" "}
          <code>action_type</code> 단일값만 받으므로, 다른 단계는 드롭다운에서{" "}
          {pipelineActionTypes.map((t) => (
            <code key={t} style={{ marginRight: "0.25rem" }}>
              {t}
            </code>
          ))}
          로 바꿔 순차 확인하세요.
        </p>
        <p className="muted" style={{ margin: "0.5rem 0 0" }}>
          총 <strong>{total.toLocaleString("ko-KR")}</strong>건
          {listBusy ? " · 불러오는 중…" : ""}
        </p>
        {/* TODO: 필터·페이지 상태를 URL query와 동기화 */}
        <PaginationBar offset={offset} limit={limit} total={total} onOffsetChange={setOffset} disabled={listBusy} />
      </SectionCard>

      <SectionCard title="로그 목록">
        {items.length === 0 && !listBusy ? (
          <EmptyState title="로그가 없습니다" description="필터를 바꾸거나 기간을 넓혀 보세요." />
        ) : (
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
                        <Button type="button" variant="ghost" size="sm" onClick={() => toggle(r.id)} disabled={listBusy}>
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
        )}
      </SectionCard>
    </div>
  );
}
