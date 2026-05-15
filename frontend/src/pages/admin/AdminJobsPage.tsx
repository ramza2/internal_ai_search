import { Fragment, useCallback, useEffect, useState } from "react";
import { getApiErrorMessage } from "@/api/httpClient";
import * as adminJobsApi from "@/api/adminJobsApi";
import { EmptyState } from "@/components/EmptyState";
import { ErrorMessage } from "@/components/ErrorMessage";
import { Loading } from "@/components/Loading";
import {
  Badge,
  Button,
  ConfirmDialog,
  DataTable,
  FilterBar,
  FilterField,
  Input,
  PageHeader,
  PaginationBar,
  SectionCard,
  Select,
} from "@/components/ui";
import { useDataSources } from "@/hooks/useDataSources";
import type {
  AdminJob,
  AdminJobChildItem,
  AdminJobChildrenResponse,
  AdminJobDetailResponse,
  AdminJobFailure,
  AdminJobFailuresResponse,
} from "@/types/adminJobs";
import { formatDateTime, formatDuration } from "@/utils/format";
import {
  getJobStatusBadgeVariant,
  getJobStatusLabel,
  getJobTypeLabel,
  getPipelineStepLabel,
  JOB_STATUS_FILTER_OPTIONS,
  JOB_TYPE_FILTER_OPTIONS,
  UI_LABELS,
} from "@/utils/userFriendlyLabels";
import docStyles from "./DocumentProcessModal.module.css";
import { AdminJobsEnqueuePanel } from "./AdminJobsEnqueuePanel";

const LIMIT_OPTIONS = [20, 50, 100] as const;

function pipelineStepLabelKr(code: string | null | undefined): string {
  return getPipelineStepLabel(code);
}

function pipelineStepsFromJobParams(params: unknown): string[] {
  if (!params || typeof params !== "object" || Array.isArray(params)) return [];
  const steps = (params as Record<string, unknown>).steps;
  if (!Array.isArray(steps)) return [];
  return steps.map((s) => String(s || "").trim().toUpperCase()).filter(Boolean);
}

function firstChildForPipelineStep(items: AdminJobChildItem[], step: string): AdminJobChildItem | undefined {
  const u = step.toUpperCase();
  return items.find((c) => (c.job_type || "").toUpperCase() === u);
}

/** Client-side stale hint only; align with backend stale policy later (TODO). */
const STALE_HEARTBEAT_MS = 30 * 60 * 1000;


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

function errSnippet(s: string | null | undefined, max = 80): string {
  if (!s) return "—";
  const t = s.trim();
  if (t.length <= max) return t;
  return `${t.slice(0, max)}…`;
}

function jobParamsRetriedFromId(params: unknown): string {
  if (!params || typeof params !== "object" || Array.isArray(params)) return "—";
  const v = (params as Record<string, unknown>).retried_from_job_id;
  return v != null && String(v).trim() !== "" ? String(v) : "—";
}

function dashStr(v: string | null | undefined): string {
  if (v == null || v === "") return "—";
  return v;
}

function dashNum(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return "—";
  return String(v);
}

function isHeartbeatStale(heartbeatAt: string | null | undefined): boolean {
  if (!heartbeatAt) return false;
  const t = new Date(heartbeatAt).getTime();
  if (Number.isNaN(t)) return false;
  return Date.now() - t > STALE_HEARTBEAT_MS;
}

function canShowJobCancelButton(status: string | undefined): boolean {
  const u = (status || "").toUpperCase();
  return u === "PENDING" || u === "RUNNING" || u === "CANCELLING";
}

function canRetryJobStatus(status: string | undefined): boolean {
  const u = (status || "").toUpperCase();
  return u === "FAILED" || u === "CANCELLED" || u === "PARTIAL";
}

function canRetryAdminJob(j: AdminJob): boolean {
  if ((j.job_type || "").toUpperCase() === "PIPELINE") return false;
  return canRetryJobStatus(j.status);
}

function isRetryLimitReached(j: AdminJob): boolean {
  const rc = j.retry_count ?? 0;
  const mx = j.max_retries ?? 1;
  return rc >= mx;
}

const RETRY_CONFIRM_MSG =
  "이 작업과 동일한 파라미터로 새 백그라운드 Job을 생성합니다. 계속하시겠습니까?";
