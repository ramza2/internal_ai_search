import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import * as dsApi from "@/api/dataSourceApi";
import { getApiErrorMessage } from "@/api/httpClient";
import { EmptyState } from "@/components/EmptyState";
import { ErrorMessage } from "@/components/ErrorMessage";
import {
  Badge,
  Button,
  ConfirmDialog,
  DataTable,
  FormField,
  SectionCard,
  Select,
} from "@/components/ui";
import type { BadgeVariant } from "@/components/ui";
import type {
  DocumentProcessItem,
  DocumentProcessRequestParams,
  DocumentProcessResponse,
} from "@/types/documentProcessing";
import { formatInt } from "@/utils/format";
import styles from "../DocumentProcessModal.module.css";

const LIMIT_OPTIONS = [10, 20, 50, 100, 500] as const;

const MB_OPTIONS: { label: string; bytes: number }[] = [
  { label: "10 MB", bytes: 10 * 1024 * 1024 },
  { label: "50 MB", bytes: 50 * 1024 * 1024 },
  { label: "100 MB", bytes: 100 * 1024 * 1024 },
];

const DOC_EXT_KEYS = ["pdf", "docx", "xlsx", "pptx", "hwpx"] as const;
type DocExtKey = (typeof DOC_EXT_KEYS)[number];

const EXT_LABELS: Record<DocExtKey, string> = {
  pdf: "PDF",
  docx: "DOCX",
  xlsx: "XLSX",
  pptx: "PPTX",
  hwpx: "HWPX",
};

function itemStatusVariant(status: string | undefined): BadgeVariant {
  const s = (status || "").toUpperCase();
  if (s === "COMPLETED" || s === "UNCHANGED") return "success";
  if (s === "SKIPPED") return "warning";
  if (s === "FAILED") return "danger";
  if (s === "PROCESS") return "primary";
  return "neutral";
}

function plannedActionVariant(action: string | undefined): BadgeVariant {
  const a = (action || "").toUpperCase();
  if (a === "PROCESS") return "primary";
  if (a === "SKIP") return "neutral";
  return "neutral";
}

function reasonVariant(code: string | undefined): BadgeVariant {
  const c = (code || "").toUpperCase();
  if (c === "PASSWORD_PROTECTED" || c === "PARSING_FAILED" || c === "DOWNLOAD_FAILED") return "danger";
  if (
    c === "NO_EXTRACTABLE_TEXT" ||
    c === "FILE_TOO_LARGE" ||
    c === "UNSUPPORTED_EXTENSION" ||
    c === "BINARY_CONTENT_DETECTED"
  )
    return "warning";
  return "neutral";
}

function canPreviewRow(item: DocumentProcessItem, dryRun: boolean): boolean {
  if (dryRun) return false;
  const st = item.status?.toUpperCase();
  if (st !== "COMPLETED" && st !== "UNCHANGED") return false;
  return (item.text_length ?? 0) > 0;
}

function shortHash(hash: string | null | undefined): string {
  if (!hash || hash.length < 10) return "—";
  return `${hash.slice(0, 10)}…`;
}

/** 파이프라인 자동 실행이 Step 3 API 파라미터를 읽을 때 사용 */
export type DocumentPipelineFormSnapshot = Pick<
  DocumentProcessRequestParams,
  "limit" | "max_file_size_bytes" | "reprocess_skipped"
> & { include_extensions?: string };

