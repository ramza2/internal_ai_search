# internal-ai-search — frontend

Vite + React + TypeScript 기반 웹 UI. 백엔드(FastAPI)와 JWT 인증으로 연동합니다.

## Figma MCP UI 반영 단계

- Cursor **Figma MCP**(`get_design_context`)로 Figma Make 파일 키 `K22EXxnQSYPvcWOmEUuvMQ`의 소스·레이아웃(헤더/사이드바/톤)을 참고했습니다.
- Make 프로젝트는 Tailwind·shadcn 기반이지만, 본 레포는 **도입하지 않고** 동일한 정보 구조를 **CSS 변수 + CSS Module + 공통 `src/components/ui`** 로 이식했습니다.
- 디자인 URL: `https://www.figma.com/make/K22EXxnQSYPvcWOmEUuvMQ/Internal-Knowledge-AI-Search-UI--%EB%B3%B5%EC%82%AC-?p=f&t=fznfbJPE3rXiMl3h-0`

## 2차 UI/UX 패치 (2026-05)

Figma 톤에 맞춘 **관리자·파이프라인 화면** 정리입니다. API·라우팅·권한·기능 범위는 변경하지 않았습니다.

### 사이드바 (`Sidebar.tsx` / `Sidebar.module.css`)

- 활성 메뉴: **pill 스타일** (`border-radius: var(--radius-lg)`, `primary-soft` 배경, primary 텍스트·아이콘).
- 라벨 단축: 검색, AI 질문, 대시보드, **저장소**, 파일 현황, 작업 이력, 사용자, 감사 로그.
- 섹션 구분: **메뉴** / **관리자**. 경로(`/search`, `/admin/data-sources` 등)는 기존과 동일.
- **TODO:** 모바일 햄버거·오버레이 사이드바(현재는 데스크톱 고정 레이아웃).

### 검색 반영 파이프라인 모달 (`PipelineRunModal`)

- 상단 **권장: 전체 검색 반영 작업 등록** 패널 + 실행 모드(바로 실행 / 백그라운드 실행).
- 기본 수집 범위: **전체 저장소** (`scan_scope=FULL`, 깊이·항목 수 제한 없음). **제한 설정 직접 지정**은 sync 단계 **고급 설정**에서 선택.
- 텍스트·문서 최대 파일 크기 기본: **서버 허용 최대(256MB)** — “무제한” 표현은 폴더 깊이/항목 수에만 사용.
- 주 CTA: 백그라운드 → **전체 검색 반영 작업 등록**(primary) + **브라우저에서 순차 등록**(outline); 즉시 → **바로 전체 실행**(동기 `sync-tree`는 LIMITED만 — FULL은 백그라운드 전용).
- **실행 옵션·진행 상세** `AdvancedSection`: 백그라운드 Job 요약·자동 새로고침, 즉시 실행 진행 바·단계 카드, 마지막 단계 요약, 파일 현황.
- **단계별 실행**: 5단계 **아코디언**(한 번에 하나만 펼침). 헤더에 단계 번호·한글 라벨·`PIPELINE_STEP_DESCRIPTIONS` 요약·단계/Job 상태 배지. 단계 내부 고급 옵션·버튼·`BackgroundJobSection`·`DocumentProcessingPanel`은 유지.
- 등록 성공 시 작업 ID는 **고급 정보** 접기 영역에만 표시.

### 저장소 관리 (`DataSourcesPage`)

- 행 액션 우선순위: **검색 반영**(primary) → **접속 확인**(outline) → **설정**(secondary).
- **사용 / 사용 중지**는 `<details>추가 옵션</details>` 안으로 이동.
- 표·폼 문구: **저장소** 용어 통일(주소, 시작 폴더 등).

## 현재 UI 구조

- **디자인 토큰:** `src/styles/global.css`의 `:root` 변수(`--color-primary`, `--color-bg`, `--color-surface`, `--color-muted`, `--color-danger`, `--radius-*`, `--shadow-card` 등).
- **공통 UI:** `src/components/ui/` (`Button`, `Input`, `Select`, `Textarea`, `Badge`, `Card`, `CollapsiblePanel`, `PageHeader`, `SectionCard`, `DataTable`, `FilterBar`/`FilterField`, `FormField`, `StatCard`, `ConfirmDialog`, `PaginationBar`, `DataSourceSelect`, `StatusBadge`, `RoleBadge`, `ResultBadge`, **`HelpText`**, **`InfoBox`**, **`AdvancedSection`** 등).
- **사용자 친화 문구:** `src/utils/userFriendlyLabels.ts` — 작업 종류·상태·파이프라인 단계·검색 모드 등 API enum의 한글 표시. 개발자용 raw 값(`job_type`, `status`, `chunk_id` 등)은 상세·고급(`<details>` / `AdvancedSection`) 영역에만 노출합니다.
- **레이아웃:** `MainLayout` — 좌측 고정 사이드바(`--sidebar-width`), 상단 헤더, 본문 `pageShell`(max-width 1240px). `AuthLayout` — 상단 브랜딩 + 중앙 카드.

