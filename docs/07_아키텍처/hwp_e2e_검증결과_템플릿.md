# HWP E2E 검증 결과 템플릿

> **용도:** [`hwp_e2e_검증계획.md`](./hwp_e2e_검증계획.md) 에 따른 수동·반자동 E2E 결과를 **로컬 복사본**에 기록한다.  
> **Git:** 이 파일을 채운 뒤에도 **샘플 HWP·추출 TXT·토큰·본문 전문**은 커밋하지 않는다. 민감 내용은 붙여넣지 말 것.

---

## 1. 검증 환경

| 항목 | 값 |
|------|-----|
| 검증 일시 | |
| OS | |
| Python | |
| hwp5txt path (`which hwp5txt`) | |
| `check_hwp_runtime.py` 결과 | ok / fail |
| backend branch / commit | |
| DB (host/port/name) | |
| Ollama (`OLLAMA_MODEL`) | |
| Embedding (`EMBEDDING_MODEL`, dimension) | |
| API base URL | |
| data_source_id | |
| 검증자 | |

---

## 2. 샘플 파일

WebDAV 테스트 저장소에 올린 파일 (파일명·경로는 **민감 시 생략** 가능).

| 구분 | 파일명 별칭 | 유형 | 예상 결과 | 비고 |
|------|-------------|------|-----------|------|
| 본문형1 | sample01 | 본문형 | `COMPLETED` | |
| 본문형2 | sample03 | 장문 | `COMPLETED` | |
| low-text | sample02 | 양식/표 위주 | `SKIPPED` / `NO_EXTRACTABLE_TEXT` | |

---

## 3. 단계별 결과

각 단계: **실행 명령** · **성공 여부** · **주요 count** · **오류** · **비고**

### 3.1 Runtime check

- **실행 명령:**
  ```bash
  python tools/hwp_poc/check_hwp_runtime.py --json
  ```
- **성공 여부:** ☐ OK ☐ FAIL
- **주요 결과:** `hwp5txt_found` / `imports` / `hwp5txt_help_ok`
- **오류:**
- **비고:**

### 3.2 sync-tree

- **실행:** UI 1단계 / curl / worker Job
- **명령·설정:** `max_depth` / `max_items` / `start_path`
- **성공 여부:** ☐ OK ☐ FAIL ☐ 미실행
- **주요 count:** upserted / truncated / deleted
- **오류:**
- **비고:** HWP `files` 행 존재 확인

### 3.3 process-pending-documents (dry_run)

- **실행 명령:**
  ```bash
  python tools/hwp_poc/hwp_e2e_api_check.py \
    --base-url http://localhost:8000 \
    --data-source-id <DS_ID> \
    --token "$INTERNAL_AI_SEARCH_TOKEN" \
    --dry-run-documents
  ```
- **성공 여부:** ☐ OK ☐ FAIL
- **target_count / items:**
- **오류:**
- **비고:**

### 3.4 process-pending-documents (실제 실행)

- **실행 명령:**
  ```bash
  python tools/hwp_poc/hwp_e2e_api_check.py \
    --base-url http://localhost:8000 \
    --data-source-id <DS_ID> \
    --token "$INTERNAL_AI_SEARCH_TOKEN" \
    --run-documents --limit 20
  ```
- **성공 여부:** ☐ OK ☐ FAIL
- **completed / skipped / failed:**
- **sample01:** status / text_length / reason
- **sample02:** status / reason (`NO_EXTRACTABLE_TEXT` 기대)
- **sample03:** status / text_length
- **오류:**
- **비고:**

### 3.5 chunk-completed-text

- **실행 명령:** `--run-chunk` (스크립트) 또는 UI 4단계
- **성공 여부:** ☐ OK ☐ FAIL
- **chunked_files / created_chunks / failed:**
- **오류:**
- **비고:**

### 3.6 embed-pending-chunks

- **실행 명령:** `--run-embedding` (스크립트) 또는 UI 5단계
- **성공 여부:** ☐ OK ☐ FAIL
- **embedded_chunks / failed_chunks / completed_files:**
- **Ollama / dimension 이슈:**
- **오류:**
- **비고:**

### 3.7 search

- **키워드:**
- **실행 명령:**
  ```bash
  python tools/hwp_poc/hwp_e2e_api_check.py \
    ... --keyword "<키워드>" --json
  ```
- **성공 여부:** ☐ OK ☐ FAIL
- **total_results:**
- **첫 히트:** file_id / chunk_id / start_line / end_line / score
- **오류:**
- **비고:**

### 3.8 answer (RAG)

- **실행:** UI `/answer` 또는 curl `POST /api/answer`
- **성공 여부:** ☐ OK ☐ FAIL
- **citations에 HWP line range:** ☐ 예 ☐ 아니오
- **오류:**
- **비고:**

### 3.9 preview

- **실행 명령:** `--keyword ... --include-preview`
- **성공 여부:** ☐ OK ☐ FAIL
- **preview line range:** start_line / end_line (citation과 일치 여부)
- **오류:**
- **비고:**

---

## 4. DB 확인 결과

SQL 실행 결과 요약만 붙여넣기 (**extracted_text 전문 금지**).

### 4.1 files (extension = hwp)

| remote_path (또는 별칭) | analysis_status | analysis_error_code | text_length (join) |
|-------------------------|-----------------|---------------------|--------------------|
| sample01 | | | |
| sample02 | | | |
| sample03 | | | |

### 4.2 file_contents

| file_id (앞 8자…) | text_length | head OK (Y/N) |
|-------------------|-------------|---------------|
| | | |

### 4.3 document_chunks

| file 별칭 | chunk_count | start_line (min) | end_line (max) | embedding NOT NULL |
|-----------|-------------|------------------|----------------|---------------------|
| sample01 | | | | |
| sample03 | | | | |

### 4.4 embedding / indexed

| file 별칭 | last_indexed_at | embedded chunk count |
|-----------|-----------------|----------------------|
| | | |

**참고 SQL:** [`hwp_e2e_검증계획.md`](./hwp_e2e_검증계획.md) §4.3–4.5

---

## 5. Go / No-Go 판정

| 기준 | 충족 |
|------|------|
| runtime check 통과 | ☐ |
| 본문형 HWP 2건 이상 E2E 통과 (`COMPLETED` → chunk → embed → search) | ☐ |
| low-text sample02 `SKIPPED` / `NO_EXTRACTABLE_TEXT` | ☐ |
| line range preview 정상 (변환 TXT 기준) | ☐ |
| search / answer citation에 `start_line` / `end_line` | ☐ |
| AGPL 법무 검토 | ☐ 완료 ☐ 진행 중 ☐ 미착수 |

**최종 판정:** ☐ **Go** ☐ **조건부 Go** ☐ **No-Go**

**조건부 Go / No-Go 사유:**

---

## 6. 후속 조치

| 항목 | 담당 | 상태 |
|------|------|------|
| Docker / 운영 이미지에 hwp5txt 반영 | | ☐ |
| requirements / Python 3.11·3.12 pin | | ☐ |
| AGPL 법무 검토 | | ☐ |
| UI 기본값·안내 (PipelineRunModal 등) | | ☐ |
| HWP 전용 error_code 정리 | | ☐ |
| converter sidecar 검토 | | ☐ |

---

*템플릿 버전: 2026-05-15*
