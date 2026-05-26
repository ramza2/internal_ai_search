import { useCallback, useState } from "react";
import { Link } from "react-router-dom";
import * as adminJobsApi from "@/api/adminJobsApi";
import * as dsApi from "@/api/dataSourceApi";
import { getApiErrorMessage } from "@/api/httpClient";
import { EmptyState } from "@/components/EmptyState";
import { ErrorMessage } from "@/components/ErrorMessage";
import {
  AdvancedSection,
  Badge,
  Button,
  CollapsiblePanel,
  ConfirmDialog,
  DataTable,
  FormField,
  InfoBox,
  Select,
} from "@/components/ui";
import type { DocumentProcessItem, DocumentProcessResponse } from "@/types/documentProcessing";
import { formatInt } from "@/utils/format";
import docStyles from "../DocumentProcessModal.module.css";
import styles from "./HwpSkippedReprocessSection.module.css";

const LIMIT_OPTIONS = [1, 5, 10, 20, 50, 100] as const;

const ENQUEUE_CONFIRM_MESSAGE =
  "내용 추출에 실패했던 HWP 문서를 다시 분석하는 백그라운드 작업을 등록합니다. 완료 후 검색 반영을 위해 검색 단위 생성 및 검색 인덱스 생성 작업이 추가로 필요할 수 있습니다. 계속하시겠습니까?";

function mapWarningToUserMessage(raw: string): string {
  const w = raw.toLowerCase();
  if (w.includes("hwp5txt_only") || w.includes("hwp5txt")) {
    return "현재 서버 설정에서는 표·양식 개선 추출이 적용되지 않을 수 있습니다. 관리자 설정을 확인해 주세요.";
  }
  if (w.includes("only_reprocess") && w.includes("precedence")) {
    return "일반 문서 처리 옵션보다 HWP 복구 전용 모드가 우선 적용됩니다.";
  }
  if (w.includes("reprocess_skipped") && w.includes("ignored")) {
    return "다른 확장자 재처리 옵션은 이 작업에서 사용되지 않습니다.";
  }
  if (w.includes("include_extensions") && w.includes("hwp")) {
    return "HWP 확장자가 포함되어야 합니다. 설정을 확인해 주세요.";
  }
  return raw;
}

function isHwpOnlyReprocessPlanned(planned: string | null | undefined): boolean {
  const a = (planned || "").toUpperCase();
  return a.includes("REPROCESS_HWP") && a.includes("NO_EXTRACTABLE");
}

function labelPlannedAction(planned: string | null | undefined): string {
  if (isHwpOnlyReprocessPlanned(planned)) return "다시 분석";
  return planned || "—";
}

function labelStatusBefore(
  status: string | null | undefined,
  errorCode: string | null | undefined
): string {
  if ((status || "").toUpperCase() === "SKIPPED" && (errorCode || "").toUpperCase() === "NO_EXTRACTABLE_TEXT") {
    return "내용 추출 불가";
  }
  if (status) return status;
  return "—";
}

function shortPath(path: string | null | undefined): string {
  if (!path) return "—";
  const p = path.replace(/\\/g, "/");
  if (p.length <= 56) return p;
  return `…${p.slice(-52)}`;
}

export type HwpSkippedReprocessSectionProps = {
  dataSourceId: string;
  dataSourceName: string;
  maxFileSizeBytes: number;
  disabled?: boolean;
};