## 페이지 목록

| 영역 | 경로 | 설명 |
|------|------|------|
| 공개 | `/login`, `/signup` | 로그인·회원가입 |
| 인증 후 | `/change-password` | 비밀번호 변경(강제 시 안내) |
| 사용자 | `/search`, `/answer`, `/files/:fileId/preview` | 통합 검색, AI 질문, 미리보기 |
| 관리자 | `/admin`, `/admin/data-sources`, `/admin/jobs`, `/admin/file-stats`, `/admin/users`, `/admin/action-logs` | 대시보드, 데이터 소스, **작업 목록(scan_jobs)** — 목록에 **개발·검증용** 테스트 Job 생성 패널(접기) 포함, 파일 통계, 사용자, 작업 로그 |

## 인증·권한 흐름 (유지)

1. `POST /api/auth/login` → `access_token`을 `localStorage`(`internal_ai_search_access_token`)에 저장.
2. 앱 시작 시 `GET /api/auth/me`로 사용자 복구(`BootstrapGate` 등 기존 흐름).
3. `must_change_password === true` → **`/change-password`**.
4. 비밀번호 변경 후 역할에 따라 **`/admin`** 또는 **`/search`**.
5. API **401**(로그인·회원가입·비밀번호 변경 제외) 시 토큰 삭제 후 **`/login`**.
6. `/admin/*`는 `AdminRoute`로 **ADMIN**만. 일반 사용자는 `/search`로 리다이렉트.

## 관리자 대시보드 (`/admin`)

- **`GET /api/admin/dashboard/summary`** 한 번으로 사용자·데이터 소스·파일(`analysis_status`별)·chunk/embedding·최근 24시간 활동(`SEARCH` / `RAG_QUESTION` / `LOGIN` / 실패 건수)·최근 스캔 작업 5건·최근 감사 로그 10건(본문 `detail` 없음)·**서버 파이프라인(`pipelines` 카운트 + `recent_pipeline_jobs` 표)**·문제 지표 카드용 카운트를 받습니다.
- **최근 스캔 작업** 테이블의 `job_type`은 `getJobTypeLabel` / `getJobStatusBadgeVariant`(`src/utils/jobLabels.ts`)로 작업 목록과 동일한 한글·배지 규칙을 씁니다.
- **서버 파이프라인:** `pipelines` 통계 카드와 **`recent_pipeline_jobs`** 테이블(소스·상태·진행률·현재 단계·시작)이 추가되었으며, 상세 단계·하위 Job은 **`/admin/jobs`** 링크로 이동해 확인하는 흐름을 권장합니다.
- 화면: `PageHeader`(설명 + **새로고침**), `SectionCard` + `StatCard` 그리드, 문제 항목별 **관리 페이지 링크**, `DataTable` 두 개(스캔 작업 / 최근 활동), 하단 **바로 가기** 카드. **차트 라이브러리는 사용하지 않음**(카드·테이블만).
- 최초 `Loading`, API 실패 시 `ErrorMessage` + 다시 시도, 스캔/활동 테이블은 빈 배열이면 `EmptyState`. 새로고침 중 버튼 비활성화.

## 관리자 작업 목록 (`/admin/jobs`)과 Worker 스켈레톤 검증

