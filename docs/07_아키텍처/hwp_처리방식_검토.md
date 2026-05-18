# HWP 바이너리 처리 방식 검토

> **문서 목적:** internal-ai-search에서 **HWP 바이너리(`.hwp`)** 본문 추출을 Linux/headless 환경에 도입하기 위한 **기술 검토**이다.  
> **범위:** 설계·비교·PoC 계획만 수행한다. 본 문서 작성 시점에는 **코드·의존성·DB·API 변경 없음**.

---

## 1. 배경

### 1.1 현재 문서 처리 구조

internal-ai-search는 WebDAV 저장소에서 파일을 수집한 뒤, 확장자별로 **1차 텍스트 추출** → `file_contents.extracted_text` 저장 → **chunk** → **embedding** → **검색/RAG** → **미리보기·citation** 순으로 처리한다.

| 단계 | API / Job | 역할 |
|------|-----------|------|
| 수집 | `sync-tree` | WebDAV 메타·경로 동기화 |
| 평문 | `process-pending-text` | txt, md, csv, log, 소스·설정 등 |
| 문서 | `process-pending-documents` | PDF, DOCX, XLSX, PPTX, HWPX |
| 청크 | `chunk-completed-text` | `document_chunks` 생성 (`start_line` / `end_line` 포함) |
| 임베딩 | `embed-pending-chunks` | pgvector 인덱싱 |
| 검색 | `/api/search`, `/api/answer` | 벡터·키워드·하이브리드 + RAG |
| 근거 | preview API, citation 메타 | **라인 범위** 기반 조회·표시 |

문서 파서는 `backend/app/parsers/` 아래 **플러그인 어댑터**로 구현되어 `registry.get_parser_for_extension()`으로 선택된다. 각 파서는 `DocumentParser.parse_bytes()` → `ParserResult(extracted_text, error_code, …)`를 반환하고, `pending_document_processor_service`가 WebDAV 다운로드·상태 전이·`file_contents` upsert·`scan_failures` 기록을 담당한다.

**백그라운드:** `PROCESS_PENDING_DOCUMENTS` Job과 `PIPELINE` 부모 Job을 통해 worker(`python -m app.worker_main`)에서 동일 코어 로직을 실행할 수 있다.

### 1.2 현재 지원·미지원 포맷

**지원 (`process-pending-documents`, `registry._DOCUMENT_EXTENSIONS`):**

| 확장자 | 파서 | 비고 |
|--------|------|------|
| `pdf` | `pdf_parser` (pypdf) | 이미지 전용 PDF는 텍스트 없음 → `NO_EXTRACTABLE_TEXT` |
| `docx` | `docx_parser` | |
| `xlsx` | `xlsx_parser` | |
| `pptx` | `pptx_parser` | |
| `hwpx` | `hwpx_parser` | ZIP/XML, **HWP Automation/COM 미사용** |

**미지원 (현재 `UNSUPPORTED_EXTENSION` 또는 별도 경로 없음):**

| 확장자 | 상태 |
|--------|------|
| `hwp` (바이너리) | 문서 Job 대상 아님, 레지스트리 미등록 |
| `doc`, `xls`, `ppt` | OLE 구형 바이너리, 미구현 |
| 이미지 기반 PDF / 스캔본 | OCR 미구현 |

`file_type` 분류(`DOCUMENT` 버킷)에는 `hwp`가 포함되지만, **process-pending-text**에서는 명시적으로 제외되고 **process-pending-documents**의 지원 집합에도 없어 실질적으로 스킵된다.

### 1.3 HWP가 중요한 이유

- 국내 사내 문서·공문·보고서에 **`.hwp` 비중이 클 수 있음**.
- 파일명·경로만으로는 RAG 품질이 부족하며 **본문 검색·요약·질의응답**에 텍스트 추출이 필요하다.
- 이미 HWPX는 지원하나, 저장·공유 관행상 **구형 HWP 바이너리**가 대량으로 남아 있을 수 있다.
- 검색/RAG 응답에는 **파일 ID + chunk + 라인 범위**로 근거를 열 수 있어야 하며, 프로젝트는 **페이지 번호보다 라인 범위**를 1차 목표로 한다.

### 1.4 기존 제약 (반드시 준수)