export function HwpSkippedReprocessSection({
  dataSourceId,
  dataSourceName,
  maxFileSizeBytes,
  disabled = false,
}: HwpSkippedReprocessSectionProps) {
  const [limit, setLimit] = useState(20);
  const [busy, setBusy] = useState(false);
  const [enqueueBusy, setEnqueueBusy] = useState(false);
  const [error, setError] = useState("");
  const [lastResponse, setLastResponse] = useState<DocumentProcessResponse | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [enqueueSuccess, setEnqueueSuccess] = useState<{
    jobId: string;
    message: string;
  } | null>(null);

  const runDryRun = useCallback(async () => {
    setError("");
    setEnqueueSuccess(null);
    setBusy(true);
    try {
      const res = await dsApi.processPendingDocuments(dataSourceId, {
        limit,
        max_file_size_bytes: maxFileSizeBytes,
        include_extensions: "hwp",
        dry_run: true,
        reprocess_skipped: false,
        only_reprocess_hwp_no_extractable_text: true,
      });
      setLastResponse(res);
    } catch (e) {
      setLastResponse(null);
      setError(getApiErrorMessage(e));
    } finally {
      setBusy(false);
    }
  }, [dataSourceId, limit, maxFileSizeBytes]);

  async function runEnqueue() {
    setError("");
    setEnqueueBusy(true);
    try {
      const r = await adminJobsApi.postAdminProcessPendingDocumentsJob({
        data_source_id: dataSourceId,
        limit,
        max_file_size_bytes: maxFileSizeBytes,
        include_extensions: "hwp",
        reprocess_skipped: false,
        reprocess_hwp_no_extractable_text: false,
        only_reprocess_hwp_no_extractable_text: true,
        priority: 0,
      });
      setEnqueueSuccess({
        jobId: r.job_id,
        message: r.message || "백그라운드 재처리 작업이 등록되었습니다.",
      });
      setLastResponse(null);
    } catch (e) {
      setError(getApiErrorMessage(e));
    } finally {
      setEnqueueBusy(false);
      setConfirmOpen(false);
    }
  }

  const targetCount = lastResponse?.status === "ok" ? (lastResponse.target_count ?? 0) : 0;
  const canEnqueue = targetCount > 0 && !busy && !enqueueBusy && !disabled;
  const items = lastResponse?.items ?? [];
  const warnings = lastResponse?.warnings ?? [];

  return (
    <CollapsiblePanel
      title="추출되지 않은 HWP 다시 처리"
      summary="이전에 내용 추출이 되지 않아 제외된 HWP만 표·양식 개선 방식으로 다시 분석 (일반 검색 반영과 별도)"
      defaultOpen={false}
    >
      <InfoBox title="안내">
        <p style={{ margin: "0 0 0.5rem" }}>
          이전에 내용 추출이 되지 않아 제외된 HWP 문서를 새로운 표·양식 추출 방식으로 다시 분석합니다. 표가 많은
          HWP 문서 복구에 사용할 수 있습니다.
        </p>
        <p style={{ margin: 0 }}>
          이 기능은 <strong>기존에 제외된 HWP만</strong> 대상으로 하며, 일반 대기 문서나 이미 처리 완료된 문서는
          포함하지 않습니다. <strong>일반 검색 반영과 별도</strong>로 실행되는 복구 작업입니다.
        </p>
      </InfoBox>

      <div className="formGrid" style={{ maxWidth: 320, marginTop: "1rem" }}>
        <FormField label="한 번에 처리할 문서 수" hint="백그라운드 작업 limit">
          <Select value={String(limit)} onChange={(e) => setLimit(Number(e.target.value))} disabled={disabled}>
            {LIMIT_OPTIONS.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </Select>
        </FormField>
      </div>

      <div className={styles.actions}>
        <Button type="button" variant="secondary" size="sm" loading={busy} disabled={disabled} onClick={() => void runDryRun()}>
          재처리 대상 확인
        </Button>
        <Button
          type="button"
          variant="primary"
          size="sm"
          loading={enqueueBusy}
          disabled={!canEnqueue}
          onClick={() => setConfirmOpen(true)}
        >
          백그라운드 재처리 작업 등록
        </Button>
      </div>

      <ErrorMessage message={error} />

      {enqueueSuccess && (
        <InfoBox variant="success" title="작업 등록됨">
          <p style={{ margin: "0 0 0.5rem" }}>{enqueueSuccess.message}</p>
          <p style={{ margin: "0 0 0.5rem" }}>
            작업 이력에서 완료를 확인한 뒤, 필요하면 <strong>검색 단위 생성</strong>과{" "}
            <strong>검색 인덱스 생성</strong> 작업을 실행하세요.
          </p>
          <Link to="/admin/jobs">작업 이력 보기</Link>
          <AdvancedSection title="고급 정보" summary="작업 ID">
            <p className={styles.mono} style={{ margin: 0, fontSize: "0.75rem" }}>
              {enqueueSuccess.jobId}
            </p>
          </AdvancedSection>
        </InfoBox>
      )}

      {lastResponse?.status === "ok" && (
        <div className={docStyles.sectionSpacer}>
          <SectionSummary
            dataSourceName={dataSourceName}
            targetCount={targetCount}
            message={lastResponse.message}
          />
          {warnings.length > 0 && (
            <div className={styles.warnings}>
              {warnings.map((w, i) => (
                <InfoBox key={i} variant="warning" title="참고">
                  <p style={{ margin: 0 }}>{mapWarningToUserMessage(w)}</p>
                </InfoBox>
              ))}
            </div>
          )}
          {targetCount === 0 ? (
            <EmptyState
              title="다시 처리할 HWP 문서가 없습니다"
              description="이미 재처리가 완료되었거나, 해당 저장소에 내용 추출 실패 상태의 HWP 문서가 없습니다."
            />
          ) : (
            <div className={docStyles.tableWrap}>
              <DataTable>
                <thead>
                  <tr>
                    <th>파일명</th>
                    <th>경로</th>
                    <th>현재 상태</th>
                    <th>예정 작업</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((row) => (
                    <HwpTargetRow key={row.file_id} item={row} />
                  ))}
                </tbody>
              </DataTable>
              <AdvancedSection title="고급 정보" summary="file_id·상태 코드">
                <div className={docStyles.tableWrap}>
                  <DataTable>
                    <thead>
                      <tr>
                        <th>file_id</th>
                        <th>planned_action</th>
                        <th>analysis_status_before</th>
                        <th>analysis_error_code_before</th>
                      </tr>
                    </thead>
                    <tbody>
                      {items.map((row) => (
                        <tr key={`adv-${row.file_id}`}>
                          <td className={styles.mono}>{row.file_id}</td>
                          <td className={styles.mono}>{row.planned_action ?? "—"}</td>
                          <td className={styles.mono}>{row.analysis_status_before ?? "—"}</td>
                          <td className={styles.mono}>{row.analysis_error_code_before ?? "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </DataTable>
                </div>
              </AdvancedSection>
            </div>
          )}
        </div>
      )}

      <ConfirmDialog
        open={confirmOpen}
        title="백그라운드 재처리 작업 등록"
        message={ENQUEUE_CONFIRM_MESSAGE}
        confirmLabel="등록"
        cancelLabel="취소"
        onCancel={() => setConfirmOpen(false)}
        onConfirm={() => void runEnqueue()}
      />
    </CollapsiblePanel>
  );
}

function SectionSummary({
  dataSourceName,
  targetCount,
  message,
}: {
  dataSourceName: string;
  targetCount: number;
  message?: string;
}) {
  return (
    <div className={docStyles.summaryGrid}>
      <div className={docStyles.summaryItem}>
        저장소
        <strong>{dataSourceName}</strong>
      </div>
      <div className={docStyles.summaryItem}>
        다시 처리할 HWP
        <strong>{formatInt(targetCount)}</strong>
      </div>
      <div className={docStyles.summaryItem}>
        처리 방식
        <strong>표·양식 문서 개선 추출</strong>
      </div>
      {message && (
        <div className={docStyles.summaryItem} style={{ gridColumn: "1 / -1" }}>
          메시지
          <strong style={{ fontWeight: 500, fontSize: "0.85rem" }}>{message}</strong>
        </div>
      )}
    </div>
  );
}

function HwpTargetRow({ item }: { item: DocumentProcessItem }) {
  return (
    <tr>
      <td>{item.filename ?? "—"}</td>
      <td className="snippet">{shortPath(item.remote_path)}</td>
      <td>
        <Badge variant="warning">
          {labelStatusBefore(item.analysis_status_before, item.analysis_error_code_before)}
        </Badge>
      </td>
      <td>
        <Badge variant="primary">{labelPlannedAction(item.planned_action)}</Badge>
      </td>
    </tr>
  );
}
