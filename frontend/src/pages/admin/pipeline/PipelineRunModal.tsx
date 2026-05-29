import { createPortal } from "react-dom";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import * as adminJobsApi from "@/api/adminJobsApi";
import * as dsApi from "@/api/dataSourceApi";
import { getApiErrorMessage } from "@/api/httpClient";
import { ErrorMessage } from "@/components/ErrorMessage";
import {
  AdvancedSection,
  Badge,
  Button,
  ConfirmDialog,
  FormField,
  InfoBox,
  Input,
  ProgressBar,
  SectionCard,
  Select,
} from "@/components/ui";
import {
  PIPELINE_MODAL_STEP_LABELS,
  PIPELINE_STEP_DESCRIPTIONS,
} from "@/utils/userFriendlyLabels";
import type { DataSource } from "@/types/dataSource";
import type { DocumentProcessResponse } from "@/types/documentProcessing";
import {
  SERVER_MAX_FILE_BYTES,
  SERVER_MAX_FILE_MB,
  type ScanScope,
} from "@/constants/pipelineLimits";
import type { AdminPipelineJobRequest } from "@/types/adminJobs";
import { PROCESS_PENDING_DOCUMENTS_DEFAULT_EXTENSIONS } from "@/types/adminJobs";
import type { FileStatsResponse } from "@/types/file";
import type {
  PipelineAutoStepKey,
  PipelineAutoStepState,
  PipelineStepStatus,
} from "@/types/pipeline";
import type {
  BackgroundPipelineStepState,
  ExecutionMode,
  PipelineBackgroundStepId,
} from "@/types/pipelineBackground";
import { formatDateTime, formatDuration, formatInt, formatRelativeTime } from "@/utils/format";
import { getJobStatusBadgeVariant, getJobStatusLabel, getJobTypeLabel } from "@/utils/jobLabels";
import {
  DocumentProcessingPanel,
  type DocumentPipelineFormSnapshot,
} from "./DocumentProcessingPanel";
import { PipelineResponseView } from "./PipelineResponseView";
import docStyles from "../DocumentProcessModal.module.css";
import styles from "./PipelineRunModal.module.css";

type StepId = "sync" | "text" | "doc" | "chunk" | "embed";

type StepSnap = {
  status: PipelineStepStatus;
  payload: Record<string, unknown> | null;
  error: string;
};

const STEP_LABEL: Record<StepId, string> = {
  sync: PIPELINE_MODAL_STEP_LABELS.sync,
  text: PIPELINE_MODAL_STEP_LABELS.text,
  doc: PIPELINE_MODAL_STEP_LABELS.doc,
  chunk: PIPELINE_MODAL_STEP_LABELS.chunk,
  embed: PIPELINE_MODAL_STEP_LABELS.embed,
};

const STEP_TO_AUTO_KEY: Record<StepId, PipelineAutoStepKey> = {
  sync: "sync",
  text: "text",
  doc: "document",
  chunk: "chunk",
  embed: "embedding",
};

const STEPS_ORDER: StepId[] = ["sync", "text", "doc", "chunk", "embed"];

const STEP_DESC_KEY: Record<StepId, keyof typeof PIPELINE_STEP_DESCRIPTIONS> = {
  sync: "sync",
  text: "text",
  doc: "document",
  chunk: "chunk",
  embed: "embedding",
};

/**
 * 자동 실행 중단 여부: HTTP 오류, 예외, 또는 응답 body의 status === "error" 일 때만 중단.
 * status === "partial" 은 경고로 남기고 다음 단계를 계속 진행한다 (failed_count가 커도 동일).
 */
function isTerminalErrorStatus(status: unknown): boolean {
  return String(status ?? "").toLowerCase() === "error";
}

function emptySnap(): StepSnap {
  return { status: "idle", payload: null, error: "" };
}

const ITEM_PREVIEW_LIMIT = 20;

function truncatePayload(data: Record<string, unknown>, limit = ITEM_PREVIEW_LIMIT): Record<string, unknown> {
  const items = data.items;
  if (!Array.isArray(items) || items.length <= limit) return data;
  const prevWarn = Array.isArray(data.warnings)
    ? data.warnings.filter((x): x is string => typeof x === "string")
    : [];
  return {
    ...data,
    items: items.slice(0, limit),
    warnings: [...prevWarn, `목록은 상위 ${limit}건만 표시합니다. (전체 ${items.length}건)`],
  };
}

const CONFIRM_MSG =
  "이 작업은 파일을 다운로드하거나 DB 상태를 변경할 수 있습니다. 계속하시겠습니까?";

const AUTO_CONFIRM_MSG =
  "전체 파이프라인을 순차 실행합니다. 이 작업은 파일 다운로드, 본문 추출, chunk 생성, embedding 저장 등 DB 상태를 변경할 수 있습니다. 계속하시겠습니까?";

const BG_AUTO_CONFIRM_MSG =
  "백그라운드 파이프라인을 순차 등록합니다. 각 단계가 완료되면 다음 단계 Job을 생성합니다. 브라우저를 닫으면 현재 실행 중인 Job은 계속 처리되지만 다음 단계 자동 등록은 중단될 수 있습니다. 계속하시겠습니까?";

const SERVER_PIPELINE_CONFIRM_MSG =
  "전체 검색 반영 작업을 등록합니다. 서버가 단계별로 순서대로 처리하며, 브라우저를 닫아도 작업이 이어집니다. 계속하시겠습니까?";

function canShowJobCancelButton(status: string | undefined): boolean {
  const u = (status || "").toUpperCase();
  return u === "PENDING" || u === "RUNNING" || u === "CANCELLING";
}

function bgStepLabel(id: PipelineBackgroundStepId): string {
  return STEP_LABEL[id];
}

function emptyBgStep(id: PipelineBackgroundStepId): BackgroundPipelineStepState {
  return { key: id, label: bgStepLabel(id) };
}

function initialBgSteps(): Record<StepId, BackgroundPipelineStepState> {
  return {
    sync: emptyBgStep("sync"),
    text: emptyBgStep("text"),
    doc: emptyBgStep("doc"),
    chunk: emptyBgStep("chunk"),
    embed: emptyBgStep("embed"),
  };
}

function initialAutoSteps(): PipelineAutoStepState[] {
  return [
    { key: "sync", label: "WebDAV 재귀 동기화", status: "idle" },
    { key: "text", label: "일반 텍스트 처리", status: "idle" },
    { key: "document", label: "문서 파일 처리", status: "idle" },
    { key: "chunk", label: "Chunk 생성", status: "idle" },
    { key: "embedding", label: "Embedding 생성", status: "idle" },
  ];
}

const AUTO_KEY_TO_LABEL: Record<PipelineAutoStepKey, string> = {
  sync: "파일 목록 수집",
  text: "텍스트 파일 내용 추출",
  document: "문서 파일 내용 추출",
  chunk: "검색 단위 생성",
  embedding: "검색 인덱스 생성",
};

type Props = {
  dataSource: DataSource;
  onClose: () => void;
  onRefresh: () => void | Promise<void>;
};