- **HWP Automation / COM 사용 금지**
- **Windows 전용·한컴오피스 설치 의존 금지**
- **Linux / headless 서버 배포 가능**한 방식만 검토
- **HWPX**는 현재 ZIP/XML(`hwpx_parser`)로 처리 중이며, 본 문서의 범위는 **`.hwp` 바이너리**에 한정
- **OCR**은 본 단계에서 구현하지 않고 후순위

---

## 2. 목표

### 2.1 1차 목표

1. HWP 바이너리에서 **본문 텍스트 추출**
2. 추출 텍스트를 **`file_contents.extracted_text`**에 저장 (기존 정책·해시·상태 전이 재사용)
3. 기존 **chunk → embedding → search/RAG** 파이프라인에 태우기
4. **라인 기반 citation** 제공 (`start_line` / `end_line`, preview API)

### 2.2 1차 목표가 아닌 것

- 원본 HWP **페이지 번호**의 정확한 매핑·표시
- 표·이미지·스타일·머리글/꼬리글의 완벽 복원
- **OCR** (이미지 PDF·스캔 HWP 내 이미지)
- HWP **편집·변환 UI** 제공
- Windows **COM 자동화**·데스크톱 한컴 연동

---

## 3. 검토 대상 방식

### 후보 A. pyhwp / hwp5txt 기반 HWP → TXT 추출

