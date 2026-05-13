# scan_jobs 기반 백그라운드 작업 전환 갭 분석

> **목적:** 레포지토리에 포함된 **실제 백엔드 코드·SQL 마이그레이션**을 기준으로 `scan_jobs` / `scan_failures` 현황과, `docs/07_아키텍처/백그라운드작업_워커구조.md`에서 제안한 워커 구조 사이의 **차이(갭)** 를 정리한다.  
> **범위:** 본 문서 작성만 수행한다. DB 스키마 변경, worker 구현, API/프론트 수정은 하지 않는다.

---

## 분석 대상 범위 (실제 조회 결과)

| 대상 | 레포 내 위치 | 비고 |
|------|----------------|------|
| `scan_jobs` DDL | **`backend/db/migrations/*.sql`에 없음** | `019_app_users.sql`, `020_action_logs.sql`만 존재. 테이블 생성 SQL은 본 레포에 포함되지 않았다. |
| `scan_failures` DDL | **동일하게 마이그레이션에 없음** | 코드 주석·INSERT로 형상만 추정 가능. |
| `scan_jobs` 쓰기 | `backend/app/services/scan_jobs_service.py` | `create_scan_job`, `complete_scan_job`, `fail_scan_job` |
| `scan_failures` 쓰기 | `backend/app/services/scan_failures_service.py` | `record_scan_failure` |
| sync-root | `file_sync_service.py` + `data_sources.py` `POST .../sync-root` | `WEBDAV_SYNC_ROOT` action_log |
| sync-tree | `file_recursive_sync_service.py` + `.../sync-tree` | `WEBDAV_SYNC_TREE` action_log |
| 텍스트/문서/chunk/embed | 각 `*_service.py` + `data_sources.py` | 대응 `action_type` 로깅 |
| 대시보드 | `admin_dashboard_service.py` | `recent_scan_jobs` 조회 |
| 설계 참고 | `docs/07_아키텍처/백그라운드작업_워커구조.md` | |
| README | **`backend/README.md`** (scan_jobs·scan_failures 상세) | 루트 `README.md`에는 `scan_jobs` 문자열 없음 |

---

## 1. 현재 scan_jobs 스키마 정리

### 1.1 DDL 부재에 대한 결론

- **레포에 `CREATE TABLE scan_jobs` / enum 정의 SQL이 없다.** 운영 DB에는 별도 초기화 스크립트나 미커밋 마이그레이션이 있을 수 있으나, **본 갭 분석은 “애플리케이션이 가정하는 스키마”** 를 `scan_jobs_service.py`의 `INSERT`/`UPDATE`와 `admin_dashboard_service.py`의 `SELECT`로 역추적한다.

### 1.2 컬럼 표 (코드 기준 역추적)