- **작업 목록**은 `GET /api/admin/jobs`로 `scan_jobs`를 조회합니다. `PENDING` / `RUNNING` / `CANCELLING` / `COMPLETED` / `FAILED` / `CANCELLED` 등 상태는 배지(`getJobStatusBadgeVariant`)로 표시하고, **`worker_id`**, **`heartbeat_at`**, **`priority`**, **`job_params`**(목록·상세)를 확인할 수 있습니다.
- **`PIPELINE`(서버 파이프라인) 목록 행:** 작업 유형 아래에 **서버 주도 파이프라인** 안내가 붙고, **진행** 열에는 자식 Job 기준 **진행 바·%·완료 단계 수/전체 단계·현재 단계(한글)** 를 표시합니다(`progress_percent`, `pipeline_current_step`, 오버레이된 `*_files` 카운터 — 백엔드 README의 PIPELINE 해석과 동일).
- **PIPELINE 상세 모달:** 상단에 하위 Job 기준 **요약**(진행률 바, 완료/실패·RUNNING/PENDING 카운트, 현재 단계), **`job_params.steps` 순서의 단계 카드**(상태 배지·진행률·child job id·시작/종료·소요·오류 요약·**상세 보기**), 접을 수 있는 **전체 하위 Job 테이블**을 함께 둡니다. `GET .../children`의 **`summary`** 필드를 사용합니다.
- **취소:** `POST /api/admin/jobs/{job_id}/cancel` — 목록·상세에서 **취소** / **취소 요청** / **취소 요청 중**(비활성) 버튼으로 호출합니다. **`PENDING`**은 즉시 **`CANCELLED`**로 끝나고, **`RUNNING`**은 **`CANCELLING`**으로 바뀐 뒤 worker가 **다음 안전 지점**에서 **`CANCELLED`**로 마무리합니다(동기 `sync-tree` API와 무관).
- **Stale heartbeat 표시:** `RUNNING`이면서 **`heartbeat_at`**이 클라이언트 기준 **30분** 이상 지난 경우 **「heartbeat 지연」** 배지를 둘 수 있습니다. 실제 정리 기준은 백엔드 **`WORKER_STALE_TIMEOUT_MINUTES`**와 동일하게 맞추려면 추후 설정/환경 변수 연동이 필요합니다(TODO).
- **백그라운드 텍스트 처리:** `POST /api/admin/jobs/process-pending-text`로 **PROCESS_PENDING_TEXT** 큐 Job 생성. **백그라운드 동기화**와 동일하게 worker 실행이 필요합니다. **PipelineRunModal**(백그라운드 실행 모드)·`/admin/jobs`·데이터 소스의 동기 `process-pending-text`(dry_run 포함)와 병행 가능한 별도 경로입니다.
- **백그라운드 문서 처리:** `POST /api/admin/jobs/process-pending-documents`로 **PROCESS_PENDING_DOCUMENTS** 큐 Job 생성. **PipelineRunModal**(백그라운드 실행 모드)·`/admin/jobs`·동기 `process-pending-documents`(dry_run 포함)와 병행 가능합니다. worker(`python -m app.worker_main`)를 실행해야 **PENDING**이 처리됩니다. 문서 추출 후 검색/RAG에는 **Chunk 생성**과 **Embedding 생성**이 여전히 필요합니다.
- **백그라운드 Chunk 생성:** `POST /api/admin/jobs/chunk-completed-text`로 **CHUNK_COMPLETED_TEXT** 큐 Job 생성. **PipelineRunModal**(백그라운드 실행 모드)·`/admin/jobs`·동기 `chunk-completed-text`(dry_run 포함)와 병행 가능합니다. worker 실행이 필요하며, 완료 후 검색/RAG에는 **Embedding 생성**(`embed-pending-chunks`)이 별도로 필요합니다.
- **백그라운드 Embedding 생성:** `POST /api/admin/jobs/embed-pending-chunks`로 **EMBED_PENDING_CHUNKS** 큐 Job 생성. **PipelineRunModal**(백그라운드 실행 모드)·`/admin/jobs`·동기 `embed-pending-chunks`(dry_run 포함)와 병행 가능합니다. worker 실행이 필요하며, 완료 후 **`/search`**·**`/answer`** 등에 벡터가 반영됩니다.
- 긴 sync-tree 실행 중 **DB heartbeat**는 백엔드에서 일정 간격으로만 갱신합니다. **진행 중 세부 heartbeat(폴더 단위 등)는 다음 단계에서 보강**할 수 있습니다.
- 화면 상단 **개발·검증용** 접이 패널에서 **테스트 Job 생성**을 누르면 `POST /api/admin/jobs/test-enqueue`를 호출합니다. **데이터 소스**는 현재 필터에 선택된 값이 있으면 그 UUID를 쓰고, 없으면 목록의 **첫 번째 데이터 소스**를 사용합니다. 둘 다 없으면 오류 메시지를 냅니다. **`fail_test`** 체크 시 의도적으로 실패하는 큐 행이 만들어집니다.
- 별도 터미널에서 백엔드 디렉터리로 이동한 뒤 **`python -m app.worker_main`**을 실행하면 큐의 **`PENDING`** 작업이 **`RUNNING` → `COMPLETED`(또는 `fail_test` 시 `FAILED`)**로 바뀌는지 확인할 수 있습니다.
- 이 버튼·엔드포인트는 **개발/검증 전용**이며, 추후 정식 **`POST /api/admin/jobs`** API로 대체·제거될 수 있습니다(코드에 TODO 주석).

