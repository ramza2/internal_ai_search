# HWP 표·양식 추출 고도화 PoC

> **용도:** 표·양식 위주 `.hwp`에서 **hwp5txt** vs **hwp5html** 추출 품질을 비교하고, 향후 **tiered extraction** 도입 여부를 판단한다.  
> **범위:** PoC 스크립트·문서만. **운영 `HwpParser`·API·DB·frontend 변경 없음.**

---

## 1. 배경

- 현재 운영 HWP 파서(`backend/app/parsers/hwp_parser.py`)는 **hwp5txt** subprocess 기반이다.
- **본문형 HWP**에서는 추출·chunk·embedding·search/RAG까지 E2E가 통과했다.
- **표·양식 위주 HWP**에서는 `<표>` placeholder만 나오거나 의미 텍스트가 매우 적은 경우가 있다.
- `HWP_MIN_EXTRACTED_TEXT_LENGTH`만 낮추면 `<표>` 같은 무의미 문자열이 인덱싱되어 **검색 품질이 오히려 나빠질** 수 있다.
- **HWPX**는 ZIP/XML 기반이라 가능하면 **HWPX 우선** 권장하나, 저장소에는 **HWP 바이너리**가 많을 수 있어 고도화 검토가 필요하다.

### 1.1 PoC 결과 요약 (2026-05-21, **3건**)

| 별칭 | 유형 | hwp5txt | hwp5html | recommendation |
|------|------|---------|----------|----------------|
| sample01 | 통합 공고문 (~61 KB) | FULL (1,333 B) | FULL (4,606 B) | HTML_BETTER |
| sample02 | RFP·품목공모 양식 (~672 KB) | **NONE** (29 B) | FULL (91,577 B) | **PREFER_HWP5HTML** |
| sample03 | 기업 현황·표 (~90 KB) | FULL* (206 B, placeholder多) | FULL (2,406 B) | HTML_BETTER |

- **sample02** 가 핵심: 운영 hwp5txt만 쓰면 `NO_EXTRACTABLE_TEXT`인 유형이 html flatten으로 **FULL** 회복.
- **sample01** 은 txt만으로도 검색 가능 — tiered 시 **hwp5txt fallback** 유지 근거.
- 3건 모두 html이 txt 대비 **표·필드 보강** — hwp5html이 표·양식 문서에서 **월등**한 경우가 다수.
- JSONL을 **두 번 실행**하면 6줄(sample01~06) — 기본 overwrite로 **1회만** 실행 권장.
- 본문-only·HWPX 대조 등 **추가 1~2건** 권장.
- **운영:** `HwpParser` **tiered 1차 구현** (`HWP_EXTRACTION_STRATEGY=tiered`, `hwp5txt_only` 롤백 가능).

상세: [`hwp_표양식_추출고도화_결과.md`](./hwp_표양식_추출고도화_결과.md)

---

## 2. 목표

| # | 목표 |
|---|------|
| 1 | **hwp5txt** vs **hwp5html** 결과 비교 (동일 샘플) |
| 2 | hwp5html HTML에 **table / td / th** 텍스트가 있는지 확인 |
| 3 | HTML → **plain / markdown-like** flatten 후 검색·RAG·**line citation**에 넣을 수 있는지 확인 |
| 4 | 기존 `file_contents` → chunk → embedding → search/RAG 구조 **유지** 가능 여부 |
| 5 | 추출 품질 등급 **FULL / PARTIAL / NONE** 기준 제안 |
| 6 | tiered extraction **Go / No-Go** 판단 자료 |

---

## 3. 제외 범위

- HWP Automation / COM
- Windows 한컴오피스 설치 의존
- OCR
- HWP → PDF 변환
- 상용 SDK/API
- 운영 `HwpParser` 즉시 교체
- `process-pending-documents` / DB / API / frontend 변경
- `requirements.txt` / `Dockerfile` 변경
- 샘플 HWP·HTML·TXT **Git 커밋**

---

## 4. 비교 후보

