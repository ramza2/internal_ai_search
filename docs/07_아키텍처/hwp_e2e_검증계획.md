# HWP E2E 검증 계획

> **선행:** [`hwp_poc_실행계획.md`](./hwp_poc_실행계획.md) (기술 PoC), [`hwp_처리방식_검토.md`](./hwp_처리방식_검토.md) (설계)  
> **범위:** `hwp_parser.py` 단위 테스트를 넘어 **실제 서비스 파이프라인**에서 HWP가 끝까지 동작하는지 수동 검증한다.  
> **주의:** **AGPL 법무 검토는 완료된 것이 아니다.** 운영·Docker 반영 전 반드시 별도 승인을 받는다.  
> **Git:** 샘플 `.hwp`·추출 `.txt`·E2E 로그에 원문이 포함될 수 있으므로 **커밋하지 않는다.**

---

## 1. 검증 목적

| 목표 | 확인 내용 |
|------|-----------|
| 파이프라인 연동 | `process-pending-documents`가 HWP를 다운로드·변환·`file_contents` 저장 |
| 청킹 | `chunk-completed-text` 후 `document_chunks`에 `start_line` / `end_line` 생성 |
| 임베딩 | `embed-pending-chunks` 후 `document_chunks.embedding` 및 `files.last_indexed_at` 설정 |
| 검색 | `POST /api/search`에서 HWP 본문 키워드 히트 |
| RAG | `POST /api/answer`에서 HWP 근거·citation (`start_line` / `end_line`) |
| 미리보기 | `GET /api/files/{file_id}/preview?chunk_id=…`에서 변환 TXT 기준 줄 범위 표시 |
| low-text 정책 | 양식·표 위주 HWP는 **SKIPPED** / `NO_EXTRACTABLE_TEXT` (실패가 아님) |

**이 문서가 검증하지 않는 것:** Docker 이미지 빌드·운영 배포 자체 (별도 체크리스트), AGPL 법무 결론, OCR, HWP Automation/COM.

---

## 2. 검증 대상 흐름

```text
sync-tree
  → files 테이블에 .hwp 메타데이터 적재 (analysis_status=PENDING 등)

process-pending-documents?include_extensions=hwp
  → WebDAV GET → HwpParser(hwp5txt) → file_contents.extracted_text

chunk-completed-text
  → document_chunks (chunk_text, start_line, end_line)

embed-pending-chunks
  → document_chunks.embedding, files.last_indexed_at

POST /api/search
  → HWP 파일·chunk 스니펫 반환

POST /api/answer
  → citations에 file_id, chunk_id, start_line, end_line

GET /api/files/{file_id}/preview?chunk_id={chunk_id}
  → 줄 번호·하이라이트·open_info
```

**동기 API vs worker:** 아래 curl은 **동기** 엔드포인트 기준이다. 운영 PIPELINE/worker 경로를 검증할 때는 동일 `job_params`로 enqueue한 뒤 `python -m app.worker_main`을 실행한다.

---

## 3. 사전 조건

### 3.1 Runtime (변환기)

- [ ] `python tools/hwp_poc/check_hwp_runtime.py` → `status: ok` (또는 실패 항목 문서화)
- [ ] `hwp5txt` 실행 가능 (`which hwp5txt` 또는 `HWP5TXT_BIN` 경로)
- [ ] Python 패키지: `pyhwp`, `six`, `lxml`, `olefile`, `cryptography` (PoC에서 `pyhwp`만으로는 `six` 누락 사례 있음)

### 3.2 Backend 설정 (`backend/.env`)

| 변수 | 기본값 | 확인 |
|------|--------|------|
| `HWP5TXT_BIN` | `hwp5txt` | CLI 경로 |
| `HWP_PARSER_TIMEOUT_SECONDS` | `120` | 장문 HWP |
| `HWP_MIN_EXTRACTED_TEXT_LENGTH` | `50` | low-text 스킵 기준 |

### 3.3 인프라

- [ ] PostgreSQL + pgvector, 마이그레이션 적용
- [ ] WebDAV(또는 테스트 저장소) 접속 가능, **ADMIN** JWT (`must_change_password=false`)
- [ ] Ollama 실행 중 (`OLLAMA_BASE_URL`, `bge-m3` 임베딩, `gemma3` 등 answer용)
- [ ] `embedding_dimension=1024` ↔ DB `vector(1024)` 일치