| column_name | data_type (추정) | nullable | default | 현재 사용 여부 | 비고 |
|-------------|------------------|----------|---------|----------------|------|
| `id` | UUID | NOT NULL | `gen_random_uuid()` | 사용 | `create_scan_job` RETURNING |
| `data_source_id` | UUID | NOT NULL | — | 사용 | INSERT에 필수 |
| `job_type` | `scan_job_type` (enum) | NOT NULL | `'MANUAL_SCAN'` | 사용 | **항상 동일 리터럴** |
| `status` | `scan_job_status` (enum) | NOT NULL | `'RUNNING'` | 사용 | 생성 시 RUNNING, 완료 시 COMPLETED, 실패 시 FAILED |
| `started_at` | TIMESTAMP | NOT NULL | `NOW()` | 사용 | 생성 시 |
| `finished_at` | TIMESTAMP | NULL | — | 사용 | `complete_scan_job` / `fail_scan_job`에서 `NOW()` |
| `total_files` | INTEGER | NULL | INSERT 시 `0` | 사용 | 완료 시 갱신 |
| `processed_files` | INTEGER | NULL | — | 사용 | 완료 시만 갱신 (`fail_scan_job`에서는 미설정) |
| `completed_files` | INTEGER | NULL | — | 사용 | 완료 시만 |
| `failed_files` | INTEGER | NULL | — | 사용 | 완료 시만 |
| `skipped_files` | INTEGER | NULL | — | 사용 | 완료 시만 |
| `deleted_files` | INTEGER | NULL | — | 사용 | 완료 시만 (sync-tree 등) |
| `current_file_path` | TEXT 등 | NULL | — | **부분** | `complete_scan_job`에서 **`NULL`로만 갱신**. 진행 중 경로 업데이트용 API **없음** |
| `error_message` | VARCHAR/TEXT | NULL | — | 사용 | 완료 시 요약(부분 성공), 실패 시 메시지 |
| *(대시보드 조회)* | — | — | — | **API 미반환** | `admin_dashboard_service._SQL_RECENT_SCAN_JOBS` / `RecentScanJobItem`에 `error_message` 없음 → 최근 job 카드에 실패 사유 노출 시 **갭** |
| `requested_by` | UUID | NULL | `NULL` | **컬럼 존재 가정** | INSERT에 명시; **항상 NULL** |
| `created_at` | TIMESTAMP | NOT NULL | `NOW()` | 사용 | |
| `updated_at` | TIMESTAMP | NOT NULL | `NOW()` | 사용 | 완료/실패 시 갱신 |

**요청하신 필드 대조**

- 위 표에 나열한 항목은 **코드에서 참조됨** (또는 `NULL` 고정).
- 레포 SQL로 **nullable/default의 최종 확정**은 불가 → DB에 직접 `\d scan_jobs` 등으로 검증 필요.

### 1.3 scan_failures (코드 기준)

`scan_failures_service.py`의 `INSERT` 기준 가정 컬럼:

| column_name | 현재 사용 여부 |
|-------------|----------------|
| `id` | 사용 (`gen_random_uuid()`) |
| `scan_job_id` | 사용 |
| `data_source_id` | 사용 |
| `file_id` | 사용 |
| `remote_path` | 사용 |
| `error_code` | 사용 |
| `error_message` | 사용 |
| `created_at` | 사용 (`NOW()`) |

**DDL:** 레포 마이그레이션에 **없음**.

---

## 2. 현재 scan_jobs.status 값 정리

### 2.1 코드에서 사용하는 PostgreSQL enum 캐스팅

- `create_scan_job`: `'RUNNING'::scan_job_status`
- `complete_scan_job`: `'COMPLETED'::scan_job_status`
- `fail_scan_job`: `'FAILED'::scan_job_status`

즉 애플리케이션 레이어에서 **명시적으로 쓰는 값은 `RUNNING`, `COMPLETED`, `FAILED` 세 가지**이다.  
DB enum에 다른 값이 **정의만** 되어 있고 코드가 안 쓰는 경우는 **레포만으로는 확인 불가**.

### 2.2 설계 문서(`백그라운드작업_워커구조.md`) 제안 상태와 비교

| 상태 | 현재 존재 여부 (코드 기준) | 현재 사용 위치 | 워커 구조에서 필요 여부 | 처리 방향 |
|------|---------------------------|----------------|-------------------------|-----------|
| `RUNNING` | 있음 | `create_scan_job` | 필요 | 유지 |
| `COMPLETED` | 있음 | `complete_scan_job` | 필요 | 유지; 워커에서 “부분 성공”과 구분하려면 `PARTIAL` 분리 검토 |
| `FAILED` | 있음 | `fail_scan_job` | 필요 | 유지 |
| `PENDING` | **코드에서 미사용** (큐 대기) | — | **필수** (DB polling worker) | enum 추가 + `create_scan_job`를 “enqueue만” 할 때 사용 |
| `CANCELLED` | 코드에서 미사용 | — | 취소 API 도입 시 필요 | enum·전이 규칙 추가 |
| `CANCELLING` | 코드에서 미사용 | — | 안전 중단 시 권장 | enum 추가 |
| `PARTIAL` | 코드에서 미사용 | — | 일부 파일 실패 후 job 종료 시 유용 | 현재는 `COMPLETED` + `error_message`로 흡수(README 기술과 동일). 워커에서는 `PARTIAL` 분리 검토 |
| `STOPPED` | 코드에서 **미참조** | — | 정의 여부는 DB 확인 필요 | `CANCELLED`와 중복 시 하나로 통합 검토 |

