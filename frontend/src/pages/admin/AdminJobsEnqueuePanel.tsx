import { useEffect, useState } from "react";
import { getApiErrorMessage } from "@/api/httpClient";
import * as adminJobsApi from "@/api/adminJobsApi";
import {
  AdvancedSection,
  Button,
  CollapsiblePanel,
  FilterField,
  Input,
  Select,
} from "@/components/ui";
import type { ScanScope } from "@/constants/pipelineLimits";
import type { DataSource } from "@/types/dataSource";
import { PROCESS_PENDING_DOCUMENTS_DEFAULT_EXTENSIONS } from "@/types/adminJobs";
import { JOB_TYPE_FILTER_OPTIONS } from "@/utils/userFriendlyLabels";
import styles from "./AdminJobsEnqueuePanel.module.css";

const DEFAULT_TEXT_JOB_EXTENSIONS = "txt,md,py,java,sql,json,yml,yaml,log,csv";

export type EnqueueKind = "sync" | "text" | "doc" | "chunk" | "embed" | "test";

const ENQUEUE_KIND_OPTIONS: { value: EnqueueKind; label: string }[] = [
  { value: "sync", label: "파일 목록 수집" },
  { value: "text", label: "텍스트 파일 내용 추출" },
  { value: "doc", label: "문서 파일 내용 추출" },
  { value: "chunk", label: "검색 단위 생성" },
  { value: "embed", label: "검색 인덱스 생성" },
  { value: "test", label: "개발용 테스트 작업" },
];

function JobFeedback({
  message,
  jobId,
}: {
  message: string | null;
  jobId: string | null;
}) {
  if (!message && !jobId) return null;
  const shortId = jobId && jobId.length > 12 ? `${jobId.slice(0, 8)}…` : jobId;
  return (
    <div className={styles.feedback}>
      {message ? <p className={styles.feedbackMsg}>{message}</p> : null}
      {jobId ? (
        <p className="muted" style={{ margin: 0, fontSize: "0.8rem" }}>
          등록된 작업: <strong title={jobId}>{shortId}</strong>
        </p>
      ) : null}
      {jobId ? (
        <AdvancedSection title="고급 정보" summary="작업 ID 전체·개발 참고">
          <p className="muted" style={{ margin: 0, fontSize: "0.8rem" }}>
            작업 ID: <code>{jobId}</code>
          </p>
          <p className="muted" style={{ margin: "0.5rem 0 0", fontSize: "0.75rem" }}>
            백그라운드 처리기(<code>python -m app.worker_main</code>)를 실행해야 대기 중 작업이 처리됩니다.
          </p>
        </AdvancedSection>
      ) : null}
    </div>
  );
}

type Props = {
  dataSources: DataSource[];
  defaultDataSourceId: string;
  listBusy: boolean;
  onEnqueued: () => Promise<void>;
};

