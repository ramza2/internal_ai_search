# HWP Tiered Parser E2E 검증 결과

> **용도:** Compose 환경에서 `HWP_EXTRACTION_STRATEGY=tiered` 적용 후 **표·양식 HWP → documents → chunk → embedding → search** 검증 기록.  
> **Git:** JWT·비밀번호·WebDAV credential·HWP 본문 전문·민감 경로 **커밋 금지**.

---

## 1. 검증 환경

| 항목 | 값 |
|------|-----|
| 검증 일시 | 2026-05-21 |
| OS | Windows 10 + Docker Desktop (WSL2) |
| compose | `docker-compose.dev.yml` |
| env | `backend/.env` (Git 미추적, HWP tiered 변수 **로컬 추가**) |
| API | `http://localhost:8000` |
| Ollama | `http://host.docker.internal:11434` (`gemma3`, `bge-m3`) |
| backend/worker | **재빌드** (`docker compose build backend backend-worker`) 후 `up -d` |
| 검증 스크립트 | `tools/hwp_poc/hwp_tiered_compose_e2e_verify.py` (컨테이너 내부 서비스 호출) |

**비고:** 관리자 JWT 로그인(`INITIAL_ADMIN_PASSWORD`)은 **401** — compose DB admin 비밀번호가 이전 E2E에서 변경된 상태. HTTP `hwp_e2e_api_check.py` 대신 **동일 파이프라인을 app 서비스 직접 호출**로 검증(동등 E2E).

---

## 2. HWP 전략 설정

| 변수 | 값 |
|------|-----|
| `HWP_EXTRACTION_STRATEGY` | **tiered** |
| `HWP5TXT_BIN` | `hwp5txt` |
| `HWP5HTML_BIN` | `hwp5html` |
| `HWP_PARSER_TIMEOUT_SECONDS` | 120 |
| `HWP_MIN_EXTRACTED_TEXT_LENGTH` | 50 |
| `HWP_HTML_MIN_EXTRACTED_TEXT_LENGTH` | 50 |
| `HWP_HTML_MIN_GAIN_RATIO` | 1.5 |

Dockerfile `ENV` 기본값과 동일. 재현성을 위해 `.env`에도 명시.

---

## 3. Runtime check (컨테이너)

```bash
docker compose --env-file backend/.env -f docker-compose.dev.yml run --rm backend \
  python tools/hwp_poc/check_hwp_runtime.py --json
```

| 항목 | 결과 |
|------|------|
| status | **ok** |
| `hwp5txt_found` / `hwp5txt_help_ok` | true |
| `hwp5html_found` / `hwp5html_help_ok` | true |
| `hwp_extraction_strategy` | **tiered** |
| imports (hwp5, six, lxml, olefile, cryptography) | 전부 true |

---

## 4. 검증 대상 준비

| 별칭 | 준비 방식 | 크기(대략) | 비고 |
|------|-----------|----------:|------|
| **table-form-hwp** | compose DB **PENDING** HWP (에이전틱 RFP 유형, 688,640 B) | 672 KB | 기존 SKIPPED baseline과 동일 유형·크기 |
| **body-hwp** | compose DB **PENDING** HWP (40~250 KB 대역 자동 선택) | 242 KB | 본문+표 혼합 |
| **skipped-baseline** | 기존 **SKIPPED** / `NO_EXTRACTABLE_TEXT` 1건 | — | **재처리 안 함**(정책) |

- **권장 A(신규 WebDAV 경로)** 는 미사용 — DB에 동일 유형 **PENDING** 3,833건 존재, 대표 file_id로 직접 처리.
- **SQL로 analysis_status 강제 변경 없음.**

---

## 5. Documents 처리 결과

| 별칭 | 결과 | parser_name | text_length | elapsed(s) | vs hwp5txt-only |
|------|------|-------------|------------:|-----------:|-----------------|
| table-form-hwp | **COMPLETED** (2회차 UNCHANGED) | **hwp5html** | **42,021** | **8.46** | PoC: txt **29 B** → SKIPPED; tiered **FULL** |
| body-hwp | **COMPLETED** | **hwp5html** | **19,603** | **24.34** | html 경로 채택 |

**간접 tiered 채택 근거 (metadata DB 미영속):**

| 키워드/마커 | table-form-hwp |
|-------------|:--------------:|
| `--- table 1 ---` | **true** |
| `품목(문제)명` | **4** |
| `관리번호` | **4** |
| `에이전틱 AI` | **12** |

**skipped-baseline (변경 없음):** `SKIPPED` / `NO_EXTRACTABLE_TEXT`, `file_contents` 없음 — tiered 도입 전 상태 유지.

---

## 6. Chunk / Embedding