## 설치·실행

**실행 명령만 모아 둔 문서:** [`docs/로컬_실행_명령.md`](../docs/로컬_실행_명령.md) (API · worker · `npm run dev` / `build` · Docker Compose)

### 호스트에서 Vite 실행

```bash
cd frontend
npm install
npm run dev
```

기본 개발 서버: `http://localhost:5173`

```bash
npm run build
npm run preview
```

### Docker Compose 개발 (`frontend` 서비스)

저장소 루트에서 backend·DB와 함께 기동합니다.

```bash
docker compose --env-file backend/.env -f docker-compose.dev.yml up -d
# frontend만 추가/재기동
docker compose --env-file backend/.env -f docker-compose.dev.yml up -d frontend
```

| 접속 | URL |
|------|-----|
| Frontend (Vite) | http://localhost:5173 |
| Backend API | http://localhost:8000 |

**`frontend/Dockerfile`:** Node 20, `npm ci`, `npm run dev -- --host 0.0.0.0 --port 5173` (개발 전용). **운영용 nginx multi-stage 빌드는 후속 TODO.**

**API 주소 (`VITE_API_BASE_URL`):** React 앱은 **브라우저(호스트 PC)** 에서 실행됩니다. axios는 **컨테이너 내부의 `backend` 호스트명이 아니라** 호스트에 publish된 **`http://localhost:8000`** 으로 요청해야 합니다. (`docker-compose.dev.yml`의 `environment` 참고.)

- **`VITE_API_BASE_URL=http://localhost:8000`** (Compose 기본): 브라우저 → 호스트 `:8000` 직접 호출.
- **`VITE_API_BASE_URL` 비움:** 상대 경로 `/api` → Vite dev 서버 프록시. Compose 컨테이너에서는 `VITE_DEV_PROXY_TARGET=http://host.docker.internal:8000` 로 프록시 대상을 백엔드에 맞춥니다 (`vite.config.ts`).

로컬 env: `cp frontend/.env.example frontend/.env` (Git 미추적). Compose는 `docker-compose.dev.yml`의 `environment`도 참고.

값 변경 후 Vite dev 서버를 재시작하세요.

## 환경 변수 (`frontend/.env`)

- **`VITE_API_BASE_URL`**
  - **비워 두기(호스트 `npm run dev` 권장):** `/api`로 요청하고 `vite.config.ts` 프록시가 `127.0.0.1:8000`으로 전달.
  - **절대 URL (`http://localhost:8000`):** 브라우저가 백엔드로 직접 호출 (Compose Docker dev 기본). 교차 출처 시 백엔드 CORS가 필요할 수 있습니다.
- **`VITE_DEV_PROXY_TARGET`:** Docker Compose frontend 컨테이너 전용. Vite `/api` 프록시 대상 (기본 `http://host.docker.internal:8000`).

값 변경 후 `npm run dev`(또는 frontend 컨테이너 재시작)를 다시 실행하세요.

## 통합 검색 고급 필터 (`/search`)

- 기본 영역: 검색어 입력 + 검색 실행. **고급 필터**는 `CollapsiblePanel`으로 접었다 펼 수 있습니다.
- **검색 모드:** vector / keyword / hybrid.
- **데이터 소스:** `useSearchDataSources()` → **`GET /api/search/data-sources`** (활성 소스만, URL·자격 증명 미포함). 목록 로드 실패 시 필터는 **전체**만 동작하고 작은 안내 문구를 표시합니다.
- **확장자:** 쉼표 구분 입력 → `include_extensions` 배열로 변환.
- **파일 유형:** DOCUMENT, SOURCE_CODE 등 버킷 선택.
- **limit:** 10 / 20 / 50 / 100.
- **min_score:** 숫자 입력. **hybrid**일 때만 **vector_weight / keyword_weight** 입력란 표시.
- 검색 후 **적용 필터 요약** 문자열, 로딩·에러·빈 결과(`EmptyState`), 미리보기 링크는 기존과 동일한 패턴을 유지합니다.

## AI 질문 고급 옵션 (`/answer`)

