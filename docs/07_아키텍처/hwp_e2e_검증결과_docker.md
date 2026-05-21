# HWP E2E 검증 결과 (Docker backend)

> **용도:** `docker-compose.dev.yml` 기반 **컨테이너 backend** + **호스트 DB/Ollama** 환경에서 HWP 파이프라인 검증 기록.  
> **Git:** 샘플 HWP·JWT·비밀번호·본문 전문 **커밋 금지**.

---

## 1. 검증 환경

| 항목 | 값 |
|------|-----|
| 검증 일시 | 2026-05-21 |
| OS | Windows 10 + Docker Desktop (WSL2 backend) |
| Python (이미지) | 3.12.13 (`python:3.12-slim-bookworm`) |
| Docker 이미지 | `internal_ai_search-backend:latest` (`08db62c11a6b`) |
| compose | `docker-compose.dev.yml` — `backend` 서비스 |
| env | `backend/.env` (로컬, **미커밋**). compose `env_file` + `DB_HOST`/`OLLAMA_BASE_URL` override |
| DB | compose `db:5432` (검증 당시는 `host.docker.internal:5433` 외부 DB — **이후 compose 전용 DB로 전환**, [`로컬_실행_명령.md`](../로컬_실행_명령.md) §5) |
| Ollama | `http://host.docker.internal:11434` — `gemma3`, `bge-m3` |
| Embedding dimension | 1024 |
| API base URL | `http://localhost:8000` (컨테이너 포트 매핑) |
| data_source_id | `3d2b7157-5d8b-4490-bc5b-ea99dec2f52e` (마스킹: WebDAV 테스트 저장소) |
| backend commit | `43269a0` (검증 시점) |
| 검증자 | 자동화 + 수동 health/E2E |

**실행 방식**

```bash
docker compose -f docker-compose.dev.yml up -d backend
```

---

## 2. 샘플 파일 (WebDAV, Git 미포함)

| 별칭 | 유형 | WebDAV | 예상 | 실제 |
|------|------|--------|------|------|
| sample01 (본문형) | 제안요청서·공고문류 HWP | 기존 sync-tree 반영 경로 | `COMPLETED` | `COMPLETED`, text_length 1.8k~42k |
| sample03 (장문) | 동일 저장소 내 장문 HWP | 기존 sync-tree | `COMPLETED` | `COMPLETED` (documents 5건 중 15k~25k) |
| sample02 (low-text) | `*RFP(hwp).hwp` | `…/2026년 … RFP(hwp).hwp` | `SKIPPED` / `NO_EXTRACTABLE_TEXT` | **SKIPPED**, `NO_EXTRACTABLE_TEXT`, chunk 0 |

**sync-tree:** 이번 검증에서 **신규 sync-tree 미실행**. 저장소에 HWP **3,861건** 이미 반영된 상태에서 E2E 진행.

**PoC 전용 `tmp/hwp_poc/samples/sample0x.hwp`:** Git 미포함. WebDAV 실제 파일로 대체 검증.

---

## 3. Health 5종 (컨테이너 backend → 호스트)

| 엔드포인트 | 결과 | 비고 |
|------------|------|------|
| `GET /health` | **ok** | |
| `GET /health/db` | **ok** | `backend/.env` 실제 `DB_PASSWORD` 사용 |
| `GET /health/llm` | **ok** | Ollama reachable, `gemma3` available |
| `GET /health/embedding` | **ok** | `bge-m3`, dimension 1024 |
| `GET /health/vector-db` | **ok** | pgvector smoke insert/search |

**이전 이슈 해소:** `env_file`을 `backend/.env`로 전환 + compose `environment`로 `DB_HOST=host.docker.internal`, `OLLAMA_BASE_URL=http://host.docker.internal:11434`.

---

## 4. HWP runtime check (컨테이너)

```bash
docker compose -f docker-compose.dev.yml run --rm backend \
  python tools/hwp_poc/check_hwp_runtime.py --json
```

| 항목 | 결과 |
|------|------|
| status | **ok** |
| hwp5txt_found | true (`/usr/local/bin/hwp5txt`) |
| hwp5txt_help_ok | true |
| imports.hwp5 / six / lxml / olefile / cryptography | 전부 true |

---

## 5. 단계별 E2E (API `http://localhost:8000`)

인증: **ACTIVE ADMIN** (`POST /api/auth/login`). 비밀번호·JWT **미기록**.

### 5.1 process-pending-documents (dry_run)

| 항목 | 값 |
|------|-----|
| 성공 | **OK** |
| target_count | 5 |
| planned_action | 전건 `PROCESS`, parser `hwp_parser` |