export function PipelineRunModal({ dataSource, onClose, onRefresh }: Props) {
  const [snap, setSnap] = useState<Record<StepId, StepSnap>>(() => ({
    sync: emptySnap(),
    text: emptySnap(),
    doc: emptySnap(),
    chunk: emptySnap(),
    embed: emptySnap(),
  }));
  const [loading, setLoading] = useState<StepId | null>(null);
  const [lastRun, setLastRun] = useState<{ step: StepId; ok: boolean } | null>(null);
  const [stats, setStats] = useState<FileStatsResponse | null>(null);
  const [statsError, setStatsError] = useState("");
  const [statsLoading, setStatsLoading] = useState(false);
  const [openStep, setOpenStep] = useState<StepId | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [confirmAutoOpen, setConfirmAutoOpen] = useState(false);
  const [pendingRun, setPendingRun] = useState<null | (() => Promise<void>)>(null);

  const [autoRunning, setAutoRunning] = useState(false);
  const [autoSteps, setAutoSteps] = useState<PipelineAutoStepState[]>(() => initialAutoSteps());
  const [autoSummary, setAutoSummary] = useState<{
    ok: boolean;
    totalMs: number;
    failedStepLabel?: string;
    errorMessage?: string;
    completedSteps: number;
    partialWarnings: string[];
  } | null>(null);

  const defaultDocPipelineParams = useCallback(
    (): DocumentPipelineFormSnapshot => ({
      limit: 0,
      max_file_size_bytes: SERVER_MAX_FILE_BYTES,
      include_extensions: PROCESS_PENDING_DOCUMENTS_DEFAULT_EXTENSIONS,
      reprocess_skipped: false,
    }),
    []
  );

  const docParamsRef = useRef<DocumentPipelineFormSnapshot | null>(defaultDocPipelineParams());
  const onRefreshRef = useRef(onRefresh);
  onRefreshRef.current = onRefresh;

  useEffect(() => {
    docParamsRef.current = defaultDocPipelineParams();
  }, [dataSource.id, defaultDocPipelineParams]);

  const patchSnap = useCallback((id: StepId, partial: Partial<StepSnap>) => {
    setSnap((prev) => ({ ...prev, [id]: { ...prev[id], ...partial } }));
  }, []);

  const applyDocumentSnap = useCallback(
    (response: DocumentProcessResponse | null, error: string): boolean => {
      if (error) {
        patchSnap("doc", { status: "error", payload: null, error });
        setLastRun({ step: "doc", ok: false });
        return false;
      }
      if (response) {
        const st = String(response.status ?? "").toLowerCase();
        const ok = st !== "error";
        const payload = truncatePayload(response as unknown as Record<string, unknown>);
        patchSnap("doc", {
          status: ok ? "success" : "error",
          payload,
          error: ok ? "" : typeof response.message === "string" ? response.message : "요청 실패",
        });
        setLastRun({ step: "doc", ok });
        return ok;
      }
      patchSnap("doc", { status: "error", payload: null, error: "응답이 없습니다." });
      setLastRun({ step: "doc", ok: false });
      return false;
    },
    [patchSnap]
  );

  const handleDocOutcome = useCallback(
    (p: { dryRun: boolean; response: DocumentProcessResponse | null; error: string }) => {
      void p.dryRun;
      applyDocumentSnap(p.response, p.error);
    },
    [applyDocumentSnap]
  );

  const runWithLoading = useCallback(
    async (id: StepId, fn: () => Promise<Record<string, unknown>>) => {
      patchSnap(id, { status: "loading", error: "", payload: null });
      setLoading(id);
      try {
        const data = await fn();
        const display = truncatePayload(data);
        const ok = !isTerminalErrorStatus(display.status);
        patchSnap(id, { status: ok ? "success" : "error", payload: display, error: "" });
        setLastRun({ step: id, ok });
        if (!ok && typeof display.message === "string") {
          patchSnap(id, { error: display.message });
        }
      } catch (e) {
        patchSnap(id, {
          status: "error",
          payload: null,
          error: getApiErrorMessage(e),
        });
        setLastRun({ step: id, ok: false });
      } finally {
        setLoading(null);
        void onRefreshRef.current();
      }
    },
    [patchSnap]
  );

  const requestConfirm = useCallback((fn: () => Promise<void>) => {
    setPendingRun(() => fn);
    setConfirmOpen(true);
  }, []);

  const onConfirmExec = useCallback(() => {
    setConfirmOpen(false);
    const fn = pendingRun;
    setPendingRun(null);
    if (fn) void fn();
  }, [pendingRun]);

  const onDocumentParamsSnapshot = useCallback((p: DocumentPipelineFormSnapshot) => {
    docParamsRef.current = p;
  }, []);

  const [startPath, setStartPath] = useState("/");
  const [scanScope, setScanScope] = useState<ScanScope>("FULL");
  const [maxDepth, setMaxDepth] = useState(3);
  const [maxItems, setMaxItems] = useState(5000);
  const [includeHidden, setIncludeHidden] = useState(false);
  const [applyExclusions, setApplyExclusions] = useState(true);
  const [detectDeleted, setDetectDeleted] = useState(true);

  const [textLimit, setTextLimit] = useState(0);
  const [textUseServerMax, setTextUseServerMax] = useState(true);
  const [textMaxMb, setTextMaxMb] = useState(SERVER_MAX_FILE_MB);
  const [textIncludeExt, setTextIncludeExt] = useState("txt,md,py,java,sql,json,yml");

  const [chunkLimit, setChunkLimit] = useState(0);
  const [chunkSize, setChunkSize] = useState(1200);
  const [chunkOverlap, setChunkOverlap] = useState(200);
  const [chunkMin, setChunkMin] = useState(100);
  const [chunkReprocess, setChunkReprocess] = useState(false);
  const [chunkIncludeExt, setChunkIncludeExt] = useState("");

  const [embedLimit, setEmbedLimit] = useState(0);
  const [embedBatch, setEmbedBatch] = useState(32);
  const [embedReembed, setEmbedReembed] = useState(false);
  const [embedIncludeExt, setEmbedIncludeExt] = useState("");

  const [executionMode, setExecutionMode] = useState<ExecutionMode>("background");
  const [bgSteps, setBgSteps] = useState<Record<StepId, BackgroundPipelineStepState>>(() => initialBgSteps());
  const [bgAutoPoll, setBgAutoPoll] = useState(false);
  const [bgSequentialRunning, setBgSequentialRunning] = useState(false);
  const [confirmBgAutoOpen, setConfirmBgAutoOpen] = useState(false);
  const [confirmServerPipelineOpen, setConfirmServerPipelineOpen] = useState(false);
  const [serverPipelineBusy, setServerPipelineBusy] = useState(false);
  const [serverPipelineErr, setServerPipelineErr] = useState("");
  const [serverPipelineJobId, setServerPipelineJobId] = useState<string | null>(null);
  const [bgCancelDialogStep, setBgCancelDialogStep] = useState<StepId | null>(null);
  const [bgCancelBusy, setBgCancelBusy] = useState(false);
  const [bgEnqueueStep, setBgEnqueueStep] = useState<StepId | null>(null);
  const bgStepsRef = useRef(bgSteps);
  const bgAbortSequentialRef = useRef(false);

  useEffect(() => {
    bgStepsRef.current = bgSteps;
  }, [bgSteps]);

  useEffect(() => {
    if (executionMode !== "background") {
      setBgAutoPoll(false);
    }
  }, [executionMode]);

  useEffect(() => {
    if (!bgAutoPoll || executionMode !== "background") return;
    const tick = () => {
      void (async () => {
        const steps = bgStepsRef.current;
        for (const id of STEPS_ORDER) {
          const jid = steps[id].jobId;
          if (!jid) continue;
          try {
            const d = await adminJobsApi.getAdminJob(jid);
            const job = d.job;
            setBgSteps((prev) => ({
              ...prev,
              [id]: {
                ...prev[id],
                jobType: job.job_type,
                status: job.status,
                progressPercent: job.progress_percent,
                workerId: job.worker_id ?? null,
                heartbeatAt: job.heartbeat_at,
                startedAt: job.started_at,
                finishedAt: job.finished_at,
                errorMessage: job.error_message,
                lastUpdatedAt: new Date().toISOString(),
              },
            }));
          } catch {
            /* 단일 폴링 실패는 무시 */
          }
        }
      })();
    };
    tick();
    const intervalId = window.setInterval(tick, 5000);
    return () => window.clearInterval(intervalId);
  }, [bgAutoPoll, executionMode]);

  const mergeJobIntoBgStep = useCallback((stepId: StepId, job: import("@/types/adminJobs").AdminJob) => {
    setBgSteps((prev) => ({
      ...prev,
      [stepId]: {
        ...prev[stepId],
        jobId: job.id,
        jobType: job.job_type,
        status: job.status,
        progressPercent: job.progress_percent,
        totalFiles: job.total_files,
        processedFiles: job.processed_files,
        completedFiles: job.completed_files,
        failedFiles: job.failed_files,
        skippedFiles: job.skipped_files,
        currentFilePath: job.current_file_path,
        workerId: job.worker_id ?? null,
        heartbeatAt: job.heartbeat_at,
        startedAt: job.started_at,
        finishedAt: job.finished_at,
        errorMessage: job.error_message,
        lastUpdatedAt: new Date().toISOString(),
      },
    }));
  }, []);

  const textMaxFileBytes = textUseServerMax
    ? SERVER_MAX_FILE_BYTES
    : Math.max(1, Number(textMaxMb) || SERVER_MAX_FILE_MB) * 1024 * 1024;

  function buildSyncTreeJobFields(): {
    scan_scope: ScanScope;
    start_path: string;
    max_depth?: number | null;
    max_items?: number | null;
    include_hidden: boolean;
    apply_exclusions: boolean;
    detect_deleted: boolean;
  } {
    const base = {
      start_path: startPath || "/",
      include_hidden: includeHidden,
      apply_exclusions: applyExclusions,
      detect_deleted: detectDeleted,
    };
    if (scanScope === "FULL") {
      return { scan_scope: "FULL", ...base, max_depth: null, max_items: null };
    }
    return {
      scan_scope: "LIMITED",
      ...base,
      max_depth: Math.min(20, Math.max(0, Number(maxDepth) || 3)),
      max_items: Math.min(50_000, Math.max(1, Number(maxItems) || 5000)),
    };
  }

  async function enqueueBackgroundJobForStep(stepId: StepId): Promise<{ jobId: string; jobType: string }> {
    const ds = dataSource.id;
    if (stepId === "sync") {
      const r = await adminJobsApi.postAdminSyncTreeJob({
        data_source_id: ds,
        ...buildSyncTreeJobFields(),
        priority: 0,
      });
      return { jobId: r.job_id, jobType: r.job_type };
    }
    if (stepId === "text") {
      const r = await adminJobsApi.postAdminProcessPendingTextJob({
        data_source_id: ds,
        limit: textLimit,
        max_file_size_bytes: textMaxFileBytes,
        include_extensions: textIncludeExt.trim() || undefined,
        priority: 0,
      });
      return { jobId: r.job_id, jobType: r.job_type };
    }
    if (stepId === "doc") {
      const p = docParamsRef.current;
      const include = p?.include_extensions?.trim();
      if (!p || !include) {
        throw new Error("문서 처리: 확장자를 하나 이상 선택해 주세요.");
      }
      const r = await adminJobsApi.postAdminProcessPendingDocumentsJob({
        data_source_id: ds,
        limit: p.limit,
        max_file_size_bytes: p.max_file_size_bytes,
        include_extensions: include,
        reprocess_skipped: p.reprocess_skipped,
        priority: 0,
      });
      return { jobId: r.job_id, jobType: r.job_type };
    }
    if (stepId === "chunk") {
      const cs = Math.min(10_000, Math.max(200, Number(chunkSize) || 1200));
      const co = Math.min(9999, Math.max(0, Number(chunkOverlap) || 0));
      if (co >= cs) {
        throw new Error("chunk_overlap은 chunk_size보다 작아야 합니다.");
      }
      const r = await adminJobsApi.postAdminChunkCompletedTextJob({
        data_source_id: ds,
        limit: Math.min(5000, Math.max(0, chunkLimit)),
        chunk_size: cs,
        chunk_overlap: co,
        min_chunk_size: Math.max(1, Math.min(10_000, Number(chunkMin) || 100)),
        reprocess: chunkReprocess,
        include_extensions: chunkIncludeExt.trim() || undefined,
        priority: 0,
      });
      return { jobId: r.job_id, jobType: r.job_type };
    }
    const r = await adminJobsApi.postAdminEmbedPendingChunksJob({
      data_source_id: ds,
      limit: Math.min(10_000, Math.max(0, embedLimit)),
      batch_size: Math.min(128, Math.max(1, embedBatch)),
      reembed: embedReembed,
      include_extensions: embedIncludeExt.trim() || undefined,
      priority: 0,
    });
    return { jobId: r.job_id, jobType: r.job_type };
  }

  async function pollJobUntilTerminal(stepId: StepId, jobId: string): Promise<{ ok: boolean; status: string }> {
    while (!bgAbortSequentialRef.current) {
      try {
        const d = await adminJobsApi.getAdminJob(jobId);
        mergeJobIntoBgStep(stepId, d.job);
        const st = (d.job.status || "").toUpperCase();
        if (st === "COMPLETED" || st === "PARTIAL") return { ok: true, status: st };
        if (st === "FAILED" || st === "CANCELLED") return { ok: false, status: st };
      } catch {
        return { ok: false, status: "ERROR" };
      }
      await new Promise((res) => setTimeout(res, 5000));
    }
    return { ok: false, status: "ABORTED" };
  }

  async function executeBackgroundAutoPipeline() {
    bgAbortSequentialRef.current = false;
    setBgSequentialRunning(true);
    setBgSteps(initialBgSteps());
    try {
      for (const stepId of STEPS_ORDER) {
        if (bgAbortSequentialRef.current) break;
        let out: { jobId: string; jobType: string };
        try {
          out = await enqueueBackgroundJobForStep(stepId);
        } catch (e) {
          const msg = getApiErrorMessage(e);
          setBgSteps((prev) => ({
            ...prev,
            [stepId]: {
              ...prev[stepId],
              errorMessage: msg,
              enqueueMessage: msg,
              status: "ENQUEUE_FAILED",
              lastUpdatedAt: new Date().toISOString(),
            },
          }));
          break;
        }
        const { jobId, jobType } = out;
        setBgSteps((prev) => ({
          ...prev,
          [stepId]: {
            ...prev[stepId],
            jobId,
            jobType,
            status: "PENDING",
            enqueueMessage: "worker를 실행해야 작업이 처리됩니다. 초기 상태: PENDING",
            lastUpdatedAt: new Date().toISOString(),
          },
        }));
        try {
          const jd = await adminJobsApi.getAdminJob(jobId);
          mergeJobIntoBgStep(stepId, jd.job);
          const st0 = (jd.job.status || "").toUpperCase();
          if (st0 === "FAILED" || st0 === "CANCELLED") break;
          if (st0 !== "COMPLETED" && st0 !== "PARTIAL") {
            const pr = await pollJobUntilTerminal(stepId, jobId);
            if (!pr.ok) break;
          }
        } catch {
          break;
        }
      }
    } finally {
      setBgSequentialRunning(false);
      void onRefreshRef.current();
    }
  }

  const refreshBgStep = useCallback(
    async (stepId: StepId) => {
      const jid = bgStepsRef.current[stepId].jobId;
      if (!jid) return;
      try {
        const d = await adminJobsApi.getAdminJob(jid);
        mergeJobIntoBgStep(stepId, d.job);
      } catch {
        /* ignore */
      }
    },
    [mergeJobIntoBgStep]
  );

  const refreshAllBgSteps = useCallback(async () => {
    for (const id of STEPS_ORDER) await refreshBgStep(id);
  }, [refreshBgStep]);

  const handleModalClose = useCallback(() => {
    bgAbortSequentialRef.current = true;
    setBgAutoPoll(false);
    onClose();
  }, [onClose]);

  const disableManualActions =
    autoRunning || loading !== null || bgSequentialRunning || bgEnqueueStep !== null || serverPipelineBusy;

  async function executeServerPipelineJob() {
    setServerPipelineErr("");
    setServerPipelineJobId(null);
    setServerPipelineBusy(true);
    try {
      const p = docParamsRef.current;
      const docExt = p?.include_extensions?.trim();
      if (!p || !docExt) {
        throw new Error("문서 처리: 확장자를 하나 이상 선택해 주세요.");
      }
      const cs = Math.min(10_000, Math.max(200, Number(chunkSize) || 1200));
      const co = Math.min(9999, Math.max(0, Number(chunkOverlap) || 0));
      if (co >= cs) {
        throw new Error("chunk_overlap은 chunk_size보다 작아야 합니다.");
      }
      const body: AdminPipelineJobRequest = {
        data_source_id: dataSource.id,
        priority: 0,
        steps: [
          "WEBDAV_SYNC_TREE",
          "PROCESS_PENDING_TEXT",
          "PROCESS_PENDING_DOCUMENTS",
          "CHUNK_COMPLETED_TEXT",
          "EMBED_PENDING_CHUNKS",
        ],
        params: {
          sync_tree: buildSyncTreeJobFields(),
          process_text: {
            limit: textLimit,
            max_file_size_bytes: textMaxFileBytes,
            include_extensions: textIncludeExt.trim() || undefined,
          },
          process_documents: {
            limit: p.limit,
            max_file_size_bytes: p.max_file_size_bytes,
            include_extensions: docExt,
            reprocess_skipped: Boolean(p.reprocess_skipped),
          },
          chunk: {
            limit: Math.min(5000, Math.max(0, chunkLimit)),
            chunk_size: cs,
            chunk_overlap: co,
            min_chunk_size: Math.max(1, Math.min(10_000, Number(chunkMin) || 100)),
            reprocess: chunkReprocess,
            include_extensions: chunkIncludeExt.trim() || undefined,
          },
          embed: {
            limit: Math.min(10_000, Math.max(0, embedLimit)),
            batch_size: Math.min(128, Math.max(1, embedBatch)),
            include_extensions: embedIncludeExt.trim() || undefined,
            reembed: embedReembed,
          },
        },
      };
      const res = await adminJobsApi.postAdminPipelineJob(body);
      setServerPipelineJobId(res.pipeline_job_id);
      void onRefreshRef.current();
    } catch (e) {
      setServerPipelineErr(getApiErrorMessage(e));
    } finally {
      setServerPipelineBusy(false);
    }
  }

  const formDisabled = autoRunning || bgSequentialRunning || serverPipelineBusy;
  const closeDisabled = autoRunning || bgSequentialRunning || loading !== null || serverPipelineBusy;

  async function handleBgEnqueue(stepId: StepId) {
    setBgEnqueueStep(stepId);
    try {
      const out = await enqueueBackgroundJobForStep(stepId);
      setBgSteps((prev) => ({
        ...prev,
        [stepId]: {
          ...prev[stepId],
          jobId: out.jobId,
          jobType: out.jobType,
          status: "PENDING",
          enqueueMessage: "worker를 실행해야 작업이 처리됩니다. 상태: PENDING",
          errorMessage: null,
          lastUpdatedAt: new Date().toISOString(),
        },
      }));
      try {
        const jd = await adminJobsApi.getAdminJob(out.jobId);
        mergeJobIntoBgStep(stepId, jd.job);
      } catch {
        /* 초기 조회 실패는 무시 */
      }
    } catch (e) {
      const msg = getApiErrorMessage(e);
      setBgSteps((prev) => ({
        ...prev,
        [stepId]: {
          ...prev[stepId],
          errorMessage: msg,
          enqueueMessage: msg,
          status: "ENQUEUE_FAILED",
          lastUpdatedAt: new Date().toISOString(),
        },
      }));
    } finally {
      setBgEnqueueStep(null);
      void onRefreshRef.current();
    }
  }

  async function confirmBgStepCancel() {
    const sid = bgCancelDialogStep;
    if (!sid) return;
    const jid = bgStepsRef.current[sid]?.jobId;
    if (!jid) {
      setBgCancelDialogStep(null);
      return;
    }
    setBgCancelBusy(true);
    try {
      await adminJobsApi.cancelAdminJob(jid);
      await refreshBgStep(sid);
    } catch (e) {
      const msg = getApiErrorMessage(e);
      setBgSteps((prev) => ({ ...prev, [sid]: { ...prev[sid], errorMessage: msg } }));
    } finally {
      setBgCancelBusy(false);
      setBgCancelDialogStep(null);
      void onRefreshRef.current();
    }
  }

  const summary = useMemo(() => {
    const entries = STEPS_ORDER.map((id) => ({
      id,
      s: snap[id].status,
    }));
    const completed = entries.filter((e) => e.s === "success").length;
    const failed = entries.filter((e) => e.s === "error").length;
    const lastLabel = lastRun ? STEP_LABEL[lastRun.step] : "—";
    const lastOk = lastRun ? (lastRun.ok ? "성공" : "실패") : "—";
    return { completed, failed, lastLabel, lastOk };
  }, [snap, lastRun]);

  const bgSummary = useMemo(() => {
    const rows = STEPS_ORDER.map((id) => bgSteps[id]);
    const withJob = rows.filter((r) => Boolean(r.jobId));
    const completed = withJob.filter((r) => {
      const s = (r.status || "").toUpperCase();
      return s === "COMPLETED" || s === "PARTIAL";
    });
    const failedWithJob = withJob.filter((r) => (r.status || "").toUpperCase() === "FAILED");
    const failedEnqueue = rows.filter((r) => (r.status || "") === "ENQUEUE_FAILED").length;
    const cancelled = withJob.filter((r) => (r.status || "").toUpperCase() === "CANCELLED");
    const inFlight = withJob.filter((r) => {
      const s = (r.status || "").toUpperCase();
      return s === "PENDING" || s === "RUNNING" || s === "CANCELLING";
    });
    return {
      created: withJob.length,
      completed: completed.length,
      failed: failedWithJob.length + failedEnqueue,
      cancelled: cancelled.length,
      inFlight: inFlight.length,
    };
  }, [bgSteps]);

  const autoProgress = useMemo(() => {
    const success = autoSteps.filter((s) => s.status === "success").length;
    const err = autoSteps.filter((s) => s.status === "error").length;
    const skipped = autoSteps.filter((s) => s.status === "skipped").length;
    const running = autoSteps.find((s) => s.status === "running");
    const terminal = autoSteps.filter((s) =>
      ["success", "error", "skipped"].includes(s.status)
    ).length;
    const pct = Math.min(100, ((terminal + (running ? 0.2 : 0)) / 5) * 100);
    return { success, err, skipped, running, pct };
  }, [autoSteps]);

  async function loadStats() {
    setStatsLoading(true);
    setStatsError("");
    try {
      const r = await dsApi.getDataSourceFileStats(dataSource.id, { include_deleted: false });
      setStats(r);
    } catch (e) {
      setStats(null);
      setStatsError(getApiErrorMessage(e));
    } finally {
      setStatsLoading(false);
    }
  }

  async function executeAutoPipeline() {
    setAutoRunning(true);
    setAutoSummary(null);
    setAutoSteps(initialAutoSteps());
    const partialWarnings: string[] = [];
    const pipelineT0 = performance.now();
    let aborted = false;
    let failedAutoKey: PipelineAutoStepKey | null = null;
    let failedMessage = "";
    let successCount = 0;

    const bumpAuto = (key: PipelineAutoStepKey, patch: Partial<PipelineAutoStepState>) => {
      setAutoSteps((prev) => prev.map((row) => (row.key === key ? { ...row, ...patch } : row)));
    };

    try {
      for (const stepId of STEPS_ORDER) {
      if (aborted) {
        bumpAuto(STEP_TO_AUTO_KEY[stepId], {
          status: "skipped",
          message: "이전 단계 실패로 실행하지 않았습니다.",
        });
        continue;
      }

      const autoKey = STEP_TO_AUTO_KEY[stepId];
      const startedAt = new Date().toISOString();
      const t0 = performance.now();
      bumpAuto(autoKey, { status: "running", startedAt, finishedAt: undefined, durationMs: undefined, errorMessage: undefined, message: undefined });
      setLoading(stepId);

      try {
        if (stepId === "sync") {
          if (scanScope === "FULL") {
            aborted = true;
            failedAutoKey = autoKey;
            failedMessage =
              "전체 저장소 처리는 백그라운드 파이프라인에서 실행해 주세요. (바로 실행은 제한 모드만 지원합니다.)";
            const durationMs = Math.round(performance.now() - t0);
            bumpAuto(autoKey, {
              status: "error",
              finishedAt: new Date().toISOString(),
              durationMs,
              errorMessage: failedMessage,
            });
            patchSnap("sync", { status: "error", payload: null, error: failedMessage });
            setLastRun({ step: "sync", ok: false });
            continue;
          }
          const lim = buildSyncTreeJobFields();
          const data = await dsApi.syncTree(dataSource.id, {
            start_path: lim.start_path,
            scan_scope: "LIMITED",
            max_depth: lim.max_depth ?? 3,
            max_items: lim.max_items ?? 5000,
            include_hidden: lim.include_hidden,
            apply_exclusions: lim.apply_exclusions,
            detect_deleted: lim.detect_deleted,
          });
          const display = truncatePayload(data);
          const ok = !isTerminalErrorStatus(display.status);
          patchSnap("sync", { status: ok ? "success" : "error", payload: display, error: ok ? "" : String(display.message ?? "") });
          setLastRun({ step: "sync", ok });
          if (String(display.status).toLowerCase() === "partial") {
            partialWarnings.push("WebDAV 동기화가 partial입니다. 일부 폴더만 실패했을 수 있으며 다음 단계는 계속 진행합니다.");
          }
          const durationMs = Math.round(performance.now() - t0);
          const finishedAt = new Date().toISOString();
          if (!ok) {
            aborted = true;
            failedAutoKey = autoKey;
            failedMessage =
              (typeof display.message === "string" && display.message) || "동기화가 실패했습니다.";
            bumpAuto(autoKey, {
              status: "error",
              finishedAt,
              durationMs,
              errorMessage: failedMessage,
            });
            patchSnap("sync", { error: failedMessage });
          } else {
            bumpAuto(autoKey, {
              status: "success",
              finishedAt,
              durationMs,
              message: typeof display.message === "string" ? display.message : undefined,
            });
            successCount += 1;
          }
          continue;
        }

        if (stepId === "text") {
          const data = await dsApi.processPendingText(dataSource.id, {
            limit: textLimit,
            max_file_size_bytes: textMaxFileBytes,
            include_extensions: textIncludeExt.trim() || undefined,
            dry_run: false,
          });
          const display = truncatePayload(data);
          const ok = !isTerminalErrorStatus(display.status);
          patchSnap("text", { status: ok ? "success" : "error", payload: display, error: ok ? "" : String(display.message ?? "") });
          setLastRun({ step: "text", ok });
          if (String(display.status).toLowerCase() === "partial") {
            partialWarnings.push("일반 텍스트 처리 응답이 partial입니다. 다음 단계는 계속 진행합니다.");
          }
          const durationMs = Math.round(performance.now() - t0);
          const finishedAt = new Date().toISOString();
          if (!ok) {
            aborted = true;
            failedAutoKey = autoKey;
            failedMessage =
              (typeof display.message === "string" && display.message) || "텍스트 처리가 실패했습니다.";
            bumpAuto(autoKey, { status: "error", finishedAt, durationMs, errorMessage: failedMessage });
            patchSnap("text", { error: failedMessage });
          } else {
            bumpAuto(autoKey, {
              status: "success",
              finishedAt,
              durationMs,
              message: typeof display.message === "string" ? display.message : undefined,
            });
            successCount += 1;
          }
          continue;
        }

        if (stepId === "doc") {
          const p = docParamsRef.current;
          const include = p?.include_extensions?.trim();
          if (!p || !include) {
            const msg = !p
              ? "문서 처리 폼이 아직 준비되지 않았습니다. 모달을 잠시 연 뒤 다시 시도해 주세요."
              : "처리할 확장자를 하나 이상 선택해 주세요.";
            aborted = true;
            failedAutoKey = autoKey;
            failedMessage = msg;
            applyDocumentSnap(null, msg);
            const durationMs = Math.round(performance.now() - t0);
            bumpAuto(autoKey, {
              status: "error",
              finishedAt: new Date().toISOString(),
              durationMs,
              errorMessage: msg,
            });
            continue;
          }
          const res = await dsApi.processPendingDocuments(dataSource.id, {
            limit: p.limit,
            max_file_size_bytes: p.max_file_size_bytes,
            include_extensions: include,
            dry_run: false,
            reprocess_skipped: p.reprocess_skipped,
          });
          const ok = applyDocumentSnap(res, "");
          const durationMs = Math.round(performance.now() - t0);
          const finishedAt = new Date().toISOString();
          const st = String(res.status ?? "").toLowerCase();
          if (st === "partial") {
            partialWarnings.push("문서 처리 응답이 partial입니다. 다음 단계는 계속 진행합니다.");
          }
          if (!ok) {
            aborted = true;
            failedAutoKey = autoKey;
            failedMessage =
              (typeof res.message === "string" && res.message.trim() !== "" && res.message) ||
              (typeof res.error === "string" && res.error.trim() !== "" && res.error) ||
              "문서 처리가 실패했습니다.";
            bumpAuto(autoKey, { status: "error", finishedAt, durationMs, errorMessage: failedMessage });
          } else {
            bumpAuto(autoKey, {
              status: "success",
              finishedAt,
              durationMs,
              message: typeof res.message === "string" ? res.message : undefined,
            });
            successCount += 1;
          }
          continue;
        }

        if (stepId === "chunk") {
          const data = await dsApi.chunkCompletedText(dataSource.id, {
            limit: chunkLimit,
            chunk_size: chunkSize,
            chunk_overlap: chunkOverlap,
            min_chunk_size: chunkMin,
            reprocess: chunkReprocess,
            dry_run: false,
            include_extensions: chunkIncludeExt.trim() || undefined,
          });
          const display = truncatePayload(data);
          const ok = !isTerminalErrorStatus(display.status);
          patchSnap("chunk", { status: ok ? "success" : "error", payload: display, error: ok ? "" : String(display.message ?? "") });
          setLastRun({ step: "chunk", ok });
          if (String(display.status).toLowerCase() === "partial") {
            partialWarnings.push("Chunk 생성 응답이 partial입니다. 다음 단계는 계속 진행합니다.");
          }
          const durationMs = Math.round(performance.now() - t0);
          const finishedAt = new Date().toISOString();
          if (!ok) {
            aborted = true;
            failedAutoKey = autoKey;
            failedMessage =
              (typeof display.message === "string" && display.message) || "Chunk 생성이 실패했습니다.";
            bumpAuto(autoKey, { status: "error", finishedAt, durationMs, errorMessage: failedMessage });
            patchSnap("chunk", { error: failedMessage });
          } else {
            bumpAuto(autoKey, {
              status: "success",
              finishedAt,
              durationMs,
              message: typeof display.message === "string" ? display.message : undefined,
            });
            successCount += 1;
          }
          continue;
        }

        if (stepId === "embed") {
          const data = await dsApi.embedPendingChunks(dataSource.id, {
            limit: embedLimit,
            batch_size: embedBatch,
            reembed: embedReembed,
            dry_run: false,
            include_extensions: embedIncludeExt.trim() || undefined,
          });
          const display = truncatePayload(data);
          const ok = !isTerminalErrorStatus(display.status);
          patchSnap("embed", { status: ok ? "success" : "error", payload: display, error: ok ? "" : String(display.message ?? "") });
          setLastRun({ step: "embed", ok });
          if (String(display.status).toLowerCase() === "partial") {
            partialWarnings.push("Embedding 생성 응답이 partial입니다.");
          }
          const durationMs = Math.round(performance.now() - t0);
          const finishedAt = new Date().toISOString();
          if (!ok) {
            aborted = true;
            failedAutoKey = autoKey;
            failedMessage =
              (typeof display.message === "string" && display.message) || "Embedding 생성이 실패했습니다.";
            bumpAuto(autoKey, { status: "error", finishedAt, durationMs, errorMessage: failedMessage });
            patchSnap("embed", { error: failedMessage });
          } else {
            bumpAuto(autoKey, {
              status: "success",
              finishedAt,
              durationMs,
              message: typeof display.message === "string" ? display.message : undefined,
            });
            successCount += 1;
          }
        }
      } catch (e) {
        const msg = getApiErrorMessage(e);
        aborted = true;
        failedAutoKey = STEP_TO_AUTO_KEY[stepId];
        failedMessage = msg;
        const durationMs = Math.round(performance.now() - t0);
        const finishedAt = new Date().toISOString();
        bumpAuto(STEP_TO_AUTO_KEY[stepId], {
          status: "error",
          finishedAt,
          durationMs,
          errorMessage: msg,
        });
        patchSnap(stepId, { status: "error", payload: null, error: msg });
        setLastRun({ step: stepId, ok: false });
      } finally {
        setLoading(null);
      }
    }

    const totalMs = Math.round(performance.now() - pipelineT0);
    setAutoSummary({
      ok: !aborted,
      totalMs,
      failedStepLabel: failedAutoKey != null ? AUTO_KEY_TO_LABEL[failedAutoKey] : undefined,
      errorMessage: failedMessage || undefined,
      completedSteps: successCount,
      partialWarnings,
    });
    } finally {
      setAutoRunning(false);
      void onRefreshRef.current();
    }
  }

  return createPortal(
    <>
      <div
        className={docStyles.overlay}
        role="presentation"
        onMouseDown={(e) => {
          if (e.target === e.currentTarget && !closeDisabled) handleModalClose();
        }}
      >
        <div className={docStyles.panel} onMouseDown={(e) => e.stopPropagation()}>
          <SectionCard
            title="검색 반영 작업 실행"
            actions={
              <Button type="button" variant="ghost" size="sm" onClick={handleModalClose} disabled={closeDisabled}>
                닫기
              </Button>
            }
          >
            <InfoBox title={`저장소: ${dataSource.name}`}>
              저장소의 모든 하위 폴더와 파일을 백그라운드에서 수집하고, 문서 내용을 분석해 AI 검색에 반영합니다.
              기본값은 <strong>전체 저장소</strong> 수집이며, 폴더 깊이·항목 수 제한은 고급 설정에서 변경할 수 있습니다.
              텍스트·문서 파일 크기는 서버 설정상 최대 {SERVER_MAX_FILE_MB}MB까지 처리합니다.
            </InfoBox>

            <div className={styles.primaryPanel}>
              <h3 className={styles.primaryPanelTitle}>권장: 전체 검색 반영 작업 등록</h3>
              <p className="muted" style={{ margin: 0, fontSize: "0.85rem" }}>
                브라우저를 닫아도 서버 worker가 순서대로 처리합니다. 진행·취소는{" "}
                <Link to="/admin/jobs">작업 이력</Link>에서 확인하세요.
              </p>

            <div className={styles.execModeRow} role="radiogroup" aria-label="실행 모드" style={{ marginTop: "0.75rem" }}>
              <span style={{ fontWeight: 600, fontSize: "0.9rem" }}>실행 모드</span>
              <label className={styles.check}>
                <input
                  type="radio"
                  name="pipeline-exec-mode"
                  checked={executionMode === "immediate"}
                  onChange={() => setExecutionMode("immediate")}
                  disabled={formDisabled}
                />
                바로 실행
              </label>
              <label className={styles.check}>
                <input
                  type="radio"
                  name="pipeline-exec-mode"
                  checked={executionMode === "background"}
                  onChange={() => setExecutionMode("background")}
                  disabled={formDisabled}
                />
                백그라운드 실행
              </label>
            </div>
            <p className="muted" style={{ fontSize: "0.8rem", marginTop: "0.35rem", marginBottom: 0 }}>
              {executionMode === "immediate" ? (
                <>바로 실행: 현재 브라우저에서 각 단계가 끝날 때까지 기다립니다.</>
              ) : (
                <>
                  백그라운드 실행: 작업을 등록하고 서버가 순서대로 처리합니다. 대량 파일에 권장합니다. 진행 상황은{" "}
                  <Link to="/admin/jobs">작업 목록</Link>에서 확인할 수 있습니다.
                </>
              )}
            </p>

            <div className={styles.primaryCtaRow}>
              {executionMode === "background" ? (
                <>
                  <Button
                    type="button"
                    variant="primary"
                    size="sm"
                    loading={serverPipelineBusy}
                    disabled={disableManualActions}
                    onClick={() => setConfirmServerPipelineOpen(true)}
                  >
                    전체 검색 반영 작업 등록
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={disableManualActions}
                    onClick={() => setConfirmBgAutoOpen(true)}
                  >
                    브라우저에서 순차 등록
                  </Button>
                </>
              ) : (
                <Button
                  type="button"
                  variant="primary"
                  size="sm"
                  disabled={disableManualActions}
                  onClick={() => setConfirmAutoOpen(true)}
                >
                  바로 전체 실행
                </Button>
              )}
            </div>
            {executionMode === "background" && serverPipelineJobId ? (
              <div className="alert alertSuccess" style={{ fontSize: "0.85rem", marginTop: "0.5rem" }}>
                <strong>전체 검색 반영 작업이 등록되었습니다.</strong>
                <p className="muted" style={{ margin: "0.35rem 0 0", fontSize: "0.82rem" }}>
                  진행 상황은 <Link to="/admin/jobs">작업 이력</Link>에서 확인하세요.
                </p>
                <AdvancedSection title="고급 정보" summary="작업 ID">
                  <p className="muted" style={{ margin: 0, fontSize: "0.8rem" }}>
                    작업 ID: <code>{serverPipelineJobId}</code>
                  </p>
                </AdvancedSection>
              </div>
            ) : null}
            {executionMode === "background" && <ErrorMessage message={serverPipelineErr} />}
            </div>

            <AdvancedSection title="실행 옵션·진행 상세" summary="백그라운드 상태, 즉시 실행 진행률, 파일 현황">
            {executionMode === "background" && (
              <div className={styles.bgToolBar}>
                <div className="muted" style={{ fontSize: "0.8rem", display: "flex", flexWrap: "wrap", gap: "0.5rem 1rem" }}>
                  <span>
                    생성된 작업: <strong>{bgSummary.created}</strong>
                  </span>
                  <span>
                    완료: <strong>{bgSummary.completed}</strong>
                  </span>
                  <span>
                    실패: <strong>{bgSummary.failed}</strong>
                  </span>
                  <span>
                    취소: <strong>{bgSummary.cancelled}</strong>
                  </span>
                  <span>
                    대기/실행: <strong>{bgSummary.inFlight}</strong>
                  </span>
                </div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", marginTop: "0.5rem", alignItems: "center" }}>
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    disabled={bgSequentialRunning}
                    onClick={() => void refreshAllBgSteps()}
                  >
                    상태 새로고침
                  </Button>
                  <label className={styles.check}>
                    <input
                      type="checkbox"
                      checked={bgAutoPoll}
                      onChange={(e) => setBgAutoPoll(e.target.checked)}
                      disabled={bgSequentialRunning}
                    />
                    자동 새로고침 (5초)
                  </label>
                </div>
              </div>
            )}

                        {executionMode === "immediate" && autoRunning && (
              <div className={styles.autoProgressWrap}>
                <div className={styles.autoProgressMeta}>
                  <span>
                    <strong>{autoProgress.success}</strong> / 5 단계 완료
                  </span>
                  {autoProgress.running && (
                    <span>
                      현재 실행 중: <strong>{autoProgress.running.label}</strong>
                    </span>
                  )}
                  <span>실패: {autoProgress.err}</span>
                  <span>건너뜀: {autoProgress.skipped}</span>
                </div>
                <div className={styles.progressTrack} aria-hidden>
                  <div className={styles.progressFill} style={{ width: `${autoProgress.pct}%` }} />
                </div>
              </div>
            )}

            {executionMode === "immediate" && autoSummary && (
              <div
                className={autoSummary.ok ? "alert alertSuccess" : "alert alertDanger"}
                style={{ marginTop: "0.65rem" }}
              >
                {autoSummary.ok ? (
                  <>
                    <strong>전체 파이프라인 실행이 완료되었습니다.</strong>
                    <div className="muted" style={{ marginTop: "0.35rem", fontSize: "0.875rem" }}>
                      완료 단계: {autoSummary.completedSteps} / 5 · 총 소요 시간 {formatDuration(autoSummary.totalMs)}
                    </div>
                  </>
                ) : (
                  <>
                    <strong>파이프라인 실행 중 오류가 발생했습니다.</strong>
                    <div className="muted" style={{ marginTop: "0.35rem", fontSize: "0.875rem" }}>
                      실패 단계: {autoSummary.failedStepLabel ?? "—"}
                      {autoSummary.errorMessage ? ` — ${autoSummary.errorMessage}` : ""}
                    </div>
                    <div className="muted" style={{ marginTop: "0.25rem", fontSize: "0.875rem" }}>
                      이후 단계는 실행되지 않았습니다.
                    </div>
                  </>
                )}
                {autoSummary.partialWarnings.length > 0 && (
                  <ul style={{ margin: "0.5rem 0 0", paddingLeft: "1.1rem", fontSize: "0.85rem" }}>
                    {autoSummary.partialWarnings.map((w) => (
                      <li key={w}>{w}</li>
                    ))}
                  </ul>
                )}
              </div>
            )}

            {executionMode === "immediate" && (autoRunning || autoSteps.some((s) => s.status !== "idle")) && (
              <div className={styles.autoStepGrid} style={{ marginTop: "0.65rem" }}>
                {autoSteps.map((row) => (
                  <div key={row.key} className={styles.autoStepCard}>
                    <div style={{ display: "flex", justifyContent: "space-between", gap: "0.5rem", alignItems: "center" }}>
                      <strong style={{ fontSize: "0.85rem" }}>{row.label}</strong>
                      <Badge
                        variant={
                          row.status === "success"
                            ? "success"
                            : row.status === "error"
                              ? "danger"
                              : row.status === "running"
                                ? "primary"
                                : row.status === "skipped"
                                  ? "neutral"
                                  : "neutral"
                        }
                      >
                        {row.status === "idle"
                          ? "대기"
                          : row.status === "running"
                            ? "실행 중"
                            : row.status === "success"
                              ? "성공"
                              : row.status === "error"
                                ? "실패"
                                : "건너뜀"}
                      </Badge>
                    </div>
                    {row.startedAt && (
                      <div className="muted" style={{ fontSize: "0.75rem", marginTop: "0.35rem" }}>
                        시작 {formatDateTime(row.startedAt)}
                        {row.finishedAt ? ` · 종료 ${formatDateTime(row.finishedAt)}` : ""}
                        {row.durationMs != null ? ` · 소요 ${formatDuration(row.durationMs)}` : ""}
                      </div>
                    )}
                    {row.message && <p className="muted" style={{ fontSize: "0.75rem", marginBottom: 0 }}>{row.message}</p>}
                    {row.errorMessage && <ErrorMessage message={row.errorMessage} />}
                  </div>
                ))}
              </div>
            )}

            <div className={styles.summaryBar}>
              <span>
                마지막 단계: <strong>{summary.lastLabel}</strong>
              </span>
              <span>
                마지막 결과:{" "}
                <Badge variant={summary.lastOk === "성공" ? "success" : summary.lastOk === "실패" ? "danger" : "neutral"}>
                  {summary.lastOk}
                </Badge>
              </span>
              <span>완료 단계: {summary.completed}</span>
              <span>실패 단계: {summary.failed}</span>
            </div>

            <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", marginTop: "0.75rem" }}>
              <Button type="button" variant="secondary" size="sm" loading={statsLoading} onClick={() => void loadStats()}>
                현재 파일 현황 보기
              </Button>
              <Link to="/admin/file-stats" className="btn btnSecondary btnSm">
                파일 통계 페이지
              </Link>
            </div>
            <p className="muted" style={{ fontSize: "0.8rem", marginTop: "0.5rem", marginBottom: 0 }}>
              파이프라인 실행 후 데이터 소스 목록을 반영하려면 상단 <strong>목록 새로고침</strong>을 눌러 주세요.
            </p>
            <ErrorMessage message={statsError} />
            {stats && (
              <p className="muted" style={{ fontSize: "0.85rem", marginBottom: 0 }}>
                파일 {formatInt(stats.summary.total_files)} · 완료{" "}
                {formatInt(stats.by_analysis_status.find((x) => x.status === "COMPLETED")?.count ?? 0)} · 스킵{" "}
                {formatInt(stats.by_analysis_status.find((x) => x.status === "SKIPPED")?.count ?? 0)}
              </p>
            )}
            </AdvancedSection>
          </SectionCard>

          <div className={styles.stepSection}>
            <h3 className={styles.stepSectionTitle}>단계별 실행</h3>
            <p className="muted" style={{ margin: "0 0 0.5rem", fontSize: "0.85rem" }}>
              필요한 단계만 펼쳐 실행하세요. 대량 작업 전에는 <strong>대상 확인</strong>을 권장합니다.
            </p>
          <div className={styles.accordion}>
            <PipelineStepAccordion
              stepId="sync"
              stepIndex={1}
              open={openStep === "sync"}
              onToggle={() => setOpenStep((s) => (s === "sync" ? null : "sync"))}
              snap={snap.sync}
              bgStep={executionMode === "background" ? bgSteps.sync : undefined}
              executionMode={executionMode}
            >
              <AdvancedSection title="고급 설정" summary="수집 범위·폴더 깊이·항목 수·숨김 파일 등">
              <div className="formGrid" style={{ maxWidth: 640 }}>
                <FormField label="시작 폴더">
                  <Input value={startPath} onChange={(e) => setStartPath(e.target.value)} disabled={formDisabled} />
                </FormField>
                <fieldset style={{ border: "none", padding: 0, margin: 0 }}>
                  <legend style={{ fontWeight: 600, fontSize: "0.85rem", marginBottom: "0.35rem" }}>
                    실행 범위 (파일 목록 수집)
                  </legend>
                  <label className={styles.check}>
                    <input
                      type="radio"
                      name="pipeline-scan-scope"
                      checked={scanScope === "FULL"}
                      onChange={() => setScanScope("FULL")}
                      disabled={formDisabled}
                    />
                    전체 저장소 처리
                  </label>
                  <label className={styles.check}>
                    <input
                      type="radio"
                      name="pipeline-scan-scope"
                      checked={scanScope === "LIMITED"}
                      onChange={() => setScanScope("LIMITED")}
                      disabled={formDisabled}
                    />
                    제한 설정 직접 지정
                  </label>
                  {scanScope === "FULL" ? (
                    <p className="muted" style={{ fontSize: "0.8rem", margin: "0.35rem 0 0" }}>
                      모든 하위 폴더를 탐색합니다. 파일 수가 많으면 오래 걸릴 수 있으며, 작업 이력에서 진행 상태를
                      확인할 수 있습니다. 바로 실행(동기 API)은 사용할 수 없습니다.
                    </p>
                  ) : null}
                </fieldset>
                {scanScope === "LIMITED" ? (
                  <>
                    <FormField label="최대 폴더 깊이">
                      <Input
                        type="number"
                        value={maxDepth}
                        onChange={(e) => setMaxDepth(Number(e.target.value) || 0)}
                        min={0}
                        max={20}
                        disabled={formDisabled}
                      />
                    </FormField>
                    <FormField label="최대 항목 수">
                      <Input
                        type="number"
                        value={maxItems}
                        onChange={(e) => setMaxItems(Number(e.target.value) || 1)}
                        min={1}
                        max={50000}
                        disabled={formDisabled}
                      />
                    </FormField>
                  </>
                ) : (
                  <>
                    <FormField label="최대 폴더 깊이">
                      <Input value="제한 없음" disabled readOnly />
                    </FormField>
                    <FormField label="최대 항목 수">
                      <Input value="제한 없음" disabled readOnly />
                    </FormField>
                  </>
                )}
                <label className={styles.check}>
                  <input
                    type="checkbox"
                    checked={includeHidden}
                    onChange={(e) => setIncludeHidden(e.target.checked)}
                    disabled={formDisabled}
                  />
                  숨김 파일 포함
                </label>
                <label className={styles.check}>
                  <input
                    type="checkbox"
                    checked={applyExclusions}
                    onChange={(e) => setApplyExclusions(e.target.checked)}
                    disabled={formDisabled}
                  />
                  제외 규칙 적용
                </label>
                <label className={styles.check}>
                  <input
                    type="checkbox"
                    checked={detectDeleted}
                    onChange={(e) => setDetectDeleted(e.target.checked)}
                    disabled={formDisabled}
                  />
                  삭제된 파일 감지
                </label>
              </div>
              </AdvancedSection>
              {executionMode === "immediate" ? (
                <Button
                  type="button"
                  variant="primary"
                  size="sm"
                  style={{ marginTop: "0.65rem" }}
                  loading={loading === "sync"}
                  disabled={(disableManualActions && loading !== "sync") || scanScope === "FULL"}
                  title={
                    scanScope === "FULL"
                      ? "전체 저장소 처리는 백그라운드 파이프라인에서 실행해 주세요."
                      : undefined
                  }
                  onClick={() =>
                    requestConfirm(() =>
                      runWithLoading("sync", () => {
                        const lim = buildSyncTreeJobFields();
                        return dsApi.syncTree(dataSource.id, {
                          start_path: lim.start_path,
                          scan_scope: "LIMITED",
                          max_depth: lim.max_depth ?? 3,
                          max_items: lim.max_items ?? 5000,
                          include_hidden: lim.include_hidden,
                          apply_exclusions: lim.apply_exclusions,
                          detect_deleted: lim.detect_deleted,
                        });
                      })
                    )
                  }
                >
                  파일 목록 수집 실행
                </Button>
              ) : (
                <Button
                  type="button"
                  variant="primary"
                  size="sm"
                  style={{ marginTop: "0.65rem" }}
                  loading={bgEnqueueStep === "sync"}
                  disabled={disableManualActions && bgEnqueueStep !== "sync"}
                  onClick={() => void handleBgEnqueue("sync")}
                >
                  파일 목록 수집 작업 등록
                </Button>
              )}
              {executionMode === "background" && (
                <BackgroundJobSection
                  step={bgSteps.sync}
                  onRefresh={() => void refreshBgStep("sync")}
                  onRequestCancel={() => setBgCancelDialogStep("sync")}
                  cancelInFlight={bgCancelBusy}
                />
              )}
              <StepResultBlock snap={snap.sync} />
            </PipelineStepAccordion>

            <PipelineStepAccordion
              stepId="text"
              stepIndex={2}
              open={openStep === "text"}
              onToggle={() => setOpenStep((s) => (s === "text" ? null : "text"))}
              snap={snap.text}
              bgStep={executionMode === "background" ? bgSteps.text : undefined}
              executionMode={executionMode}
            >
              <AdvancedSection title="고급 설정" summary="처리 건수·파일 크기·확장자">
              <div className="formGrid" style={{ maxWidth: 640 }}>
                <FormField label="처리할 파일 수" hint="0 = 전체">
                  <Select
                    value={String(textLimit)}
                    onChange={(e) => setTextLimit(Number(e.target.value))}
                    disabled={formDisabled}
                  >
                    {[0, 10, 20, 50, 100, 200, 500, 1000, 5000].map((n) => (
                      <option key={n} value={n}>
                        {n === 0 ? "전체" : n}
                      </option>
                    ))}
                  </Select>
                </FormField>
                <FormField
                  label="최대 파일 크기"
                  hint={`서버 설정상 최대 ${SERVER_MAX_FILE_MB}MB까지 처리합니다.`}
                >
                  <label className={styles.check}>
                    <input
                      type="radio"
                      name="pipeline-text-size"
                      checked={textUseServerMax}
                      onChange={() => setTextUseServerMax(true)}
                      disabled={formDisabled}
                    />
                    서버 허용 최대 크기까지 ({SERVER_MAX_FILE_MB} MB)
                  </label>
                  <label className={styles.check}>
                    <input
                      type="radio"
                      name="pipeline-text-size"
                      checked={!textUseServerMax}
                      onChange={() => setTextUseServerMax(false)}
                      disabled={formDisabled}
                    />
                    직접 지정
                  </label>
                  {!textUseServerMax ? (
                    <Select
                      value={String(textMaxMb)}
                      onChange={(e) => setTextMaxMb(Number(e.target.value))}
                      disabled={formDisabled}
                    >
                      {[1, 2, 5, 10, 20, 50, 100, SERVER_MAX_FILE_MB].map((n) => (
                        <option key={n} value={n}>
                          {n} MB
                        </option>
                      ))}
                    </Select>
                  ) : null}
                </FormField>
                <FormField label="대상 확장자" hint="쉼표로 구분. 비우면 전체 허용">
                  <Input value={textIncludeExt} onChange={(e) => setTextIncludeExt(e.target.value)} disabled={formDisabled} />
                </FormField>
              </div>
              </AdvancedSection>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", marginTop: "0.65rem" }}>
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  loading={loading === "text"}
                  disabled={disableManualActions && loading !== "text"}
                  onClick={() =>
                    void runWithLoading("text", () =>
                      dsApi.processPendingText(dataSource.id, {
                        limit: textLimit,
                        max_file_size_bytes: textMaxFileBytes,
                        include_extensions: textIncludeExt.trim() || undefined,
                        dry_run: true,
                      })
                    )
                  }
                >
                  대상 확인
                </Button>
                {executionMode === "immediate" ? (
                  <Button
                    type="button"
                    variant="primary"
                    size="sm"
                    loading={loading === "text"}
                    disabled={disableManualActions && loading !== "text"}
                    onClick={() =>
                      requestConfirm(() =>
                        runWithLoading("text", () =>
                          dsApi.processPendingText(dataSource.id, {
                            limit: textLimit,
                            max_file_size_bytes: textMaxFileBytes,
                            include_extensions: textIncludeExt.trim() || undefined,
                            dry_run: false,
                          })
                        )
                      )
                    }
                  >
                    실제 실행
                  </Button>
                ) : (
                  <Button
                    type="button"
                    variant="primary"
                    size="sm"
                    loading={bgEnqueueStep === "text"}
                    disabled={disableManualActions && bgEnqueueStep !== "text"}
                    onClick={() => void handleBgEnqueue("text")}
                  >
                    텍스트 추출 작업 등록
                  </Button>
                )}
              </div>
              {executionMode === "background" && (
                <BackgroundJobSection
                  step={bgSteps.text}
                  onRefresh={() => void refreshBgStep("text")}
                  onRequestCancel={() => setBgCancelDialogStep("text")}
                  cancelInFlight={bgCancelBusy}
                />
              )}
              <StepResultBlock snap={snap.text} />
            </PipelineStepAccordion>

            <PipelineStepAccordion
              stepId="doc"
              stepIndex={3}
              open={openStep === "doc"}
              onToggle={() => setOpenStep((s) => (s === "doc" ? null : "doc"))}
              snap={snap.doc}
              bgStep={executionMode === "background" ? bgSteps.doc : undefined}
              executionMode={executionMode}
            >
              <DocumentProcessingPanel
                dataSourceId={dataSource.id}
                dataSourceName={dataSource.name}
                showIntroBullets={false}
                showFollowUpChunkEmbed={false}
                embedResultInParent
                onDocumentApiOutcome={handleDocOutcome}
                onRunComplete={onRefresh}
                onDocumentParamsSnapshot={onDocumentParamsSnapshot}
                disableRunButtons={disableManualActions}
                suppressDocumentRealRun={executionMode === "background"}
                defaultMaxFileBytes={SERVER_MAX_FILE_BYTES}
              />
              {executionMode === "background" && (
                <>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", marginTop: "0.65rem" }}>
                    <Button
                      type="button"
                      variant="primary"
                      size="sm"
                      loading={bgEnqueueStep === "doc"}
                      disabled={disableManualActions && bgEnqueueStep !== "doc"}
                      onClick={() => void handleBgEnqueue("doc")}
                    >
                      문서 추출 작업 등록
                    </Button>
                  </div>
                  <BackgroundJobSection
                    step={bgSteps.doc}
                    onRefresh={() => void refreshBgStep("doc")}
                    onRequestCancel={() => setBgCancelDialogStep("doc")}
                    cancelInFlight={bgCancelBusy}
                  />
                </>
              )}
              <StepResultBlock snap={snap.doc} />
            </PipelineStepAccordion>

            <PipelineStepAccordion
              stepId="chunk"
              stepIndex={4}
              open={openStep === "chunk"}
              onToggle={() => setOpenStep((s) => (s === "chunk" ? null : "chunk"))}
              snap={snap.chunk}
              bgStep={executionMode === "background" ? bgSteps.chunk : undefined}
              executionMode={executionMode}
            >
              <AdvancedSection title="고급 설정" summary="단위 크기·겹침·재처리">
              <div className="formGrid" style={{ maxWidth: 640 }}>
                <FormField label="처리할 파일 수" hint="0 = 전체">
                  <Select
                    value={String(chunkLimit)}
                    onChange={(e) => setChunkLimit(Number(e.target.value))}
                    disabled={formDisabled}
                  >
                    {[0, 20, 50, 100, 200, 500, 1000, 5000].map((n) => (
                      <option key={n} value={n}>
                        {n === 0 ? "전체" : n}
                      </option>
                    ))}
                  </Select>
                </FormField>
                <FormField label="검색 단위 크기">
                  <Input
                    type="number"
                    value={chunkSize}
                    onChange={(e) => setChunkSize(Number(e.target.value) || 200)}
                    disabled={formDisabled}
                  />
                </FormField>
                <FormField label="단위 겹침">
                  <Input
                    type="number"
                    value={chunkOverlap}
                    onChange={(e) => setChunkOverlap(Number(e.target.value) || 0)}
                    disabled={formDisabled}
                  />
                </FormField>
                <FormField label="최소 단위 크기">
                  <Input
                    type="number"
                    value={chunkMin}
                    onChange={(e) => setChunkMin(Number(e.target.value) || 0)}
                    disabled={formDisabled}
                  />
                </FormField>
                <label className={styles.check}>
                  <input
                    type="checkbox"
                    checked={chunkReprocess}
                    onChange={(e) => setChunkReprocess(e.target.checked)}
                    disabled={formDisabled}
                  />
                  기존 결과 다시 만들기
                </label>
                <FormField label="대상 확장자" hint="선택">
                  <Input
                    value={chunkIncludeExt}
                    onChange={(e) => setChunkIncludeExt(e.target.value)}
                    placeholder="비우면 필터 없음"
                    disabled={formDisabled}
                  />
                </FormField>
              </div>
              </AdvancedSection>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", marginTop: "0.65rem" }}>
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  loading={loading === "chunk"}
                  disabled={disableManualActions && loading !== "chunk"}
                  onClick={() =>
                    void runWithLoading("chunk", () =>
                      dsApi.chunkCompletedText(dataSource.id, {
                        limit: chunkLimit,
                        chunk_size: chunkSize,
                        chunk_overlap: chunkOverlap,
                        min_chunk_size: chunkMin,
                        reprocess: chunkReprocess,
                        dry_run: true,
                        include_extensions: chunkIncludeExt.trim() || undefined,
                      })
                    )
                  }
                >
                  대상 확인
                </Button>
                {executionMode === "immediate" ? (
                  <Button
                    type="button"
                    variant="primary"
                    size="sm"
                    loading={loading === "chunk"}
                    disabled={disableManualActions && loading !== "chunk"}
                    onClick={() =>
                      requestConfirm(() =>
                        runWithLoading("chunk", () =>
                          dsApi.chunkCompletedText(dataSource.id, {
                            limit: chunkLimit,
                            chunk_size: chunkSize,
                            chunk_overlap: chunkOverlap,
                            min_chunk_size: chunkMin,
                            reprocess: chunkReprocess,
                            dry_run: false,
                            include_extensions: chunkIncludeExt.trim() || undefined,
                          })
                        )
                      )
                    }
                  >
                    실제 실행
                  </Button>
                ) : (
                  <Button
                    type="button"
                    variant="primary"
                    size="sm"
                    loading={bgEnqueueStep === "chunk"}
                    disabled={disableManualActions && bgEnqueueStep !== "chunk"}
                    onClick={() => void handleBgEnqueue("chunk")}
                  >
                    검색 단위 생성 작업 등록
                  </Button>
                )}
              </div>
              {executionMode === "background" && (
                <BackgroundJobSection
                  step={bgSteps.chunk}
                  onRefresh={() => void refreshBgStep("chunk")}
                  onRequestCancel={() => setBgCancelDialogStep("chunk")}
                  cancelInFlight={bgCancelBusy}
                />
              )}
              <StepResultBlock snap={snap.chunk} />
            </PipelineStepAccordion>

            <PipelineStepAccordion
              stepId="embed"
              stepIndex={5}
              open={openStep === "embed"}
              onToggle={() => setOpenStep((s) => (s === "embed" ? null : "embed"))}
              snap={snap.embed}
              bgStep={executionMode === "background" ? bgSteps.embed : undefined}
              executionMode={executionMode}
            >
              <AdvancedSection title="고급 설정" summary="배치 크기·재인덱싱·확장자">
              <div className="formGrid" style={{ maxWidth: 640 }}>
                <FormField label="처리할 단위 수" hint="0 = 전체">
                  <Select
                    value={String(embedLimit)}
                    onChange={(e) => setEmbedLimit(Number(e.target.value))}
                    disabled={formDisabled}
                  >
                    {[0, 100, 200, 500, 1000, 2000, 5000, 10000].map((n) => (
                      <option key={n} value={n}>
                        {n === 0 ? "전체" : n}
                      </option>
                    ))}
                  </Select>
                </FormField>
                <FormField label="배치 크기">
                  <Input
                    type="number"
                    value={embedBatch}
                    onChange={(e) => setEmbedBatch(Number(e.target.value) || 1)}
                    min={1}
                    max={128}
                    disabled={formDisabled}
                  />
                </FormField>
                <label className={styles.check}>
                  <input
                    type="checkbox"
                    checked={embedReembed}
                    onChange={(e) => setEmbedReembed(e.target.checked)}
                    disabled={formDisabled}
                  />
                  기존 인덱스 다시 만들기
                </label>
                <FormField label="대상 확장자" hint="선택">
                  <Input value={embedIncludeExt} onChange={(e) => setEmbedIncludeExt(e.target.value)} disabled={formDisabled} />
                </FormField>
              </div>
              </AdvancedSection>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", marginTop: "0.65rem" }}>
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  loading={loading === "embed"}
                  disabled={disableManualActions && loading !== "embed"}
                  onClick={() =>
                    void runWithLoading("embed", () =>
                      dsApi.embedPendingChunks(dataSource.id, {
                        limit: embedLimit,
                        batch_size: embedBatch,
                        reembed: embedReembed,
                        dry_run: true,
                        include_extensions: embedIncludeExt.trim() || undefined,
                      })
                    )
                  }
                >
                  대상 확인
                </Button>
                {executionMode === "immediate" ? (
                  <Button
                    type="button"
                    variant="primary"
                    size="sm"
                    loading={loading === "embed"}
                    disabled={disableManualActions && loading !== "embed"}
                    onClick={() =>
                      requestConfirm(() =>
                        runWithLoading("embed", () =>
                          dsApi.embedPendingChunks(dataSource.id, {
                            limit: embedLimit,
                            batch_size: embedBatch,
                            reembed: embedReembed,
                            dry_run: false,
                            include_extensions: embedIncludeExt.trim() || undefined,
                          })
                        )
                      )
                    }
                  >
                    실제 실행
                  </Button>
                ) : (
                  <Button
                    type="button"
                    variant="primary"
                    size="sm"
                    loading={bgEnqueueStep === "embed"}
                    disabled={disableManualActions && bgEnqueueStep !== "embed"}
                    onClick={() => void handleBgEnqueue("embed")}
                  >
                    검색 인덱스 생성 작업 등록
                  </Button>
                )}
              </div>
              {executionMode === "background" && (
                <BackgroundJobSection
                  step={bgSteps.embed}
                  onRefresh={() => void refreshBgStep("embed")}
                  onRequestCancel={() => setBgCancelDialogStep("embed")}
                  cancelInFlight={bgCancelBusy}
                />
              )}
              <StepResultBlock snap={snap.embed} />
            </PipelineStepAccordion>
          </div>
          </div>
        </div>
      </div>

      <ConfirmDialog
        open={confirmOpen}
        title="실제 실행"
        message={CONFIRM_MSG}
        confirmLabel="계속"
        cancelLabel="취소"
        onCancel={() => {
          setConfirmOpen(false);
          setPendingRun(null);
        }}
        onConfirm={onConfirmExec}
      />

      <ConfirmDialog
        open={confirmAutoOpen}
        title="바로 전체 실행"
        message={AUTO_CONFIRM_MSG}
        confirmLabel="계속"
        cancelLabel="취소"
        onCancel={() => setConfirmAutoOpen(false)}
        onConfirm={() => {
          setConfirmAutoOpen(false);
          void executeAutoPipeline();
        }}
      />

      <ConfirmDialog
        open={confirmBgAutoOpen}
        title="브라우저에서 순차 등록"
        message={BG_AUTO_CONFIRM_MSG}
        confirmLabel="계속"
        cancelLabel="취소"
        onCancel={() => setConfirmBgAutoOpen(false)}
        onConfirm={() => {
          setConfirmBgAutoOpen(false);
          void executeBackgroundAutoPipeline();
        }}
      />

      <ConfirmDialog
        open={confirmServerPipelineOpen}
        title="전체 작업 등록"
        message={SERVER_PIPELINE_CONFIRM_MSG}
        confirmLabel="계속"
        cancelLabel="취소"
        onCancel={() => setConfirmServerPipelineOpen(false)}
        onConfirm={() => {
          setConfirmServerPipelineOpen(false);
          void executeServerPipelineJob();
        }}
      />

      <ConfirmDialog
        open={bgCancelDialogStep !== null}
        title="작업 취소"
        message="이 작업에 취소 요청을 보냅니다. 실행 중인 작업은 다음 안전 지점에서 중단됩니다. 계속하시겠습니까?"
        confirmLabel="계속"
        cancelLabel="취소"
        onCancel={() => setBgCancelDialogStep(null)}
        onConfirm={() => {
          void confirmBgStepCancel();
        }}
      />
    </>,
    document.body
  );
}