**마이그레이션:** DB에 이미 `STOPPED` 등 레거시 값이 있으면 백필·매핑 표가 필요하다. 레포 DDL 부재로 **판단 보류**.

---

## 3. 현재 scan_jobs.job_type 값 정리

### 3.1 코드에서 사용하는 값

`scan_jobs_service.create_scan_job`의 INSERT는 **항상** 다음만 사용한다.

```text
'MANUAL_SCAN'::scan_job_type
```

### 3.2 action_logs의 action_type (참고: scan_jobs와 별도)

`data_sources.py`에서 파이프라인 관련 호출에 대해 기록하는 값 (일부만 발췌):

| API / 의미 | action_type (`write_action_log_safe`) |
|------------|----------------------------------------|
| sync-root | `WEBDAV_SYNC_ROOT` |
| sync-tree | `WEBDAV_SYNC_TREE` |
| process-pending-text | `PROCESS_PENDING_TEXT` |
| process-pending-documents | `PROCESS_PENDING_DOCUMENTS` |
| chunk-completed-text | `CHUNK_COMPLETED_TEXT` |
| embed-pending-chunks | `EMBED_PENDING_CHUNKS` |

→ **감사 로그는 작업 종류별로 세분화**되어 있으나, **`scan_jobs.job_type`은 전부 `MANUAL_SCAN`으로 동일**하다.

### 3.3 job_type 비교 표

| job_type (이름) | 현재 scan_jobs에 존재 | 현재 사용 API·서비스 | 워커 전환 대상 | 권장 job_type 이름 (비동기 시) |
|-----------------|----------------------|----------------------|----------------|--------------------------------|
| `MANUAL_SCAN` | **유일하게 사용** | sync-root, sync-tree, text, document, chunk, embed (실행 시) | 전부 | 유지하되 의미가 모호 → **`SYNC_ROOT` / `SYNC_TREE` / …** 로 분리 권장 |
| `SYNC_ROOT` | 없음 (DB enum 미확인) | sync-root | 대상 | `WEBDAV_SYNC_ROOT` 또는 `SYNC_ROOT` |
| `SYNC_TREE` | 없음 | sync-tree | 대상 | `WEBDAV_SYNC_TREE` |
| `PROCESS_PENDING_TEXT` | 없음 | 텍스트 처리 | 대상 | action_log와 동일 문자열 권장 |
| `PROCESS_PENDING_DOCUMENTS` | 없음 | 문서 처리 | 대상 | 동일 |
| `CHUNK_COMPLETED_TEXT` | 없음 | chunk | 대상 | 동일 |
| `EMBED_PENDING_CHUNKS` | 없음 | embed | 대상 | 동일 |

**분석 결론:**  
현재 **모든 장시간 작업이 `scan_jobs` 상에서는 동일 `MANUAL_SCAN`**이다. 대시보드 `recent_scan_jobs`만으로는 **어느 API에서 생성된 job인지 구분이 어렵다** (HTTP 로그·`action_logs`와 시간 맞춰 추정하는 수준).  
워커 전환 전 **`job_type` 세분화(또는 `job_params`에 원 API 식별자 저장)** 가 강하게 권장된다.

---

## 4. 현재 코드 사용 방식 분석

### 4.1 scan_jobs 서비스 API (실제 함수명)

| 함수 | 파일 | 역할 |
|------|------|------|
| `create_scan_job(ds_id)` | `scan_jobs_service.py` | `MANUAL_SCAN` + `RUNNING` + `requested_by=NULL`, `total_files=0` |
| `complete_scan_job(...)` | 동일 | `COMPLETED`, 카운터 일괄, `current_file_path=NULL`, `error_message` 선택 |
| `fail_scan_job(job_id, error_message)` | 동일 | `FAILED`, `finished_at`, `error_message`만 (**카운터 미갱신**) |