- **고급 옵션** 패널: 검색 모드, 데이터 소스(`GET /api/search/data-sources`와 동일 훅), 확장자, 파일 유형, `search_limit`, `context_limit`, `answer_min_score`, 검색용 `min_score`, `temperature`, `max_context_chars`, hybrid 가중치, **dry_run** 체크박스.
- **keyword** 모드 선택 시: 임베딩 없이 키워드 검색만 쓴다는 짧은 안내 배너.
- **dry_run:** LLM 없이 `context_preview` 테이블로 후보 청크를 확인. 일반 답변과 **근거 부족** 문구는 서로 다른 스타일 박스로 구분.
- 브라우저 세션에 옵션·결과를 저장(`ragSessionCache` v2)해 새로고침 후에도 복원됩니다.

## 작업 목록 (`/admin/jobs`)

- **API:** `src/api/adminJobsApi.ts` — `GET /api/admin/jobs`, `GET /api/admin/jobs/{id}`, `GET /api/admin/jobs/{id}/children`, `GET /api/admin/jobs/{id}/failures`, **`POST /api/admin/pipeline-jobs`**, **`POST /api/admin/jobs/{id}/cancel`**, **`POST /api/admin/jobs/{id}/retry`**, **`POST /api/admin/jobs/sync-tree`**, **`POST /api/admin/jobs/process-pending-text`**, **`POST /api/admin/jobs/process-pending-documents`**, **`POST /api/admin/jobs/chunk-completed-text`**, **`POST /api/admin/jobs/embed-pending-chunks`**, **`POST /api/admin/jobs/test-enqueue`** (개발·검증용, `src/types/adminJobs.ts`).
- **job_type 표시:** `src/utils/jobLabels.ts`의 `getJobTypeLabel`로 한글 라벨(예: `MANUAL_SCAN` → 수동 작업, `WEBDAV_SYNC_TREE` → 재귀 동기화). 백엔드에만 있는 코드는 그대로 표시합니다. 상태 배지는 `getJobStatusBadgeVariant`로 대시보드와 공유합니다(`CANCELLING`·`CANCELLED` 포함).
- **요청자:** 상세 모달에서 `requested_by_name` / `requested_by_login_id`를 표시합니다. 값이 없으면 **알 수 없음**(과거 `MANUAL_SCAN` 행 등).
- **필터:** `status`, `job_type`, `data_source_id`, `keyword`(소스 이름·`current_file_path`·`error_message` ILIKE), `from_date` / `to_date`, `limit`(20/50/100), `offset`. 상태 필터에 **`CANCELLING`**, **`CANCELLED`** 포함. **조회** 시 적용·offset 리셋, **초기화**로 필터 초기화.
- **백그라운드 Job 생성:** **백그라운드 동기화 (sync-tree)**, **백그라운드 텍스트 처리**, **백그라운드 문서 처리**, **백그라운드 Chunk 생성**, **백그라운드 Embedding 생성** 섹션에서 각각 `sync-tree`, `process-pending-text`, `process-pending-documents`, `chunk-completed-text`, **`embed-pending-chunks`** 호출. 성공 시 job_id·worker 실행 안내(Embedding 섹션에는 완료 후 검색/RAG 반영 안내 포함).
- **목록:** 작업 유형(한글 + 코드)·상태 배지·소스명·**우선순위**·**job_params**(짧은 JSON)·**worker_id**·**heartbeat**·(지연 시 **heartbeat 지연** 배지)·시작/종료·`formatDuration` 소요 시간·진행률(퍼센트 + processed/total)·완료/실패/스킵/삭제 카운트·오류 요약·**상세**·**취소/취소 요청**·**재시도**(`FAILED`/`CANCELLED`/`PARTIAL`만; `retry_count >= max_retries`이면 **재시도 한도 도달** 안내 후 **강제 재시도**로 `force=true` 확인) 버튼(`ConfirmDialog`).
- **상세:** 모달에서 job 메타·카운터·`error_message` 및 **실패 목록** 테이블(`scan_failures`). 실패가 없으면 `EmptyState`. 상단에 취소·재시도(목록과 동일 정책). `retry_count`/`max_retries`, `parent_job_id`, `pipeline_step`, `job_params`의 **`retried_from_job_id`** 표시. 재시도 성공 시 **새 Job 보기**로 새 `PENDING` 행 상세를 열 수 있습니다. **`python -m app.worker_main`** 실행이 필요합니다.
- **경고:** `scan_jobs` / `scan_failures` 테이블이 없는 개발 DB에서는 API가 빈 목록과 `warnings`를 주며 UI에 안내합니다.
- **백엔드 감사:** 취소 API는 **`JOB_CANCEL_REQUEST`**, 재시도 API는 **`JOB_RETRY_REQUEST`**를 best-effort로 남길 수 있습니다. 목록·상세 **GET**은 `action_logs`에 기록하지 않습니다.
- **개발·검증용 테스트 Job:** 상단 접이 패널에서 `POST /api/admin/jobs/test-enqueue` 호출(위 **관리자 작업 목록과 Worker 스켈레톤 검증** 참고). 정식 범용 job 생성 API가 생기면 UI·엔드포인트를 대체할 예정입니다.
- **과거 데이터:** DB에 남아 있는 오래된 행은 `job_type`이 `MANUAL_SCAN`일 수 있습니다(백엔드가 일괄 백필하지 않음). 실제 실행 단계는 `action_logs`와 시간대를 맞춰 추정해야 합니다.
- **Worker 준비 필드(마이그레이션 022):** 테이블에 `priority`, `worker_id`, `heartbeat_at`, `pipeline_step`, `retry_count` / `max_retries`, `cancel_requested`, `parent_job_id`, `job_params` 등이 있으면 목록·상세에 표시합니다. **Embedding** 등 백그라운드 Job은 CLI에서 **`python -m app.worker_main`**을 실행해야 **`PENDING`**이 처리됩니다. `job_params`는 `<details>` 로 접기/펼치기 JSON(서버에서 비밀 키 제거).

