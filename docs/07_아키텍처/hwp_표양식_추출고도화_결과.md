# HWP 표·양식 추출 고도화 PoC 결과

> **용도:** `tools/hwp_poc/hwp_table_extraction_poc.py` 실행 결과 기록.  
> **Git:** 샘플 HWP·HTML·TXT·본문 전문 **커밋 금지**.  
> **운영 (2026-05-21 이후):** `HwpParser`에 **tiered extraction 1차 구현** (`HWP_EXTRACTION_STRATEGY=tiered` 기본). `hwp5txt_only`로 되돌릴 수 있음. AGPL·표·양식 E2E는 계속 미완.

---

## 1. 검증 환경

| 항목 | 값 |
|------|-----|
| 검증 일시 | 2026-05-21 (1건) · **2026-05-21 확장 (3건)** |
| 실행 위치 | 로컬 Windows (PoC 스크립트) |
| Python | 3.12 권장 (backend 이미지와 동일 계열) |
| hwp5txt / hwp5html | ✅ |
| PoC 스크립트 | `tools/hwp_poc/hwp_table_extraction_poc.py` (v2: table block 지표, normalized keyword, JSONL overwrite) |
| `--keywords` | `품목(문제)명,관리번호,에이전틱 AI` |
| 리포트 | `tmp/hwp_poc/table_output/hwp_table_extraction_report.jsonl` |

샘플은 **별칭·유형·크기**만 기록. 원본 파일명·경로는 **미기록**.

**리포트 주의:** 동일 3건을 **두 번 실행**하면 JSONL에 **6줄**(sample01~06)이 쌓일 수 있음. `--append` 없이 한 번만 실행하거나, 리포트 파일 삭제 후 재실행(기본 **overwrite**).

---

## 2. 검증 대상 (3건)

| 별칭 | 유형 | 크기 | 비고 |
|------|------|-----:|------|
| **sample01** | 통합 **공고문** (표·본문 혼합) | 62,976 B (~61 KB) | hwp5txt도 **FULL** — 공고 요약·표 일부 txt로 추출됨 |
| **sample02** | **RFP·품목공모 양식형** (대형) | 688,640 B (~672 KB) | hwp5txt **NONE** — 운영 시 `NO_EXTRACTABLE_TEXT` 유형 |
| **sample03** | **기업 현황·표 중심** 자료 | 92,160 B (~90 KB) | txt는 짧지만 placeholder 비율 높음 — html이 표 내용 보강 |

---

## 3. 종합 비교표 (3건)

| 별칭 | hwp5txt (B) | txt quality | hwp5html flatten (B) | html quality | HTML table | html_table_text_estimate | recommendation |
|------|------------:|-------------|---------------------:|--------------|------------:|-------------------------:|----------------|
| sample01 | 1,333 | FULL | 4,606 | FULL | 4 | 1,793 | **HTML_BETTER** |
| sample02 | 29 | **NONE** | 91,577 | FULL | 24 | 31,006 | **PREFER_HWP5HTML** |
| sample03 | 206 | FULL* | 2,406 | FULL | 5 | 808 | **HTML_BETTER** |

\* sample03: txt `quality_txt=FULL`이나 한글 45자·placeholder 5 — **운영 min length·육안으로는 부족**할 수 있음. html 한글 620자·표 블록 808(estimate)로 보강.

**hwp5txt elapsed (ms):** sample01 941 · sample02 1,952 · sample03 804  
**hwp5html elapsed (ms):** sample01 830 · sample02 8,739 · sample03 992  

---

## 4. 유형별 요약

### sample01 — 공고문형

- **hwp5txt:** 43줄, 한글 344자 — 공고 본문·일부 표 라벨 **이미 검색 가능** 수준.
- **hwp5html:** flatten이 txt 대비 **~3.5×** (4,606 B), 표 블록 5개.
- **키워드:** `에이전틱 AI` html 2회 (RFP 키워드는 공고문에 없을 수 있음).
- **해석:** tiered에서 **html이 txt보다 풍부**하나, txt만으로도 FULL인 케이스 → **fallback hwp5txt 유지** 가치 있음.

### sample02 — RFP·품목공모 양식형 (핵심)

- **hwp5txt:** 29 B, 9줄, 한글 4자, `<표>` 4 — **NONE**, 운영 스킵과 동일.
- **hwp5html:** 91,577 B, 2,411줄, 한글 24,371자, table 24 — **FULL**, **PREFER_HWP5HTML**.
- **키워드 (html):** `품목(문제)명` 4 · `관리번호` 4 · `에이전틱 AI` 12 (normalized `에이전틱ai` 16).
- **해석:** 1차 PoC와 동일 — **tiered extraction 최대 수혜** 유형.