### 3.4 샘플 파일 (로컬만, Git 커밋 금지)

| 유형 | 권장 | 용도 |
|------|------|------|
| 본문형 | `tmp/hwp_poc/samples/sample01.hwp`, `sample03.hwp` | COMPLETED → chunk → search |
| low-text | `sample02.hwp` | SKIPPED / `NO_EXTRACTABLE_TEXT` |

WebDAV에 업로드할 때 **원문이 포함된 경로·파일명**을 이 문서에 붙여넣지 말 것 (민감 문서 가능).

### 3.5 법무·라이선스

- [ ] **pyhwp (AGPLv3+)** — 운영·SaaS 반영 **전** 법무 검토 (미완료 시 E2E는 **스테이징/내부**만)
- [ ] 운영 Python **3.11 / 3.12** 고정 및 의존성 **pin** TODO (PoC는 3.14 사용 사례 있음)

---

## 4. 수동 검증 절차

플레이스홀더: `{BASE}` = `http://localhost:8000`, `{DS_ID}` = 데이터 소스 UUID, `{TOKEN}` = Admin Bearer JWT, `{FILE_ID}` / `{CHUNK_ID}` = 검증 중인 HWP 파일·청크 UUID.

### 4.0 Runtime 점검 (샘플 HWP 불필요)

```bash
# 저장소 루트
python tools/hwp_poc/check_hwp_runtime.py
python tools/hwp_poc/check_hwp_runtime.py --json
python tools/hwp_poc/check_hwp_runtime.py --hwp5txt-bin hwp5txt --timeout-seconds 10
```

### 4.1 데이터 소스·동기화

```bash
# 접속 확인 (ADMIN)
curl -sS -X POST "{BASE}/api/data-sources/{DS_ID}/test-connection" \
  -H "Authorization: Bearer {TOKEN}"

# 트리 동기화 — .hwp가 files에 들어오는지 확인
curl -sS -X POST "{BASE}/api/data-sources/{DS_ID}/sync-tree?start_path=/&max_depth=5&max_items=5000" \
  -H "Authorization: Bearer {TOKEN}"
```

**SQL (선택):**

```sql
SELECT id, remote_path, extension, analysis_status, analysis_error_code
FROM files
WHERE data_source_id = '{DS_ID}'::uuid
  AND lower(extension) = 'hwp'
  AND is_directory = FALSE
ORDER BY remote_path;
```

### 4.2 process-pending-documents

```bash
# dry_run — 대상·planned_action만 확인
curl -sS -X POST "{BASE}/api/data-sources/{DS_ID}/process-pending-documents?dry_run=true&limit=20&include_extensions=hwp" \
  -H "Authorization: Bearer {TOKEN}"

# 실제 처리
curl -sS -X POST "{BASE}/api/data-sources/{DS_ID}/process-pending-documents?limit=20&include_extensions=hwp&reprocess_skipped=false" \
  -H "Authorization: Bearer {TOKEN}"
```

이전에 `UNSUPPORTED_EXTENSION`으로 스킵된 HWP가 있으면:

```bash
curl -sS -X POST "{BASE}/api/data-sources/{DS_ID}/process-pending-documents?reprocess_skipped=true&include_extensions=hwp&limit=50" \
  -H "Authorization: Bearer {TOKEN}"
```

### 4.3 file_contents 확인

```sql
SELECT f.id, f.remote_path, f.analysis_status, f.analysis_error_code,
       fc.text_length, left(fc.extracted_text, 200) AS head_preview
FROM files f
LEFT JOIN file_contents fc ON fc.file_id = f.id
WHERE f.data_source_id = '{DS_ID}'::uuid
  AND lower(f.extension) = 'hwp'
  AND f.is_directory = FALSE;
```

- 본문형: `analysis_status = 'COMPLETED'`, `text_length` ≥ `HWP_MIN_EXTRACTED_TEXT_LENGTH` (의미 길이는 parser 내부 strip 기준)
- low-text: `analysis_status = 'SKIPPED'`, `analysis_error_code = 'NO_EXTRACTABLE_TEXT'`

### 4.4 chunk-completed-text