## 작업 로그 (`/admin/action-logs`)

- **필터:** user_id, action_type(선택 상수 + 전체), result, data_source, target_file_id, keyword, from_date, to_date, limit(20/50/100/200).
- **파이프라인 작업** 프리셋: `WEBDAV_SYNC_TREE`로 `action_type`을 맞춘 뒤 조회합니다. API는 `action_type` **단일값**만 받으므로, `PROCESS_PENDING_TEXT`, `PROCESS_PENDING_DOCUMENTS`, `CHUNK_COMPLETED_TEXT`, `EMBED_PENDING_CHUNKS` 등은 드롭다운에서 바꿔 순차 확인합니다.
- **조회** 시에만 적용 필터가 반영되며 offset은 0으로 리셋됩니다. **필터 초기화**로 전부 초기화합니다.
- **PaginationBar:** offset 기반 이전/다음, 현재 페이지·총 건수 표시. `total`으로 마지막 페이지를 계산합니다.
- 상세 JSON은 행 **펼치기**로 유지합니다.

## 사용자 관리 (`/admin/users`)

- 상태·역할·키워드·limit(20/50/100) **조회** 후 목록 로드. **필터 초기화** 지원.
- **PaginationBar** + API `total` 표시. 승인·역할 변경 등 작업 후 **현재 필터·offset**을 유지한 채 목록만 다시 불러옵니다.
- **StatusBadge / RoleBadge**로 상태·역할 표시. 마지막 관리자 보호 등 API 오류는 **ErrorMessage**로 구분 표시(목록 로드 오류와 별도).

## 문서 파일 처리 UI (파이프라인 모달 Step 3)

- **데이터 소스** 목록에서는 **파이프라인 실행** 모달만 엽니다. 문서 추출 UI는 모달 **3. 문서 파일 처리** 단계에서 `DocumentProcessingPanel`을 그대로 사용합니다(`POST /api/data-sources/{id}/process-pending-documents`).
- **지원 포맷:** PDF, DOCX, XLSX, PPTX, HWPX, **HWP (바이너리, hwp5txt)**.
- **미지원:** DOC, XLS, PPT (구형 OLE).
- **HWP Automation/COM 미사용.** HWPX는 ZIP/XML, HWP는 Linux/headless `hwp5txt` 변환. 검색 근거는 **변환 텍스트 기준 줄 번호**(원본 HWP 페이지 아님). 서버에 pyhwp/hwp5txt 설치 및 **AGPL 법무 검토** 필요. OCR 없음.
- **dry_run:** 「대상 확인」으로 `dry_run=true` 호출 — 다운로드·DB 반영 없이 대상만 확인.
- **reprocess_skipped:** 기존 `UNSUPPORTED_EXTENSION`으로 스킵된 지원 확장자 파일을 다시 처리할 때 사용.
- **추출되지 않은 HWP 다시 처리** (Step 3 하단 접이식 영역, `HwpSkippedReprocessSection`):
  - **대상:** 이전에 내용 추출이 되지 않아 제외된 **HWP만** (일반 대기 문서·이미 완료된 문서 제외). **전체 검색 반영·일반 문서 처리 Job에는 자동 포함되지 않습니다.**
  - **재처리 대상 확인:** `POST .../process-pending-documents?dry_run=true` + only 모드 — **DB 변경 없음**, 대상 수·목록만 표시.
  - **백그라운드 재처리 작업 등록:** `POST /api/admin/jobs/process-pending-documents` (`PROCESS_PENDING_DOCUMENTS`, worker 필요). 동기 「문서 처리 실행」은 제공하지 않습니다.
  - **완료 후:** 파일 내용은 다시 추출되지만, 검색/RAG 반영을 위해 **검색 단위 생성**·**검색 인덱스 생성**을 별도로 실행해야 할 수 있습니다. 작업 이력은 **`/admin/jobs`** 에서 확인합니다.