### sample03 — 현황·표 중심

- **hwp5txt:** 206 B, placeholder 5, 한글 45 — 짧지만 스크립트상 FULL.
- **hwp5html:** 2,406 B, 한글 620, table 5, estimate 808 — **HTML_BETTER**.
- **키워드:** RFP용 키워드 0 (문서 유형상 정상).
- **해석:** 표·현황표 **셀 텍스트는 html 쪽이 유의미** — txt만 쓰면 정보 손실 가능.

---

## 5. hwp5txt vs hwp5html (sample02, 양식형 기준)

| 항목 | hwp5txt | hwp5html flatten | 비율(대략) |
|------|--------:|-----------------:|-----------:|
| 텍스트 크기 | 29 B | 91,577 B | **~3,160×** |
| 줄 수 | 9 | 2,411 | **~268×** |
| 한글 수 | 4 | 24,371 | **~6,093×** |
| 품질 | NONE | FULL | — |

3건 중 **1건(sample02)** 에서 극단적 격차. 나머지 2건은 txt도 일부 추출되나 html이 **표·필드 보강**.

---

## 6. 키워드 hit (3건, `--keywords` 권장값)

| 별칭 | 품목(문제)명 | 관리번호 | 에이전틱 AI | 비고 |
|------|-------------:|---------:|------------:|------|
| sample01 html | 0 | 0 | 2 | 공고문 |
| sample02 html | 4 | 4 | 12 | RFP 양식 — **txt 전부 0** |
| sample03 html | 0 | 0 | 0 | 현황자료 — 키워드 미해당 |

normalized hit으로 `에이전틱 AI` / `에이전틱AI` 차이는 sample02 html에서 보완됨.

---

## 7. 지표·리포트

| 지표 | sample02 예시 | 설명 |
|------|---------------|------|
| `html_table_block_count` | 24 | `--- table N ---` 블록 수 |
| `html_table_text_estimate` | 31,006 | placeholder 제외 의미 길이 |
| `recovered_table_text_estimate` | 0 | `\t` 행만 합산(레거시) — **0 ≠ 표 부재** |

---

## 8. Go / No-Go (tiered extraction)

| 기준 | 3건 기준 |
|------|----------|
| hwp5html이 표·양식 샘플에서 txt 대비 유의미 증가 | ☑ (sample02 극단, sample01·03 보강) |
| 일부 문서는 hwp5txt만으로 FULL | ☑ (sample01) → **fallback 필수** |
| flatten·line citation 호환 | ☑ (E2E 미실시) |
| hwp5html 런타임 | ☑ 대형 ~8.7 s / 672 KB, 소형 ~1 s |
| AGPL | ☐ 법무 **미완** |
| 샘플 다양성 | △ **3건** (본문-only·HWPX 대조 등 추가 권장) |

**판정:** **조건부 Go → tiered 1차 구현 완료** (기본 전략 `tiered`, 코드: `hwp_parser.py`, `hwp_html_flattener.py`, `hwp_quality.py`)

**사유:** 양식형에서 txt NONE → html FULL. 공고문형은 txt도 쓸 만해 **html 우선 + txt fallback**이 3건과 맞음. 남은 것: compose E2E·metadata 영속화(별도)·AGPL.

---

## 9. 권장 방향 (구현은 별도 PR)

```
hwp5html → flatten → quality check
  → FULL/PARTIAL: html 경로 사용
  → NONE: hwp5txt fallback → 재검사
  → 둘 다 NONE: NO_EXTRACTABLE_TEXT
```

- **HWPX 우선** · 표 많은 HWP는 HWPX 권장 유지  
- metadata 후보: `converter_used`, `extraction_quality`, `table_count`, `table_text_length`, `fallback_used`

---

## 10. 다음 단계

| 우선순위 | 항목 |
|----------|------|
| P1 | JSONL **6줄 → 3줄** 정리(리포트 삭제 후 overwrite 재실행) |
| P2 | 본문-only HWP 1~2건 추가 |
| P3 | sample02 flatten → ingest/search **E2E** |
| P4 | tiered `HwpParser` PoC 브랜치 |
| P5 | AGPL 검토 |

---

## 11. 관련 문서

- 계획: [`hwp_표양식_추출고도화_poc.md`](./hwp_표양식_추출고도화_poc.md)
- 템플릿: [`hwp_표양식_추출고도화_결과템플릿.md`](./hwp_표양식_추출고도화_결과템플릿.md)
- HWP 처리 검토: [`hwp_처리방식_검토.md`](./hwp_처리방식_검토.md)

---

*문서 버전: 2026-05-21 · 3건 PoC (sample01 공고 / sample02 RFP 양식 / sample03 현황)*
