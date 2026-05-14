import { Fragment, useCallback, useEffect, useState } from "react";
import { getApiErrorMessage } from "@/api/httpClient";
import * as adminJobsApi from "@/api/adminJobsApi";
import { EmptyState } from "@/components/EmptyState";
import { ErrorMessage } from "@/components/ErrorMessage";
import { Loading } from "@/components/Loading";
import {
  Badge,
  Button,
  CollapsiblePanel,
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
import type { AdminJob, AdminJobDetailResponse, AdminJobFailure, AdminJobFailuresResponse } from "@/types/adminJobs";
import { PROCESS_PENDING_DOCUMENTS_DEFAULT_EXTENSIONS } from "@/types/adminJobs";
import { formatDateTime, formatDuration } from "@/utils/format";
import { getJobStatusBadgeVariant, getJobTypeLabel } from "@/utils/jobLabels";
import docStyles from "./DocumentProcessModal.module.css";
import jobsTableStyles from "./AdminJobsPage.module.css";

const STATUS_OPTIONS = [
  "",
  "RUNNING",
  "COMPLETED",
  "FAILED",
  "PENDING",
  "CANCELLING",
  "CANCELLED",
  "PARTIAL",
  "STOPPED",
] as const;

const JOB_TYPE_FILTER_CODES = [
  "MANUAL_SCAN",
  "WEBDAV_SYNC_ROOT",
  "WEBDAV_SYNC_TREE",
  "PROCESS_PENDING_TEXT",
  "PROCESS_PENDING_DOCUMENTS",
  "CHUNK_COMPLETED_TEXT",
  "EMBED_PENDING_CHUNKS",
] as const;

const LIMIT_OPTIONS = [20, 50, 100] as const;

/** Client-side stale hint only; align with backend stale policy later (TODO). */
const STALE_HEARTBEAT_MS = 30 * 60 * 1000;

const DEFAULT_TEXT_JOB_EXTENSIONS = "txt,md,py,java,sql,json,yml,yaml,log,csv";

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

function jobParamsPreview(params: unknown): string {
  if (params == null) return "—";
  try {
    const s = JSON.stringify(params);
    if (s.length <= 72) return s;
    return `${s.slice(0, 69)}...`;
  } catch {
    return "—";
  }
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

  const [testJobType, setTestJobType] = useState<string>("WEBDAV_SYNC_TREE");
  const [testFailTest, setTestFailTest] = useState(false);
  const [testBusy, setTestBusy] = useState(false);
  const [testMsg, setTestMsg] = useState<string | null>(null);

  const [syncDsId, setSyncDsId] = useState("");
  const [syncStartPath, setSyncStartPath] = useState("/");
  const [syncMaxDepth, setSyncMaxDepth] = useState(3);
  const [syncMaxItems, setSyncMaxItems] = useState(5000);
  const [syncIncludeHidden, setSyncIncludeHidden] = useState(false);
  const [syncApplyExclusions, setSyncApplyExclusions] = useState(true);
  const [syncDetectDeleted, setSyncDetectDeleted] = useState(false);
  const [syncPriority, setSyncPriority] = useState(0);
  const [syncBusy, setSyncBusy] = useState(false);
  const [syncMsg, setSyncMsg] = useState<string | null>(null);
  const [syncJobId, setSyncJobId] = useState<string | null>(null);

  const [textDsId, setTextDsId] = useState("");
  const [textLimit, setTextLimit] = useState(100);
  const [textMaxMb, setTextMaxMb] = useState(5);
  const [textIncludeExt, setTextIncludeExt] = useState(DEFAULT_TEXT_JOB_EXTENSIONS);
  const [textPriority, setTextPriority] = useState(0);
  const [textBusy, setTextBusy] = useState(false);
  const [textMsg, setTextMsg] = useState<string | null>(null);
  const [textJobId, setTextJobId] = useState<string | null>(null);

  const [docDsId, setDocDsId] = useState("");
  const [docLimit, setDocLimit] = useState(50);
  const [docMaxMb, setDocMaxMb] = useState(50);
  const [docIncludeExt, setDocIncludeExt] = useState(PROCESS_PENDING_DOCUMENTS_DEFAULT_EXTENSIONS);
  const [docReprocessSkipped, setDocReprocessSkipped] = useState(false);
  const [docPriority, setDocPriority] = useState(0);
  const [docBusy, setDocBusy] = useState(false);
  const [docMsg, setDocMsg] = useState<string | null>(null);
  const [docJobId, setDocJobId] = useState<string | null>(null);

  const [chunkDsId, setChunkDsId] = useState("");
  const [chunkLimit, setChunkLimit] = useState(100);
  const [chunkSize, setChunkSize] = useState(1200);
  const [chunkOverlap, setChunkOverlap] = useState(200);
  const [chunkMinSize, setChunkMinSize] = useState(100);
  const [chunkIncludeExt, setChunkIncludeExt] = useState("");
  const [chunkReprocess, setChunkReprocess] = useState(false);
  const [chunkPriority, setChunkPriority] = useState(0);
  const [chunkBusy, setChunkBusy] = useState(false);
  const [chunkMsg, setChunkMsg] = useState<string | null>(null);
  const [chunkJobId, setChunkJobId] = useState<string | null>(null);

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

  useEffect(() => {
    const sid = applied.dataSourceId.trim();
    if (sid) setSyncDsId(sid);
  }, [applied.dataSourceId]);

  useEffect(() => {
    const sid = applied.dataSourceId.trim();
    if (sid) setTextDsId(sid);
  }, [applied.dataSourceId]);

  useEffect(() => {
    const sid = applied.dataSourceId.trim();
    if (sid) setDocDsId(sid);
  }, [applied.dataSourceId]);

  useEffect(() => {
    const sid = applied.dataSourceId.trim();
    if (sid) setChunkDsId(sid);
  }, [applied.dataSourceId]);

  async function onTestEnqueue() {
    const dsId = applied.dataSourceId.trim() || (dataSources[0]?.id ?? "");
    if (!dsId) {
      setTestMsg("데이터 소스가 없습니다. 필터에서 소스를 선택하거나 데이터 소스를 먼저 등록하세요.");
      return;
    }
    setTestBusy(true);
    setTestMsg(null);
    try {
      const res = await adminJobsApi.postAdminTestEnqueue({
        data_source_id: dsId,
        job_type: testJobType,
        fail_test: testFailTest,
        priority: 0,
      });
      setTestMsg(res.message ?? "Test job queued successfully");
      await fetchList();
    } catch (e) {
      setTestMsg(getApiErrorMessage(e));
    } finally {
      setTestBusy(false);
    }
  }

  async function onEnqueueSyncTree() {
    const dsId = syncDsId.trim() || applied.dataSourceId.trim() || dataSources[0]?.id || "";
    if (!dsId) {
      setSyncMsg("데이터 소스를 선택하세요. (필터의 소스 또는 아래 선택 목록)");
      setSyncJobId(null);
      return;
    }
    setSyncBusy(true);
    setSyncMsg(null);
    setSyncJobId(null);
    try {
      const res = await adminJobsApi.postAdminSyncTreeJob({
        data_source_id: dsId,
        start_path: syncStartPath.trim() || "/",
        max_depth: Math.min(20, Math.max(0, Number(syncMaxDepth) || 3)),
        max_items: Math.min(50_000, Math.max(1, Number(syncMaxItems) || 5000)),
        include_hidden: syncIncludeHidden,
        apply_exclusions: syncApplyExclusions,
        detect_deleted: syncDetectDeleted,
        priority: Number.isFinite(syncPriority) ? syncPriority : 0,
      });
      setSyncJobId(res.job_id);
      setSyncMsg(`${res.message} · job_id: ${res.job_id}. worker를 실행해야 PENDING 작업이 처리됩니다.`);
      await fetchList();
    } catch (e) {
      setSyncMsg(getApiErrorMessage(e));
    } finally {
      setSyncBusy(false);
    }
  }

  async function onEnqueueProcessPendingText() {
    const dsId = textDsId.trim() || applied.dataSourceId.trim() || dataSources[0]?.id || "";
    if (!dsId) {
      setTextMsg("데이터 소스를 선택하세요. (필터의 소스 또는 아래 선택 목록)");
      setTextJobId(null);
      return;
    }
    const lim = Math.min(5000, Math.max(1, Number(textLimit) || 100));
    const maxMb = Math.max(0.001, Number(textMaxMb) || 5);
    const maxBytes = Math.round(maxMb * 1024 * 1024);
    setTextBusy(true);
    setTextMsg(null);
    setTextJobId(null);
    try {
      const extTrim = textIncludeExt.trim();
      const res = await adminJobsApi.postAdminProcessPendingTextJob({
        data_source_id: dsId,
        limit: lim,
        max_file_size_bytes: maxBytes,
        include_extensions: extTrim.length > 0 ? extTrim : undefined,
        priority: Number.isFinite(textPriority) ? textPriority : 0,
      });
      setTextJobId(res.job_id);
      setTextMsg(`${res.message} · job_id: ${res.job_id}. worker를 실행해야 PENDING 작업이 처리됩니다.`);
      await fetchList();
    } catch (e) {
      setTextMsg(getApiErrorMessage(e));
    } finally {
      setTextBusy(false);
    }
  }

  async function onEnqueueProcessPendingDocuments() {
    const dsId = docDsId.trim() || applied.dataSourceId.trim() || dataSources[0]?.id || "";
    if (!dsId) {
      setDocMsg("데이터 소스를 선택하세요. (필터의 소스 또는 아래 선택 목록)");
      setDocJobId(null);
      return;
    }
    const lim = Math.min(5000, Math.max(1, Number(docLimit) || 50));
    const maxMb = Math.max(0.001, Number(docMaxMb) || 50);
    const maxBytes = Math.round(maxMb * 1024 * 1024);
    setDocBusy(true);
    setDocMsg(null);
    setDocJobId(null);
    try {
      const extTrim = docIncludeExt.trim();
      const res = await adminJobsApi.postAdminProcessPendingDocumentsJob({
        data_source_id: dsId,
        limit: lim,
        max_file_size_bytes: maxBytes,
        include_extensions: extTrim.length > 0 ? extTrim : undefined,
        reprocess_skipped: docReprocessSkipped,
        priority: Number.isFinite(docPriority) ? docPriority : 0,
      });
      setDocJobId(res.job_id);
      setDocMsg(
        `${res.message} · job_id: ${res.job_id}.\n` +
          "worker를 실행해야 PENDING 작업이 처리됩니다.\n" +
          "처리 후 검색/RAG 반영을 위해 Chunk 생성과 Embedding 생성이 필요합니다."
      );
      await fetchList();
    } catch (e) {
      setDocMsg(getApiErrorMessage(e));
    } finally {
      setDocBusy(false);
    }
  }

  async function onEnqueueChunkCompletedText() {
    const dsId = chunkDsId.trim() || applied.dataSourceId.trim() || dataSources[0]?.id || "";
    if (!dsId) {
      setChunkMsg("데이터 소스를 선택하세요. (필터의 소스 또는 아래 선택 목록)");
      setChunkJobId(null);
      return;
    }
    const lim = Math.min(5000, Math.max(1, Number(chunkLimit) || 100));
    const cs = Math.min(10_000, Math.max(200, Number(chunkSize) || 1200));
    const co = Math.min(9999, Math.max(0, Number(chunkOverlap) || 0));
    if (co >= cs) {
      setChunkMsg("chunk_overlap은 chunk_size보다 작아야 합니다.");
      setChunkJobId(null);
      return;
    }
    const ms = Math.min(10_000, Math.max(1, Number(chunkMinSize) || 100));
    setChunkBusy(true);
    setChunkMsg(null);
    setChunkJobId(null);
    try {
      const extTrim = chunkIncludeExt.trim();
      const res = await adminJobsApi.postAdminChunkCompletedTextJob({
        data_source_id: dsId,
        limit: lim,
        chunk_size: cs,
        chunk_overlap: co,
        min_chunk_size: ms,
        reprocess: chunkReprocess,
        include_extensions: extTrim.length > 0 ? extTrim : undefined,
        priority: Number.isFinite(chunkPriority) ? chunkPriority : 0,
      });
      setChunkJobId(res.job_id);
      setChunkMsg(
        `${res.message} · job_id: ${res.job_id}.\n` +
          "worker를 실행해야 PENDING 작업이 처리됩니다.\n" +
          "처리 후 검색/RAG 반영을 위해 Embedding 생성이 필요합니다."
      );
      await fetchList();
    } catch (e) {
      setChunkMsg(getApiErrorMessage(e));
    } finally {
      setChunkBusy(false);
    }
  }

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

  async function reloadDetailFor(jobId: string) {
    setDetailBusy(true);
    setDetailErr("");
    try {
      const d = await adminJobsApi.getAdminJob(jobId);
      setDetail(d);
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

  if (loading && items.length === 0) return <Loading />;

  return (
    <div>
      <PageHeader
        title="작업 목록"
        description="WebDAV 동기화, 텍스트 처리, 문서 처리, Chunk, Embedding 작업 이력을 확인합니다. PENDING·RUNNING·CANCELLING 작업은 취소 요청이 가능하며, RUNNING은 다음 안전 지점에서 중단됩니다."
      />
      <ErrorMessage message={error} />
      {cancelFeedback != null && cancelFeedback !== "" && (
        <p className="muted" style={{ marginTop: "0.25rem", fontSize: "0.9rem" }}>
          {cancelFeedback}
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
              <option value="">전체</option>
              {JOB_TYPE_FILTER_CODES.map((code) => (
                <option key={code} value={code}>
                  {getJobTypeLabel(code)} ({code})
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

      <SectionCard title="백그라운드 동기화 (WebDAV sync-tree)">
        <p className="muted" style={{ marginTop: 0, fontSize: "0.85rem" }}>
          <code>POST /api/admin/jobs/sync-tree</code>로 <strong>WEBDAV_SYNC_TREE</strong> 작업을 큐에 넣습니다. 동기 API{" "}
          <code>POST /api/data-sources/…/sync-tree</code>와 별개이며, <strong>worker</strong>(<code>python -m app.worker_main</code>)를
          실행해야 처리됩니다. PipelineRunModal의 동기 실행은 변경되지 않았습니다.
        </p>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(11rem, 1fr))",
            gap: "0.75rem",
            alignItems: "end",
            marginTop: "0.5rem",
          }}
        >
          <FilterField label="data_source_id">
            <Select
              value={syncDsId}
              onChange={(e) => setSyncDsId(e.target.value)}
              disabled={syncBusy || listBusy}
            >
              <option value="">선택…</option>
              {dataSources.map((ds) => (
                <option key={ds.id} value={ds.id}>
                  {ds.name}
                  {!ds.is_active ? " (비활성)" : ""}
                </option>
              ))}
            </Select>
          </FilterField>
          <FilterField label="start_path">
            <Input
              value={syncStartPath}
              onChange={(e) => setSyncStartPath(e.target.value)}
              placeholder="/"
              disabled={syncBusy || listBusy}
            />
          </FilterField>
          <FilterField label="max_depth">
            <Input
              type="number"
              min={0}
              max={20}
              value={String(syncMaxDepth)}
              onChange={(e) => setSyncMaxDepth(Number(e.target.value))}
              disabled={syncBusy || listBusy}
            />
          </FilterField>
          <FilterField label="max_items">
            <Input
              type="number"
              min={1}
              max={50000}
              value={String(syncMaxItems)}
              onChange={(e) => setSyncMaxItems(Number(e.target.value))}
              disabled={syncBusy || listBusy}
            />
          </FilterField>
          <FilterField label="priority">
            <Input
              type="number"
              value={String(syncPriority)}
              onChange={(e) => setSyncPriority(Number(e.target.value))}
              disabled={syncBusy || listBusy}
            />
          </FilterField>
        </div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: "1rem", marginTop: "0.65rem", fontSize: "0.875rem" }}>
          <label style={{ display: "inline-flex", gap: "0.35rem", alignItems: "center", cursor: "pointer" }}>
            <input
              type="checkbox"
              checked={syncIncludeHidden}
              onChange={(e) => setSyncIncludeHidden(e.target.checked)}
              disabled={syncBusy || listBusy}
            />
            include_hidden
          </label>
          <label style={{ display: "inline-flex", gap: "0.35rem", alignItems: "center", cursor: "pointer" }}>
            <input
              type="checkbox"
              checked={syncApplyExclusions}
              onChange={(e) => setSyncApplyExclusions(e.target.checked)}
              disabled={syncBusy || listBusy}
            />
            apply_exclusions
          </label>
          <label style={{ display: "inline-flex", gap: "0.35rem", alignItems: "center", cursor: "pointer" }}>
            <input
              type="checkbox"
              checked={syncDetectDeleted}
              onChange={(e) => setSyncDetectDeleted(e.target.checked)}
              disabled={syncBusy || listBusy}
            />
            detect_deleted
          </label>
        </div>
        <div style={{ marginTop: "0.75rem" }}>
          <Button type="button" variant="primary" size="sm" onClick={() => void onEnqueueSyncTree()} disabled={syncBusy || listBusy}>
            Sync-tree Job 생성
          </Button>
        </div>
        {syncJobId != null && syncJobId !== "" && (
          <p className="muted" style={{ marginTop: "0.5rem", fontSize: "0.8rem" }}>
            마지막 생성 job_id: <code>{syncJobId}</code>
          </p>
        )}
        {syncMsg != null && syncMsg !== "" && (
          <p className="muted" style={{ marginTop: "0.5rem", fontSize: "0.85rem", whiteSpace: "pre-wrap" }}>
            {syncMsg}
          </p>
        )}
      </SectionCard>

      <SectionCard title="백그라운드 텍스트 처리">
        <p className="muted" style={{ marginTop: 0, fontSize: "0.85rem" }}>
          <code>POST /api/admin/jobs/process-pending-text</code>로 <strong>PROCESS_PENDING_TEXT</strong> 작업을 큐에 넣습니다. 동기 API{" "}
          <code>POST /api/data-sources/…/process-pending-text</code>(dry_run 포함) 및 PipelineRunModal과 별개입니다.{" "}
          <strong>worker</strong>(<code>python -m app.worker_main</code>)를 실행해야 처리됩니다.
        </p>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(11rem, 1fr))",
            gap: "0.75rem",
            alignItems: "end",
            marginTop: "0.5rem",
          }}
        >
          <FilterField label="data_source_id">
            <Select
              value={textDsId}
              onChange={(e) => setTextDsId(e.target.value)}
              disabled={textBusy || listBusy}
            >
              <option value="">선택…</option>
              {dataSources.map((ds) => (
                <option key={ds.id} value={ds.id}>
                  {ds.name}
                  {!ds.is_active ? " (비활성)" : ""}
                </option>
              ))}
            </Select>
          </FilterField>
          <FilterField label="limit">
            <Input
              type="number"
              min={1}
              max={5000}
              value={String(textLimit)}
              onChange={(e) => setTextLimit(Number(e.target.value))}
              disabled={textBusy || listBusy}
            />
          </FilterField>
          <FilterField label="max_file_size_mb">
            <Input
              type="number"
              min={0.001}
              step={0.5}
              value={String(textMaxMb)}
              onChange={(e) => setTextMaxMb(Number(e.target.value))}
              disabled={textBusy || listBusy}
            />
          </FilterField>
          <FilterField label="priority">
            <Input
              type="number"
              value={String(textPriority)}
              onChange={(e) => setTextPriority(Number(e.target.value))}
              disabled={textBusy || listBusy}
            />
          </FilterField>
        </div>
        <FilterField label="include_extensions" wide>
          <Input
            value={textIncludeExt}
            onChange={(e) => setTextIncludeExt(e.target.value)}
            placeholder={DEFAULT_TEXT_JOB_EXTENSIONS}
            disabled={textBusy || listBusy}
          />
        </FilterField>
        <div style={{ marginTop: "0.75rem" }}>
          <Button
            type="button"
            variant="primary"
            size="sm"
            onClick={() => void onEnqueueProcessPendingText()}
            disabled={textBusy || listBusy}
          >
            Text 처리 Job 생성
          </Button>
        </div>
        {textJobId != null && textJobId !== "" && (
          <p className="muted" style={{ marginTop: "0.5rem", fontSize: "0.8rem" }}>
            마지막 생성 job_id: <code>{textJobId}</code>
          </p>
        )}
        {textMsg != null && textMsg !== "" && (
          <p className="muted" style={{ marginTop: "0.5rem", fontSize: "0.85rem", whiteSpace: "pre-wrap" }}>
            {textMsg}
          </p>
        )}
      </SectionCard>

      <SectionCard title="백그라운드 문서 처리">
        <p className="muted" style={{ marginTop: 0, fontSize: "0.85rem" }}>
          <code>POST /api/admin/jobs/process-pending-documents</code>로 <strong>PROCESS_PENDING_DOCUMENTS</strong> 작업을 큐에 넣습니다. 동기 API{" "}
          <code>POST /api/data-sources/…/process-pending-documents</code>(dry_run 포함) 및 DataSourcesPage 문서 처리 모달·PipelineRunModal과 별개입니다.{" "}
          <strong>worker</strong>(<code>python -m app.worker_main</code>)를 실행해야 처리됩니다.
        </p>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(11rem, 1fr))",
            gap: "0.75rem",
            alignItems: "end",
            marginTop: "0.5rem",
          }}
        >
          <FilterField label="data_source_id">
            <Select
              value={docDsId}
              onChange={(e) => setDocDsId(e.target.value)}
              disabled={docBusy || listBusy}
            >
              <option value="">선택…</option>
              {dataSources.map((ds) => (
                <option key={ds.id} value={ds.id}>
                  {ds.name}
                  {!ds.is_active ? " (비활성)" : ""}
                </option>
              ))}
            </Select>
          </FilterField>
          <FilterField label="limit">
            <Input
              type="number"
              min={1}
              max={5000}
              value={String(docLimit)}
              onChange={(e) => setDocLimit(Number(e.target.value))}
              disabled={docBusy || listBusy}
            />
          </FilterField>
          <FilterField label="max_file_size_mb">
            <Input
              type="number"
              min={0.001}
              step={0.5}
              value={String(docMaxMb)}
              onChange={(e) => setDocMaxMb(Number(e.target.value))}
              disabled={docBusy || listBusy}
            />
          </FilterField>
          <FilterField label="priority">
            <Input
              type="number"
              value={String(docPriority)}
              onChange={(e) => setDocPriority(Number(e.target.value))}
              disabled={docBusy || listBusy}
            />
          </FilterField>
        </div>
        <FilterField label="include_extensions" wide>
          <Input
            value={docIncludeExt}
            onChange={(e) => setDocIncludeExt(e.target.value)}
            placeholder={PROCESS_PENDING_DOCUMENTS_DEFAULT_EXTENSIONS}
            disabled={docBusy || listBusy}
          />
        </FilterField>
        <label
          style={{
            display: "inline-flex",
            gap: "0.35rem",
            alignItems: "center",
            fontSize: "0.875rem",
            cursor: "pointer",
            marginTop: "0.35rem",
          }}
        >
          <input
            type="checkbox"
            checked={docReprocessSkipped}
            onChange={(e) => setDocReprocessSkipped(e.target.checked)}
            disabled={docBusy || listBusy}
          />
          기존 UNSUPPORTED_EXTENSION 스킵 문서를 다시 처리 (reprocess_skipped)
        </label>
        <div style={{ marginTop: "0.75rem" }}>
          <Button
            type="button"
            variant="primary"
            size="sm"
            onClick={() => void onEnqueueProcessPendingDocuments()}
            disabled={docBusy || listBusy}
          >
            문서 처리 Job 생성
          </Button>
        </div>
        {docJobId != null && docJobId !== "" && (
          <p className="muted" style={{ marginTop: "0.5rem", fontSize: "0.8rem" }}>
            마지막 생성 job_id: <code>{docJobId}</code>
          </p>
        )}
        {docMsg != null && docMsg !== "" && (
          <p className="muted" style={{ marginTop: "0.5rem", fontSize: "0.85rem", whiteSpace: "pre-wrap" }}>
            {docMsg}
          </p>
        )}
      </SectionCard>

      <SectionCard title="백그라운드 Chunk 생성">
        <p className="muted" style={{ marginTop: 0, fontSize: "0.85rem" }}>
          <code>POST /api/admin/jobs/chunk-completed-text</code>로 <strong>CHUNK_COMPLETED_TEXT</strong> 작업을 큐에 넣습니다. 동기 API{" "}
          <code>POST /api/data-sources/…/chunk-completed-text</code>(dry_run 포함) 및 PipelineRunModal과 별개입니다.{" "}
          <strong>worker</strong>(<code>python -m app.worker_main</code>)를 실행해야 처리됩니다.
        </p>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(11rem, 1fr))",
            gap: "0.75rem",
            alignItems: "end",
            marginTop: "0.5rem",
          }}
        >
          <FilterField label="data_source_id">
            <Select
              value={chunkDsId}
              onChange={(e) => setChunkDsId(e.target.value)}
              disabled={chunkBusy || listBusy}
            >
              <option value="">선택…</option>
              {dataSources.map((ds) => (
                <option key={ds.id} value={ds.id}>
                  {ds.name}
                  {!ds.is_active ? " (비활성)" : ""}
                </option>
              ))}
            </Select>
          </FilterField>
          <FilterField label="limit">
            <Input
              type="number"
              min={1}
              max={5000}
              value={String(chunkLimit)}
              onChange={(e) => setChunkLimit(Number(e.target.value))}
              disabled={chunkBusy || listBusy}
            />
          </FilterField>
          <FilterField label="chunk_size">
            <Input
              type="number"
              min={200}
              max={10000}
              value={String(chunkSize)}
              onChange={(e) => setChunkSize(Number(e.target.value))}
              disabled={chunkBusy || listBusy}
            />
          </FilterField>
          <FilterField label="chunk_overlap">
            <Input
              type="number"
              min={0}
              max={9999}
              value={String(chunkOverlap)}
              onChange={(e) => setChunkOverlap(Number(e.target.value))}
              disabled={chunkBusy || listBusy}
            />
          </FilterField>
          <FilterField label="min_chunk_size">
            <Input
              type="number"
              min={1}
              max={10000}
              value={String(chunkMinSize)}
              onChange={(e) => setChunkMinSize(Number(e.target.value))}
              disabled={chunkBusy || listBusy}
            />
          </FilterField>
          <FilterField label="priority">
            <Input
              type="number"
              value={String(chunkPriority)}
              onChange={(e) => setChunkPriority(Number(e.target.value))}
              disabled={chunkBusy || listBusy}
            />
          </FilterField>
        </div>
        <FilterField label="include_extensions (선택)" wide>
          <Input
            value={chunkIncludeExt}
            onChange={(e) => setChunkIncludeExt(e.target.value)}
            placeholder="예: txt,md,pdf,docx,hwpx — 비우면 서버 기본(필터 없음)"
            disabled={chunkBusy || listBusy}
          />
        </FilterField>
        <label
          style={{
            display: "inline-flex",
            gap: "0.35rem",
            alignItems: "center",
            fontSize: "0.875rem",
            cursor: "pointer",
            marginTop: "0.35rem",
          }}
        >
          <input
            type="checkbox"
            checked={chunkReprocess}
            onChange={(e) => setChunkReprocess(e.target.checked)}
            disabled={chunkBusy || listBusy}
          />
          기존 Chunk를 재생성합니다 (reprocess). 취소는 파일 단위 안전 지점에서만 적용됩니다.
        </label>
        <div style={{ marginTop: "0.75rem" }}>
          <Button
            type="button"
            variant="primary"
            size="sm"
            onClick={() => void onEnqueueChunkCompletedText()}
            disabled={chunkBusy || listBusy}
          >
            Chunk 생성 Job 생성
          </Button>
        </div>
        {chunkJobId != null && chunkJobId !== "" && (
          <p className="muted" style={{ marginTop: "0.5rem", fontSize: "0.8rem" }}>
            마지막 생성 job_id: <code>{chunkJobId}</code>
          </p>
        )}
        {chunkMsg != null && chunkMsg !== "" && (
          <p className="muted" style={{ marginTop: "0.5rem", fontSize: "0.85rem", whiteSpace: "pre-wrap" }}>
            {chunkMsg}
          </p>
        )}
      </SectionCard>

      <CollapsiblePanel
        title="개발·검증용 (Worker 스켈레톤)"
        summary="PENDING 테스트 Job을 넣고 별도 터미널에서 백엔드 python -m app.worker_main 실행 후 목록을 새로고침해 RUNNING → COMPLETED 전이를 확인합니다."
        defaultOpen={false}
      >
        <p className="muted" style={{ marginTop: 0, fontSize: "0.8rem" }}>
          {/* TODO: 정식 POST /api/admin/jobs 도입 시 이 패널·test-enqueue 호출 제거·대체 예정 */}
          POST /api/admin/jobs/test-enqueue — 관리자 전용. action_logs 미기록(백엔드 README 참고).
        </p>
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: "0.75rem",
            alignItems: "flex-end",
            marginTop: "0.5rem",
          }}
        >
          <FilterField label="job_type">
            <Select
              value={testJobType}
              onChange={(e) => setTestJobType(e.target.value)}
              disabled={testBusy || listBusy}
            >
              {JOB_TYPE_FILTER_CODES.map((code) => (
                <option key={code} value={code}>
                  {getJobTypeLabel(code)} ({code})
                </option>
              ))}
            </Select>
          </FilterField>
          <label
            style={{
              display: "inline-flex",
              gap: "0.35rem",
              alignItems: "center",
              fontSize: "0.875rem",
              cursor: "pointer",
            }}
          >
            <input
              type="checkbox"
              checked={testFailTest}
              onChange={(e) => setTestFailTest(e.target.checked)}
              disabled={testBusy || listBusy}
            />
            fail_test
          </label>
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={() => void onTestEnqueue()}
            disabled={testBusy || listBusy}
          >
            테스트 Job 생성
          </Button>
        </div>
        {testMsg != null && testMsg !== "" && (
          <p className="muted" style={{ marginTop: "0.65rem", fontSize: "0.85rem" }}>
            {testMsg}
          </p>
        )}
      </CollapsiblePanel>

      <SectionCard title="작업 이력">
        {items.length === 0 && !listBusy ? (
          <EmptyState title="작업이 없습니다" description="필터를 바꾸거나 기간을 넓혀 보세요." />
        ) : (
          <div style={{ overflowX: "auto" }}>
            <DataTable>
              <thead>
                <tr>
                  <th>작업 유형</th>
                  <th>status</th>
                  <th>소스</th>
                  <th>우선순위</th>
                  <th className={jobsTableStyles.thJobParams}>job_params</th>
                  <th>파이프라인</th>
                  <th>worker</th>
                  <th>heartbeat</th>
                  <th>재시도</th>
                  <th>시작</th>
                  <th>종료</th>
                  <th>소요</th>
                  <th>진행</th>
                  <th>완료/실패/스킵/삭제</th>
                  <th>오류 요약</th>
                  <th style={{ minWidth: "7rem" }}>작업</th>
                </tr>
              </thead>
              <tbody>
                {items.map((j) => (
                  <tr key={j.id}>
                    <td>
                      <div>{getJobTypeLabel(j.job_type)}</div>
                      <div className="muted" style={{ fontSize: "0.75rem" }}>
                        {j.job_type}
                      </div>
                    </td>
                    <td>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.35rem", alignItems: "center" }}>
                        <Badge variant={getJobStatusBadgeVariant(j.status)}>{j.status}</Badge>
                        {j.status?.toUpperCase() === "RUNNING" && isHeartbeatStale(j.heartbeat_at) && (
                          <Badge variant="neutral">heartbeat 지연</Badge>
                        )}
                      </div>
                    </td>
                    <td>{j.data_source_name ?? "—"}</td>
                    <td style={{ fontSize: "0.85rem" }}>{dashNum(j.priority)}</td>
                    <td
                      className={jobsTableStyles.tdJobParams}
                      title={j.job_params != null ? JSON.stringify(j.job_params) : undefined}
                    >
                      {jobParamsPreview(j.job_params)}
                    </td>
                    <td className="snippet" style={{ fontSize: "0.8rem", maxWidth: "7rem" }}>
                      {dashStr(j.pipeline_step)}
                    </td>
                    <td className="snippet" style={{ fontSize: "0.75rem", maxWidth: "6rem" }}>
                      {dashStr(j.worker_id)}
                    </td>
                    <td style={{ fontSize: "0.75rem", whiteSpace: "nowrap" }}>
                      {formatDateTime(j.heartbeat_at)}
                    </td>
                    <td style={{ fontSize: "0.8rem" }}>
                      {dashNum(j.retry_count)} / {dashNum(j.max_retries)}
                    </td>
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
                      <div style={{ display: "flex", flexDirection: "column", gap: "0.35rem", alignItems: "stretch" }}>
                        <Button type="button" variant="ghost" size="sm" onClick={() => void openDetail(j.id)} disabled={listBusy}>
                          상세
                        </Button>
                        {canShowJobCancelButton(j.status) && (
                          <Button
                            type="button"
                            variant="secondary"
                            size="sm"
                            disabled={listBusy || cancelBusy || j.status?.toUpperCase() === "CANCELLING"}
                            onClick={() => setCancelConfirmJob(j)}
                          >
                            {j.status?.toUpperCase() === "CANCELLING"
                              ? "취소 요청 중"
                              : j.status?.toUpperCase() === "PENDING"
                                ? "취소"
                                : "취소 요청"}
                          </Button>
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
                      disabled={detailBusy || cancelBusy || detail.job.status?.toUpperCase() === "CANCELLING"}
                      onClick={() => setCancelConfirmJob(detail.job)}
                    >
                      {detail.job.status?.toUpperCase() === "CANCELLING"
                        ? "취소 요청 중"
                        : detail.job.status?.toUpperCase() === "PENDING"
                          ? "취소"
                          : "취소 요청"}
                    </Button>
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
                      <Badge variant={getJobStatusBadgeVariant(detail.job.status)}>{detail.job.status}</Badge>
                      {detail.job.status?.toUpperCase() === "RUNNING" && isHeartbeatStale(detail.job.heartbeat_at) && (
                        <Badge variant="neutral">heartbeat 지연</Badge>
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
                    <dt className="muted">cancel_requested</dt>
                    <dd style={{ margin: 0 }}>{detail.job.cancel_requested ? "예" : "아니오"}</dd>
                    <dt className="muted">worker / heartbeat</dt>
                    <dd style={{ margin: 0 }}>
                      {dashStr(detail.job.worker_id)} · {formatDateTime(detail.job.heartbeat_at)}
                    </dd>
                    <dt className="muted">priority</dt>
                    <dd style={{ margin: 0 }}>{dashNum(detail.job.priority)}</dd>
                    <dt className="muted">retry</dt>
                    <dd style={{ margin: 0 }}>
                      {dashNum(detail.job.retry_count)} / {dashNum(detail.job.max_retries)}
                    </dd>
                    <dt className="muted">pipeline_step</dt>
                    <dd style={{ margin: 0 }}>{dashStr(detail.job.pipeline_step)}</dd>
                    <dt className="muted">parent_job_id</dt>
                    <dd className="snippet" style={{ margin: 0 }}>
                      {detail.job.parent_job_id ?? "—"}
                    </dd>
                  </dl>

                  {detail.job.job_params != null && (
                    <details style={{ marginTop: "0.75rem", fontSize: "0.85rem" }}>
                      <summary style={{ cursor: "pointer", marginBottom: "0.35rem" }}>job_params (JSON)</summary>
                      <pre
                        style={{
                          margin: 0,
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
                    </details>
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
        message="이 작업에 취소 요청을 보냅니다. 실행 중인 작업은 다음 안전 지점에서 중단됩니다. 계속하시겠습니까?"
        confirmLabel="확인"
        cancelLabel="닫기"
        danger
        onCancel={() => {
          if (!cancelBusy) setCancelConfirmJob(null);
        }}
        onConfirm={() => void confirmCancelJob()}
      />
    </div>
  );
}
