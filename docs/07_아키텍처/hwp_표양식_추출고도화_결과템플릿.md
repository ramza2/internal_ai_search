# HWP 표·양식 추출 고도화 PoC — 결과 템플릿

> **용도:** `hwp_table_extraction_poc.py` 실행 후 **로컬 복사본**에만 기록.  
> **Git:** 샘플 HWP·HTML·TXT·본문 전문 **커밋 금지**.

---

## 1. 검증 환경

| 항목 | 값 |
|------|-----|
| 검증 일시 | YYYY-MM-DD |
| OS | (예: Windows 10 + WSL2 / Linux) |
| Python | |
| pyhwp / hwp5txt / hwp5html | `check_hwp_runtime.py --json` / `which hwp5html` |
| Docker backend | 예 / 아니오 |
| PoC 스크립트 | `tools/hwp_poc/hwp_table_extraction_poc.py` |
| `--keywords` | (예: `품목(문제)명,관리번호,에이전틱 AI`) |
| `--append` | 기본 **없음** (JSONL overwrite). 있으면 append |
| `--timeout-seconds` | |
| 리포트 모드 | overwrite / append |

---

## 2. 샘플 목록 (별칭만)

| 별칭 | 유형 | 크기(bytes) | 비고 |
|------|------|------------:|------|
| sample01 | 표 위주 | | |
| sample02 | 양식/RFP | | |
| sample03 | 본문+표 혼합 | | |
| sample04 | | | |

실제 파일명·경로는 민감 시 **기록하지 않음**. `tmp/hwp_poc/table_samples/` 로컬만.

---

## 3. hwp5txt vs hwp5html 비교표

| 파일(별칭) | 유형 | hwp5txt 줄 수 | hwp5txt 텍스트(B) | placeholder 수 | hwp5html 줄 수 | hwp5html flatten(B) | HTML table 수 | html_table_block_text_size | html_table_text_estimate | quality_txt | quality_html | recommendation |
|------------|------|-------------:|------------------:|---------------:|-------------:|--------------------:|--------------:|---------------------------:|-------------------------:|-------------:|--------------|----------------|
| sample01 | | | | | | | | | | | | |
| sample02 | | | | | | | | | | | | |

- `html_table_block_*`: flatten `--- table N ---` 마커 구간 집계
- `recovered_table_text_estimate`: `\t` 포함 행만 합산(레거시, 0이어도 표 부재를 뜻하지 않음)

JSONL: `tmp/hwp_poc/table_output/hwp_table_extraction_report.jsonl` (기본 **overwrite**, `--append` 시만 추가)

---

## 4. 키워드 회수 결과

> substring 기준. 띄어쓰기 차이는 **별도 정규화하지 않음** — 실제 문서 라벨에 맞춰 `--keywords` 입력.  
> JSONL에는 `keyword_hits_*_normalized`(공백 제거 비교)도 포함.

| 별칭 | keyword | hits_txt | hits_html | hits_txt_norm | hits_html_norm | 비고 |
|------|---------|--------:|----------:|--------------:|---------------:|------|
| sample01 | | | | | | |
| sample02 | | | | | | |

---

## 5. 표 품질 메모 (육안, 본문 전문 기록 금지)

### sample01

- hwp5txt: (예: `<표>` N회, 셀 라벨 없음)
- hwp5html flatten: (예: `--- table 1 ---` 이후 탭 구분 행 확인)
- citation 줄 단위: 가능 / 어려움

### sample02

- …

---

## 6. Go / No-Go (tiered extraction)

| 기준 | 충족 |
|------|------|
| hwp5html이 표 샘플에서 txt 대비 **의미 텍스트 유의미 증가** | ☐ |
| flatten 텍스트가 chunk line citation에 **실용적** | ☐ |
| AGPL·운영 이미지에 hwp5html 추가 **수용 가능** (법무) | ☐ |
| 실패 시 hwp5txt fallback **유지** 설계 가능 | ☐ |

**판정:** Go / 조건부 Go / No-Go

**사유:**

### 다음 판단 (체크)

| 항목 | 판단 |
|------|------|
| 추가 샘플 3~5건 필요 | ☐ 예 / ☐ 아니오 |
| tiered extraction **설계·PoC 확장** 가능 | ☐ |
| **운영 `HwpParser` 변경** | ☐ 진행 / ☐ **보류** (AGPL·샘플·E2E 후) |

---

## 7. 향후 구현 제안 (PoC Go 시)

1. `HwpParser`: tiered — `hwp5html` → flatten → 길이/품질 검사 → fallback `hwp5txt`
2. `analysis_metadata` 또는 로그에 `converter_used`, `extraction_quality` (스키마 변경은 별도 PR)
3. 관리자 UI: 표·양식 HWP **부분 추출** 안내 문구
4. HWPX 동일 경로 우선 정책 유지

---

## 8. 발견 이슈 / TODO

| # | 이슈 | 조치 |
|---|------|------|
| 1 | | |
| 2 | | |

---

*템플릿 버전: 2026-05-21*