**없는 함수:** `update_scan_job_progress` 같은 **중간 진행률 갱신**은 `scan_jobs_service`에 **없다**.

### 4.2 호출처 요약

| 서비스 | scan_job 생성 | 완료/실패 |
|--------|----------------|-----------|
| `file_sync_service` (sync-root) | O | complete / fail |
| `file_recursive_sync_service` (sync-tree) | O | complete / fail (다수 경로) |
| `pending_text_processor_service` | **dry_run이 아닐 때만** | complete / fail |
| `pending_document_processor_service` | dry_run 아닐 때만 | complete / fail |
| `chunk_text_processor_service` | dry_run 아닐 때만 | complete / fail |
| `chunk_embedding_service` | dry_run 아닐 때만 | complete / fail |

### 4.3 필드 채움 규칙

- **시작:** `job_type`, `status=RUNNING`, `started_at`, `data_source_id`, `total_files=0`, `requested_by=NULL`, 타임스탬프.
- **성공 완료:** `complete_scan_job`이 **모든 카운터 + `error_message`(선택) + `finished_at` + `current_file_path=NULL`**.
- **실패:** `fail_scan_job`은 **`status`, `finished_at`, `error_message`, `updated_at`** 중심. **진행 카운터는 이전 값 유지 또는 미기록**(실패 시점에 스냅샷 없음).
- **`current_file_path`:** 완료 시 NULL만 설정. **진행 중 업데이트 없음** → 워커 설계의 “현재 파일” 표시와 **갭 큼**.

### 4.4 scan_failures 연동

- `record_scan_failure(scan_job_id, data_source_id, file_id, remote_path, error_code, error_message)`.
- 허용 코드: `DOWNLOAD_FAILED`, `DECODING_FAILED`, `FILE_TOO_LARGE`, `BINARY_CONTENT_DETECTED`, `PARSING_FAILED`, `PASSWORD_PROTECTED`, `NO_EXTRACTABLE_TEXT`.
- **`CHUNK_SAVE_FAILED`:** `chunk_text_processor_service.py`에서 호출하나, **`_PERSISTABLE_ERROR_CODES`에 없어 INSERT가 no-op** 될 수 있다. `backend/README.md`는 기록한다고 설명 → **문서·코드 불일치 갭**.

### 4.5 action_logs와의 관계

- **중복 아님·보완 관계:**  
  - `action_logs`: **누가( user_id )**, **어떤 HTTP 작업(action_type)**, **성공/실패(result)**, 쿼리 파라미터 요약 `detail`.  
  - `scan_jobs`: **배치 단위 진행·카운터**, `scan_job_id`가 응답 JSON에 포함되어 프론트에서 표시 가능.
- **직접 FK 연결 없음** (`action_logs`에 `scan_job_id` 컬럼은 본 분석 범위의 API 코드에서 미확인).
- **대시보드:** `recent_scan_jobs`와 `recent_actions`는 **별도 쿼리**; 상호 조인되지 않음.

---

## 5. 워커 구조에 필요한 추가 필드 갭 분석

(설계 문서 제안 필드 vs 현재 코드에서 확인된 컬럼)