```bash
curl -sS -X POST "{BASE}/api/data-sources/{DS_ID}/chunk-completed-text?limit=100&include_extensions=hwp" \
  -H "Authorization: Bearer {TOKEN}"
```

```sql
SELECT dc.file_id, dc.chunk_index, dc.start_line, dc.end_line,
       length(dc.chunk_text) AS chunk_len, dc.embedding IS NOT NULL AS has_embedding
FROM document_chunks dc
JOIN files f ON f.id = dc.file_id
WHERE f.data_source_id = '{DS_ID}'::uuid
  AND lower(f.extension) = 'hwp'
ORDER BY f.remote_path, dc.chunk_index;
```

### 4.5 embed-pending-chunks

```bash
curl -sS -X POST "{BASE}/api/data-sources/{DS_ID}/embed-pending-chunks?limit=500&batch_size=32&include_extensions=hwp" \
  -H "Authorization: Bearer {TOKEN}"
```

```sql
SELECT f.id, f.remote_path, f.last_indexed_at,
       count(dc.id) AS chunk_count,
       count(dc.embedding) AS embedded_count
FROM files f
JOIN document_chunks dc ON dc.file_id = f.id
WHERE f.data_source_id = '{DS_ID}'::uuid
  AND lower(f.extension) = 'hwp'
  AND f.analysis_status = 'COMPLETED'
GROUP BY f.id, f.remote_path, f.last_indexed_at;
```

- `embedded_count = chunk_count`, `last_indexed_at IS NOT NULL` → 검색 대상 조건 충족

### 4.6 search

본문에 실제로 들어 있는 **고유 키워드**로 질의 (예: sample01/03 본문 일부).

```bash
curl -sS -X POST "{BASE}/api/search" \
  -H "Authorization: Bearer {TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "<HWP 본문에 있는 키워드>",
    "data_source_id": "{DS_ID}",
    "include_extensions": ["hwp"],
    "limit": 10
  }'
```

키워드 모드(임베딩 없이) 교차 확인:

```bash
curl -sS -X POST "{BASE}/api/search" \
  -H "Authorization: Bearer {TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "<키워드>",
    "data_source_id": "{DS_ID}",
    "include_extensions": ["hwp"],
    "search_mode": "keyword",
    "limit": 10
  }'
```

응답에서 확인: `extension` = `hwp`, `start_line` / `end_line` 존재, `snippet`만 반환(full text 없음).

### 4.7 answer (RAG)

```bash
curl -sS -X POST "{BASE}/api/answer" \
  -H "Authorization: Bearer {TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "<질문>",
    "data_source_id": "{DS_ID}",
    "include_extensions": ["hwp"],
    "search_limit": 10,
    "context_limit": 5
  }'
```

`citations[]`에 HWP `file_id`, `chunk_id`, `start_line`, `end_line`, `remote_path` 확인.

### 4.8 file preview

search/answer 응답에서 받은 `{FILE_ID}`, `{CHUNK_ID}` 사용:

```bash
curl -sS "{BASE}/api/files/{FILE_ID}/preview?chunk_id={CHUNK_ID}&context_lines=5&max_chars=8000" \
  -H "Authorization: Bearer {TOKEN}"
```

또는:

```bash
curl -sS "{BASE}/api/files/{FILE_ID}/chunks/{CHUNK_ID}/preview?context_lines=5" \
  -H "Authorization: Bearer {TOKEN}"
```

확인: `preview_start_line` / `preview_end_line`이 citation과 일치, 본문이 **변환 TXT 줄 번호** 기준임.

---

## 5. 기대 결과

### 5.1 본문형 HWP (sample01·sample03 유형)

| 단계 | 기대 |
|------|------|
| documents | `files.analysis_status = COMPLETED`, parser `hwp5txt` |
| contents | `file_contents.text_length` > threshold, 한글 본문 존재 |
| chunks | `document_chunks` ≥ 1, `start_line`/`end_line` ≥ 1 |
| embedding | 모든 chunk `embedding IS NOT NULL`, `last_indexed_at` 설정 |
| search | `include_extensions: ["hwp"]` 시 해당 파일 히트 |
| answer | citations에 line range |
| preview | chunk_id 기준 줄 창 표시 |

### 5.2 low-text HWP (sample02 유형)

