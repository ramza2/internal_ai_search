# HWP SKIPPED / NO_EXTRACTABLE_TEXT 명시적 재처리 E2E 검증 결과

> **용도:** `reprocess_hwp_no_extractable_text` 옵션으로 tiered 도입 이전 `SKIPPED` HWP를 관리자가 명시 재처리한 결과.  
> **Git:** JWT·비밀번호·WebDAV credential·HWP 본문 전문·민감 경로 **커밋 금지**.

---

## 1. 검증 환경

| 항목 | 값 |
|------|-----|
| 검증 일시 | 2026-05-21 |
| compose | `docker-compose.dev.yml` |
| `HWP_EXTRACTION_STRATEGY` | **tiered** (backend 이미지 ENV + `.env`) |
| API | `http://localhost:8000` |
| backend/worker | **재빌드·재기동** (`reprocess_hwp_no_extractable_text` 반영) |

---

## 2. 재처리 대상 조건 (이번 단계)

| 포함 | 제외 |
|------|------|
| `extension=hwp` | COMPLETED / FAILED HWP |
| `analysis_status=SKIPPED` | PDF 등 다른 확장자 `NO_EXTRACTABLE_TEXT` |
| `analysis_error_code=NO_EXTRACTABLE_TEXT` | 자동 일괴·parser 변경만 재실행 |
| `reprocess_hwp_no_extractable_text=true` (관리자 명시) | `reprocess_skipped` 의미 변경 없음 |

---

## 3. 검증 대상 문서

| 항목 | 값 |
|------|-----|
| data_source_id | `cd148eec-6d05-4486-b0b4-ebecebb3860a` (tiered E2E와 동일 WebDAV 저장소) |
| file_id (별칭 **skipped-baseline**) | `9f69bb54-b4a2-4c2e-914b-d95cc76bf3f4` |
| 처리 전 | `SKIPPED` / `NO_EXTRACTABLE_TEXT`, `parser_name` 없음, `text_length` 없음 |
| 크기 | 약 672 KB (표·양식 RFP 유형) |
| 동 DS PENDING HWP | 약 3,830건 — `limit=1`만으로는 PENDING이 먼저 선택됨 (정렬 `updated_at ASC`) |

**COMPLETED HWP 미대상 확인:** 동 DS에 `COMPLETED` 20건 존재. 재처리 SQL은 `SKIPPED`/`NO_EXTRACTABLE_TEXT`만 OR 조건에 포함 — **COMPLETED 행은 조회·갱신 대상 아님**.

---

## 4. dry_run (서비스 계층)

스크립트: `tools/hwp_poc/hwp_reprocess_internal_verify.py` (컨테이너)

| 항목 | 결과 |
|------|------|
| `fetch` + flag=true 시 skipped 파일 포함 | **true** (`fetch_includes_skipped_file`) |
| `planned_action` (해당 행) | **REPROCESS_HWP_NO_EXTRACTABLE_TEXT** |
| `dry_run` + `limit=1` | `target_count=1` (선두 PENDING 1건 — 운영 시 limit·큐 순서 주의) |

동기 API dry_run도 동일 코어(`run_process_pending_documents`) 사용.

---

## 5. 실제 재처리 (서비스 계층, 단일 SKIPPED 파일)

스크립트: `tools/hwp_poc/hwp_reprocess_service_e2e_verify.py` — 대상 file_id에 `_process_one_file` 직접 호출 (PENDING 3,830건 앞선 queue 회피).

| 항목 | 전 | 후 |
|------|----|----|
| `analysis_status` | SKIPPED | **COMPLETED** |
| `analysis_error_code` | NO_EXTRACTABLE_TEXT | **null** |
| `parser_name` | — | **hwp5html** |
| `text_length` | — | **42,021** |
| 처리 시간(대략) | — | **~14 s** |

**판정:** tiered 도입 전 `hwp5txt_only`로 스킵되었던 표·양식 HWP가 **명시 재처리**로 복구됨.

---

## 6. chunk / embedding (별도 실행, 자동 연쇄 없음)