| 필드 | 현재 존재 여부 | 필요도 | 이유 | 추가 권장 여부 |
|------|----------------|--------|------|----------------|
| `requested_by` | **컬럼은 INSERT에 존재**, 값은 항상 NULL | 권장 | 감사·쿼터; 워커에도 동일 | ADMIN `user_id` 채우기 |
| `job_params` (JSONB) | 코드상 **없음** | 필수에 가깝음 | limit, dry_run, 경로 등 큐 재현·재시도에 필요 | **추가 권장** |
| `progress_percent` | 없음 | 선택 | 카운터로 계산 가능하면 생략 가능 | 선택 |
| `cancel_requested` | 없음 | 권장 | 취소 시그널 | **추가 권장** |
| `worker_id` | 없음 | 권장 | stale·디버깅 | **추가 권장** |
| `heartbeat_at` | 없음 | 필수에 가깝음 | 재시작·stale 복구 | **추가 권장** |
| `parent_job_id` | 없음 | 권장 | 파이프라인 job | 파이프라인 도입 시 |
| `pipeline_step` | 없음 | 권장 | 단계 표시 | 파이프라인 도입 시 |
| `retry_count` / `max_retries` | 없음 | 권장 | 운영 정책 | **추가 권장** |
| `priority` | 없음 | 선택 | 다중 tenant 시 | 선택 |
| `locked_at` | 없음 | 선택 | `FOR UPDATE` 외 별도 lease | DB worker면 SKIP LOCKED로 대체 가능 |
| `locked_by` | 없음 | 선택 | worker 식별과 중복 가능 | `worker_id`와 통합 검토 |

---

## 6. 인덱스 갭 분석

### 6.1 레포 마이그레이션 현황

- `backend/db/migrations`에는 **`scan_jobs` / `scan_failures`용 `CREATE INDEX`가 없다.**

### 6.2 제안 인덱스 (마이그레이션 초안 수준, 미적용)

**scan_jobs (worker polling)**

- `(status, created_at)` — `PENDING`/`RUNNING` 폴링 + 오래된 순 처리  
- `(status, job_type)` — 유형별 worker 분리 시  
- `(data_source_id, status)` — 소스별 대기/실행 조회·중복 방지 쿼리

**scan_jobs (파이프라인·운영)**

- `(parent_job_id)` — child 조회  
- `(heartbeat_at)` — stale 스윕 (부분 인덱스 `WHERE status='RUNNING'` 등 PostgreSQL 버전에 맞게)

**scan_failures**

- `(scan_job_id)` — job 상세에서 실패 목록  
- `(file_id)` — 파일 단위 추적 (카디널리티·쓰기 패턴에 따라 선택)

---

## 7. 중복 실행 방지 정책 분석

### 7.1 현재 동기 API 동작

- `data_sources` 라우터는 요청마다 서비스 함수를 **즉시 실행**한다.
- **`scan_jobs`나 DB 레벨에서 “동일 data_source에 동시 작업 1건”을 막는 로직은 검색 범위 내에 없다.**
- 따라서 이론상 **같은 `data_source_id`에 sync-tree를 동시에 두 번 호출 가능**하다(두 HTTP 요청이 병렬로 들어올 경우).

### 7.2 케이스별 현재 가능성 및 권장

| 케이스 | 현재 가능성 | 권장 정책 (워커 도입 시) |
|--------|-------------|---------------------------|
| 동일 data_source + sync-tree 동시 | **가능** (앱 차단 없음) | 동일 `job_type`에 `RUNNING`/`PENDING` 있으면 **거절 또는 큐잉** |
| sync-tree 중 + process-pending-text | **가능** | 데이터 정합성 리스크 → **동일 소스에 “인덱싱 계열” job 동시 1개** 또는 단계 허용 매트릭스 정의 |
| chunk 중 + embedding | **가능** | 순서 의존이 있으면 **파이프라인 단일 job** 또는 **단계 락** |
| embedding 중 + reembed | **가능** | 동일 논리 리소스 경합 → **직렬화 또는 embed job 단일** |
| 문서 처리 중 + chunk | **가능** | 운영 가이드: chunk 전 문서 완료 권장; **정책으로 강제할지** 결정 |
| search / answer / preview | 일반 사용자 경로 | **인덱싱 job과 독립** 유지 권장 |
| data_source 설정 변경 | 별도 API | 작업 중 변경은 **경고 또는 잠금** 검토 |

---

## 8. 기존 동기 API와 비동기 API 병행 전략 (코드 기준 구체화)

`백그라운드작업_워커구조.md`의 4단계 전략을, **현재 라우트·로그·scan_job 생성 여부**에 맞춰 보완한다.