export type DocumentProcessingPanelProps = {
  dataSourceId: string;
  dataSourceName: string;
  /** 모달 상단 안내 불릿 (파이프라인 임베드 시 false) */
  showIntroBullets?: boolean;
  /** 추출 성공 후 Chunk/Embedding 바로가기 */
  showFollowUpChunkEmbed?: boolean;
  onRunComplete?: () => void;
  /** true이면 패널 내부 결과 카드는 숨기고 `onDocumentApiOutcome`로만 부모에 전달 */
  embedResultInParent?: boolean;
  /** 파이프라인 모달에서 Step 3 요약 카드에 반영 */
  onDocumentApiOutcome?: (payload: {
    dryRun: boolean;
    response: DocumentProcessResponse | null;
    error: string;
  }) => void;
  /** 현재 폼값 스냅샷(자동 실행 등에서 재사용) */
  onDocumentParamsSnapshot?: (p: DocumentPipelineFormSnapshot) => void;
  /** 파이프라인 전체 자동 실행 중에는 수동 실행 버튼 비활성화 */
  disableRunButtons?: boolean;
};

export function DocumentProcessingPanel({
  dataSourceId,
  dataSourceName,
  showIntroBullets = true,
  showFollowUpChunkEmbed = true,
  onRunComplete,
  embedResultInParent = false,
  onDocumentApiOutcome,
  onDocumentParamsSnapshot,
  disableRunButtons = false,
}: DocumentProcessingPanelProps) {
  const [limit, setLimit] = useState(50);
  const [maxBytes, setMaxBytes] = useState(52_428_800);
  const [extSelected, setExtSelected] = useState<Record<DocExtKey, boolean>>(() => {
    const o = {} as Record<DocExtKey, boolean>;
    for (const k of DOC_EXT_KEYS) o[k] = true;
    return o;
  });
  const [reprocessSkipped, setReprocessSkipped] = useState(false);
  const [recommendDryRunNote, setRecommendDryRunNote] = useState(true);
  const [busy, setBusy] = useState(false);
  const [chunkBusy, setChunkBusy] = useState(false);
  const [embedBusy, setEmbedBusy] = useState(false);
  const [processError, setProcessError] = useState("");
  const [followUpMsg, setFollowUpMsg] = useState<{ tone: "success" | "danger"; text: string } | null>(null);
  const [lastResponse, setLastResponse] = useState<DocumentProcessResponse | null>(null);
  const [confirmRunOpen, setConfirmRunOpen] = useState(false);

  const buildIncludeExtensions = useCallback((): string | undefined => {
    const parts = DOC_EXT_KEYS.filter((k) => extSelected[k]);
    if (parts.length === 0) return undefined;
    return parts.join(",");
  }, [extSelected]);

  useEffect(() => {
    const include = buildIncludeExtensions();
    onDocumentParamsSnapshot?.({
      limit,
      max_file_size_bytes: maxBytes,
      include_extensions: include,
      reprocess_skipped: reprocessSkipped,
    });
  }, [limit, maxBytes, extSelected, reprocessSkipped, buildIncludeExtensions, onDocumentParamsSnapshot]);

  const resetForm = useCallback(() => {
    setLimit(50);
    setMaxBytes(52_428_800);
    const o = {} as Record<DocExtKey, boolean>;
    for (const k of DOC_EXT_KEYS) o[k] = true;
    setExtSelected(o);
    setReprocessSkipped(false);
    setRecommendDryRunNote(true);
    setProcessError("");
    setFollowUpMsg(null);
    setLastResponse(null);
  }, []);

  useEffect(() => {
    resetForm();
  }, [dataSourceId, resetForm]);

  async function runProcess(dryRun: boolean) {
    setProcessError("");
    setFollowUpMsg(null);
    const include = buildIncludeExtensions();
    if (!include || include === "") {
      setProcessError("처리할 확장자를 하나 이상 선택해 주세요.");
      return;
    }
    setBusy(true);
    try {
      const res = await dsApi.processPendingDocuments(dataSourceId, {
        limit,
        max_file_size_bytes: maxBytes,
        include_extensions: include,
        dry_run: dryRun,
        reprocess_skipped: reprocessSkipped,
      });
      setLastResponse(res);
      onDocumentApiOutcome?.({ dryRun: dryRun, response: res, error: "" });
    } catch (e) {
      setLastResponse(null);
      const msg = getApiErrorMessage(e);
      setProcessError(msg);
      onDocumentApiOutcome?.({ dryRun: dryRun, response: null, error: msg });
    } finally {
      setBusy(false);
      onRunComplete?.();
    }
  }

  async function runChunk() {
    setFollowUpMsg(null);
    setChunkBusy(true);
    try {
      const data = await dsApi.chunkCompletedText(dataSourceId, {
        limit: 200,
        chunk_size: 1200,
        chunk_overlap: 200,
        min_chunk_size: 100,
        reprocess: false,
        dry_run: false,
      });
      const msg = typeof data.message === "string" ? data.message : "Chunk 작업이 완료되었습니다.";
      setFollowUpMsg({ tone: data.status === "error" ? "danger" : "success", text: msg });
    } catch (e) {
      setFollowUpMsg({ tone: "danger", text: getApiErrorMessage(e) });
    } finally {
      setChunkBusy(false);
      onRunComplete?.();
    }
  }

  async function runEmbed() {
    setFollowUpMsg(null);
    setEmbedBusy(true);
    try {
      const data = await dsApi.embedPendingChunks(dataSourceId, {
        limit: 500,
        batch_size: 32,
        reembed: false,
        dry_run: false,
      });
      const msg = typeof data.message === "string" ? data.message : "Embedding 작업이 완료되었습니다.";
      setFollowUpMsg({ tone: data.status === "error" ? "danger" : "success", text: msg });
    } catch (e) {
      setFollowUpMsg({ tone: "danger", text: getApiErrorMessage(e) });
    } finally {
      setEmbedBusy(false);
      onRunComplete?.();
    }
  }

  const showFollowUp =
    showFollowUpChunkEmbed &&
    lastResponse?.status === "ok" &&
    lastResponse.dry_run === false &&
    (lastResponse.completed_count ?? 0) > 0;

  const dryRun = lastResponse?.dry_run === true;
  const zeroTargets = lastResponse?.status === "ok" && (lastResponse.target_count ?? 0) === 0;

  return (
    <>
      <p className="muted" style={{ marginTop: 0 }}>
        <strong>{dataSourceName}</strong> — PDF, DOCX, XLSX, PPTX, HWPX 문서를 추출하여 검색/RAG 파이프라인에 연결합니다.
      </p>
      {showIntroBullets && (
        <ul className="muted" style={{ margin: "0.5rem 0 0", paddingLeft: "1.2rem", fontSize: "0.875rem" }}>
          <li>HWP Automation / COM은 사용하지 않습니다.</li>
          <li>HWPX는 ZIP/XML 기반으로 처리합니다.</li>
          <li>HWP, DOC, XLS, PPT는 아직 미지원입니다.</li>
          <li>처리 후에는 Chunk 생성과 Embedding 생성이 별도로 필요합니다.</li>
        </ul>
      )}

      <div className="formGrid" style={{ maxWidth: 560, marginTop: "1rem" }}>
        <FormField label="처리 개수 (limit)">
          <Select value={String(limit)} onChange={(e) => setLimit(Number(e.target.value))}>
            {LIMIT_OPTIONS.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField label="최대 파일 크기" hint="WebDAV 다운로드 상한">
          <Select value={String(maxBytes)} onChange={(e) => setMaxBytes(Number(e.target.value))}>
            {MB_OPTIONS.map((m) => (
              <option key={m.bytes} value={m.bytes}>
                {m.label}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField label="처리 확장자">
          <div className={styles.extGrid}>
            {DOC_EXT_KEYS.map((k) => (
              <label key={k} style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem", fontSize: "0.875rem" }}>
                <input
                  type="checkbox"
                  checked={extSelected[k]}
                  onChange={(e) => setExtSelected((s) => ({ ...s, [k]: e.target.checked }))}
                />
                {EXT_LABELS[k]}
              </label>
            ))}
          </div>
        </FormField>
        <label style={{ display: "flex", alignItems: "flex-start", gap: "0.5rem", fontSize: "0.875rem" }}>
          <input type="checkbox" checked={recommendDryRunNote} onChange={(e) => setRecommendDryRunNote(e.target.checked)} />
          <span>
            실제 처리 전 드라이런으로 대상만 확인하는 것을 권장합니다. (<strong>대상 확인</strong> 버튼 사용)
          </span>
        </label>
        <label style={{ display: "flex", alignItems: "flex-start", gap: "0.5rem", fontSize: "0.875rem" }}>
          <input type="checkbox" checked={reprocessSkipped} onChange={(e) => setReprocessSkipped(e.target.checked)} />
          <span>
            기존에 UNSUPPORTED_EXTENSION으로 스킵된 문서 파일을 다시 처리합니다. (<code>reprocess_skipped</code>)
          </span>
        </label>
      </div>

      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", marginTop: "1rem" }}>
        <Button
          type="button"
          variant="secondary"
          loading={busy}
          disabled={disableRunButtons}
          onClick={() => void runProcess(true)}
        >
          대상 확인 (dry_run)
        </Button>
        <Button
          type="button"
          variant="primary"
          loading={busy}
          disabled={disableRunButtons}
          onClick={() => setConfirmRunOpen(true)}
        >
          문서 처리 실행
        </Button>
      </div>

      <ErrorMessage message={processError} />
      {followUpMsg && (
        <div
          className={`alert ${followUpMsg.tone === "success" ? "alertSuccess" : "alertDanger"}`}
          style={{ marginTop: "0.75rem" }}
        >
          {followUpMsg.text}
        </div>
      )}

      {lastResponse && lastResponse.status === "ok" && !embedResultInParent && (
        <div className={styles.sectionSpacer}>
          <SectionCard title="결과 요약">
            <p style={{ marginTop: 0, fontSize: "0.9rem" }}>{lastResponse.message}</p>
            <div className={styles.summaryGrid}>
              <div className={styles.summaryItem}>
                대상 <strong>{formatInt(lastResponse.target_count ?? 0)}</strong>
              </div>
              {typeof lastResponse.processed_count === "number" && (
                <div className={styles.summaryItem}>
                  처리 <strong>{formatInt(lastResponse.processed_count)}</strong>
                </div>
              )}
              {typeof lastResponse.completed_count === "number" && (
                <div className={styles.summaryItem}>
                  완료 <strong>{formatInt(lastResponse.completed_count)}</strong>
                </div>
              )}
              {typeof lastResponse.skipped_count === "number" && (
                <div className={styles.summaryItem}>
                  스킵 <strong>{formatInt(lastResponse.skipped_count)}</strong>
                </div>
              )}
              {typeof lastResponse.failed_count === "number" && (
                <div className={styles.summaryItem}>
                  실패 <strong>{formatInt(lastResponse.failed_count)}</strong>
                </div>
              )}
              <div className={styles.summaryItem}>
                드라이런 <strong>{lastResponse.dry_run ? "예" : "아니오"}</strong>
              </div>
              {lastResponse.scan_job_id != null && lastResponse.scan_job_id !== "" && (
                <div className={styles.summaryItem}>
                  scan_job <strong className={styles.mono}>{String(lastResponse.scan_job_id).slice(0, 8)}…</strong>
                </div>
              )}
            </div>

            {zeroTargets && (
              <EmptyState
                title="대상 파일이 없습니다"
                description="조건에 맞는 PENDING(또는 재처리 대상) 문서가 없습니다. 동기화·확장자 필터·reprocess_skipped 옵션을 확인해 주세요."
              />
            )}

            {!zeroTargets && lastResponse.items && lastResponse.items.length > 0 && (
              <div className={styles.tableWrap}>
                <DataTable>
                  <thead>
                    <tr>
                      <th>파일명</th>
                      <th>경로</th>
                      <th>확장자</th>
                      {dryRun ? <th>planned</th> : <th>상태</th>}
                      {!dryRun && <th>parser</th>}
                      {!dryRun && <th>길이</th>}
                      <th>reason / 기타</th>
                      {!dryRun && <th>미리보기</th>}
                      {!dryRun && <th>hash</th>}
                    </tr>
                  </thead>
                  <tbody>
                    {lastResponse.items.map((row) => (
                      <DocumentResultRow key={row.file_id} item={row} dryRun={dryRun} />
                    ))}
                  </tbody>
                </DataTable>
              </div>
            )}

            {showFollowUp && (
              <div className={styles.followUp}>
                <strong>문서 텍스트 추출이 완료되었습니다.</strong> 검색/RAG에 반영하려면 아래 작업이 필요합니다.
                <ol style={{ margin: "0.5rem 0 0", paddingLeft: "1.2rem" }}>
                  <li>
                    Chunk 생성 — <code className={styles.mono}>POST /api/data-sources/{"{id}"}/chunk-completed-text</code>
                  </li>
                  <li>
                    Embedding 생성 — <code className={styles.mono}>POST /api/data-sources/{"{id}"}/embed-pending-chunks</code>
                  </li>
                </ol>
                <div className={styles.followUpActions}>
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    loading={chunkBusy}
                    disabled={disableRunButtons}
                    onClick={() => void runChunk()}
                  >
                    Chunk 생성 실행
                  </Button>
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    loading={embedBusy}
                    disabled={disableRunButtons}
                    onClick={() => void runEmbed()}
                  >
                    Embedding 생성 실행
                  </Button>
                </div>
              </div>
            )}

            {lastResponse.dry_run === false &&
              (lastResponse.completed_count ?? 0) === 0 &&
              (lastResponse.target_count ?? 0) > 0 && (
                <p className="muted" style={{ marginBottom: 0 }}>
                  이번 실행에서 COMPLETED로 전환된 파일이 없습니다. 스킵/실패 사유는 표를 참고하세요.
                </p>
              )}
          </SectionCard>
        </div>
      )}

      <ConfirmDialog
        open={confirmRunOpen}
        title="문서 처리 실행"
        message="이 작업은 파일을 다운로드하거나 DB 상태를 변경할 수 있습니다. 계속하시겠습니까?"
        confirmLabel="실행"
        cancelLabel="취소"
        onCancel={() => setConfirmRunOpen(false)}
        onConfirm={() => {
          setConfirmRunOpen(false);
          void runProcess(false);
        }}
      />
    </>
  );
}

function DocumentResultRow({ item, dryRun }: { item: DocumentProcessItem; dryRun: boolean }) {
  const preview = canPreviewRow(item, dryRun);
  const status = item.status;
  const planned = item.planned_action;
  const reason = item.reason;

  return (
    <tr>
      <td>{item.filename ?? "—"}</td>
      <td className="snippet">{item.remote_path ?? "—"}</td>
      <td>{item.extension ?? "—"}</td>
      {dryRun ? (
        <td>{planned && <Badge variant={plannedActionVariant(planned)}>{planned}</Badge>}</td>
      ) : (
        <>
          <td>{status && <Badge variant={itemStatusVariant(status)}>{status}</Badge>}</td>
          <td className="snippet">{item.parser_name ?? "—"}</td>
          <td>{item.text_length != null ? formatInt(item.text_length) : "—"}</td>
        </>
      )}
      <td>{reason ? <Badge variant={reasonVariant(reason)}>{reason}</Badge> : <span className="muted">—</span>}</td>
      {!dryRun && (
        <td>
          {preview ? (
            <Link className="btn btnSecondary btnSm" to={`/files/${item.file_id}/preview?from=doc-process`}>
              열기
            </Link>
          ) : (
            <span className="muted">—</span>
          )}
        </td>
      )}
      {!dryRun && <td className={styles.mono}>{shortHash(item.content_hash)}</td>}
    </tr>
  );
}