| 단계 | 결과 |
|------|------|
| `chunk-completed-text` (`include_extensions=hwp`) | **43** chunks 생성, failed **0** |
| `embed-pending-chunks` | **43** embedded, failed **0** |

재처리 API/Job 성공만으로는 chunk·embedding **미실행** (기존 정책 유지).

---

## 7. search / preview / answer (HTTP)

| 단계 | 결과 |
|------|------|
| Admin JWT 로그인 | **미완** — `backend/.env`에 **`E2E_ADMIN_PASSWORD` 미설정**, `INITIAL_ADMIN_PASSWORD`는 **401** (비밀번호 변경된 DB) |
| `POST /api/search` | HTTP 경로 **미실행** (서비스 계층 chunk·embed까지 완료, 검색 가능 상태) |
| preview / answer | HTTP 경로 **미실행** |

**HTTP E2E 재현 명령** (`E2E_ADMIN_PASSWORD` 설정 후):

```bash
python tools/hwp_poc/hwp_reprocess_api_e2e_verify.py \
  --base-url http://localhost:8000 \
  --data-source-id cd148eec-6d05-4486-b0b4-ebecebb3860a \
  --limit 1 --keyword "관리번호"
```

**인증 메모:** `INITIAL_ADMIN_PASSWORD`는 빈 DB bootstrap용. 비밀번호 변경 후에는 **`E2E_ADMIN_PASSWORD`**(Git 미추적)만 현재 로그인에 사용.

---

## 8. API / worker 반영 요약

| 위치 | 필드 |
|------|------|
| `POST .../process-pending-documents` | query `reprocess_hwp_no_extractable_text` (default false) |
| `POST /api/admin/jobs/process-pending-documents` | body 동일 |
| `job_params` | `reprocess_hwp_no_extractable_text` |
| `action_logs` detail | boolean만 추가 |
| dry_run `planned_action` | `REPROCESS_HWP_NO_EXTRACTABLE_TEXT` |

---

## 9. 단위 테스트

| 항목 | 결과 |
|------|------|
| `backend/tests/test_reprocess_hwp_no_extractable_text.py` | 로컬 호스트 pytest는 `psycopg` 미설치로 수집 실패 가능 — **컨테이너/CI dev 의존성**에서 실행 권장 |
| 검증 항목 | flag false 시 NO_EXTRACTABLE_TEXT HWP 미포함, flag true 시 hwp+SKIPPED만, PDF 제외, dry_run non-mutating, worker `job_params` 전달 |

---

## 10. 롤백

| 설정 | 효과 |
|------|------|
| `HWP_EXTRACTION_STRATEGY=hwp5txt_only` | tiered 이점 제한 (API는 차단하지 않음, `warnings` 가능) |
| `reprocess_hwp_no_extractable_text=false` (기본) | 기존 동작 유지 |

---

## 11. 최종 판정

| 범위 | 판정 |
|------|------|
| API·worker·대상 조회·SKIPPED→COMPLETED (서비스) | **Go** |
| chunk / embedding (별도 Job) | **Go** |
| HTTP login → preview / answer E2E | **보류** (`E2E_ADMIN_PASSWORD` 필요) |

---

## 12. 후속 TODO

| 우선순위 | 항목 |
|----------|------|
| P1 | `E2E_ADMIN_PASSWORD` 설정 후 `hwp_reprocess_api_e2e_verify.py`로 HTTP search·preview·answer 기록 |
| P2 | PENDING 대량 큐 앞에서 SKIPPED만 재처리 시 운영 가이드(limit·큐 소진·UI file 선택은 후속) |
| P3 | COMPLETED HWP 재추출·기존 chunk 교체 정책 (별도 단계) |

---

## 13. 관련 문서

- tiered E2E: [`hwp_tiered_parser_e2e_검증결과.md`](./hwp_tiered_parser_e2e_검증결과.md)
- 정책: [`hwp_처리방식_검토.md`](./hwp_처리방식_검토.md) § 명시적 재처리
- `backend/README.md` — `reprocess_hwp_no_extractable_text`

---

*문서 버전: 2026-05-21 · SKIPPED HWP 명시 재처리*