export function AdminJobsEnqueuePanel({ dataSources, defaultDataSourceId, listBusy, onEnqueued }: Props) {
  const [kind, setKind] = useState<EnqueueKind>("sync");

  const [syncDsId, setSyncDsId] = useState("");
  const [syncStartPath, setSyncStartPath] = useState("/");
  const [syncScanScope, setSyncScanScope] = useState<ScanScope>("FULL");
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

  const [embedDsId, setEmbedDsId] = useState("");
  const [embedLimit, setEmbedLimit] = useState(500);
  const [embedBatchSize, setEmbedBatchSize] = useState(32);
  const [embedIncludeExt, setEmbedIncludeExt] = useState("");
  const [embedReembed, setEmbedReembed] = useState(false);
  const [embedPriority, setEmbedPriority] = useState(0);
  const [embedBusy, setEmbedBusy] = useState(false);
  const [embedMsg, setEmbedMsg] = useState<string | null>(null);
  const [embedJobId, setEmbedJobId] = useState<string | null>(null);

  const [testJobType, setTestJobType] = useState<string>("WEBDAV_SYNC_TREE");
  const [testFailTest, setTestFailTest] = useState(false);
  const [testBusy, setTestBusy] = useState(false);
  const [testMsg, setTestMsg] = useState<string | null>(null);

  useEffect(() => {
    const sid = defaultDataSourceId.trim();
    if (!sid) return;
    setSyncDsId(sid);
    setTextDsId(sid);
    setDocDsId(sid);
    setChunkDsId(sid);
    setEmbedDsId(sid);
  }, [defaultDataSourceId]);

  function resolveDsId(preferred: string): string {
    return preferred.trim() || defaultDataSourceId.trim() || dataSources[0]?.id || "";
  }

  const formDisabled = listBusy;

  async function onEnqueueSyncTree() {
    const dsId = resolveDsId(syncDsId);
    if (!dsId) {
      setSyncMsg("저장소를 선택하세요.");
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
        scan_scope: syncScanScope,
        max_depth:
          syncScanScope === "FULL"
            ? null
            : Math.min(20, Math.max(0, Number(syncMaxDepth) || 3)),
        max_items:
          syncScanScope === "FULL"
            ? null
            : Math.min(50_000, Math.max(1, Number(syncMaxItems) || 5000)),
        include_hidden: syncIncludeHidden,
        apply_exclusions: syncApplyExclusions,
        detect_deleted: syncDetectDeleted,
        priority: Number.isFinite(syncPriority) ? syncPriority : 0,
      });
      setSyncJobId(res.job_id);
      setSyncMsg(res.message ?? "파일 목록 수집 작업이 등록되었습니다.");
      await onEnqueued();
    } catch (e) {
      setSyncMsg(getApiErrorMessage(e));
    } finally {
      setSyncBusy(false);
    }
  }

  async function onEnqueueProcessPendingText() {
    const dsId = resolveDsId(textDsId);
    if (!dsId) {
      setTextMsg("저장소를 선택하세요.");
      setTextJobId(null);
      return;
    }
    const lim = Math.min(5000, Math.max(1, Number(textLimit) || 100));
    const maxMb = Math.max(0.001, Number(textMaxMb) || 5);
    setTextBusy(true);
    setTextMsg(null);
    setTextJobId(null);
    try {
      const extTrim = textIncludeExt.trim();
      const res = await adminJobsApi.postAdminProcessPendingTextJob({
        data_source_id: dsId,
        limit: lim,
        max_file_size_bytes: Math.round(maxMb * 1024 * 1024),
        include_extensions: extTrim.length > 0 ? extTrim : undefined,
        priority: Number.isFinite(textPriority) ? textPriority : 0,
      });
      setTextJobId(res.job_id);
      setTextMsg(res.message ?? "텍스트 추출 작업이 등록되었습니다.");
      await onEnqueued();
    } catch (e) {
      setTextMsg(getApiErrorMessage(e));
    } finally {
      setTextBusy(false);
    }
  }

  async function onEnqueueProcessPendingDocuments() {
    const dsId = resolveDsId(docDsId);
    if (!dsId) {
      setDocMsg("저장소를 선택하세요.");
      setDocJobId(null);
      return;
    }
    const lim = Math.min(5000, Math.max(1, Number(docLimit) || 50));
    const maxMb = Math.max(0.001, Number(docMaxMb) || 50);
    setDocBusy(true);
    setDocMsg(null);
    setDocJobId(null);
    try {
      const extTrim = docIncludeExt.trim();
      const res = await adminJobsApi.postAdminProcessPendingDocumentsJob({
        data_source_id: dsId,
        limit: lim,
        max_file_size_bytes: Math.round(maxMb * 1024 * 1024),
        include_extensions: extTrim.length > 0 ? extTrim : undefined,
        reprocess_skipped: docReprocessSkipped,
        priority: Number.isFinite(docPriority) ? docPriority : 0,
      });
      setDocJobId(res.job_id);
      setDocMsg(res.message ?? "문서 추출 작업이 등록되었습니다.");
      await onEnqueued();
    } catch (e) {
      setDocMsg(getApiErrorMessage(e));
    } finally {
      setDocBusy(false);
    }
  }

  async function onEnqueueChunkCompletedText() {
    const dsId = resolveDsId(chunkDsId);
    if (!dsId) {
      setChunkMsg("저장소를 선택하세요.");
      setChunkJobId(null);
      return;
    }
    const lim = Math.min(5000, Math.max(1, Number(chunkLimit) || 100));
    const cs = Math.min(10_000, Math.max(200, Number(chunkSize) || 1200));
    const co = Math.min(9999, Math.max(0, Number(chunkOverlap) || 0));
    if (co >= cs) {
      setChunkMsg("단위 겹침은 검색 단위 크기보다 작아야 합니다.");
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
      setChunkMsg(res.message ?? "검색 단위 생성 작업이 등록되었습니다.");
      await onEnqueued();
    } catch (e) {
      setChunkMsg(getApiErrorMessage(e));
    } finally {
      setChunkBusy(false);
    }
  }

  async function onEnqueueEmbedPendingChunks() {
    const dsId = resolveDsId(embedDsId);
    if (!dsId) {
      setEmbedMsg("저장소를 선택하세요.");
      setEmbedJobId(null);
      return;
    }
    const lim = Math.min(10_000, Math.max(1, Number(embedLimit) || 500));
    const bs = Math.min(128, Math.max(1, Number(embedBatchSize) || 32));
    setEmbedBusy(true);
    setEmbedMsg(null);
    setEmbedJobId(null);
    try {
      const extTrim = embedIncludeExt.trim();
      const res = await adminJobsApi.postAdminEmbedPendingChunksJob({
        data_source_id: dsId,
        limit: lim,
        batch_size: bs,
        reembed: embedReembed,
        include_extensions: extTrim.length > 0 ? extTrim : undefined,
        priority: Number.isFinite(embedPriority) ? embedPriority : 0,
      });
      setEmbedJobId(res.job_id);
      setEmbedMsg(res.message ?? "검색 인덱스 생성 작업이 등록되었습니다.");
      await onEnqueued();
    } catch (e) {
      setEmbedMsg(getApiErrorMessage(e));
    } finally {
      setEmbedBusy(false);
    }
  }

  async function onTestEnqueue() {
    const dsId = resolveDsId("");
    if (!dsId) {
      setTestMsg("저장소가 없습니다. 필터에서 저장소를 선택하거나 먼저 등록하세요.");
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
      setTestMsg(res.message ?? "테스트 작업이 등록되었습니다.");
      await onEnqueued();
    } catch (e) {
      setTestMsg(getApiErrorMessage(e));
    } finally {
      setTestBusy(false);
    }
  }

  const dsSelect = (value: string, onChange: (v: string) => void, disabled: boolean) => (
    <FilterField label="저장소">
      <Select value={value} onChange={(e) => onChange(e.target.value)} disabled={disabled}>
        <option value="">선택…</option>
        {dataSources.map((ds) => (
          <option key={ds.id} value={ds.id}>
            {ds.name}
            {!ds.is_active ? " (비활성)" : ""}
          </option>
        ))}
      </Select>
    </FilterField>
  );

  const gridStyle = {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fill, minmax(11rem, 1fr))",
    gap: "0.75rem",
    alignItems: "end",
  } as const;

  return (
    <CollapsiblePanel
      title="백그라운드 작업 등록"
      summary="저장소 수집·내용 추출·검색 인덱스 생성을 백그라운드로 등록합니다. 일반 운영은 저장소 화면의 「검색 반영 실행」을 권장합니다."
      defaultOpen={false}
    >
      <FilterField label="작업 종류" wide>
        <Select
          value={kind}
          onChange={(e) => setKind(e.target.value as EnqueueKind)}
          disabled={formDisabled}
        >
          {ENQUEUE_KIND_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </Select>
      </FilterField>

      {kind === "sync" && (
        <div className={styles.formBlock}>
          <div style={gridStyle}>
            {dsSelect(syncDsId, setSyncDsId, syncBusy || formDisabled)}
            <FilterField label="시작 폴더">
              <Input value={syncStartPath} onChange={(e) => setSyncStartPath(e.target.value)} disabled={syncBusy || formDisabled} />
            </FilterField>
            <FilterField label="수집 범위">
              <Select
                value={syncScanScope}
                onChange={(e) => setSyncScanScope(e.target.value as ScanScope)}
                disabled={syncBusy || formDisabled}
              >
                <option value="FULL">전체 저장소 처리</option>
                <option value="LIMITED">제한 설정 직접 지정</option>
              </Select>
            </FilterField>
            {syncScanScope === "LIMITED" ? (
              <>
                <FilterField label="최대 폴더 깊이">
                  <Input
                    type="number"
                    min={0}
                    max={20}
                    value={String(syncMaxDepth)}
                    onChange={(e) => setSyncMaxDepth(Number(e.target.value))}
                    disabled={syncBusy || formDisabled}
                  />
                </FilterField>
                <FilterField label="최대 항목 수">
                  <Input
                    type="number"
                    min={1}
                    max={50000}
                    value={String(syncMaxItems)}
                    onChange={(e) => setSyncMaxItems(Number(e.target.value))}
                    disabled={syncBusy || formDisabled}
                  />
                </FilterField>
              </>
            ) : null}
            <FilterField label="우선순위">
              <Input type="number" value={String(syncPriority)} onChange={(e) => setSyncPriority(Number(e.target.value))} disabled={syncBusy || formDisabled} />
            </FilterField>
          </div>
          <AdvancedSection title="고급 설정" summary="숨김 파일·제외 규칙·삭제 감지">
            <div className={styles.checkRow}>
              <label className={styles.check}>
                <input type="checkbox" checked={syncIncludeHidden} onChange={(e) => setSyncIncludeHidden(e.target.checked)} disabled={syncBusy || formDisabled} />
                숨김 파일 포함
              </label>
              <label className={styles.check}>
                <input type="checkbox" checked={syncApplyExclusions} onChange={(e) => setSyncApplyExclusions(e.target.checked)} disabled={syncBusy || formDisabled} />
                제외 규칙 적용
              </label>
              <label className={styles.check}>
                <input type="checkbox" checked={syncDetectDeleted} onChange={(e) => setSyncDetectDeleted(e.target.checked)} disabled={syncBusy || formDisabled} />
                삭제된 파일 감지
              </label>
            </div>
          </AdvancedSection>
          <div className={styles.actions}>
            <Button type="button" variant="primary" size="sm" onClick={() => void onEnqueueSyncTree()} loading={syncBusy} disabled={formDisabled}>
              작업 등록
            </Button>
          </div>
          <JobFeedback message={syncMsg} jobId={syncJobId} />
        </div>
      )}

      {kind === "text" && (
        <div className={styles.formBlock}>
          <div style={gridStyle}>
            {dsSelect(textDsId, setTextDsId, textBusy || formDisabled)}
            <FilterField label="처리 건수">
              <Input type="number" min={1} max={5000} value={String(textLimit)} onChange={(e) => setTextLimit(Number(e.target.value))} disabled={textBusy || formDisabled} />
            </FilterField>
            <FilterField label="최대 파일 크기(MB)">
              <Input type="number" min={0.001} step={0.5} value={String(textMaxMb)} onChange={(e) => setTextMaxMb(Number(e.target.value))} disabled={textBusy || formDisabled} />
            </FilterField>
            <FilterField label="우선순위">
              <Input type="number" value={String(textPriority)} onChange={(e) => setTextPriority(Number(e.target.value))} disabled={textBusy || formDisabled} />
            </FilterField>
          </div>
          <FilterField label="대상 확장자" wide>
            <Input value={textIncludeExt} onChange={(e) => setTextIncludeExt(e.target.value)} placeholder={DEFAULT_TEXT_JOB_EXTENSIONS} disabled={textBusy || formDisabled} />
          </FilterField>
          <div className={styles.actions}>
            <Button type="button" variant="primary" size="sm" onClick={() => void onEnqueueProcessPendingText()} loading={textBusy} disabled={formDisabled}>
              작업 등록
            </Button>
          </div>
          <JobFeedback message={textMsg} jobId={textJobId} />
        </div>
      )}

      {kind === "doc" && (
        <div className={styles.formBlock}>
          <div style={gridStyle}>
            {dsSelect(docDsId, setDocDsId, docBusy || formDisabled)}
            <FilterField label="처리 건수">
              <Input type="number" min={1} max={5000} value={String(docLimit)} onChange={(e) => setDocLimit(Number(e.target.value))} disabled={docBusy || formDisabled} />
            </FilterField>
            <FilterField label="최대 파일 크기(MB)">
              <Input type="number" min={0.001} step={0.5} value={String(docMaxMb)} onChange={(e) => setDocMaxMb(Number(e.target.value))} disabled={docBusy || formDisabled} />
            </FilterField>
            <FilterField label="우선순위">
              <Input type="number" value={String(docPriority)} onChange={(e) => setDocPriority(Number(e.target.value))} disabled={docBusy || formDisabled} />
            </FilterField>
          </div>
          <FilterField label="대상 확장자" wide>
            <Input value={docIncludeExt} onChange={(e) => setDocIncludeExt(e.target.value)} placeholder={PROCESS_PENDING_DOCUMENTS_DEFAULT_EXTENSIONS} disabled={docBusy || formDisabled} />
          </FilterField>
          <label className={styles.check}>
            <input type="checkbox" checked={docReprocessSkipped} onChange={(e) => setDocReprocessSkipped(e.target.checked)} disabled={docBusy || formDisabled} />
            지원하지 않는 확장자로 건너뛴 문서 다시 처리
          </label>
          <div className={styles.actions}>
            <Button type="button" variant="primary" size="sm" onClick={() => void onEnqueueProcessPendingDocuments()} loading={docBusy} disabled={formDisabled}>
              작업 등록
            </Button>
          </div>
          <JobFeedback message={docMsg} jobId={docJobId} />
        </div>
      )}

      {kind === "chunk" && (
        <div className={styles.formBlock}>
          <div style={gridStyle}>
            {dsSelect(chunkDsId, setChunkDsId, chunkBusy || formDisabled)}
            <FilterField label="처리 건수">
              <Input type="number" min={1} max={5000} value={String(chunkLimit)} onChange={(e) => setChunkLimit(Number(e.target.value))} disabled={chunkBusy || formDisabled} />
            </FilterField>
            <FilterField label="검색 단위 크기">
              <Input type="number" min={200} max={10000} value={String(chunkSize)} onChange={(e) => setChunkSize(Number(e.target.value))} disabled={chunkBusy || formDisabled} />
            </FilterField>
            <FilterField label="단위 겹침">
              <Input type="number" min={0} max={9999} value={String(chunkOverlap)} onChange={(e) => setChunkOverlap(Number(e.target.value))} disabled={chunkBusy || formDisabled} />
            </FilterField>
            <FilterField label="최소 단위 크기">
              <Input type="number" min={1} max={10000} value={String(chunkMinSize)} onChange={(e) => setChunkMinSize(Number(e.target.value))} disabled={chunkBusy || formDisabled} />
            </FilterField>
            <FilterField label="우선순위">
              <Input type="number" value={String(chunkPriority)} onChange={(e) => setChunkPriority(Number(e.target.value))} disabled={chunkBusy || formDisabled} />
            </FilterField>
          </div>
          <FilterField label="대상 확장자 (선택)" wide>
            <Input value={chunkIncludeExt} onChange={(e) => setChunkIncludeExt(e.target.value)} placeholder="비우면 필터 없음" disabled={chunkBusy || formDisabled} />
          </FilterField>
          <label className={styles.check}>
            <input type="checkbox" checked={chunkReprocess} onChange={(e) => setChunkReprocess(e.target.checked)} disabled={chunkBusy || formDisabled} />
            기존 검색 단위 다시 만들기
          </label>
          <div className={styles.actions}>
            <Button type="button" variant="primary" size="sm" onClick={() => void onEnqueueChunkCompletedText()} loading={chunkBusy} disabled={formDisabled}>
              작업 등록
            </Button>
          </div>
          <JobFeedback message={chunkMsg} jobId={chunkJobId} />
        </div>
      )}

      {kind === "embed" && (
        <div className={styles.formBlock}>
          <div style={gridStyle}>
            {dsSelect(embedDsId, setEmbedDsId, embedBusy || formDisabled)}
            <FilterField label="처리 건수">
              <Input type="number" min={1} max={10000} value={String(embedLimit)} onChange={(e) => setEmbedLimit(Number(e.target.value))} disabled={embedBusy || formDisabled} />
            </FilterField>
            <FilterField label="배치 크기">
              <Input type="number" min={1} max={128} value={String(embedBatchSize)} onChange={(e) => setEmbedBatchSize(Number(e.target.value))} disabled={embedBusy || formDisabled} />
            </FilterField>
            <FilterField label="우선순위">
              <Input type="number" value={String(embedPriority)} onChange={(e) => setEmbedPriority(Number(e.target.value))} disabled={embedBusy || formDisabled} />
            </FilterField>
          </div>
          <FilterField label="대상 확장자 (선택)" wide>
            <Input value={embedIncludeExt} onChange={(e) => setEmbedIncludeExt(e.target.value)} placeholder="비우면 필터 없음" disabled={embedBusy || formDisabled} />
          </FilterField>
          <label className={styles.check}>
            <input type="checkbox" checked={embedReembed} onChange={(e) => setEmbedReembed(e.target.checked)} disabled={embedBusy || formDisabled} />
            기존 검색 인덱스 다시 만들기
          </label>
          <div className={styles.actions}>
            <Button type="button" variant="primary" size="sm" onClick={() => void onEnqueueEmbedPendingChunks()} loading={embedBusy} disabled={formDisabled}>
              작업 등록
            </Button>
          </div>
          <JobFeedback message={embedMsg} jobId={embedJobId} />
        </div>
      )}

      {kind === "test" && (
        <div className={styles.formBlock}>
          <p className="muted" style={{ marginTop: 0, fontSize: "0.85rem" }}>
            <strong>개발·검증용</strong> — 실제 운영에는 사용하지 마세요. 테스트 작업을 큐에 넣고 백그라운드 처리기를 실행해 상태 전이를 확인합니다.
          </p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.75rem", alignItems: "flex-end" }}>
            <FilterField label="작업 종류 (원본 코드)">
              <Select value={testJobType} onChange={(e) => setTestJobType(e.target.value)} disabled={testBusy || formDisabled}>
                {JOB_TYPE_FILTER_OPTIONS.filter((o) => o.value).map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </Select>
            </FilterField>
            <label className={styles.check}>
              <input type="checkbox" checked={testFailTest} onChange={(e) => setTestFailTest(e.target.checked)} disabled={testBusy || formDisabled} />
              의도적 실패
            </label>
            <Button type="button" variant="secondary" size="sm" onClick={() => void onTestEnqueue()} loading={testBusy} disabled={formDisabled}>
              테스트 작업 등록
            </Button>
          </div>
          {testMsg ? <p className={styles.feedbackMsg}>{testMsg}</p> : null}
          <AdvancedSection title="고급 정보" summary="API·개발 참고">
            <p className="muted" style={{ margin: 0, fontSize: "0.75rem" }}>
              POST /api/admin/jobs/test-enqueue — 관리자 전용. action_logs 미기록.
            </p>
          </AdvancedSection>
        </div>
      )}
    </CollapsiblePanel>
  );
}