- **백그라운드 실행** 모드에서는 동기 「문서 처리 실행」 버튼을 숨기고, 같은 폼으로 **문서 처리 Job 생성**(`POST /api/admin/jobs/process-pending-documents`)만 제공합니다. 실제 추출 후 검색/RAG에는 **Chunk 생성**과 **Embedding**이 필요합니다.

## 인덱싱 파이프라인 실행 UI (`/admin/data-sources`)

- 각 **저장소** 행의 **검색 반영** → 오버레이 **`PipelineRunModal`**에서 (1) `sync-tree` (2) `process-pending-text` (3) `process-pending-documents` — `DocumentProcessingPanel` (4) `chunk-completed-text` (5) `embed-pending-chunks` 를 **아코디언 단계**로 다룹니다.
- **실행 모드 (기본: 백그라운드 실행)**
  - **바로 실행:** 각 단계는 동기 `POST /api/data-sources/{id}/...` 를 호출합니다. 상단 **바로 전체 실행**으로 5단계를 순차 HTTP 실행합니다(옵션은 카드 입력값, 자동 실행 시 `dry_run=false` 강제).
  - **백그라운드 실행:** **전체 작업 등록** → `postAdminPipelineJob` (`POST /api/admin/pipeline-jobs`, 권장). **브라우저에서 순차 등록** → 브라우저가 단계별 `POST /api/admin/jobs/...` 를 순차 등록(레거시, 탭 종료 시 미등록 단계 중단 가능). **대상 확인(dry_run)** 은 동기 API. 단계별 Job 상태는 **`getAdminJob`** 폴링·**상태 새로고침**·**자동 새로고침(5초)** (`AdvancedSection` 안). 취소는 `/admin/jobs` 와 동일 정책.
  - 진행·`pipeline_job_id`·하위 Job 상세는 **`/admin/jobs`**(및 대시보드 최근 파이프라인)에서 확인합니다. 모달에는 요약 안내와 **고급 정보**의 작업 ID만 둡니다.
- **dry_run:** 텍스트·문서·Chunk·Embedding 단계의 **대상 확인** 버튼은 서버가 대상만 계산하고 DB/다운로드를 바꾸지 않는 호출입니다. **즉시 실행** 모드에서 **실제 실행**은 DB·파일 처리가 일어날 수 있으며 공통 확인 다이얼로그를 거칩니다. **sync-tree**는 dry_run이 없으므로 **동기화 실행**(즉시 모드) 또는 **동기화 Job 생성**(백그라운드 모드) 전에 옵션을 확인하세요.
- **중간 실패 (즉시 자동):** 어느 단계든 HTTP 오류·예외·또는 응답 `status === "error"` 이면 그 단계는 `error`, 이후 단계는 `skipped` 로 표시하고 자동 실행을 중단합니다. 응답 `status === "partial"` 인 경우에는 경고 문구를 남기고 **다음 단계는 계속 진행**합니다(`failed_count`가 커도 동일).
- **진행·소요 시간:** **즉시 실행** 자동 실행 중 상단에 완료 수·현재 단계·실패/건너뜀 수·프로그레스 바를 표시하고, 단계별 카드에 시작/종료 시각·`formatDuration(ms)` 기반 소요 시간을 표시합니다.
- **즉시 실행 한계:** 백그라운드 큐가 아니라 **탭이 열려 있는 동안의 순차 HTTP 요청**입니다.
- 단계별 응답은 각 카드 아래에 요약·경고·`items` 상위 20건(초과 시 안내 문구)으로 표시합니다. 상단 바에 마지막 실행 단계/결과·완료·실패 단계 수를 표시합니다(즉시 실행 결과 기준).
- **현재 파일 현황 보기**는 `GET /api/data-sources/{id}/file-stats`를 호출합니다. 단계 **수동** 실행 후에는 기존과 같이 `onRefresh`로 목록을 갱신합니다. **자동 실행**이 모두 끝난 뒤에도 한 번 갱신하며, 화면 상단 **목록 새로고침**으로 데이터 소스 테이블을 다시 불러올 수 있습니다.
- 자동 실행(즉시)·백그라운드 순차 등록이 돌아가는 동안에는 닫기·해당 모드의 전체 실행·각 단계 실행·Job 생성 버튼이 비활성화되고, 문서 단계 패널의 동기 실행도 비활성화됩니다.