function stepSnapBadge(snap: StepSnap): ReactNode {
  if (snap.status === "idle") return null;
  const label =
    snap.status === "success"
      ? "완료"
      : snap.status === "error"
        ? "실패"
        : snap.status === "loading"
          ? "처리 중"
          : snap.status;
  const variant =
    snap.status === "success"
      ? "success"
      : snap.status === "error"
        ? "danger"
        : snap.status === "loading"
          ? "primary"
          : "neutral";
  return <Badge variant={variant}>{label}</Badge>;
}

function bgStepStatusBadge(status: string | undefined): ReactNode {
  const u = (status || "").toUpperCase();
  if (!u) return null;
  return <Badge variant={getJobStatusBadgeVariant(u)}>{getJobStatusLabel(u)}</Badge>;
}

function PipelineStepAccordion({
  stepId,
  stepIndex,
  open,
  onToggle,
  snap,
  bgStep,
  executionMode,
  children,
}: {
  stepId: StepId;
  stepIndex: number;
  open: boolean;
  onToggle: () => void;
  snap: StepSnap;
  bgStep?: BackgroundPipelineStepState;
  executionMode: ExecutionMode;
  children: ReactNode;
}) {
  const desc = PIPELINE_STEP_DESCRIPTIONS[STEP_DESC_KEY[stepId]];
  return (
    <div className={styles.accordionItem}>
      <button
        type="button"
        className={`${styles.accordionHead} ${open ? styles.accordionHeadOpen : ""}`}
        onClick={onToggle}
        aria-expanded={open}
      >
        <span className={styles.stepNum}>{stepIndex}</span>
        <span className={styles.stepHeadText}>
          <strong>{STEP_LABEL[stepId]}</strong>
          <span className={styles.stepHeadDesc}>{desc}</span>
        </span>
        <span className={styles.accordionHeadRight}>
          {stepSnapBadge(snap)}
          {executionMode === "background" && bgStep ? bgStepStatusBadge(bgStep.status) : null}
          <span className={styles.chevron} aria-hidden>
            {open ? "▲" : "▼"}
          </span>
        </span>
      </button>
      {open ? <div className={styles.accordionBody}>{children}</div> : null}
    </div>
  );
}