**개요:** [pyhwp](https://github.com/mete0r/pyhwp)는 HWP Document Format **v5** 파서이며, 실험적 컨버터 **`hwp5txt`**로 평문을 출력한다. CLI 예: `hwp5txt [--output OUTPUT] <file.hwp>`.

| 검토 항목 | 내용 |
|-----------|------|
| Linux/headless | **가능.** GUI·COM 불필요. CLI/라이브러리 호출로 서버에서 실행 가능. |
| 설치 | `pip install pyhwp`(또는 배포 이미지에 사전 설치). 의존: `cryptography`, `lxml`, `olefile` 등. 일부 변환 경로는 `xsltproc`/`xmllint` 필요할 수 있음(문서화된 experimental converters). |
| CLI | **가능.** `hwp5txt` 엔트리포인트. stdout 또는 `--output` 파일. |
| Python 연동 | (1) `subprocess`로 `hwp5txt` 실행 후 stdout/파일 읽기, (2) pyhwp API로 내부 파싱 후 텍스트 조립. 기존 `DocumentParser.parse_bytes()` 패턴에 (1)이 단순. |
| 텍스트 품질 | 본문·단락은 **양호한 편**. 표는 구조가 깨지거나 탭/공백으로 평탄화될 수 있음. 머리글/각주/필드 일부 누락 가능. |
| 한글 인코딩 | UTF-8 출력 전제로 설계; **PoC에서 깨짐·조합 문자** 검증 필요. |
| 표/문단 구조 | **부분 보존**(줄바꿈·공백 수준). 셀 병합·복잡 표는 품질 편차. |
| 오류 처리 | 손상 파일·비 v5·암호화 시 예외/비정상 종료 → `ParserResult`의 `error_code`로 매핑. |
| 라인 citation | **적합.** 평문 1줄 = 1 logical line(정규화 후)로 chunking_service와 정합. |
| 운영 리스크 | **중간.** AGPL 라이선스(§3.1), 패키지 유지보수·Python 버전 호환, 대용량 파일 시 CPU/시간. |
| 라이선스 | **확인 필요.** pyhwp는 **AGPLv3+**로 공개됨. 사내 상용·폐쇄 배포 시 법무·라이선스 검토 필수. 대안으로 subprocess만 쓰고 소스 배포 의무 범위를 검토하거나, 별도 상용 변환기 계약 검토. |

### 후보 B. HWP → TXT 변환 CLI를 별도 컨테이너로 분리

**개요:** 후보 A와 동일한 `hwp5txt`(또는 동급 CLI)를 **converter 전용 Docker 이미지**에서 실행하고, API/worker는 HTTP/gRPC/볼륨 마운트로 요청.

| 검토 항목 | 내용 |
|-----------|------|
| 장점 | **장애 격리**(변환기 크래시가 API 프로세스에 직접 전파되지 않음), 리소스 limit·스케일 아웃, 보안 샌드박스. |
| 임시 파일 | 입력 HWP·출력 TXT를 **전용 tmpfs/볼륨**에 두고 작업 후 삭제. |
| 보안 | 네트워크 최소화, 인증된 내부 호출만 허용. |
| 운영 복잡도 | **증가.** 이미지 2종, 헬스체크, 버전 동기화, 로컬 dev 재현. |
| Docker | **가능.** converter 이미지에 pyhwp + 의존성 고정. |
| 대량 처리 | worker timeout·동시 변환 수 제한과 병행 설계 필요. |

초기 MVP는 **단일 이미지 + subprocess(A)** 로 시작하고, PoC에서 불안정·메모리 이슈가 있으면 **B로 승격**하는 점진 전략이 합리적이다.

### 후보 C. HWP → PDF 변환 후 기존 PDF parser로 추출

**개요:** 외부 도구로 PDF 생성 → `pdf_parser`로 텍스트·(간접적) 페이지 인덱스 활용.

| 검토 항목 | 내용 |
|-----------|------|
| 페이지 citation | PDF **페이지 번호**는 얻기 쉬우나, **원본 HWP 페이지와 1:1 대응이 보장되지 않음**. 프로젝트 1차 목표(라인 citation)와도 우선순위 불일치. |
| 텍스트 추출 | 텍스트 레이어가 있는 PDF면 `pypdf`로 가능. |
| 이미지 PDF | 변환 결과가 스캔 이미지면 **OCR 필요** → 본 단계 범위 밖. |
| Linux/headless | **불확실·낮음.** LibreOffice 등은 Linux에서 HWP 지원이 제한적. 상용·Windows 전용 변환기는 제약 위반. |
| 품질/속도 | 2단계 변환으로 **느리고** 오류 지점 증가. |
| MVP 적합성 | **낮음.** 페이지 근거가 필수일 때만 별도 트랙으로 재검토. |

### 후보 D. 직접 HWP 바이너리 파싱 라이브러리 조사

**개요:** Python에서 HWP OLE/레코드를 직접 읽는 라이브러리 또는 자체 구현.

| 검토 항목 | 내용 |
|-----------|------|
| Python 라이브러리 | 실질적으로 **pyhwp가 유일에 가까운 오픈소스** 선택지. 상용 SDK는 별도 계약·폐쇄형. |
| 유지보수 | pyhwp: GitHub 활동·PyPI 버전이 **간헐적**(최신 Python 호환 PoC 필수). |
| HWP v5 | pyhwp **주 타깃**. HWP 97/3.x 등 구형은 지원 미흡 가능. |
| 본문 추출 | **가능**(hwp5txt 또는 내부 API). |
| 표/문단 | pyhwp 수준과 동일(후보 A와 중복). |
| 운영 안정성 | 자체 파서 구현은 **매우 높은 비용** → 비권장. |

후보 D는 “A와 다른 제3의 라이브러리”보다 **A의 구현 깊이(라이브러리 vs CLI)** 선택에 가깝다.

### 후보 E. 현재처럼 UNSUPPORTED 유지

| 검토 항목 | 내용 |
|-----------|------|
| 구현 리스크 | **최소.** |
| 사용자 불편 | HWP 다수 환경에서 **검색·RAG 공백** 지속. |
| 우선순위 | DOC/XLS/PPT, OCR보다 **사내 HWP 비중**에 따라 **상향 가능**. |
| 현재 동작 | `hwp` → `process-pending-documents` 미대상 → `UNSUPPORTED_EXTENSION` 스킵, `scan_failures` **미기록**(의도적). |

---

## 4. 후보 비교표

| 후보 | Linux/headless | 구현 난이도 | 텍스트 품질 | 라인 citation 적합성 | 페이지 citation 가능성 | 운영 리스크 | 추천도 |
|------|----------------|-------------|-------------|----------------------|------------------------|-------------|--------|
| **A. pyhwp / hwp5txt → TXT** | 가능 | 보통 | 보통~양호 | **높음** | 낮음 | 중간 (AGPL·의존성) | **높음** |
| **B. converter 컨테이너** | 가능 | 보통~높음 | A와 동일 | 높음 | 낮음 | 중간 (복잡도) | **보통** |
| **C. HWP → PDF → pdf_parser** | 불확실 | 높음 | 편차 큼 | 보통 | 중간 (PDF 페이지) | 높음 | **낮음** |
| **D. 직접 파싱 / 기타 라이브러리** | 가능(=pyhwp) | 매우 높음 | 미확인 | 높음 | 낮음 | 높음 | **보류** |
| **E. UNSUPPORTED 유지** | 해당 없음 | 없음 | 없음 | 없음 | 없음 | 낮음 | **보류** (단기) |

---

## 5. 권장 방향

현재 프로젝트 제약·기존 아키텍처를 기준으로 **권장안**은 다음과 같다.

1. **HWP → TXT 추출**을 1차 경로로 채택한다.
2. 구체 도구는 **pyhwp / hwp5txt 계열**을 PoC 1순위로 검토한다 (Linux headless, COM 미사용).
3. 추출 결과는 기존과 동일하게 **`file_contents.extracted_text`**에 저장한다.
4. citation은 **라인 범위(`start_line` / `end_line`)** 를 우선 제공한다.
5. **페이지 기반 citation**은 HWP 원문 페이지가 필요할 때만 별도 트랙(후보 C 등)을 검토한다.
6. **HWP → PDF**는 MVP에 넣지 않는다.
7. **OCR**은 이미지 PDF·스캔 문서 단계에서 별도 마일스톤으로 분리한다.
8. **AGPL** 및 Python 런타임 호환은 PoC 전에 **법무·플랫폼 팀 확인**을 선행한다.
9. 운영 안정성 PoC 결과가 나쁘면 **후보 B(컨테이너 격리)** 로 승격한다.

### 5.1 PoC 결과 (2026-05, WSL2/Linux)

| 항목 | 결과 |
|------|------|
| 도구 | `hwp5txt` (pyhwp) + 명시적 `six`, `lxml`, `olefile`, `cryptography` |
| 변환 성공 | sample01/02/03 모두 `conversion_success=true` |
| 안정성 | 2회 실행 시 `line_count`·출력 hash 동일 |
| 본문형 | sample01 (~289줄), sample03 (~1114줄) — RAG 적합 |
| low-text | sample02 (~24줄, ~206B) — `HWP_MIN_EXTRACTED_TEXT_LENGTH`로 `NO_EXTRACTABLE_TEXT` 스킵 |
| stderr | `UnderlineStyle value: 15` 경고만 (비치명) |
| Python | PoC 환경 3.14 — 운영은 **3.11/3.12 고정** 권장 |

**판정:** 후보 A **기술 PoC Go** → **`hwp_parser.py` 1차 구현 완료** (AGPL·운영 런타임 조건부).

---

## 6. 기존 파서 구조와 연결 방안

### 6.1 예상 파일·레지스트리

```
backend/app/parsers/
├── hwp_parser.py          # 또는 hwp_text_converter_parser.py
├── registry.py            # _DOCUMENT_EXTENSIONS, _ORDERED에 HwpParser 추가
└── (기존) hwpx_parser.py  # HWPX는 유지, HWP와 별도
```

`HwpParser` 책임:

- `supports(extension) → extension == "hwp"`
- `parse_bytes(content, filename, extension)`:
  - 임시 디렉터리에 바이트 저장(또는 stdin 파이프 가능 여부 PoC)
  - `hwp5txt` subprocess 실행 (list 인자, timeout)
  - stdout/출력 파일을 UTF-8 텍스트로 읽기
  - `ParserResult` 반환 (`parser_name`, `parser_version`, `metadata`에 converter 버전)

`registry.py` 변경 예:

```python
_DOCUMENT_EXTENSIONS = frozenset({..., "hwp"})
_ORDERED = (..., HwpParser(), HwpxParser(), ...)
```

`pending_document_processor_service` / `PROCESS_PENDING_DOCUMENTS_DEFAULT_EXTENSIONS`:

- 기본 `include_extensions`에 `hwp` 추가 여부는 **기능 플래그·PoC 후** 결정 (일괄 활성화 vs 관리자 opt-in).

### 6.2 처리 흐름

```
WebDAV에서 .hwp 다운로드
    → HwpParser (hwp5txt 등)
    → extracted_text (UTF-8, 줄바꿈 정규화)
    → file_contents upsert + files.analysis_status = COMPLETED
    → chunk-completed-text (start_line / end_line)
    → embed-pending-chunks
    → search / RAG (citation 메타)
    → GET preview?start_line=&end_line= (라인 범위)
```

HWPX(`.hwpx`) 경로는 **기존 `hwpx_parser` 유지**—동일 Job에 두 확장자가 공존.

### 6.3 기존 정책 재사용

- `max_file_size_bytes`, `limit`, `reprocess_skipped`, worker heartbeat, `scan_jobs` / `scan_failures` 패턴은 **변경 없이** 재사용.
- `UNSUPPORTED_EXTENSION`은 레지스트리 등록 **전**에만 해당; 등록 후에는 아래 §8 오류 코드 사용.

---

## 7. line 기반 citation 전략

### 7.1 원칙

프로젝트는 chunking 시 **정규화된 extracted_text** 기준으로 `start_line` / `end_line`을 계산한다(`chunking_service` 주석과 동일). HWP도 **추출 TXT 기준 라인**을 단일 진실 공급원(Single Source of Truth)으로 한다.

### 7.2 처리 단계

1. **hwp5txt 출력**을 UTF-8 문자열로 수집.
2. 줄바꿈을 `\n`으로 통일(CRLF → LF).
3. `file_contents.extracted_text`에 저장.
4. `chunk-completed-text`가 기존과 같이 chunk 생성 → `document_chunks.start_line`, `end_line` (1-based, inclusive).
5. 검색/RAG 결과에 `file_id`, `chunk_id`, `start_line`, `end_line` 포함.
6. `GET /api/files/{id}/preview?start_line=&end_line=` 로 해당 범위 표시.

### 7.3 사용자·UI 안내

- citation은 **「원문 HWP 페이지」가 아니라 「추출·변환된 텍스트의 줄 번호」** 임을 명시한다.
- 표가 한 줄로 합쳐진 경우, 라인 번호가 원본 화면 행과 다를 수 있음.
- 관리자 UI(파이프라인 모달·문서 처리 패널)에 **「HWP: 줄 번호는 변환 텍스트 기준」** 도움말 추가 검토.

### 7.4 페이지 번호

- 1차 릴리스에서는 **제공하지 않음**.
- 메타데이터에 `source_format: hwp`, `converter: hwp5txt`, `converter_version` 정도만 optional 저장.

---

## 8. 실패 처리 정책

기존 `pending_document_processor_service` 오류 코드 체계에 맞춘다.

| 상황 | analysis_status | error_code (제안) | scan_failures |
|------|-----------------|-------------------|---------------|
| 변환 도구 미설치 / PATH 없음 | SKIPPED | `HWP_CONVERTER_NOT_AVAILABLE` | 선택: 기록(소량) 또는 `PARSING_FAILED` 통합 |
| hwp5txt 비정상 종료·손상 파일 | FAILED | `HWP_CONVERSION_FAILED` 또는 `PARSING_FAILED` | **기록** (`PARSING_FAILED`와 통합 가능) |
| 추출 텍스트 없음·공백만 | SKIPPED | `NO_EXTRACTABLE_TEXT` | 기록 가능(기존과 동일) |
| 암호·보호 문서 | FAILED | `PASSWORD_PROTECTED` 또는 `HWP_PROTECTED` | **기록** |
| `size_bytes` > max | SKIPPED | `FILE_TOO_LARGE` | **기록** |
| HWP 3.x 등 미지원 버전 | SKIPPED | `UNSUPPORTED_HWP_VERSION` | 기록 또는 스킵만 |
| 확장자만 hwp인데 레지스트리 미등록 | SKIPPED | `UNSUPPORTED_EXTENSION` | **미기록**(기존 정책) |

**권장:**

- 운영·대시보드 단순화를 위해 **`PARSING_FAILED`에 세부 `analysis_error_message`/`metadata.converter_stderr`** 를 넣고, 필요 시 전용 코드(`HWP_*`)를 추가한다.
- `UNSUPPORTED_EXTENSION`은 **의도적 스킵·대량 노이즈 방지**를 위해 `scan_failures`에 넣지 않는다(기존 README와 동일).
- `DOWNLOAD_FAILED`, WebDAV 인증 실패는 기존과 동일.

---

## 9. 보안 고려사항

| 항목 | 대응 |
|------|------|
| Command injection | 파일명을 **shell 문자열에 붙이지 않음**. `subprocess.run([executable, ...], ...)` **list 인자**만 사용. |
| 경로 조작 | 저장 파일명은 **UUID 기반** 임시명, 사용자 `remote_path`는 인자로 직접 전달하지 않음. |
| Timeout | 파일 크기별 **상한 timeout**(예: 60~300초) PoC로 조정. |
| 임시 파일 | `tempfile.TemporaryDirectory()` 등으로 **작업 종료 시 삭제**. |
| 출력 크기 | 추출 텍스트 **최대 문자 수** cap(기존 HWPX `MAX_TOTAL_CHARS`와 유사 정책). |
| 로깅 | credential, token, password, **원문 전체 텍스트** 로그 금지(기존 processor 주석 준수). stderr는 길이 제한 후 일부만. |
| Worker | 장시간 변환 시 **heartbeat 지연** 가능 → PDF/DOCX와 동일하게 파일 간 heartbeat, 향후 parser 훅 검토. |
| 격리 | 가능하면 **후보 B**처럼 converter 전용 컨테이너·non-root·read-only root FS 검토. |

---

## 10. 운영 고려사항

| 항목 | 내용 |
|------|------|
| 설치 | 운영 이미지에 `pyhwp` + 시스템 패키지(`libxml2`, `xsltproc` 등 PoC로 확인) 포함. |
| Docker | 단일 backend 이미지에 포함 vs **converter sidecar** — PoC 후 결정. |
| 처리 속도 | 파일당 수 초~수십 초 가정. 대량 HWP 시 **worker `limit`·동시 worker 수** 조절. |
| Timeout | `WORKER_STALE_TIMEOUT`·Job 단위 timeout과 변환 timeout 정합. |
| 재처리 | `reprocess_skipped=true` + `include_extensions=hwp` 또는 `FAILED` → **재시도 Job** (`/admin/jobs/.../retry`). |
| 관리자 UI | 지원 확장자 목록에 **hwp** 표시, 미설치 시 「HWP 변환기 unavailable」 배지. |
| 사용자 안내 | HWP 미지원/실패 시 「HWPX로 저장 후 재업로드」·「변환 실패: 암호/구버전」 등 짧은 메시지. |

---

## 11. PoC 계획

구현 전 **Linux(배포 타깃과 동일 OS)** 에서 다음을 수행한다.

| 단계 | 내용 |
|------|------|
| 1 | 샘플 HWP **3~5개** 준비: 일반 문서, 표 포함, 장문, (가능 시) 암호/보호, (가능 시) 구형 HWP |
| 2 | `hwp5txt`(또는 동급) 설치·버전 고정 |
| 3 | CLI로 TXT 출력, **육안 품질**·표 손실 확인 |
| 4 | **한글 깨짐·인코딩** 확인 |
| 5 | 동일 파일 2회 실행 시 **줄 번호 안정성**(동일 입력 → 동일 줄 구조) |
| 6 | 처리 시간·메모리 측정(장문·표 문서) |
| 7 | 실패 케이스 목록화(손상, 암호, v3, 0바이트) |
| 8 | **AGPL**·Python 버전(프로젝트 3.11+ / 3.14 등) 호환 확인 |
| 9 | Go/No-Go: `hwp_parser.py` adapter 착수 여부 결정 |

**산출물:** PoC 결과 표(파일명, 크기, 소요 시간, 줄 수, 성공/실패, 비고), 권장 timeout·max_chars.

---

## 12. 향후 구현 단계 제안

1. HWP 처리 방식 **PoC** (본 문서 §11)
2. **`hwp_parser.py`** adapter 초안 (subprocess + 임시 파일)
3. **`registry.py`**에 `hwp` 등록, 기본 extensions 정책 결정
4. `process-pending-documents` **dry_run**에서 hwp 대상 건수 확인
5. HWP → TXT → **`file_contents`** 저장 E2E (동기 API)
6. **line 기반 preview/citation** 검증 (검색 → preview 링크)
7. worker **`PROCESS_PENDING_DOCUMENTS`** / PIPELINE에서 hwp 처리 검증
8. 관리자·프론트에 **HWP 지원 상태**·안내 문구
9. **실패 코드**·`scan_failures`·대시보드 지표 정리
10. 품질 고도화(표 개선, converter 컨테이너, 구버전 정책)

---

## 13. 이번 단계에서 하지 말아야 할 것

- HWP parser **구현**
- pyhwp **설치** (운영/개발 환경 변경)
- `requirements.txt` **수정**
- backend / frontend **코드 수정**
- DB **스키마·마이그레이션**
- API **스펙 변경**
- **OCR** 구현
- HWP Automation / **COM** 도입
- Windows 전용·**한컴오피스 설치 의존** 방식 제안

---

## 14. 완료 보고

### 생성·수정한 파일 목록

| 경로 | 작업 |
|------|------|
| `docs/07_아키텍처/hwp_처리방식_검토.md` | **신규 작성** (본 문서) |

코드·`requirements.txt`·DB·API·프론트엔드는 **변경 없음**.

### 작성한 문서 경로

- `docs/07_아키텍처/hwp_처리방식_검토.md`

### 검토한 HWP 처리 후보

- **A.** pyhwp / hwp5txt → TXT  
- **B.** 변환 CLI 별도 컨테이너  
- **C.** HWP → PDF → pdf_parser  
- **D.** 직접 바이너리 파싱 / 기타 라이브러리  
- **E.** 현행 UNSUPPORTED 유지  

### 후보별 장단점 요약

| 후보 | 장점 | 단점 |
|------|------|------|
| A | Linux headless, 기존 파이프라인·라인 citation과 정합, 구현 범위 명확 | AGPL, 표/구버전 품질, 의존성·Python 호환 |
| B | 장애·보안 격리, 스케일 | 운영·배포 복잡도 증가 |
| C | PDF 페이지 메타 가능 | Linux HWP→PDF 불확실, 2단계·OCR 리스크, 목표와 불일치 |
| D | (이론적) 최적화 여지 | pyhwp 외 대안 부족, 자체 구현 비용 과다 |
| E | 리스크 제로 | 사내 HWP 본문 검색 공백 지속 |

### 권장 방향

**후보 A (HWP → TXT, pyhwp/hwp5txt)** 를 1차로 PoC하고, 추출 텍스트를 `file_contents` → chunk → search/RAG에 연결한다. AGPL·호환성 확인 후 진행. 운영 이슈 시 **후보 B**로 격리 승격.

### line 기반 citation 전략

추출 TXT를 정규화해 `file_contents`에 저장하고, `chunking_service`가 **1-based `start_line` / `end_line`** 을 부여한다. 검색·RAG·preview는 이 라인 범위를 사용하며, **원본 HWP 페이지 번호는 1차 제공하지 않는다.**

### 실패 처리 정책

기존 `SKIPPED` / `FAILED` / `NO_EXTRACTABLE_TEXT` / `PASSWORD_PROTECTED` / `FILE_TOO_LARGE` / `PARSING_FAILED` 체계를 확장한다. HWP 전용 코드(`HWP_CONVERTER_NOT_AVAILABLE`, `HWP_CONVERSION_FAILED`, `UNSUPPORTED_HWP_VERSION` 등)는 PoC 후 확정. `UNSUPPORTED_EXTENSION`은 레지스트리 미등록·의도 스킵 시 **`scan_failures` 미기록** 유지.

### 보안 고려사항

subprocess list 인자, 임시 파일·timeout·출력 크기 제한, 민감 정보·전체 본문 로그 금지, 필요 시 converter 샌드박스.

### PoC 계획

§11 — Linux에서 샘플 3~5종, 품질·인코딩·줄 안정성·성능·실패 케이스·라이선스·Python 호환 확인 후 Go/No-Go.

### 향후 구현 순서

§12 — PoC → parser adapter → registry → dry_run → E2E → citation 검증 → worker → UI → 실패 코드 → 고도화.

### 아직 결정이 필요한 항목

- **AGPLv3+** 사내 배포·네트워크 서비스 제공 시 의무 범위 (법무)
- 프로젝트 **Python 버전**과 pyhwp **호환성** (PoC)
- `hwp5txt` vs pyhwp **내부 API** 직접 호출 선택
- HWP 전용 `error_code` vs `PARSING_FAILED` **통합 여부**
- 기본 `include_extensions`에 **hwp 자동 포함** vs opt-in
- converter **단일 이미지 vs sidecar**
- **HWP 3.x / 97** 지원 범위(스킵 메시지 정책)
- 변환 **timeout·max_chars** 구체값

### 다음 단계 제안

1. 이해관계자 리뷰(본 문서)  
2. **PoC 티켓** 생성 — Linux 환경, 샘플 HWP, hwp5txt 실행·결과 아카이브  
3. PoC 통과 시 **`hwp_parser.py` + registry** 구현 티켓 (별도 PR, `requirements.txt`·이미지 문서화 포함)  
4. 프론트 관리자 UI에 HWP 지원·「변환 텍스트 기준 줄 번호」 안내 반영  

---

*문서 버전: 2026-05-15 · internal-ai-search 아키텍처 검토*
