import { createPortal } from "react-dom";
import { useCallback, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import * as dsApi from "@/api/dataSourceApi";
import { getApiErrorMessage } from "@/api/httpClient";
import { ErrorMessage } from "@/components/ErrorMessage";
import {
  Badge,
  Button,
  ConfirmDialog,
  FormField,
  Input,
  SectionCard,
  Select,
} from "@/components/ui";
import type { DataSource } from "@/types/dataSource";
import type { DocumentProcessResponse } from "@/types/documentProcessing";
import type { FileStatsResponse } from "@/types/file";
import type {
  PipelineAutoStepKey,
  PipelineAutoStepState,
  PipelineStepStatus,
} from "@/types/pipeline";
import { formatDateTime, formatDuration, formatInt } from "@/utils/format";
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
  sync: "1. WebDAV 재귀 동기화",
  text: "2. 일반 텍스트 파일 처리",
  doc: "3. 문서 파일 처리",
  chunk: "4. Chunk 생성",
  embed: "5. Embedding 생성",
};

const STEP_TO_AUTO_KEY: Record<StepId, PipelineAutoStepKey> = {
  sync: "sync",
  text: "text",
  doc: "document",
  chunk: "chunk",
  embed: "embedding",
};

const STEPS_ORDER: StepId[] = ["sync", "text", "doc", "chunk", "embed"];

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
  sync: "WebDAV 재귀 동기화",
  text: "일반 텍스트 처리",
  document: "문서 파일 처리",
  chunk: "Chunk 생성",
  embedding: "Embedding 생성",
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

  const docParamsRef = useRef<DocumentPipelineFormSnapshot | null>(null);
  const onRefreshRef = useRef(onRefresh);
  onRefreshRef.current = onRefresh;

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
  const [maxDepth, setMaxDepth] = useState(3);
  const [maxItems, setMaxItems] = useState(5000);
  const [includeHidden, setIncludeHidden] = useState(false);
  const [applyExclusions, setApplyExclusions] = useState(true);
  const [detectDeleted, setDetectDeleted] = useState(false);

  const [textLimit, setTextLimit] = useState(100);
  const [textMaxMb, setTextMaxMb] = useState(5);
  const [textIncludeExt, setTextIncludeExt] = useState("txt,md,py,java,sql,json,yml");

  const [chunkLimit, setChunkLimit] = useState(100);
  const [chunkSize, setChunkSize] = useState(1200);
  const [chunkOverlap, setChunkOverlap] = useState(200);
  const [chunkMin, setChunkMin] = useState(100);
  const [chunkReprocess, setChunkReprocess] = useState(false);
  const [chunkIncludeExt, setChunkIncludeExt] = useState("");

  const [embedLimit, setEmbedLimit] = useState(500);
  const [embedBatch, setEmbedBatch] = useState(32);
  const [embedReembed, setEmbedReembed] = useState(false);
  const [embedIncludeExt, setEmbedIncludeExt] = useState("");

  const disableManualActions = autoRunning || loading !== null;
  const formDisabled = autoRunning;
  const closeDisabled = autoRunning;

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
          const data = await dsApi.syncTree(dataSource.id, {
            start_path: startPath || "/",
            max_depth: maxDepth,
            max_items: maxItems,
            include_hidden: includeHidden,
            apply_exclusions: applyExclusions,
            detect_deleted: detectDeleted,
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
            max_file_size_bytes: textMaxMb * 1024 * 1024,
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
          if (e.target === e.currentTarget && !autoRunning) onClose();
        }}
      >
        <div className={docStyles.panel} onMouseDown={(e) => e.stopPropagation()}>
          <SectionCard
            title="인덱싱 파이프라인 실행"
            actions={
              <Button type="button" variant="ghost" size="sm" onClick={onClose} disabled={closeDisabled}>
                닫기
              </Button>
            }
          >
            <p className="muted" style={{ marginTop: 0 }}>
              <strong>{dataSource.name}</strong> — WebDAV 파일 수집부터 텍스트/문서 추출, Chunk 생성, Embedding 생성까지 단계별로 실행합니다.
            </p>
            <ul className="muted" style={{ margin: "0.35rem 0 0", paddingLeft: "1.2rem", fontSize: "0.875rem" }}>
              <li>각 단계는 개별 실행할 수 있으며, 대량 작업 전에는 dry_run으로 대상 확인을 권장합니다.</li>
              <li>
                <strong>대상 확인</strong>은 실제 파일 다운로드/DB 변경 없이 대상만 확인합니다. <strong>실제 실행</strong>은 DB 상태를 바꿀 수 있습니다.
              </li>
              <li>동기화(Step 1)는 dry_run 옵션이 없습니다. 실행 전 범위를 확인하세요.</li>
              <li>
                <strong>자동 실행은 실제 실행 모드로 동작하며 dry_run은 적용되지 않습니다.</strong> 자동 실행 전 단계별 대상 확인(dry_run)을 권장합니다.
              </li>
            </ul>

            <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", marginTop: "0.75rem", alignItems: "center" }}>
              <Button
                type="button"
                variant="primary"
                size="sm"
                disabled={disableManualActions}
                onClick={() => setConfirmAutoOpen(true)}
              >
                권장 순서로 전체 실행
              </Button>
              <span className="muted" style={{ fontSize: "0.8rem", maxWidth: "28rem" }}>
                WebDAV 동기화부터 Embedding 생성까지 순차 실행합니다. 중간 단계가 실패하면 다음 단계는 실행하지 않습니다.
              </span>
            </div>

            {autoRunning && (
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

            {autoSummary && (
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

            {(autoRunning || autoSteps.some((s) => s.status !== "idle")) && (
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
          </SectionCard>

          <div className={styles.stepStack}>
            <SectionCard title={STEP_LABEL.sync}>
              <div className="formGrid" style={{ maxWidth: 640 }}>
                <FormField label="start_path">
                  <Input value={startPath} onChange={(e) => setStartPath(e.target.value)} disabled={formDisabled} />
                </FormField>
                <FormField label="max_depth">
                  <Input
                    type="number"
                    value={maxDepth}
                    onChange={(e) => setMaxDepth(Number(e.target.value) || 0)}
                    min={0}
                    max={20}
                    disabled={formDisabled}
                  />
                </FormField>
                <FormField label="max_items">
                  <Input
                    type="number"
                    value={maxItems}
                    onChange={(e) => setMaxItems(Number(e.target.value) || 1)}
                    min={1}
                    max={50000}
                    disabled={formDisabled}
                  />
                </FormField>
                <label className={styles.check}>
                  <input
                    type="checkbox"
                    checked={includeHidden}
                    onChange={(e) => setIncludeHidden(e.target.checked)}
                    disabled={formDisabled}
                  />
                  include_hidden
                </label>
                <label className={styles.check}>
                  <input
                    type="checkbox"
                    checked={applyExclusions}
                    onChange={(e) => setApplyExclusions(e.target.checked)}
                    disabled={formDisabled}
                  />
                  apply_exclusions
                </label>
                <label className={styles.check}>
                  <input
                    type="checkbox"
                    checked={detectDeleted}
                    onChange={(e) => setDetectDeleted(e.target.checked)}
                    disabled={formDisabled}
                  />
                  detect_deleted
                </label>
              </div>
              <Button
                type="button"
                variant="primary"
                size="sm"
                style={{ marginTop: "0.65rem" }}
                loading={loading === "sync"}
                disabled={disableManualActions && loading !== "sync"}
                onClick={() =>
                  requestConfirm(() =>
                    runWithLoading("sync", () =>
                      dsApi.syncTree(dataSource.id, {
                        start_path: startPath || "/",
                        max_depth: maxDepth,
                        max_items: maxItems,
                        include_hidden: includeHidden,
                        apply_exclusions: applyExclusions,
                        detect_deleted: detectDeleted,
                      })
                    )
                  )
                }
              >
                동기화 실행
              </Button>
              <StepResultBlock snap={snap.sync} />
            </SectionCard>

            <SectionCard title={STEP_LABEL.text}>
              <div className="formGrid" style={{ maxWidth: 640 }}>
                <FormField label="limit">
                  <Select
                    value={String(textLimit)}
                    onChange={(e) => setTextLimit(Number(e.target.value))}
                    disabled={formDisabled}
                  >
                    {[10, 20, 50, 100, 200, 500, 1000].map((n) => (
                      <option key={n} value={n}>
                        {n}
                      </option>
                    ))}
                  </Select>
                </FormField>
                <FormField label="max_file_size_mb">
                  <Select
                    value={String(textMaxMb)}
                    onChange={(e) => setTextMaxMb(Number(e.target.value))}
                    disabled={formDisabled}
                  >
                    {[1, 2, 5, 10, 20, 50].map((n) => (
                      <option key={n} value={n}>
                        {n} MB
                      </option>
                    ))}
                  </Select>
                </FormField>
                <FormField label="include_extensions" hint="쉼표 구분, 비우면 전체 허용">
                  <Input value={textIncludeExt} onChange={(e) => setTextIncludeExt(e.target.value)} disabled={formDisabled} />
                </FormField>
              </div>
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
                        max_file_size_bytes: textMaxMb * 1024 * 1024,
                        include_extensions: textIncludeExt.trim() || undefined,
                        dry_run: true,
                      })
                    )
                  }
                >
                  대상 확인
                </Button>
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
                          max_file_size_bytes: textMaxMb * 1024 * 1024,
                          include_extensions: textIncludeExt.trim() || undefined,
                          dry_run: false,
                        })
                      )
                    )
                  }
                >
                  실제 실행
                </Button>
              </div>
              <StepResultBlock snap={snap.text} />
            </SectionCard>

            <SectionCard title={STEP_LABEL.doc}>
              <DocumentProcessingPanel
                dataSourceId={dataSource.id}
                dataSourceName={dataSource.name}
                showIntroBullets={false}
                showFollowUpChunkEmbed={false}
                embedResultInParent
                onDocumentApiOutcome={handleDocOutcome}
                onRunComplete={onRefresh}
                onDocumentParamsSnapshot={onDocumentParamsSnapshot}
                disableRunButtons={autoRunning}
              />
              <StepResultBlock snap={snap.doc} />
            </SectionCard>

            <SectionCard title={STEP_LABEL.chunk}>
              <div className="formGrid" style={{ maxWidth: 640 }}>
                <FormField label="limit">
                  <Select
                    value={String(chunkLimit)}
                    onChange={(e) => setChunkLimit(Number(e.target.value))}
                    disabled={formDisabled}
                  >
                    {[20, 50, 100, 200, 500, 1000].map((n) => (
                      <option key={n} value={n}>
                        {n}
                      </option>
                    ))}
                  </Select>
                </FormField>
                <FormField label="chunk_size">
                  <Input
                    type="number"
                    value={chunkSize}
                    onChange={(e) => setChunkSize(Number(e.target.value) || 200)}
                    disabled={formDisabled}
                  />
                </FormField>
                <FormField label="chunk_overlap">
                  <Input
                    type="number"
                    value={chunkOverlap}
                    onChange={(e) => setChunkOverlap(Number(e.target.value) || 0)}
                    disabled={formDisabled}
                  />
                </FormField>
                <FormField label="min_chunk_size">
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
                  reprocess
                </label>
                <FormField label="include_extensions" hint="선택">
                  <Input
                    value={chunkIncludeExt}
                    onChange={(e) => setChunkIncludeExt(e.target.value)}
                    placeholder="비우면 필터 없음"
                    disabled={formDisabled}
                  />
                </FormField>
              </div>
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
              </div>
              <StepResultBlock snap={snap.chunk} />
            </SectionCard>

            <SectionCard title={STEP_LABEL.embed}>
              <div className="formGrid" style={{ maxWidth: 640 }}>
                <FormField label="limit">
                  <Select
                    value={String(embedLimit)}
                    onChange={(e) => setEmbedLimit(Number(e.target.value))}
                    disabled={formDisabled}
                  >
                    {[100, 200, 500, 1000, 2000, 5000].map((n) => (
                      <option key={n} value={n}>
                        {n}
                      </option>
                    ))}
                  </Select>
                </FormField>
                <FormField label="batch_size">
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
                  reembed
                </label>
                <FormField label="include_extensions" hint="선택">
                  <Input value={embedIncludeExt} onChange={(e) => setEmbedIncludeExt(e.target.value)} disabled={formDisabled} />
                </FormField>
              </div>
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
              </div>
              <StepResultBlock snap={snap.embed} />
            </SectionCard>
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
        title="전체 파이프라인 실행"
        message={AUTO_CONFIRM_MSG}
        confirmLabel="계속"
        cancelLabel="취소"
        onCancel={() => setConfirmAutoOpen(false)}
        onConfirm={() => {
          setConfirmAutoOpen(false);
          void executeAutoPipeline();
        }}
      />
    </>,
    document.body
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
