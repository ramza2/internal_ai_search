import { Fragment, useCallback, useEffect, useState } from "react";
import { getApiErrorMessage } from "@/api/httpClient";
import * as adminJobsApi from "@/api/adminJobsApi";
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
import type { BadgeVariant } from "@/components/ui";
import { useDataSources } from "@/hooks/useDataSources";
import type { AdminJob, AdminJobDetailResponse, AdminJobFailure, AdminJobFailuresResponse } from "@/types/adminJobs";
import { formatDateTime, formatDuration } from "@/utils/format";
import docStyles from "./DocumentProcessModal.module.css";

const STATUS_OPTIONS = ["", "RUNNING", "COMPLETED", "FAILED", "PENDING", "CANCELLED", "STOPPED", "PARTIAL"] as const;

const JOB_TYPE_OPTIONS = [
  "",
  "MANUAL_SCAN",
  "WEBDAV_SYNC_TREE",
  "PROCESS_PENDING_TEXT",
  "PROCESS_PENDING_DOCUMENTS",
  "CHUNK_COMPLETED_TEXT",
  "EMBED_PENDING_CHUNKS",
] as const;

const LIMIT_OPTIONS = [20, 50, 100] as const;

type Draft = {
  status: string;
  jobType: string;
  dataSourceId: string;
  keyword: string;
  fromDate: string;
  toDate: string;
};

const emptyDraft = (): Draft => ({
  status: "",
  jobType: "",
  dataSourceId: "",
  keyword: "",
  fromDate: "",
  toDate: "",
});

function jobStatusVariant(s: string): BadgeVariant {
  const u = (s || "").toUpperCase();
  if (u === "COMPLETED") return "success";
  if (u === "FAILED") return "danger";
  if (u === "RUNNING") return "warning";
  if (u === "PENDING") return "primary";
  if (u === "PARTIAL") return "warning";
  if (u === "CANCELLED" || u === "STOPPED") return "neutral";
  return "neutral";
}

function errSnippet(s: string | null | undefined, max = 80): string {
  if (!s) return "—";
  const t = s.trim();
  if (t.length <= max) return t;
  return `${t.slice(0, max)}…`;
}

