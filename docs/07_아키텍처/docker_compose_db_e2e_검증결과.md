# Docker Compose DB E2E 검증 결과

> **용도:** `docker-compose.dev.yml`의 **compose 전용 DB**(`db:5432`) + 컨테이너 backend/worker + 호스트 Ollama 환경에서 **초기 관리자 → 데이터 소스 → sync-tree → HWP E2E → PIPELINE** 전체 서비스 흐름 검증 기록.  
> **Git:** JWT·비밀번호·WebDAV credential·HWP 본문 전문·민감 경로 **커밋 금지**.

---

## 1. 검증 환경

| 항목 | 값 |
|------|-----|
| 검증 일시 | 2026-05-21 |
| OS | Windows 10 + Docker Desktop (WSL2) |
| 저장소 commit | `4137c16` |
| compose | `docker-compose.dev.yml` |
| env | `backend/.env` (Git 미추적). compose `env_file` + `DB_HOST=db`, `OLLAMA_BASE_URL=http://host.docker.internal:11434` |
| API | `http://localhost:8000` |
| Ollama | `http://host.docker.internal:11434` — `gemma3`, `bge-m3` (1024차원) |
| 검증자 | 자동화 스크립트 + 수동 health/DB 확인 |

**실행 (저장소 루트):**

```bash
docker compose --env-file backend/.env -f docker-compose.dev.yml down -v
docker compose --env-file backend/.env -f docker-compose.dev.yml up -d
docker compose --env-file backend/.env -f docker-compose.dev.yml --profile worker up -d backend-worker
```

**주의:** `down -v`는 compose named volume `internal_ai_search_db_data`만 삭제한다. 기존 호스트 `:5433` 외부 DB 컨테이너·`D:\docker-data` 볼륨은 compose에 **마운트하지 않음**.

---

## 2. Docker 이미지 / compose 구성

| 서비스 | 이미지 | 비고 |
|--------|--------|------|
| `db` | `pgvector/pgvector:pg18-bookworm` | PostgreSQL 18.4 + pgvector |
| `db-migrate` | `internal_ai_search-db-migrate:latest` (backend Dockerfile 빌드) | `scripts/apply_migrations.py` |
| `backend` | `internal_ai_search-backend:latest` | Python 3.12, `hwp5txt` 포함 |
| `backend-worker` | `internal_ai_search-backend-worker:latest` | profile `worker` |

| DB 항목 | 값 |
|---------|-----|
| compose 내부 | `db:5432`, DB `internal_ai_search`, user `openlink` |
| 호스트 publish | `localhost:5434` (기본 `DB_PUBLISH_PORT`) |
| volume | `internal_ai_search_db_data` → `/var/lib/postgresql` (PG18+ 경로) |
| 외부 DB 연결 | **없음** (compose volume만 사용) |

---

## 3. db-migrate 결과

`db-migrate` 로그 (최초 `down -v` 후 1회 기동):

| 순서 | SQL |
|------|-----|
| 1 | `docker/db/schema/baseline_schema.sql` |
| 2 | `backend/db/migrations/019_app_users.sql` |
| 3 | `020_action_logs.sql` |
| 4 | `021_scan_job_type_values.sql` |
| 5 | `022_scan_jobs_worker_fields.sql` |
| 6 | `023_scan_job_type_pipeline.sql` |

- 종료 코드: **0** (`[db-migrate] done`)
- 재기동 시: `baseline skipped (data_sources already exists)` 후 019–023 재적용 시도 — **멱등 DDL** 전제(오류 없이 완료)

---

## 4. Health 5종

| 엔드포인트 | 결과 |
|------------|------|
| `GET /health` | **ok** |
| `GET /health/db` | **ok** (PostgreSQL 18.4, compose `db`) |
| `GET /health/llm` | **ok** (`gemma3` available) |
| `GET /health/embedding` | **ok** (`bge-m3`, dimension 1024) |
| `GET /health/vector-db` | **ok** (insert + cosine search) |

---

## 5. Initial admin bootstrap