### 후보 A: 현재 hwp5txt (운영)

| | |
|---|---|
| 장점 | 이미 구현·검증됨, 단순 subprocess |
| 단점 | 표·양식 약함, `<표>` placeholder |

### 후보 B: hwp5html (이번 PoC **주력**)

| | |
|---|---|
| 기대 | HTML `table` / `td` / `th`에 셀 텍스트 |
| 후처리 | stdlib `HTMLParser`로 flatten → 탭·줄바꿈 텍스트 |
| 리스크 | 출력 옵션·버전 차이, pyhwp **AGPL** 동일 |

CLI (pyhwp, Docker backend 기준):

```text
hwp5html [--html] [--output OUTPUT] <hwp5file>
```

### 후보 C: hwp5proc / BodyText XML

| | |
|---|---|
| 기대 | 내부 XML/노드 순회로 표·문단 직접 추출 |
| 리스크 | 구현량·구조 분석 부담 |
| 이번 단계 | **조사·후보만** (스크립트 미구현) |

### 후보 D: 표 전용 extractor

- `hwp5-table-extractor`, `hwplib-py`, `hwp2md` 등 — **이름만 후보**
- 라이선스·유지보수·호환성은 **후속 PoC**

---

## 5. 품질 지표 (JSONL)

`tools/hwp_poc/hwp_table_extraction_poc.py`가 파일별로 기록:

| 필드 | 설명 |
|------|------|
| `hwp5txt_*` | success, elapsed_ms, text_size, line_count, sha256, table_placeholder_count |
| `hwp5html_*` | success, raw_size, flatten_text_size, flatten_line_count, table_count, sha256 |
| `korean_char_count_txt/html` | 한글 글자 수 |
| `keyword_hits_txt/html` | `--keywords` substring 매칭 |
| `keyword_hits_txt/html_normalized` | 공백 제거 후 비교 (예: `에이전틱AI` ↔ `에이전틱 AI`) |
| `html_table_block_count` / `html_table_block_line_count` | flatten `--- table N ---` 블록 수·줄 수 |
| `html_table_block_text_size` / `html_table_text_estimate` | 블록 내 텍스트·의미 길이(placeholder 제외) |
| `recovered_table_text_estimate` | `\t` 포함 행만 합산(레거시; 0 ≠ 표 부재) |
| `quality_txt` / `quality_html` | FULL / PARTIAL / NONE |
| `recommendation` | HTML_BETTER, PREFER_HWP5HTML, KEEP_HWP5TXT, NO_EXTRACTABLE_TEXT 등 |
| 리포트 JSONL | 기본 **overwrite**; `--append` 시에만 추가 |

---

## 6. 품질 등급 기준 (제안)

### FULL

- 본문 또는 **표 셀** 텍스트가 충분히 추출됨 (의미 길이·한글/숫자 기준, PoC 스크립트 `_MIN_MEANINGFUL_LEN` 참고)
- 검색/RAG·chunk line citation에 **그대로 사용 가능**

### PARTIAL

- 일부 텍스트는 있으나 표·양식 **핵심값 일부 누락** 가능
- 검색은 가능하나 UI/메타에 **「부분 추출」** 안내 권장

### NONE

- `<표>` placeholder 비율이 높고 의미 텍스트 부족
- 운영 정책: **`NO_EXTRACTABLE_TEXT` / SKIPPED** (현행과 동일)

### recommendation (경로 비교)

| 값 | 의미 |
|----|------|
| `HTML_BETTER` | flatten HTML 의미 텍스트가 hwp5txt 대비 **2배 이상** (TODO threshold) |
| `PREFER_HWP5HTML` | txt NONE, html PARTIAL/FULL |
| `KEEP_HWP5TXT` | html NONE, txt PARTIAL/FULL |
| `TIERED_HTML_THEN_TXT` | 둘 다 FULL — tiered 1차 html, 2차 txt fallback |
| `NO_EXTRACTABLE_TEXT` | 둘 다 NONE |
| `REVIEW_MANUAL` | 자동 판정 애매 — 육안·템플릿 기록 |