export function AdminJobsPage() {
  const { items: dataSources } = useDataSources(true);
  const [draft, setDraft] = useState<Draft>(emptyDraft);
  const [applied, setApplied] = useState<Draft>(emptyDraft);
  const [limit, setLimit] = useState(50);
  const [offset, setOffset] = useState(0);
  const [items, setItems] = useState<AdminJob[]>([]);
  const [total, setTotal] = useState(0);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [listMessage, setListMessage] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [listBusy, setListBusy] = useState(false);

  const [modalJobId, setModalJobId] = useState<string | null>(null);
  const [detail, setDetail] = useState<AdminJobDetailResponse | null>(null);
  const [detailErr, setDetailErr] = useState("");
  const [detailBusy, setDetailBusy] = useState(false);
  const [failures, setFailures] = useState<AdminJobFailuresResponse | null>(null);
  const [failuresBusy, setFailuresBusy] = useState(false);
  const [failuresErr, setFailuresErr] = useState("");

  const fetchList = useCallback(async () => {
    setListBusy(true);
    setError("");
    try {
      const res = await adminJobsApi.getAdminJobs({
        data_source_id: applied.dataSourceId.trim() || undefined,
        status: applied.status.trim() || undefined,
        job_type: applied.jobType.trim() || undefined,
        keyword: applied.keyword.trim() || undefined,
        from_date: applied.fromDate || undefined,
        to_date: applied.toDate || undefined,
        limit,
        offset,
      });
      setItems(res.items);
      setTotal(res.total);
      setWarnings(res.warnings ?? []);
      setListMessage(res.message ?? null);
    } catch (e) {
      setError(getApiErrorMessage(e));
      setItems([]);
      setTotal(0);
      setWarnings([]);
      setListMessage(null);
    } finally {
      setListBusy(false);
      setLoading(false);
    }
  }, [applied, limit, offset]);

  useEffect(() => {
    void fetchList();
  }, [fetchList]);

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

  async function openDetail(jobId: string) {
    setModalJobId(jobId);
    setDetail(null);
    setDetailErr("");
    setFailures(null);
    setFailuresErr("");
    setDetailBusy(true);
    try {
      const d = await adminJobsApi.getAdminJob(jobId);
      setDetail(d);
    } catch (e) {
      setDetailErr(getApiErrorMessage(e));
    } finally {
      setDetailBusy(false);
    }
    setFailuresBusy(true);
    try {
      const f = await adminJobsApi.getAdminJobFailures(jobId, { limit: 100, offset: 0 });
      setFailures(f);
    } catch (e) {
      setFailuresErr(getApiErrorMessage(e));
    } finally {
      setFailuresBusy(false);
    }
  }

  function closeDetail() {
    setModalJobId(null);
    setDetail(null);
    setDetailErr("");
    setFailures(null);
    setFailuresErr("");
  }

  if (loading && items.length === 0) return <Loading />;

  return (
    <div>
      <PageHeader
        title="작업 목록"
        description="WebDAV 동기화, 텍스트 처리, 문서 처리, Chunk, Embedding 작업 이력을 확인합니다. (조회 전용 — 취소·재시도는 백그라운드 worker 도입 후 예정)"
      />
      <ErrorMessage message={error} />

      {warnings.length > 0 && (
        <div className="alert alertInfo" style={{ marginBottom: "0.75rem" }}>
          {warnings.map((w) => (
            <div key={w}>{w}</div>
          ))}
        </div>
      )}
      {listMessage && (
        <p className="muted" style={{ marginTop: 0 }}>
          {listMessage}
        </p>
      )}

      <SectionCard title="필터">
        <FilterBar>
          <FilterField label="status">
            <Select
              value={draft.status}
              onChange={(e) => setDraft((d) => ({ ...d, status: e.target.value }))}
              disabled={listBusy}
            >
              {STATUS_OPTIONS.map((s) => (
                <option key={s || "all"} value={s}>
                  {s === "" ? "전체" : s}
                </option>
              ))}
            </Select>
          </FilterField>
          <FilterField label="job_type">
            <Select
              value={draft.jobType}
              onChange={(e) => setDraft((d) => ({ ...d, jobType: e.target.value }))}
              disabled={listBusy}
            >
              {JOB_TYPE_OPTIONS.map((s) => (
                <option key={s || "all"} value={s}>
                  {s === "" ? "전체" : s}
                </option>
              ))}
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
          <FilterField label="keyword" wide>
            <Input
              value={draft.keyword}
              onChange={(e) => setDraft((d) => ({ ...d, keyword: e.target.value }))}
              placeholder="소스 이름, 경로, 오류 메시지"
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
              {LIMIT_OPTIONS.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </Select>
          </FilterField>
          <Button type="button" variant="primary" size="sm" onClick={onSearch} disabled={listBusy}>
            조회
          </Button>
          <Button type="button" variant="secondary" size="sm" onClick={onReset} disabled={listBusy}>
            초기화
          </Button>
        </FilterBar>
        <p className="muted" style={{ margin: "0.5rem 0 0" }}>
          총 <strong>{total.toLocaleString("ko-KR")}</strong>건{listBusy ? " · 불러오는 중…" : ""}
        </p>
        <PaginationBar offset={offset} limit={limit} total={total} onOffsetChange={setOffset} disabled={listBusy} />
      </SectionCard>

      <SectionCard title="작업 이력">
        {items.length === 0 && !listBusy ? (
          <EmptyState title="작업이 없습니다" description="필터를 바꾸거나 기간을 넓혀 보세요." />
        ) : (
          <DataTable>
            <thead>
              <tr>
                <th>job_type</th>
                <th>status</th>
                <th>소스</th>
                <th>시작</th>
                <th>종료</th>
                <th>소요</th>
                <th>진행</th>
                <th>완료/실패/스킵/삭제</th>
                <th>오류 요약</th>
                <th style={{ width: "6rem" }} />
              </tr>
            </thead>
            <tbody>
              {items.map((j) => (
                <tr key={j.id}>
                  <td>
                    <span className="snippet">{j.job_type}</span>
                  </td>
                  <td>
                    <Badge variant={jobStatusVariant(j.status)}>{j.status}</Badge>
                  </td>
                  <td>{j.data_source_name ?? "—"}</td>
                  <td>{formatDateTime(j.started_at)}</td>
                  <td>{formatDateTime(j.finished_at)}</td>
                  <td>{j.duration_ms != null ? formatDuration(j.duration_ms) : "—"}</td>
                  <td>
                    {j.progress_percent != null ? `${j.progress_percent}%` : "—"}
                    <div className="muted" style={{ fontSize: "0.75rem" }}>
                      {j.processed_files}/{j.total_files}
                    </div>
                  </td>
                  <td style={{ fontSize: "0.8rem" }}>
                    {j.completed_files}/{j.failed_files}/{j.skipped_files}/{j.deleted_files}
                  </td>
                  <td className="snippet" style={{ maxWidth: "12rem", fontSize: "0.8rem" }}>
                    {errSnippet(j.error_message, 100)}
                  </td>
                  <td>
                    <Button type="button" variant="ghost" size="sm" onClick={() => void openDetail(j.id)} disabled={listBusy}>
                      상세
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </DataTable>
        )}
      </SectionCard>

      {modalJobId && (
        <div
          className={docStyles.overlay}
          role="presentation"
          onMouseDown={(e) => {
            if (e.target === e.currentTarget) closeDetail();
          }}
        >
          <div className={docStyles.panel} onMouseDown={(e) => e.stopPropagation()}>
            <SectionCard
              title="작업 상세"
              actions={
                <Button type="button" variant="ghost" size="sm" onClick={closeDetail}>
                  닫기
                </Button>
              }
            >
              {detailBusy && <p className="muted">불러오는 중…</p>}
              <ErrorMessage message={detailErr} />
              {detail && (
                <Fragment>
                  {(detail.warnings?.length ?? 0) > 0 && (
                    <div className="alert alertInfo" style={{ marginBottom: "0.5rem" }}>
                      {detail.warnings!.map((w) => (
                        <div key={w}>{w}</div>
                      ))}
                    </div>
                  )}
                  <div className="muted" style={{ fontSize: "0.85rem", marginBottom: "0.5rem" }}>
                    <Badge variant={jobStatusVariant(detail.job.status)}>{detail.job.status}</Badge> · {detail.job.job_type}{" "}
                    · 실패 행 <strong>{detail.failures_count}</strong>건
                  </div>
                  <dl style={{ display: "grid", gridTemplateColumns: "10rem 1fr", gap: "0.35rem 0.75rem", fontSize: "0.875rem" }}>
                    <dt className="muted">소스</dt>
                    <dd style={{ margin: 0 }}>{detail.job.data_source_name ?? "—"}</dd>
                    <dt className="muted">시작 / 종료</dt>
                    <dd style={{ margin: 0 }}>
                      {formatDateTime(detail.job.started_at)} — {formatDateTime(detail.job.finished_at)}
                    </dd>
                    <dt className="muted">소요</dt>
                    <dd style={{ margin: 0 }}>
                      {detail.job.duration_ms != null ? formatDuration(detail.job.duration_ms) : "—"}
                    </dd>
                    <dt className="muted">카운터</dt>
                    <dd style={{ margin: 0 }}>
                      total {detail.job.total_files} · processed {detail.job.processed_files} · completed {detail.job.completed_files} · failed{" "}
                      {detail.job.failed_files} · skipped {detail.job.skipped_files} · deleted {detail.job.deleted_files}
                    </dd>
                    <dt className="muted">error_message</dt>
                    <dd className="snippet" style={{ margin: 0, whiteSpace: "pre-wrap" }}>
                      {detail.job.error_message ?? "—"}
                    </dd>
                  </dl>

                  <h4 style={{ marginTop: "1rem", fontSize: "0.95rem" }}>실패 목록</h4>
                  {failuresBusy && <p className="muted">실패 행 불러오는 중…</p>}
                  <ErrorMessage message={failuresErr} />
                  {failures && (failures.warnings?.length ?? 0) > 0 && (
                    <div className="alert alertInfo" style={{ marginBottom: "0.5rem" }}>
                      {failures.warnings!.map((w) => (
                        <div key={w}>{w}</div>
                      ))}
                    </div>
                  )}
                  {failures && !failuresBusy && failures.items.length === 0 ? (
                    <EmptyState title="실패 기록 없음" description="이 작업에 대해 scan_failures에 저장된 행이 없습니다." />
                  ) : failures && failures.items.length > 0 ? (
                    <DataTable>
                      <thead>
                        <tr>
                          <th>remote_path</th>
                          <th>error_code</th>
                          <th>error_message</th>
                          <th>created_at</th>
                        </tr>
                      </thead>
                      <tbody>
                        {failures.items.map((f: AdminJobFailure) => (
                          <tr key={f.id}>
                            <td className="snippet">{f.remote_path ?? "—"}</td>
                            <td>
                              <Badge variant="neutral">{f.error_code}</Badge>
                            </td>
                            <td className="snippet">{f.error_message ?? "—"}</td>
                            <td>{formatDateTime(f.created_at)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </DataTable>
                  ) : null}
                </Fragment>
              )}
            </SectionCard>
          </div>
        </div>
      )}
    </div>
  );
}