| 확인 항목 | 결과 |
|-----------|------|
| `app_users`에 ADMIN 1건 생성 | **ok** (`login_id=admin`, `role=ADMIN`, `status=ACTIVE`) |
| 최초 `must_change_password` | **true** |
| 비밀번호 변경 API 후 | **false** (E2E용: `backend/.env`에 `E2E_ADMIN_PASSWORD` 설정 필요) |
| 최초 로그인 | `INITIAL_ADMIN_PASSWORD`로 **ok** |
| 변경 후 로그인 | **현재 admin 비밀번호** (`E2E_ADMIN_PASSWORD`)로 **ok** |

**비고:** `must_change_password=true` 상태에서는 데이터 소스 등록 등 대부분 ADMIN API가 거부된다. E2E 전에 `POST /api/auth/change-password` 수행 필요.

---

## 6. 데이터 소스 등록 / 접속

| 항목 | 결과 |
|------|------|
| 등록 방식 | legacy 호스트 DB(`internal-ai-search-db`, `:5433`)에서 **암호문만** 읽어 API `POST /api/data-sources`로 재등록 (credential 평문은 로그/문서에 **미기록**) |
| 표시 이름 | WebDAV 테스트 저장소 (compose E2E 별칭; DB name 필드는 운영명 + suffix) |
| `data_source_id` | `50c0e224-0c9a-458b-956c-b81d945f7db5` |
| `POST .../test-connection` | **200 ok** |
| `last_connection_success` | **true** |
| 목록 API에 `credential_secret` 노출 | **없음** |

**주의:** compose DB는 빈 상태이므로 WebDAV credential이 `.env`에 없으면 legacy DB 1회 참조 또는 UI 수동 등록이 필요하다. **compose는 legacy 볼륨에 연결하지 않음.**

---

## 7. sync-tree (파일 목록 수집)

| 항목 | 값 |
|------|-----|
| 방식 | `POST /api/admin/jobs/sync-tree` (worker) |
| `scan_scope` | **LIMITED** (`max_depth=3`, `max_items=500`) |
| `job_id` | `57fd6f73-7411-4f5a-aa80-726cadeee43d` |
| 최종 상태 | **COMPLETED** (`total_files=543`, `processed_files=500`) |
| `files` (비디렉터리) | **249** |
| HWP 건수 | **39** |
| extension 상위 | pdf 137, hwp 39, pptx 35, … |

**전체 저장소(FULL) 정책:**

| 경로 | `scan_scope=FULL` | 결과 |
|------|-------------------|------|
| 동기 `POST /api/data-sources/{id}/sync-tree` | 시도 | **HTTP 400** (백그라운드/worker만 허용 — 기존 정책 유지) |
| worker `POST /api/admin/jobs/sync-tree` | 이번 검증은 LIMITED | FULL 대량 검증은 **별도 성능 검증**으로 분리 |

---

## 8. HWP runtime check

```bash
docker compose --env-file backend/.env -f docker-compose.dev.yml run --rm backend \
  python tools/hwp_poc/check_hwp_runtime.py --json
```

| 항목 | 결과 |
|------|------|
| status | **ok** |
| `hwp5txt_found` | true (`/usr/local/bin/hwp5txt`) |
| imports (hwp5, six, lxml, olefile, cryptography) | 전부 true |

---

## 9. HWP E2E (API)

인증: ACTIVE ADMIN, **현재 admin 비밀번호** + JWT (**미기록**).  
`data_source_id`: `50c0e224-0c9a-458b-956c-b81d945f7db5`, `--limit 20`.

### 9.1 dry_run documents

| 항목 | 결과 |
|------|------|
| target_count | 20 |
| planned | 전건 `PROCESS` / `hwp_parser` |

### 9.2 process-pending-documents (실행)

| 항목 | 결과 |
|------|------|
| processed | 20 |
| completed | **3** (본문형, text_length 628–34,685) |
| skipped | **17** (`NO_EXTRACTABLE_TEXT`) |
| failed | 0 |

### 9.3 chunk / embedding

| 단계 | 결과 |
|------|------|
| chunk | chunked_files **3**, created_chunks **67** |
| embedding | embedded_chunks **67**, failed **0** |