| 현재 API | 현재 동작 | 비동기 job_type 후보 | 동기 API 유지 | 비동기 전환 우선순위 |
|----------|-----------|----------------------|---------------|---------------------|
| `POST .../sync-tree` | 동기 BFS, `scan_job` 생성·완료, `WEBDAV_SYNC_TREE` action_log | `WEBDAV_SYNC_TREE` | 1~2단계: 유지 | **1** (가장 길어질 수 있음) |
| `POST .../process-pending-text` | 동기, dry_run 시 scan_job 없음, `PROCESS_PENDING_TEXT` | `PROCESS_PENDING_TEXT` | 유지 | **2** |
| `POST .../process-pending-documents` | 동기, dry_run 시 없음, `PROCESS_PENDING_DOCUMENTS` | `PROCESS_PENDING_DOCUMENTS` | 유지 | **3** |
| `POST .../chunk-completed-text` | 동기, dry_run 시 없음, `CHUNK_COMPLETED_TEXT` | `CHUNK_COMPLETED_TEXT` | 유지 | **4** |
| `POST .../embed-pending-chunks` | 동기, dry_run 시 없음, `EMBED_PENDING_CHUNKS` | `EMBED_PENDING_CHUNKS` | 유지 | **5** |
| `POST .../sync-root` (참고) | 동기, `scan_job` 사용, `WEBDAV_SYNC_ROOT` | `WEBDAV_SYNC_ROOT` | 유지 | sync-tree보다 짧으나 동일 패턴으로 큐잉 가능 |

**dry_run:** 현재는 **scan_job을 열지 않음** (README·코드 일치). 비동기 도입 시에도 **dry_run은 동기 조회 API 유지** 또는 **별도 “preview job”** 정책을 분리하는 것이 단순하다.

---

## 9. 마이그레이션 초안 (문서 내 SQL 예시만 — 적용 금지)

> 아래는 **토의용 초안**이다. 실제 enum 이름·컬럼 존재 여부는 운영 DB와 맞춘 뒤 조정해야 한다.  
> `ALTER TYPE ... ADD VALUE IF NOT EXISTS`는 **PostgreSQL 15+** 구문이므로, 하위 버전에서는 존재 여부를 수동 확인한 뒤 `ADD VALUE`만 실행해야 한다.

