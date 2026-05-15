/**
 * 운영자·일반 사용자용 표시 문구. API/DB enum 값은 변경하지 않습니다.
 * 개발자용 raw 값은 상세·고급 영역에서 별도 표시합니다.
 */

import type { BadgeVariant } from "@/components/ui";

/** 작업 종류 (scan_jobs.job_type) */
export const JOB_TYPE_LABELS: Record<string, string> = {
  MANUAL_SCAN: "수동 작업",
  WEBDAV_SYNC_ROOT: "루트 폴더 수집",
  WEBDAV_SYNC_TREE: "파일 목록 수집",
  PROCESS_PENDING_TEXT: "텍스트 파일 내용 추출",
  PROCESS_PENDING_DOCUMENTS: "문서 파일 내용 추출",
  CHUNK_COMPLETED_TEXT: "검색 단위 생성",
  EMBED_PENDING_CHUNKS: "검색 인덱스 생성",
  PIPELINE: "전체 검색 반영 작업",
};

/** 작업 상태 (scan_jobs.status) */
export const JOB_STATUS_LABELS: Record<string, string> = {
  PENDING: "대기 중",
  RUNNING: "처리 중",
  CANCELLING: "취소 중",
  CANCELLED: "취소됨",
  COMPLETED: "완료",
  FAILED: "실패",
  PARTIAL: "일부 완료",
  STOPPED: "중지됨",
};

/** 파이프라인 단계 코드 → 한글 */
export const PIPELINE_STEP_LABELS: Record<string, string> = {
  WEBDAV_SYNC_TREE: "파일 목록 수집",
  PROCESS_PENDING_TEXT: "텍스트 파일 내용 추출",
  PROCESS_PENDING_DOCUMENTS: "문서 파일 내용 추출",
  CHUNK_COMPLETED_TEXT: "검색 단위 생성",
  EMBED_PENDING_CHUNKS: "검색 인덱스 생성",
};

/** 파이프라인 모달 단계 순서용 짧은 라벨 */
export const PIPELINE_MODAL_STEP_LABELS: Record<string, string> = {
  sync: "1. 파일 목록 수집",
  text: "2. 텍스트 파일 내용 추출",
  doc: "3. 문서 파일 내용 추출",
  chunk: "4. 검색 단위 생성",
  embed: "5. 검색 인덱스 생성",
};

export const PIPELINE_STEP_DESCRIPTIONS: Record<string, string> = {
  sync: "저장소의 폴더와 파일 목록을 읽어 DB에 저장합니다.",
  text: "txt, md, 소스코드, 설정 파일 등의 내용을 읽어 검색 가능한 텍스트로 저장합니다.",
  doc: "PDF, DOCX, XLSX, PPTX, HWPX 문서에서 텍스트를 추출합니다. HWP, DOC, XLS, PPT는 아직 지원하지 않습니다.",
  chunk: "긴 문서를 검색하기 좋은 작은 단위로 나눕니다.",
  embed: "AI 검색이 가능하도록 문서 조각을 벡터 인덱스로 변환합니다.",
};

/** 필터 드롭다운: 상태 (value = raw enum) */
export const JOB_STATUS_FILTER_OPTIONS: { value: string; label: string }[] = [
  { value: "", label: "전체" },
  { value: "PENDING", label: "대기 중" },
  { value: "RUNNING", label: "처리 중" },
  { value: "CANCELLING", label: "취소 중" },
  { value: "COMPLETED", label: "완료" },
  { value: "FAILED", label: "실패" },
  { value: "CANCELLED", label: "취소됨" },
  { value: "PARTIAL", label: "일부 완료" },
];

/** 필터 드롭다운: 작업 종류 */
export const JOB_TYPE_FILTER_OPTIONS: { value: string; label: string }[] = [
  { value: "", label: "전체" },
  { value: "PIPELINE", label: "전체 검색 반영 작업" },
  { value: "WEBDAV_SYNC_TREE", label: "파일 목록 수집" },
  { value: "PROCESS_PENDING_TEXT", label: "텍스트 파일 내용 추출" },
  { value: "PROCESS_PENDING_DOCUMENTS", label: "문서 파일 내용 추출" },
  { value: "CHUNK_COMPLETED_TEXT", label: "검색 단위 생성" },
  { value: "EMBED_PENDING_CHUNKS", label: "검색 인덱스 생성" },
  { value: "MANUAL_SCAN", label: "수동 작업" },
];

/** UI 필드·컬럼 라벨 */
export const UI_LABELS = {
  job: "작업",
  worker: "백그라운드 처리기",
  pipeline: "전체 검색 반영 작업",
  chunk: "검색 단위",
  embedding: "검색 인덱스",
  dryRun: "대상 확인",
  scanJobs: "작업 이력",
  heartbeat: "마지막 상태 갱신",
  jobParams: "작업 설정",
  retryCount: "재시도 횟수",
  workerId: "처리기 ID",
  dataSource: "저장소",
  jobType: "작업 종류",
  status: "상태",
  progress: "진행률",
  startedAt: "시작 시간",
  finishedAt: "종료 시간",
  duration: "소요 시간",
  errorMessage: "오류 메시지",
  parentJob: "상위 작업",
  pipelineStep: "단계",
  priority: "우선순위",
  jobId: "작업 ID",
  advancedInfo: "고급 정보",
  advancedSettings: "고급 설정",
  rawJobType: "원본 작업 코드",
  rawStatus: "원본 상태 코드",
} as const;

export function getJobTypeLabel(jobType: string): string {
  const k = (jobType || "").trim().toUpperCase();
  if (!k) return "—";
  return JOB_TYPE_LABELS[k] ?? jobType;
}

export function getJobStatusLabel(status: string): string {
  const u = (status || "").trim().toUpperCase();
  if (!u) return "—";
  return JOB_STATUS_LABELS[u] ?? status;
}

export function getPipelineStepLabel(code: string | null | undefined): string {
  if (!code) return "—";
  const u = code.trim().toUpperCase();
  return PIPELINE_STEP_LABELS[u] ?? code;
}

export function getJobStatusBadgeVariant(status: string): BadgeVariant {
  const u = (status || "").toUpperCase();
  if (u === "COMPLETED") return "success";
  if (u === "FAILED") return "danger";
  if (u === "RUNNING") return "warning";
  if (u === "PENDING") return "primary";
  if (u === "PARTIAL") return "warning";
  if (u === "CANCELLING") return "warning";
  if (u === "CANCELLED" || u === "STOPPED") return "neutral";
  return "neutral";
}

/** 검색 모드 */
export const SEARCH_MODE_LABELS: Record<string, string> = {
  vector: "의미 검색",
  keyword: "키워드 검색",
  hybrid: "통합 검색",
};

export function getSearchModeLabel(mode: string): string {
  const k = (mode || "").trim().toLowerCase();
  return SEARCH_MODE_LABELS[k] ?? mode;
}