### 9.4 search / preview / answer

| 단계 | 키워드 | 결과 |
|------|--------|------|
| search | `에이전틱AI` | total_results **5**, 첫 히트 **hwp**, lines 202–229, score ≈ 0.45 |
| preview | (search 1위 chunk) | lines **197–234**, line_count 38 |
| answer | `에이전틱AI에 대해 요약해줘` | citations **5**, **전건 hwp**, lines (202, 229) 등 |

---

## 10. PIPELINE 검증

| 항목 | 값 |
|------|-----|
| API | `POST /api/admin/pipeline-jobs` |
| `pipeline_job_id` | `a90c9460-…` (parent) |
| params | `sync_tree`: LIMITED, `max_depth=2`, `max_items=100` |
| child 순서 | `WEBDAV_SYNC_TREE` → `PROCESS_PENDING_TEXT` → `PROCESS_PENDING_DOCUMENTS` → `CHUNK_COMPLETED_TEXT` → `EMBED_PENDING_CHUNKS` |
| children summary | **5/5 COMPLETED**, progress **100%**, failed **0** |

---

## 11. 최종 판정

| 기준 | 충족 |
|------|------|
| compose DB 초기화 + migrate | ☑ |
| health 5종 | ☑ |
| initial admin bootstrap + 비밀번호 변경 | ☑ |
| WebDAV DS 등록·접속 | ☑ |
| sync-tree (LIMITED) + HWP files 반영 | ☑ |
| HWP runtime + E2E (documents→search→preview→answer) | ☑ |
| PIPELINE 5단계 | ☑ |
| AGPL 법무 / 운영 배포 | ☐ 별도 |

**최종 판정:** **Go** (compose DB 기준 개발·E2E 검증 범위)

**사유:** 빈 compose DB에서 migrate·bootstrap·WebDAV·worker sync·HWP 파이프라인·PIPELINE·RAG까지 설계대로 동작. FULL 저장소 대량 sync는 시간·부하상 이번 범위에서 LIMITED로 대체.

---

## 12. 발견된 문제 / 제한

| # | 내용 | 심각도 |
|---|------|--------|
| 1 | 빈 compose DB에는 WebDAV credential이 없음 — **legacy `:5433` DB 1회 기동** 또는 수동 등록 필요 (compose 볼륨과 분리) | 운영 문서화 |
| 2 | `must_change_password=true` 시 ADMIN 기능 API 거부 | 기대 동작 |
| 3 | LIMITED sync(깊이 3) 샘플에서 HWP 20건 중 17건 `NO_EXTRACTABLE_TEXT` | 샘플·경로 제한; 본문형 3건으로 E2E 충분 |
| 4 | `tools/e2e_compose_verify.py`는 호스트 `psycopg` 없이 `docker compose exec db psql` 사용 | 보조 스크립트 개선 완료 |
| 5 | `db-migrate` 재실행 시 019–023 재적용 로그 — 멱등 전제 | 낮음 |

---

## 13. 후속 조치

| 우선순위 | 항목 |
|----------|------|
| P1 | `E2E_WEBDAV_*` 또는 UI 등록만으로 legacy DB 없이 compose E2E 재현 가능하게 보조 스크립트/문서 보강 |
| P2 | FULL `scan_scope` worker enqueue + 대량 저장소 **성능·시간** 별도 검증 |
| P3 | AGPL 법무 검토 · 운영 배포 승인 |
| P4 | pyhwp/requirements pin (스테이징 freeze) |

---

## 14. 관련 문서

- [`hwp_e2e_검증결과_docker.md`](./hwp_e2e_검증결과_docker.md) — 이전: compose backend + **호스트 외부 DB** E2E
- [`hwp_e2e_검증계획.md`](./hwp_e2e_검증계획.md)
- [`hwp_운영이미지_반영계획.md`](./hwp_운영이미지_반영계획.md)
- [`../로컬_실행_명령.md`](../로컬_실행_명령.md)
- `tools/e2e_compose_verify.py` — health·bootstrap·DS import·LIMITED sync enqueue 보조