```sql
-- 예시 초안이며 실제 적용 전 검토 필요
-- 1) scan_job_status 에 큐/취소/부분 상태 추가 (이미 있으면 ALTER TYPE ... ADD VALUE)
ALTER TYPE scan_job_status ADD VALUE IF NOT EXISTS 'PENDING';
ALTER TYPE scan_job_status ADD VALUE IF NOT EXISTS 'CANCELLING';
ALTER TYPE scan_job_status ADD VALUE IF NOT EXISTS 'CANCELLED';
ALTER TYPE scan_job_status ADD VALUE IF NOT EXISTS 'PARTIAL';

-- 2) scan_job_type 세분화 (기존 MANUAL_SCAN 유지 + 신규 값 추가)
ALTER TYPE scan_job_type ADD VALUE IF NOT EXISTS 'WEBDAV_SYNC_ROOT';
ALTER TYPE scan_job_type ADD VALUE IF NOT EXISTS 'WEBDAV_SYNC_TREE';
ALTER TYPE scan_job_type ADD VALUE IF NOT EXISTS 'PROCESS_PENDING_TEXT';
ALTER TYPE scan_job_type ADD VALUE IF NOT EXISTS 'PROCESS_PENDING_DOCUMENTS';
ALTER TYPE scan_job_type ADD VALUE IF NOT EXISTS 'CHUNK_COMPLETED_TEXT';
ALTER TYPE scan_job_type ADD VALUE IF NOT EXISTS 'EMBED_PENDING_CHUNKS';
ALTER TYPE scan_job_type ADD VALUE IF NOT EXISTS 'PIPELINE';

-- 3) scan_jobs 확장 컬럼
ALTER TABLE scan_jobs ADD COLUMN IF NOT EXISTS job_params JSONB;
ALTER TABLE scan_jobs ADD COLUMN IF NOT EXISTS cancel_requested BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE scan_jobs ADD COLUMN IF NOT EXISTS worker_id VARCHAR(100);
ALTER TABLE scan_jobs ADD COLUMN IF NOT EXISTS heartbeat_at TIMESTAMPTZ;
ALTER TABLE scan_jobs ADD COLUMN IF NOT EXISTS parent_job_id UUID REFERENCES scan_jobs(id);
ALTER TABLE scan_jobs ADD COLUMN IF NOT EXISTS pipeline_step TEXT;
ALTER TABLE scan_jobs ADD COLUMN IF NOT EXISTS retry_count INT NOT NULL DEFAULT 0;
ALTER TABLE scan_jobs ADD COLUMN IF NOT EXISTS max_retries INT NOT NULL DEFAULT 1;
ALTER TABLE scan_jobs ADD COLUMN IF NOT EXISTS priority INT NOT NULL DEFAULT 0;

-- 4) 인덱스 (이름은 배포 규칙에 맞게 변경)
CREATE INDEX CONCURRENTLY IF NOT EXISTS scan_jobs_status_created_idx
  ON scan_jobs (status, created_at);
CREATE INDEX CONCURRENTLY IF NOT EXISTS scan_jobs_ds_status_idx
  ON scan_jobs (data_source_id, status);
CREATE INDEX CONCURRENTLY IF NOT EXISTS scan_jobs_parent_idx
  ON scan_jobs (parent_job_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS scan_failures_job_idx
  ON scan_failures (scan_job_id);

-- 5) 백필 예시 (기존 row는 모두 MANUAL_SCAN 이력)
-- UPDATE scan_jobs SET job_type = 'WEBDAV_SYNC_TREE' ... 은 action_logs와 조인해 추론하거나 불가 시 수동.
```

**scan_failures:** `CHUNK_SAVE_FAILED`를 실제로 저장하려면  
`ALTER TYPE ...` 또는 `error_code`를 `VARCHAR`로 두고, **`record_scan_failure` 허용 목록에 `CHUNK_SAVE_FAILED` 추가**가 필요하다.

---

## 10. README·설계 문서와의 정합성 메모

- **`backend/README.md`:** `scan_jobs`·`scan_failures` 동작이 단계별로 상세히 적혀 있으며, **대시보드 `recent_scan_jobs`** 설명과 일치한다.
- **루트 `README.md`:** `scan_jobs` 언급 없음 → **온보딩은 backend README 기준**이 현실적이다.
- **`백그라운드작업_워커구조.md`:** `PENDING` 큐·heartbeat 등은 **현재 스키마/코드와 차이**가 있으며, 본 문서 **§2·§5**가 그 갭을 수치화한다.

---

## 11. 요약 체크리스트 (워커 도입 전)

1. **운영 DB에서 `scan_jobs` / `scan_failures` 실제 DDL·enum 값 확보** (레포에 없음).  
2. **`job_type` 단일화(`MANUAL_SCAN`) 해소** 방안 확정.  
3. **`PENDING` + worker dequeue** 모델과 기존 **`RUNNING` 즉시 삽입`** 모델 중 하나로 통일.  
4. **`fail_scan_job` 시 카운터·진행 스냅샷** 정책 결정.  
5. **`CHUNK_SAVE_FAILED` vs `scan_failures_service` 허용 목록** 정합화.  
6. **동시 실행 방지**를 DB 제약으로 할지 애플리케이션으로 할지 결정.  
7. **인덱스**는 실제 쿼리 패턴(폴링 쿼리 문) 확정 후 추가.

---

## 부록: 이번 단계에서 하지 않은 것

- DB 스키마 변경 및 위 SQL의 실제 실행  
- worker / 신규 API / 프론트 수정  

(요구사항과 동일.)