| 단계 | 결과 |
|------|------|
| chunk-completed-text | ok — chunked_files **20**, created_chunks **381**, failed **0**, ~1.7 s |
| embed-pending-chunks | ok — embedded_chunks **381**, failed **0**, ~55.8 s |

---

## 7. Search

| 키워드 | total_results | 비고 |
|--------|:-------------:|------|
| 관리번호 | **5** | HWP 히트 |
| 품목(문제)명 | **5** | HWP 히트 |
| 에이전틱 AI | **5** | **table-form-hwp** file_id, start_line **507** |

표·양식 HWP에서 **hwp5txt only 시 회수 불가했던 라벨**이 검색됨.

**Preview / Answer:** 이번 자동 스크립트는 search까지 수행. Preview·Answer는 기존 `hwp_e2e_api_check.py --include-preview` 및 RAG answer API로 **동일 compose DB·동일 키워드**로 재현 가능(JWT 필요).

---

## 8. 처리 시간·성능

| 유형 | tiered 1건 (이번) | PoC 참고 (hwp5txt / hwp5html) |
|------|------------------:|------------------------------:|
| table-form (~672 KB) | **~8.5 s** | ~2 s / **~8.7 s** |
| body (~242 KB) | **~24.3 s** | — |

- tiered는 **hwp5html 우선** → 표·양식 대형은 PoC와 유사한 **8~10 s** 수준.
- 본문+표 혼합 일부는 **20 s+** — 대량 HWP 배치 시 worker timeout·동시 처리 부하 **모니터링 필요**.
- 이번 단계에서 **최적화·threshold 조정 없음**.

worker heartbeat/stale 이슈: **미발생**(단건·소량 처리).

---

## 9. 롤백

```env
HWP_EXTRACTION_STRATEGY=hwp5txt_only
```

`backend/README.md`에 문서화됨. 이번 검증에서 `hwp5txt_only` 전체 E2E **재실행은 생략**(설정 로드·문서만 확인).

---

## 10. 기존 HWP 재분석 정책 (후속)

| 항목 | 내용 |
|------|------|
| 이미 **COMPLETED** (hwp5txt) | parser 업그레이드 후 **자동 갱신 없음** |
| **SKIPPED** / `NO_EXTRACTABLE_TEXT` | `reprocess_skipped`는 **UNSUPPORTED_EXTENSION**만 대상 — **NO_EXTRACTABLE_TEXT는 자동 재처리 안 됨** |
| 이번 baseline | RFP SKIPPED 1건 **그대로 SKIPPED** |
| 필요 시 | 관리자 **선택 재처리** job 또는 **신규 WebDAV 경로** sync 후 PENDING 처리 |

이번 단계에서 **일괄 재분석 기능 구현 없음**.

---

## 11. 최종 판정

| 기준 | 충족 |
|------|------|
| runtime tiered (hwp5html+hwp5txt) | ☑ |
| table-form-hwp **COMPLETED**, text_length ≫ 29 B | ☑ |
| table marker·표 셀 키워드 회수 | ☑ |
| chunk / embedding / search | ☑ |
| 롤백 설정 명확 | ☑ |
| AGPL / metadata DB 영속 / API JWT E2E | ☐ |

**최종 판정:** **Go** (Compose tiered HWP 파이프라인 검증 범위)

**사유:** PENDING 표·양식형 HWP가 **hwp5html** 경로로 COMPLETED 되고, `관리번호`·`품목(문제)명`·`에이전틱 AI`가 search에 노출됨. 기존 SKIPPED 건은 정책상 미재처리.

---

## 12. 후속 TODO

| 우선순위 | 항목 |
|----------|------|
| P1 | `E2E_ADMIN_PASSWORD` 정리 후 **HTTP API** 경로로 `hwp_e2e_api_check.py` 재현 |
| P2 | preview / answer citation E2E 기록 |
| P3 | `ParserResult.metadata` → DB/관리 UI 영속화 |
| P4 | ~~NO_EXTRACTABLE_TEXT HWP 선택 재처리~~ → [`hwp_skipped_재처리_e2e_검증결과.md`](./hwp_skipped_재처리_e2e_검증결과.md) (`reprocess_hwp_no_extractable_text`) |
| P5 | AGPL 검토 · 대량 HWP 성능 테스트 |

---

## 13. 관련 문서

- PoC: [`hwp_표양식_추출고도화_결과.md`](./hwp_표양식_추출고도화_결과.md)
- Compose DB E2E: [`docker_compose_db_e2e_검증결과.md`](./docker_compose_db_e2e_검증결과.md)
- 스크립트: `tools/hwp_poc/hwp_tiered_compose_e2e_verify.py`, `tools/hwp_poc/check_hwp_runtime.py`

---

*문서 버전: 2026-05-21 · Compose tiered E2E*