function cancelJobButtonLabel(status: string | undefined): string {
  const u = (status || "").toUpperCase();
  if (u === "CANCELLING") return "취소 요청 중";
  if (u === "PENDING") return "취소";
  return "취소 요청";
}

function BackgroundJobSection({
  step,
  onRefresh,
  onRequestCancel,
  cancelInFlight,
}: {
  step: BackgroundPipelineStepState;
  onRefresh: () => void;
  onRequestCancel: () => void;
  cancelInFlight: boolean;
}) {
  const st = (step.status || "").toUpperCase();
  const showCard =
    Boolean(step.jobId) || st === "ENQUEUE_FAILED" || Boolean(step.enqueueMessage && !step.jobId);
  if (!showCard) return null;

  return (
    <div className={styles.bgJobCard}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", alignItems: "center" }}>
        <strong style={{ fontSize: "0.85rem" }}>백그라운드 Job</strong>
        <Link to="/admin/jobs" className="btn btnSecondary btnSm">
          작업 목록 (/admin/jobs)
        </Link>
        {step.jobId && (
          <Button type="button" variant="ghost" size="sm" onClick={onRefresh}>
            이 단계만 새로고침
          </Button>
        )}
      </div>
      {step.enqueueMessage && (
        <p className="muted" style={{ fontSize: "0.78rem", marginTop: "0.35rem", marginBottom: 0 }}>
          {step.enqueueMessage}
        </p>
      )}
      {step.jobId && (
        <>
          <div style={{ marginTop: "0.35rem", display: "flex", flexWrap: "wrap", gap: "0.5rem", alignItems: "center" }}>
            <span className="muted" style={{ fontSize: "0.78rem" }}>
              Job ID: <code style={{ fontSize: "0.78rem" }}>{step.jobId}</code>
            </span>
            {step.jobType && (
              <span className="muted" style={{ fontSize: "0.75rem" }}>
                {getJobTypeLabel(step.jobType)} ({step.jobType})
              </span>
            )}
            {step.status && <Badge variant={getJobStatusBadgeVariant(step.status)}>{step.status}</Badge>}
          </div>
          {((step.totalFiles ?? 0) > 0 || step.progressPercent != null) && (
            <div style={{ marginTop: "0.35rem" }}>
              <ProgressBar percent={step.progressPercent} height={6} maxWidth="100%" showLabel animate />
              <div className="muted" style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem 1rem", marginTop: "0.25rem", fontSize: "0.75rem" }}>
                <span>처리 {step.processedFiles ?? 0}/{step.totalFiles ?? 0}</span>
                <span>완료 {step.completedFiles ?? 0}</span>
                {(step.failedFiles ?? 0) > 0 && <span style={{ color: "var(--color-danger, #dc2626)" }}>실패 {step.failedFiles}</span>}
                {(step.skippedFiles ?? 0) > 0 && <span>건너뜀 {step.skippedFiles}</span>}
              </div>
              {st === "RUNNING" && step.currentFilePath && (
                <div className="muted" style={{ marginTop: "0.2rem", fontSize: "0.72rem", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={step.currentFilePath}>
                  현재 파일: {step.currentFilePath}
                </div>
              )}
            </div>
          )}
          <div className={styles.bgJobMeta}>
            <div>
              <span className="muted">heartbeat</span> {step.heartbeatAt ? formatRelativeTime(step.heartbeatAt) : "—"}
            </div>
            <div>
              <span className="muted">시작</span> {step.startedAt ? formatDateTime(step.startedAt) : "—"}
            </div>
            <div>
              <span className="muted">종료</span> {step.finishedAt ? formatDateTime(step.finishedAt) : "—"}
            </div>
            <div>
              <span className="muted">worker</span> {step.workerId ?? "—"}
            </div>
          </div>
          {step.errorMessage ? <ErrorMessage message={step.errorMessage} /> : null}
          {canShowJobCancelButton(step.status) && (
            <div style={{ marginTop: "0.5rem" }}>
              <Button
                type="button"
                variant="secondary"
                size="sm"
                disabled={cancelInFlight || st === "CANCELLING"}
                onClick={onRequestCancel}
              >
                {cancelJobButtonLabel(step.status)}
              </Button>
            </div>
          )}
        </>
      )}
      {!step.jobId && st === "ENQUEUE_FAILED" && step.errorMessage ? <ErrorMessage message={step.errorMessage} /> : null}
    </div>
  );
}

function StepResultBlock({ snap }: { snap: StepSnap }) {
  if (snap.status === "idle" && !snap.payload && !snap.error) return null;
  return (
    <div style={{ marginTop: "0.65rem" }}>
      {snap.status === "loading" && <p className="muted">실행 중…</p>}
      <ErrorMessage message={snap.error} />
      {snap.payload && <PipelineResponseView data={snap.payload} />}
    </div>
  );
}