| 단계 | 기대 |
|------|------|
| documents | `SKIPPED`, `analysis_error_code = NO_EXTRACTABLE_TEXT` |
| chunks | 생성되지 않음 (또는 이전 run 잔여 chunk 없음) |
| search | 해당 파일은 인덱스 대상 아님 (`last_indexed_at` 없음) |
| 운영 해석 | **검색 가치 낮은 문서로 스킵** — 파이프라인 장애 아님 |

---

## 6. 실패 시 점검

| 증상 | 가능 원인 | 조치 |
|------|-----------|------|
| `HWP_CONVERTER_NOT_AVAILABLE` / converter not on PATH | `hwp5txt` 미설치, `HWP5TXT_BIN` 오타 | `check_hwp_runtime.py`, `pip install pyhwp six lxml olefile`, PATH |
| subprocess 실패, `ModuleNotFoundError: six` 등 | pyhwp 의존 누락 | `pip install six lxml olefile cryptography` |
| `HWP_CONVERSION_TIMEOUT` | 파일过大, timeout 짧음 | `HWP_PARSER_TIMEOUT_SECONDS` 상향, 파일 크기 확인 |
| `NO_EXTRACTABLE_TEXT` (의도한 low-text) | 양식·표만 있음 | 정상 스킵; threshold 조정은 정책 결정 |
| `PARSING_FAILED` / `HWP_CONVERSION_FAILED` | 손상 HWP, 미지원 버전 | stderr_summary(metadata), PoC 재현 |
| `PASSWORD_PROTECTED` | 암호 문서 | 별도 정책 |
| `DOWNLOAD_FAILED` | WebDAV 권한·경로 | `test-connection`, credential |
| chunk 0건 | `analysis_status`≠COMPLETED, `TEXT_TOO_SHORT` | documents 단계·`min_chunk_size` |
| embedding NULL | Ollama down, batch 실패 | `/health/llm`, worker 로그 |
| search 0건 | `last_indexed_at` NULL, extension 필터 | embed 단계·`include_extensions` |
| `dimension_mismatch` | 모델/DB 차원 불일치 | `embedding_dimension`, migration |
| preview 줄 불일치 | chunk 재생성 전후 | `reprocess=true`로 chunk 재생성 |

**로그 주의:** 추출 전문·credential·Authorization 값을 티켓/Slack에 붙이지 않는다.

---

## 7. Go / No-Go

### Go (스테이징 HWP 활성화 후보)

- [ ] 본문형 HWP **2건 이상** 위 파이프라인 E2E 통과
- [ ] preview API에서 **line range** 정상 (변환 TXT 기준)
- [ ] search·answer citation에 `start_line` / `end_line` 정상
- [ ] low-text 1건 이상 **SKIPPED** / `NO_EXTRACTABLE_TEXT` 안전 처리
- [ ] `check_hwp_runtime.py`가 대상 환경(로컬/WSL/스테이징)에서 통과
- [ ] AGPL: **검토 완료** 또는 **운영 보류·내부 전용** 조건이 문서·릴리스 노트에 명시됨

### No-Go

- `process-pending-documents`에서 동일 본문형 HWP가 **반복 실패**
- chunk `start_line`/`end_line`과 preview·citation **불일치**
- HWP 본문 키워드가 search/answer에 **전혀** 나타나지 않음
- 운영/Linux 이미지에서 **hwp5txt 설치·실행 불가** (Docker 체크리스트에서 해소 전)
- AGPL 리스크 **해소 불가** 및 대안(상용 변환기·HWPX 권장만) 미정

---

## 8. 관련 문서·도구

| 항목 | 경로 |
|------|------|
| Runtime 점검 | `python tools/hwp_poc/check_hwp_runtime.py` |
| PoC 실행 | [`hwp_poc_실행계획.md`](./hwp_poc_실행계획.md) |
| 설계·정책 | [`hwp_처리방식_검토.md`](./hwp_처리방식_검토.md) |
| Backend 운영 | `backend/README.md` — HWP 운영 점검 |
| Docker 반영 | **본 마일스톤 범위 외** — E2E Go 이후 별도 PR |

---

*문서 버전: 2026-05-15 · HWP parser 1차 구현 이후 E2E 검증용*