> 정확한 threshold는 샘플 라벨링 후 코드·문서 **TODO**로 조정한다.

---

## 7. 향후 구현 방향 (PoC 성공 시)

```
HwpParser (tiered, 제안)
  1) hwp5html → HTML flatten → extracted_text
  2) fallback: hwp5txt
  3) 여전히 부족 → SKIPPED / NO_EXTRACTABLE_TEXT
```

메타데이터(제안, DB/API 변경은 별도 설계):

- `extraction_quality`: FULL | PARTIAL | NONE
- `table_placeholder_ratio`
- `converter_used`: hwp5html | hwp5txt

---

## 8. 운영 정책

- **HWPX 우선** 권장 (동일 저장소에 HWPX 있으면 HWP보다 우선 처리)
- 표·양식 HWP는 **부분 추출 가능성** 안내
- **AGPL** 법무 검토 지속 (pyhwp / hwp5html 동일 계열)
- `<표>`만 있는 텍스트는 **인덱싱하지 않음** (min length만 낮추지 않음)

---

## 9. 실행 방법

### 9.1 준비

```bash
mkdir -p tmp/hwp_poc/table_samples
# 표/양식 HWP 샘플을 tmp/hwp_poc/table_samples 에 복사 (Git 커밋 금지)

python tools/hwp_poc/check_hwp_runtime.py --json
```

### 9.2 PoC 실행 (로컬 권장)

```bash
python tools/hwp_poc/hwp_table_extraction_poc.py \
  --input-dir tmp/hwp_poc/table_samples \
  --output-dir tmp/hwp_poc/table_output \
  --keywords "품목(문제)명,관리번호,에이전틱 AI" \
  --timeout-seconds 120 \
  --json
```

산출물 (`tmp/hwp_poc/table_output/`, gitignored):

- `{stem}.hwp5txt.txt`
- `{stem}.hwp5html.raw.html`
- `{stem}.hwp5html.flatten.txt`
- `hwp_table_extraction_report.jsonl`

### 9.3 Docker (선택)

```bash
docker compose --env-file backend/.env -f docker-compose.dev.yml run --rm \
  -v "${PWD}/tools:/app/tools" \
  -v "${PWD}/tmp/hwp_poc:/app/tmp/hwp_poc" \
  backend python tools/hwp_poc/hwp_table_extraction_poc.py \
    --input-dir tmp/hwp_poc/table_samples \
    --output-dir tmp/hwp_poc/table_output \
    --keywords "품목(문제)명,관리번호,에이전틱 AI"
```

(PowerShell: `-v "${PWD}/tools:/app/tools"` 등 동일.) 이미지에 PoC 스크립트가 없으면 **`tools` 볼륨 마운트 필수**. 샘플·출력은 `tmp/hwp_poc` 마운트. **로컬 Python 실행을 우선**해도 된다.

### 9.4 결과 기록

- 1차 기록: [`hwp_표양식_추출고도화_결과.md`](./hwp_표양식_추출고도화_결과.md)
- 추가 실행·샘플: [`hwp_표양식_추출고도화_결과템플릿.md`](./hwp_표양식_추출고도화_결과템플릿.md)

---

## 10. 관련 문서·도구

| 항목 | 경로 |
|------|------|
| PoC 스크립트 | `tools/hwp_poc/hwp_table_extraction_poc.py` |
| 1차 결과 | `docs/07_아키텍처/hwp_표양식_추출고도화_결과.md` |
| 결과 템플릿 | `docs/07_아키텍처/hwp_표양식_추출고도화_결과템플릿.md` |
| HWP 처리 검토 | `docs/07_아키텍처/hwp_처리방식_검토.md` |
| hwp5txt PoC | `docs/07_아키텍처/hwp_poc_실행계획.md` |
| 운영 E2E | `docs/07_아키텍처/hwp_e2e_검증계획.md` |

---

*문서 버전: 2026-05-21 · PoC 단계 (운영 미반영)*