## 데이터 소스 API 구분

- **검색·AI 질문:** `useSearchDataSources()` → `GET /api/search/data-sources` — 일반 **USER**도 호출 가능(ACTIVE + 비밀번호 변경 완료). 응답에는 `id`, `name`, `source_type`, `description`, `last_scan_at`, `last_connection_success`만 포함됩니다.
- **관리자 화면** (`DataSourcesPage`, 작업 로그 필터, 파일 통계 소스 선택 등): `useDataSources()` → `GET /api/data-sources` — **ADMIN** 전용 CRUD 목록(기존과 동일).

### 관리자용 문서 처리 API (curl)

백엔드 **Step 21** `process-pending-documents`는 UI 버튼 없이도 curl로 호출할 수 있습니다. 인제스트 후에는 `chunk-completed-text` → `embed-pending-chunks` 순으로 이어가면 검색/RAG에 반영됩니다.

```bash
curl -X POST "http://localhost:8000/api/data-sources/{id}/process-pending-documents?limit=20&include_extensions=pdf,docx,hwpx" \
  -H "Authorization: Bearer <admin-token>"

curl -X POST "http://localhost:8000/api/data-sources/{id}/process-pending-documents?reprocess_skipped=true&include_extensions=pdf,docx,xlsx,pptx,hwpx,hwp" \
  -H "Authorization: Bearer <admin-token>"

curl -X POST "http://localhost:8000/api/data-sources/{id}/process-pending-documents?dry_run=true" \
  -H "Authorization: Bearer <admin-token>"
```

## 파일 통계 (`/admin/file-stats`)

- **전체:** `GET /api/files/stats` + `include_deleted` 쿼리.
- **특정 소스:** `GET /api/data-sources/{id}/file-stats`.
- 상단에서 소스 선택·삭제 포함 체크박스·새로고침.
- 요약 카드: 전체 항목, 파일 수, 디렉터리 수, 전체 용량, 마지막 동기화(+ 파일 최근 수정 힌트).
- 테이블: 분석 상태·파일 유형·확장자·대용량 TOP. TOP 목록은 확장자 휴리스틱으로 **텍스트 미리보기** 가능 시 `/files/{id}/preview` 링크.
- **문서 처리·스킵 안내** 카드: `SKIPPED` 건수·PDF 등 문서형 확장자 처리 안내(데이터 소스의 **파이프라인 실행** 모달 Step 3로 연결).

## 타입 (`src/types`)

- `search.ts`, `answer.ts`, `admin.ts`, `adminDashboard.ts`, `dataSource.ts`(`AdminDataSource` 별칭), **`searchDataSource.ts`**(`SearchDataSource`), `file.ts`, **`documentProcessing.ts`**, **`pipeline.ts`**, **`syncTree.ts`**, **`textProcessing.ts`**, **`chunking.ts`**, **`embedding.ts`** 에 요청/응답·파이프라인 UI 상태 타입을 맞춰 두었습니다.

## 아직 남은 TODO (프론트)

- **URL query state**와 필터·페이지(offset) 동기화 — 작업 로그·사용자 관리 등.
- **모바일 사이드바**(햄버거·오버레이) — 2차 패치에서 스타일만 반영.
- 관리자 **온보딩**(첫 방문 시 저장소 연결·검색 반영 안내).
- 파이프라인 **실패 후 재개** UX(실패 단계부터 이어 실행 등) — 현재는 작업 이력에서 재시도·수동 단계 실행.
- **HWP** 지원 정책 UI(미지원 안내·HWPX 권장) 강화.
- **차트 라이브러리** 도입(파일 통계 시각화).
- 미리보기 **쿼리 하이라이트** 정밀(offset 기반).
- 백엔드 **소스별 사용자 권한(ACL)** 도입 시 검색용 목록 API에서 행 필터링.

## 다음 단계 제안

- React Query 등으로 목록·통계 **캐시/재검증** (선택).
- 차트 라이브러리로 파일 통계 시각화(선택).
- Figma Code Connect 연동 시 `ui` 컴포넌트와 1:1 매핑.