const RETRY_FORCE_CONFIRM_MSG = "재시도 한도를 초과했습니다. 강제로 새 Job을 생성하시겠습니까?";

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

  const [cancelConfirmJob, setCancelConfirmJob] = useState<AdminJob | null>(null);
  const [cancelBusy, setCancelBusy] = useState(false);
  const [cancelFeedback, setCancelFeedback] = useState<string | null>(null);

  const [retryDialog, setRetryDialog] = useState<null | { job: AdminJob; force: boolean }>(null);
  const [retryBusy, setRetryBusy] = useState(false);
  const [retryFeedback, setRetryFeedback] = useState<string | null>(null);
  const [retryNewJobId, setRetryNewJobId] = useState<string | null>(null);

  const [jobChildren, setJobChildren] = useState<AdminJobChildrenResponse | null>(null);
  const [jobChildrenBusy, setJobChildrenBusy] = useState(false);
  const [jobChildrenErr, setJobChildrenErr] = useState("");

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
    setRetryNewJobId(null);
    setModalJobId(jobId);
    setDetail(null);
    setDetailErr("");
    setJobChildren(null);
    setJobChildrenErr("");
    setFailures(null);
    setFailuresErr("");
    setDetailBusy(true);
    try {
      const d = await adminJobsApi.getAdminJob(jobId);
      setDetail(d);
      if (d.job.job_type?.toUpperCase() === "PIPELINE") {
        setJobChildrenBusy(true);
        try {
          const ch = await adminJobsApi.getAdminJobChildren(jobId);
          setJobChildren(ch);
        } catch (ec) {
          setJobChildrenErr(getApiErrorMessage(ec));
          setJobChildren(null);
        } finally {
          setJobChildrenBusy(false);
        }
      } else {
        setJobChildren(null);
      }
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
    setJobChildren(null);
    setJobChildrenErr("");
    setFailures(null);
    setFailuresErr("");
    setRetryNewJobId(null);
  }

  async function reloadDetailFor(jobId: string) {
    setDetailBusy(true);
    setDetailErr("");
    try {
      const d = await adminJobsApi.getAdminJob(jobId);
      setDetail(d);
      if (d.job.job_type?.toUpperCase() === "PIPELINE") {
        setJobChildrenBusy(true);
        setJobChildrenErr("");
        try {
          const ch = await adminJobsApi.getAdminJobChildren(jobId);
          setJobChildren(ch);
        } catch (ec) {
          setJobChildrenErr(getApiErrorMessage(ec));
          setJobChildren(null);
        } finally {
          setJobChildrenBusy(false);
        }
      } else {
        setJobChildren(null);
      }
    } catch (e) {
      setDetailErr(getApiErrorMessage(e));
    } finally {
      setDetailBusy(false);
    }
    setFailuresBusy(true);
    setFailuresErr("");
    try {
      const f = await adminJobsApi.getAdminJobFailures(jobId, { limit: 100, offset: 0 });
      setFailures(f);
    } catch (e) {
      setFailuresErr(getApiErrorMessage(e));
    } finally {
      setFailuresBusy(false);
    }
  }

  async function confirmCancelJob() {
    if (!cancelConfirmJob || cancelBusy) return;
    const jid = cancelConfirmJob.id;
    setCancelBusy(true);
    setCancelFeedback(null);
    try {
      const res = await adminJobsApi.cancelAdminJob(jid);
      setCancelFeedback(res.message);
      setCancelConfirmJob(null);
      await fetchList();
      if (modalJobId === jid) await reloadDetailFor(jid);
    } catch (e) {
      setCancelFeedback(getApiErrorMessage(e));
      setCancelConfirmJob(null);
    } finally {
      setCancelBusy(false);
    }
  }

  async function confirmRetry() {
    if (!retryDialog || retryBusy) return;
    const jid = retryDialog.job.id;
    const force = retryDialog.force;
    setRetryBusy(true);
    setRetryFeedback(null);
    setRetryNewJobId(null);
    try {
      const res = await adminJobsApi.retryAdminJob(jid, { force, priority: null });
      setRetryDialog(null);
      setRetryFeedback(`${res.message ?? "재시도 작업이 등록되었습니다."} (작업 ID: ${res.new_job_id})`);
      setRetryNewJobId(res.new_job_id);
      await fetchList();
      if (modalJobId === jid) await reloadDetailFor(jid);
    } catch (e) {
      setRetryFeedback(getApiErrorMessage(e));
      setRetryDialog(null);
    } finally {
      setRetryBusy(false);
    }
  }

  if (loading && items.length === 0) return <Loading />;

  return (
    <div>
      <PageHeader
        title="작업 목록"
        description="파일 수집, 내용 추출, 검색 인덱스 생성 작업의 진행 상태를 확인합니다. 대기·처리 중·취소 중인 작업은 취소 요청이 가능합니다."
      />
      <ErrorMessage message={error} />
      {cancelFeedback != null && cancelFeedback !== "" && (
        <p className="muted" style={{ marginTop: "0.25rem", fontSize: "0.9rem" }}>
          {cancelFeedback}
        </p>
      )}
      {retryFeedback != null && retryFeedback !== "" && (
        <p className="muted" style={{ marginTop: "0.25rem", fontSize: "0.9rem" }}>
          {retryFeedback}
        </p>
      )}

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
          <FilterField label="상태">
            <Select
              value={draft.status}
              onChange={(e) => setDraft((d) => ({ ...d, status: e.target.value }))}
              disabled={listBusy}
            >
              {JOB_STATUS_FILTER_OPTIONS.map((o) => (
                <option key={o.value || "all"} value={o.value}>
                  {o.label}
                </option>
              ))}
            </Select>
          </FilterField>
          <FilterField label="작업 종류">
            <Select
              value={draft.jobType}
              onChange={(e) => setDraft((d) => ({ ...d, jobType: e.target.value }))}
              disabled={listBusy}
            >
              <option value="">전체</option>
              {JOB_TYPE_FILTER_OPTIONS.filter((o) => o.value).map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </Select>
          </FilterField>
          <FilterField label="저장소" wide>
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
          <FilterField label="검색어" wide>
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
          <FilterField label="시작일">
            <Input
              type="date"
              value={draft.fromDate}
              onChange={(e) => setDraft((d) => ({ ...d, fromDate: e.target.value }))}
              disabled={listBusy}
            />
          </FilterField>
          <FilterField label="종료일">
            <Input
              type="date"
              value={draft.toDate}
              onChange={(e) => setDraft((d) => ({ ...d, toDate: e.target.value }))}
              disabled={listBusy}
            />
          </FilterField>
          <FilterField label="개수">
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

      <AdminJobsEnqueuePanel
        dataSources={dataSources}
        defaultDataSourceId={applied.dataSourceId}
        listBusy={listBusy}
        onEnqueued={fetchList}
      />

      <SectionCard title="작업 이력">
        {items.length === 0 && !listBusy ? (
          <EmptyState title="작업이 없습니다" description="필터를 바꾸거나 기간을 넓혀 보세요." />
        ) : (
          <div style={{ overflowX: "auto" }}>
            <DataTable>
              <thead>
                <tr>
                  <th>작업 종류</th>
                  <th>상태</th>
                  <th>저장소</th>
                  <th>시작</th>
                  <th>종료</th>
                  <th>소요</th>
                  <th>진행</th>
                  <th>오류 요약</th>
                  <th style={{ minWidth: "7rem" }}>작업</th>
                </tr>
              </thead>
              <tbody>
                {items.map((j) => (
                  <tr key={j.id}>
                    <td>
                      <div>{getJobTypeLabel(j.job_type)}</div>
                      {j.job_type?.toUpperCase() === "PIPELINE" ? (
                        <div className="muted" style={{ fontSize: "0.7rem" }}>
                          전체 검색 반영
                        </div>
                      ) : null}
                      {j.parent_job_id ? (
                        <div className="muted" style={{ fontSize: "0.72rem" }}>
                          하위 단계
                        </div>
                      ) : null}
                    </td>
                    <td>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.35rem", alignItems: "center" }}>
                        <Badge variant={getJobStatusBadgeVariant(j.status)}>{getJobStatusLabel(j.status)}</Badge>
                        {j.status?.toUpperCase() === "RUNNING" && isHeartbeatStale(j.heartbeat_at) && (
                          <Badge variant="neutral">상태 갱신 지연</Badge>
                        )}
                      </div>
                    </td>
                    <td>{j.data_source_name ?? "—"}</td>
                    <td>{formatDateTime(j.started_at)}</td>
                    <td>{formatDateTime(j.finished_at)}</td>
                    <td>{j.duration_ms != null ? formatDuration(j.duration_ms) : "—"}</td>
                    <td>
                      {j.job_type?.toUpperCase() === "PIPELINE" ? (
                        <div>
                          <div
                            style={{
                              height: 6,
                              borderRadius: 3,
                              background: "var(--color-border, #e4e4e7)",
                              overflow: "hidden",
                              marginBottom: "0.25rem",
                              maxWidth: "8rem",
                            }}
                            aria-hidden
                          >
                            <div
                              style={{
                                height: "100%",
                                width: `${Math.min(100, Math.max(0, Number(j.progress_percent) || 0))}%`,
                                background: "var(--color-primary, #2563eb)",
                              }}
                            />
                          </div>
                          <div>{j.progress_percent != null ? `${j.progress_percent}%` : "—"}</div>
                          <div className="muted" style={{ fontSize: "0.72rem", lineHeight: 1.35 }}>
                            단계 {(j.completed_files ?? 0) + (j.skipped_files ?? 0)}/{j.total_files || "—"} 완료
                          </div>
                          <div className="muted" style={{ fontSize: "0.72rem" }}>
                            현재: {pipelineStepLabelKr(j.pipeline_current_step)}
                          </div>
                        </div>
                      ) : (
                        <>
                          {j.progress_percent != null ? `${j.progress_percent}%` : "—"}
                          <div className="muted" style={{ fontSize: "0.75rem" }}>
                            {j.processed_files}/{j.total_files}
                          </div>
                        </>
                      )}
                    </td>
                    <td className="snippet" style={{ maxWidth: "12rem", fontSize: "0.8rem" }}>
                      {errSnippet(j.error_message, 100)}
                    </td>
                    <td>
                      <div style={{ display: "flex", flexDirection: "column", gap: "0.35rem", alignItems: "stretch" }}>
                        <Button type="button" variant="ghost" size="sm" onClick={() => void openDetail(j.id)} disabled={listBusy}>
                          상세
                        </Button>
                        {canShowJobCancelButton(j.status) && (
                          <Button
                            type="button"
                            variant="secondary"
                            size="sm"
                            disabled={listBusy || cancelBusy || retryBusy || j.status?.toUpperCase() === "CANCELLING"}
                            onClick={() => setCancelConfirmJob(j)}
                          >
                            {j.status?.toUpperCase() === "CANCELLING"
                              ? "취소 요청 중"
                              : j.status?.toUpperCase() === "PENDING"
                                ? "취소"
                                : "취소 요청"}
                          </Button>
                        )}
                        {canRetryAdminJob(j) && (
                          <>
                            {!isRetryLimitReached(j) ? (
                              <Button
                                type="button"
                                variant="secondary"
                                size="sm"
                                disabled={listBusy || retryBusy}
                                onClick={() => setRetryDialog({ job: j, force: false })}
                              >
                                재시도
                              </Button>
                            ) : (
                              <>
                                <span className="muted" style={{ fontSize: "0.68rem", lineHeight: 1.2 }}>
                                  재시도 한도 도달
                                </span>
                                <Button
                                  type="button"
                                  variant="secondary"
                                  size="sm"
                                  disabled={listBusy || retryBusy}
                                  onClick={() => setRetryDialog({ job: j, force: true })}
                                >
                                  강제 재시도
                                </Button>
                              </>
                            )}
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </DataTable>
          </div>
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
                <Fragment>
                  {detail && canShowJobCancelButton(detail.job.status) && (
                    <Button
                      type="button"
                      variant="secondary"
                      size="sm"
                      style={{ marginRight: "0.5rem" }}
                      disabled={detailBusy || cancelBusy || retryBusy || detail.job.status?.toUpperCase() === "CANCELLING"}
                      onClick={() => setCancelConfirmJob(detail.job)}
                    >
                      {detail.job.status?.toUpperCase() === "CANCELLING"
                        ? "취소 요청 중"
                        : detail.job.status?.toUpperCase() === "PENDING"
                          ? "취소"
                          : "취소 요청"}
                    </Button>
                  )}
                  {detail && canRetryAdminJob(detail.job) && (
                    <>
                      {!isRetryLimitReached(detail.job) ? (
                        <Button
                          type="button"
                          variant="secondary"
                          size="sm"
                          style={{ marginRight: "0.5rem" }}
                          disabled={detailBusy || retryBusy}
                          onClick={() => setRetryDialog({ job: detail.job, force: false })}
                        >
                          재시도
                        </Button>
                      ) : (
                        <>
                          <span className="muted" style={{ marginRight: "0.35rem", fontSize: "0.75rem" }}>
                            재시도 한도 도달
                          </span>
                          <Button
                            type="button"
                            variant="secondary"
                            size="sm"
                            style={{ marginRight: "0.5rem" }}
                            disabled={detailBusy || retryBusy}
                            onClick={() => setRetryDialog({ job: detail.job, force: true })}
                          >
                            강제 재시도
                          </Button>
                        </>
                      )}
                    </>
                  )}
                  <Button type="button" variant="ghost" size="sm" onClick={closeDetail}>
                    닫기
                  </Button>
                </Fragment>
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
                    <span style={{ display: "inline-flex", flexWrap: "wrap", gap: "0.35rem", alignItems: "center" }}>
                      <Badge variant={getJobStatusBadgeVariant(detail.job.status)}>{getJobStatusLabel(detail.job.status)}</Badge>
                      {detail.job.status?.toUpperCase() === "RUNNING" && isHeartbeatStale(detail.job.heartbeat_at) && (
                        <Badge variant="neutral">상태 갱신 지연</Badge>
                      )}
                    </span>{" "}
                    · {getJobTypeLabel(detail.job.job_type)}{" "}
                    <span className="muted" style={{ fontSize: "0.8rem" }}>
                      ({detail.job.job_type})
                    </span>{" "}
                    · 실패 행 <strong>{detail.failures_count}</strong>건
                  </div>
                  <dl style={{ display: "grid", gridTemplateColumns: "10rem 1fr", gap: "0.35rem 0.75rem", fontSize: "0.875rem" }}>
                    <dt className="muted">요청자</dt>
                    <dd style={{ margin: 0 }}>
                      {detail.job.requested_by_login_id || detail.job.requested_by_name ? (
                        <>
                          {detail.job.requested_by_name ?? "—"}{" "}
                          <span className="muted">
                            ({detail.job.requested_by_login_id ?? "—"})
                          </span>
                        </>
                      ) : (
                        "알 수 없음"
                      )}
                    </dd>
                    <dt className="muted">{UI_LABELS.jobType}</dt>
                    <dd style={{ margin: 0 }}>{getJobTypeLabel(detail.job.job_type)}</dd>
                    <dt className="muted">{UI_LABELS.status}</dt>
                    <dd style={{ margin: 0 }}>{getJobStatusLabel(detail.job.status)}</dd>
                    <dt className="muted">저장소</dt>
                    <dd style={{ margin: 0 }}>{detail.job.data_source_name ?? "—"}</dd>
                    <dt className="muted">진행률</dt>
                    <dd style={{ margin: 0 }}>
                      {detail.job.progress_percent != null ? `${detail.job.progress_percent}%` : "—"}
                    </dd>
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
                      {detail.job.job_type?.toUpperCase() === "PIPELINE" ? (
                        <span className="muted" style={{ fontSize: "0.82rem" }}>
                          파이프라인 부모 Job: 아래 수치는{" "}
                          <strong>단계(하위 Job) 기준</strong>으로 API에서 집계한 값입니다. (DB 컬럼명은 *_files
                          입니다.)
                          <br />
                          total {detail.job.total_files} · 종료 단계 {detail.job.processed_files} · COMPLETED{" "}
                          {detail.job.completed_files} · FAILED {detail.job.failed_files} · PARTIAL {detail.job.skipped_files}{" "}
                          · CANCELLED {detail.job.deleted_files}
                        </span>
                      ) : (
                        <>
                          total {detail.job.total_files} · processed {detail.job.processed_files} · completed{" "}
                          {detail.job.completed_files} · failed {detail.job.failed_files} · skipped {detail.job.skipped_files}{" "}
                          · deleted {detail.job.deleted_files}
                        </>
                      )}
                    </dd>
                    <dt className="muted">{UI_LABELS.errorMessage}</dt>
                    <dd className="snippet" style={{ margin: 0, whiteSpace: "pre-wrap" }}>
                      {detail.job.error_message ?? "—"}
                    </dd>
                  </dl>

                  <details style={{ marginTop: "0.75rem", fontSize: "0.85rem" }}>
                    <summary style={{ cursor: "pointer", fontWeight: 600 }}>{UI_LABELS.advancedInfo}</summary>
                    <dl
                      style={{
                        display: "grid",
                        gridTemplateColumns: "10rem 1fr",
                        gap: "0.35rem 0.75rem",
                        marginTop: "0.5rem",
                      }}
                    >
                      <dt className="muted">{UI_LABELS.jobId}</dt>
                      <dd className="snippet" style={{ margin: 0 }}>{detail.job.id}</dd>
                      <dt className="muted">{UI_LABELS.rawJobType}</dt>
                      <dd style={{ margin: 0 }}>{detail.job.job_type}</dd>
                      <dt className="muted">{UI_LABELS.rawStatus}</dt>
                      <dd style={{ margin: 0 }}>{detail.job.status}</dd>
                      <dt className="muted">{UI_LABELS.workerId}</dt>
                      <dd style={{ margin: 0 }}>{dashStr(detail.job.worker_id)}</dd>
                      <dt className="muted">{UI_LABELS.heartbeat}</dt>
                      <dd style={{ margin: 0 }}>{formatDateTime(detail.job.heartbeat_at)}</dd>
                      <dt className="muted">취소 요청</dt>
                      <dd style={{ margin: 0 }}>{detail.job.cancel_requested ? "예" : "아니오"}</dd>
                      <dt className="muted">{UI_LABELS.priority}</dt>
                      <dd style={{ margin: 0 }}>{dashNum(detail.job.priority)}</dd>
                      <dt className="muted">재시도</dt>
                      <dd style={{ margin: 0 }}>
                        {dashNum(detail.job.retry_count)} / {dashNum(detail.job.max_retries)}
                      </dd>
                      <dt className="muted">{UI_LABELS.pipelineStep}</dt>
                      <dd style={{ margin: 0 }}>{getPipelineStepLabel(detail.job.pipeline_step)}</dd>
                      <dt className="muted">{UI_LABELS.parentJob}</dt>
                      <dd className="snippet" style={{ margin: 0 }}>
                        {detail.job.parent_job_id ?? "—"}
                      </dd>
                      <dt className="muted">이전 작업 ID</dt>
                      <dd className="snippet" style={{ margin: 0 }}>
                        {jobParamsRetriedFromId(detail.job.job_params)}
                      </dd>
                    </dl>
                    {detail.job.job_params != null && (
                      <pre
                        style={{
                          margin: "0.5rem 0 0",
                          padding: "0.5rem",
                          background: "var(--color-surface-elevated, #f4f4f5)",
                          borderRadius: "var(--radius-sm, 6px)",
                          overflow: "auto",
                          maxHeight: "14rem",
                          fontSize: "0.75rem",
                        }}
                      >
                        {JSON.stringify(detail.job.job_params, null, 2)}
                      </pre>
                    )}
                  </details>

                  {retryNewJobId && (
                    <div className="alert alertInfo" style={{ marginTop: "0.65rem", fontSize: "0.85rem" }}>
                      새 작업이 <strong>대기 중</strong>으로 등록되었습니다. 백그라운드 처리기를 실행해야 처리됩니다.{" "}
                      <Button
                        type="button"
                        variant="secondary"
                        size="sm"
                        style={{ marginLeft: "0.35rem" }}
                        onClick={() => {
                          const nid = retryNewJobId;
                          setRetryNewJobId(null);
                          void openDetail(nid);
                        }}
                      >
                        새 Job 보기
                      </Button>
                      <Button type="button" variant="ghost" size="sm" onClick={() => setRetryNewJobId(null)}>
                        닫기
                      </Button>
                    </div>
                  )}
                  {detail.job.job_type?.toUpperCase() === "PIPELINE" && (
                    <Fragment>
                      <h4 style={{ marginTop: "1rem", fontSize: "0.95rem" }}>파이프라인 진행</h4>
                      {jobChildrenBusy && <p className="muted">하위 목록 불러오는 중…</p>}
                      <ErrorMessage message={jobChildrenErr} />

                      {jobChildren?.summary ? (
                        <div
                          style={{
                            marginTop: "0.5rem",
                            padding: "0.75rem",
                            borderRadius: "var(--radius-sm, 8px)",
                            background: "var(--color-surface-elevated, #f4f4f5)",
                            fontSize: "0.875rem",
                          }}
                        >
                          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem 1rem", alignItems: "center" }}>
                            <Badge variant={getJobStatusBadgeVariant(detail.job.status)}>{detail.job.status}</Badge>
                            {jobChildren.summary.failed_steps > 0 || jobChildren.summary.cancelled_steps > 0 ? (
                              <Badge variant="danger">단계 실패/취소</Badge>
                            ) : null}
                            <span>
                              진행률 <strong>{jobChildren.summary.progress_percent}%</strong>
                            </span>
                            <span className="muted">
                              완료 단계 {jobChildren.summary.completed_steps + jobChildren.summary.partial_steps} /{" "}
                              {jobChildren.summary.total_steps}
                            </span>
                            <span className="muted">
                              현재 단계: <strong>{pipelineStepLabelKr(jobChildren.summary.current_step)}</strong>
                            </span>
                          </div>
                          <div
                            style={{
                              marginTop: "0.5rem",
                              height: 8,
                              borderRadius: 4,
                              background: "var(--color-border, #e4e4e7)",
                              overflow: "hidden",
                            }}
                            aria-hidden
                          >
                            <div
                              style={{
                                height: "100%",
                                width: `${Math.min(100, Math.max(0, jobChildren.summary.progress_percent))}%`,
                                background: "var(--color-primary, #2563eb)",
                              }}
                            />
                          </div>
                          <p className="muted" style={{ margin: "0.5rem 0 0", fontSize: "0.78rem" }}>
                            RUNNING {jobChildren.summary.running_steps} · PENDING {jobChildren.summary.pending_steps} ·
                            FAILED {jobChildren.summary.failed_steps} · CANCELLED {jobChildren.summary.cancelled_steps}
                          </p>
                        </div>
                      ) : null}

                      {jobChildren && jobChildren.items.length === 0 && !jobChildrenBusy ? (
                        <p className="muted" style={{ fontSize: "0.85rem", marginTop: "0.5rem" }}>
                          아직 등록된 하위 Job이 없습니다. worker가 부모를 처리하면 첫 단계 Job이 생성됩니다.
                        </p>
                      ) : null}

                      {jobChildren && jobChildren.items.length > 0 ? (
                        <div style={{ marginTop: "0.85rem", display: "flex", flexDirection: "column", gap: "0.65rem" }}>
                          {pipelineStepsFromJobParams(detail.job.job_params).map((stepCode, idx) => {
                            const ch = firstChildForPipelineStep(jobChildren.items, stepCode);
                            const ord = idx + 1;
                            const dur =
                              ch?.duration_ms != null && ch.duration_ms >= 0 ? formatDuration(ch.duration_ms) : "—";
                            return (
                              <div
                                key={`${stepCode}-${ord}`}
                                style={{
                                  border: "1px solid var(--color-border, #e4e4e7)",
                                  borderRadius: "var(--radius-sm, 8px)",
                                  padding: "0.65rem 0.75rem",
                                  background: "var(--color-surface, #fff)",
                                }}
                              >
                                <div style={{ display: "flex", flexWrap: "wrap", gap: "0.35rem 0.75rem", alignItems: "center" }}>
                                  <strong style={{ fontSize: "0.88rem" }}>
                                    {ord}. {pipelineStepLabelKr(stepCode)}
                                  </strong>
                                  {ch ? (
                                    <Badge variant={getJobStatusBadgeVariant(ch.status)}>{ch.status}</Badge>
                                  ) : (
                                    <Badge variant="neutral">대기</Badge>
                                  )}
                                  {ch?.progress_percent != null ? (
                                    <span className="muted" style={{ fontSize: "0.8rem" }}>
                                      {ch.progress_percent}%
                                    </span>
                                  ) : null}
                                </div>
                                <div className="muted" style={{ fontSize: "0.78rem", marginTop: "0.35rem" }}>
                                  child job: {ch ? <code style={{ fontSize: "0.75rem" }}>{ch.id}</code> : "—"} · 시작{" "}
                                  {ch ? formatDateTime(ch.started_at) : "—"} · 종료 {ch ? formatDateTime(ch.finished_at) : "—"} ·
                                  소요 {dur}
                                </div>
                                {ch?.error_message ? (
                                  <p className="muted" style={{ margin: "0.35rem 0 0", fontSize: "0.78rem" }}>
                                    오류: {errSnippet(ch.error_message, 120)}
                                  </p>
                                ) : null}
                                {ch ? (
                                  <div style={{ marginTop: "0.45rem" }}>
                                    <Button type="button" variant="secondary" size="sm" onClick={() => void openDetail(ch.id)}>
                                      상세 보기
                                    </Button>
                                  </div>
                                ) : null}
                              </div>
                            );
                          })}
                        </div>
                      ) : null}

                      {jobChildren && jobChildren.items.length > 0 ? (
                        <details style={{ marginTop: "0.85rem", fontSize: "0.85rem" }}>
                          <summary style={{ cursor: "pointer" }}>전체 하위 Job 테이블</summary>
                          <div style={{ marginTop: "0.5rem", overflowX: "auto" }}>
                            <DataTable>
                              <thead>
                                <tr>
                                  <th>유형</th>
                                  <th>단계</th>
                                  <th>status</th>
                                  <th>진행</th>
                                  <th>시작</th>
                                  <th>종료</th>
                                  <th />
                                </tr>
                              </thead>
                              <tbody>
                                {jobChildren.items.map((c: AdminJobChildItem) => (
                                  <tr key={c.id}>
                                    <td>
                                      <div>{getJobTypeLabel(c.job_type)}</div>
                                      <div className="muted" style={{ fontSize: "0.72rem" }}>
                                        {c.job_type}
                                      </div>
                                    </td>
                                    <td className="snippet" style={{ fontSize: "0.8rem" }}>
                                      {dashStr(c.pipeline_step)}
                                    </td>
                                    <td>
                                      <Badge variant={getJobStatusBadgeVariant(c.status)}>{c.status}</Badge>
                                    </td>
                                    <td>{c.progress_percent != null ? `${c.progress_percent}%` : "—"}</td>
                                    <td style={{ fontSize: "0.8rem" }}>{formatDateTime(c.started_at)}</td>
                                    <td style={{ fontSize: "0.8rem" }}>{formatDateTime(c.finished_at)}</td>
                                    <td>
                                      <Button type="button" variant="ghost" size="sm" onClick={() => void openDetail(c.id)}>
                                        상세 보기
                                      </Button>
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </DataTable>
                          </div>
                        </details>
                      ) : null}
                    </Fragment>
                  )}

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

      <ConfirmDialog
        open={cancelConfirmJob !== null}
        title="작업 취소"
        message={
          cancelConfirmJob?.job_type?.toUpperCase() === "PIPELINE"
            ? "파이프라인(부모) 작업을 취소하면 실행 중인 하위 Job에도 취소 요청이 전달됩니다. 하위 작업이 모두 종료되면 부모 작업이 취소 완료로 마무리됩니다. 계속하시겠습니까?"
            : "이 작업에 취소 요청을 보냅니다. 실행 중인 작업은 다음 안전 지점에서 중단됩니다. 계속하시겠습니까?"
        }
        confirmLabel="확인"
        cancelLabel="닫기"
        danger
        onCancel={() => {
          if (!cancelBusy) setCancelConfirmJob(null);
        }}
        onConfirm={() => void confirmCancelJob()}
      />

      <ConfirmDialog
        open={retryDialog !== null}
        title={retryDialog?.force === true ? "강제 재시도" : "작업 재시도"}
        message={retryDialog?.force === true ? RETRY_FORCE_CONFIRM_MSG : RETRY_CONFIRM_MSG}
        confirmLabel="계속"
        cancelLabel="취소"
        onCancel={() => {
          if (!retryBusy) setRetryDialog(null);
        }}
        onConfirm={() => void confirmRetry()}
      />
    </div>
  );
}