### 5.2 process-pending-documents (실행, limit=5)

| 항목 | 값 |
|------|-----|
| 성공 | **OK** |
| processed | 5 |
| completed | 5 |
| skipped | 0 |
| failed | 0 |
| parser | `hwp5txt` |
| text_length (요약) | 1,809 ~ 24,968 |

### 5.3 chunk-completed-text

| 항목 | 값 |
|------|-----|
| 성공 | **OK** |
| chunked_files | 14 (HWP 포함 기존 COMPLETED) |
| created_chunks | 363 |

### 5.4 embed-pending-chunks

| 항목 | 값 |
|------|-----|
| 성공 | **OK** |
| embedded_chunks | 363 |
| failed_chunks | 0 |
| completed_files | 14 |

### 5.5 search

| 항목 | 값 |
|------|-----|
| 키워드 | `에이전틱AI` |
| 성공 | **OK** |
| total_results | 5 |
| 첫 히트 | extension `hwp`, start_line 1, end_line 108, score ≈ 0.54 |

### 5.6 preview

| 항목 | 값 |
|------|-----|
| 성공 | **OK** |
| line range | 1–113 (search citation 1–108와 근접) |
| text_preview | 마스킹 1~2줄만 확인 (공고·사업명 키워드 포함) |

### 5.7 answer (RAG)

| 항목 | 값 |
|------|-----|
| 성공 | **OK** |
| citations | 5 |
| 첫 citation | extension `hwp`, start_line 1, end_line 108 |

---

## 6. DB 확인 요약

### 6.1 low-text (`*RFP(hwp).hwp`)

| analysis_status | analysis_error_code | text_length | chunk_count |
|-----------------|---------------------|-------------|-------------|
| SKIPPED | NO_EXTRACTABLE_TEXT | NULL | 0 |

### 6.2 본문형 (documents 5건 + 기존 COMPLETED)

| 별칭 | status | text_length (예) | chunk / embed |
|------|--------|------------------|---------------|
| 본문형 배치 5건 | COMPLETED | 1.8k–25k | chunk·embed OK |
| `body-agentic` (529자) | COMPLETED | 529 | 파이프라인 대상 |

---

## 7. Go / No-Go 판정

| 기준 | 충족 |
|------|------|
| 컨테이너 health 5종 ok | ☑ |
| runtime check ok | ☑ |
| 본문형 HWP E2E (documents→chunk→embed→search) | ☑ |
| low-text `SKIPPED` / `NO_EXTRACTABLE_TEXT` | ☑ |
| preview line range | ☑ |
| answer citation line range | ☑ |
| AGPL 법무 | ☐ **미완** (기록만) |
| 운영 배포 승인 | ☐ **해당 없음** |

**최종 판정:** **Go** (Docker 개발 검증 범위)

**사유:** 컨테이너에서 `hwp5txt`·backend·호스트 DB/Ollama 연동 및 HWP E2E 파이프라인이 설계대로 동작. AGPL·운영 배포는 별도.

---

## 8. 발견 사항 / 조치

| 이슈 | 조치 |
|------|------|
| `backend/.env`에 CHANGE_ME 그대로 두면 `/health/db` 실패 | `cp backend/.env.example backend/.env` 후 실제 값으로 교체 |
| `INITIAL_ADMIN_PASSWORD` 미설정 시 login 401 | E2E는 ACTIVE admin JWT로 API 호출 (로컬 `.env`에 비밀번호 설정 권장) |
| embedding health 이전 timeout | 이번 검증에서 **기본 timeout으로 ok** (필요 시 `EMBEDDING_TIMEOUT_SECONDS` 상향) |

---

## 9. 후속 조치

| 항목 | 상태 |
|------|------|
| Docker 운영 이미지·CI gate | ☐ |
| HWP pip pin (컨테이너 freeze) | ☐ |
| AGPL 법무 검토 | ☐ |
| 표·양식 HWP 추출 고도화 PoC | ☐ |
| `hwp_e2e_검증계획.md`에 Docker 시나리오 링크 | ☐ |

---

## 10. 관련 문서

- [`hwp_e2e_검증계획.md`](./hwp_e2e_검증계획.md)
- [`hwp_e2e_검증결과_템플릿.md`](./hwp_e2e_검증결과_템플릿.md)
- [`hwp_운영이미지_반영계획.md`](./hwp_운영이미지_반영계획.md)
- `backend/README.md` — Docker 개발 실행

*문서 버전: 2026-05-21 · Docker backend E2E 검증 기록*
