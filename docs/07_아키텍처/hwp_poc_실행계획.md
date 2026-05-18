# HWP 텍스트 추출 PoC 실행 계획

> **선행 문서:** [`hwp_처리방식_검토.md`](./hwp_처리방식_검토.md)  
> **범위:** Linux/headless에서 **HWP 바이너리(`.hwp`) → TXT** 추출 가능 여부를 **독립 PoC**로 검증한다.  
> **본 단계:** 실행 계획 문서 + 실험용 스크립트 초안만 제공한다. **운영 코드·DB·API·frontend 변경 없음.**

### Windows 개발 PC에서 실행할 때

- **PowerShell/CMD에서 직접 PoC를 돌리기보다 WSL2 Ubuntu 등 Linux 환경에서 실행하는 것을 권장**한다. (최종 배포가 Linux/headless이므로 동일 OS에서 검증)
- 상세 절차: [`hwp_poc_windows_wsl_가이드.md`](./hwp_poc_windows_wsl_가이드.md)
- **Git:** 루트 `.gitignore`에 `tmp/hwp_poc/`, `.venv-hwp-poc/` 가 포함되어 있어 샘플 HWP·변환 TXT·PoC venv가 커밋되지 않도록 한다. 샘플·출력은 **민감 문서**일 수 있으므로 **절대 커밋하지 않는다.**

---

## 1. PoC 목적

| 목적 | 설명 |
|------|------|
| 추출 안정성 | Linux/headless에서 `.hwp`를 TXT로 **안정적으로** 변환할 수 있는지 |
| 한글 품질 | 추출 텍스트 **한글 깨짐** 여부 |
| 줄 번호 안정성 | 동일 파일 **2회 변환** 시 `line_count`·출력 hash **동일성** (향후 line citation 전제) |
| 구조 손실 | **표·문단** 손실 수준 육안·메모 기록 |
| 성능 | 파일당 **처리 시간·메모리**(선택) 측정 |
| 라이선스·호환 | **pyhwp AGPLv3+**, **Python 버전** 호환 — Go/No-Go 판단 근거 |
| 의사결정 | **Go / 조건부 Go / No-Go** 기준 확정 → `hwp_parser.py` 구현 티켓 여부 |

---

## 2. PoC 범위

### 포함

- pyhwp / **hwp5txt** 설치 가능 여부 확인 (PoC 전용 venv)
- 샘플 HWP 파일 변환
- TXT 결과 품질·메타데이터 기록
- 동일 파일 **2회** 변환 시 line count / SHA-256 동일성
- 실패 케이스·stderr 요약 기록
- 변환 **소요 시간(ms)** 측정
- 실험 스크립트: `tools/hwp_poc/hwp5txt_poc.py`

### 제외

- 운영 **parser** 구현 (`hwp_parser.py`)
- `requirements.txt` / Dockerfile 반영
- `process-pending-documents` · `registry.py` 통합
- UI 반영
- **OCR**
- **HWP Automation / COM**
- Windows **한컴오피스** 설치 의존 방식
- 샘플 HWP·출력 TXT의 **Git 커밋**

---

## 3. 테스트 환경

PoC 실행자가 **실행 직전** 아래를 기록해 보고서(또는 이 문서 §7 표 상단 메모)에 남긴다.  
**Cursor/에이전트는 Python·OS 버전을 가정하지 않는다.**

```bash
python --version
# 또는: python3 --version

cat /etc/os-release
# WSL2: 위 명령 동일. Windows 호스트만 쓰는 경우 uname -a 도 기록

which hwp5txt
hwp5txt --help   # 실패 시 pip show pyhwp
```

| 항목 | 기록 내용 (예) |
|------|----------------|
| OS | `cat /etc/os-release` 출력 |
| Python | `python --version` (프로젝트 venv 사용 시 **그 venv** 기준) |
| 후보 도구 | pyhwp + `hwp5txt` CLI |
| 샘플 위치 | `tmp/hwp_poc/samples/` (로컬만, **커밋 금지**) |

**권장 환경:** 배포 타깃과 동일한 **Linux 서버** 또는 **WSL2**.  
PoC 전용 **가상환경**을 만들어 `pip install pyhwp` 한다. **프로젝트 `requirements.txt`는 수정하지 않는다.**

---

## 4. 샘플 파일 기준

**3~5개**의 `.hwp`를 준비한다.

| # | 유형 | 목적 |
|---|------|------|
| 1 | 일반 텍스트 문서 | 기본 한글·문단 추출 |
| 2 | 표 포함 문서 | 표 평탄화·구조 손실 확인 |
| 3 | 긴 문서 | timeout·성능 |
| 4 | (가능 시) 암호/보호 문서 | 실패 코드·stderr 패턴 |
| 5 | (가능 시) 오래된 HWP | 버전 호환 |

**저장 위치 (권장):** `tmp/hwp_poc/samples/`

**Git 정책:**

- 샘플 HWP·출력 TXT는 **저장소에 커밋하지 않는다** (원문·추출 본문 유출 방지).
- 루트 `.gitignore`에 **`tmp/hwp_poc/`**, **`.venv-hwp-poc/`** 가 등록되어 있어야 한다. (민감 문서가 포함될 수 있음.)
- Windows에서 WSL2로 PoC할 때도 동일 경로(`tmp/hwp_poc/`)를 쓰면 ignore가 적용된다.

---

## 5. 검증 항목

파일·실행(run)마다 아래를 기록한다. (`hwp5txt_poc.py`가 JSONL에 대부분 자동 기록)

| 필드 | 설명 |
|------|------|
| `filename` | 원본 파일명 |
| `file_size_bytes` | HWP 크기 |
| `conversion_success` | 종료 코드 0 + 비어 있지 않은 출력 |
| `elapsed_ms` | 변환 소요 |
| `output_text_size` | UTF-8 바이트 길이 |
| `line_count` | 줄 수 |
| `sha256_of_output_text` | 출력 텍스트 SHA-256 |
| `first_5_lines` | 앞 5줄만(각 줄 최대 200자) — 전문 로그 금지 |
| `contains_korean_ok` | 한글 음절 존재 여부(휴리스틱) |
| `table_quality_note` | 기본 `manual_review_required` — 육안 후 수동 갱신 |
| `error_message` | 실패 시 요약 |
| `stderr_summary` | stderr 최대 500자 |

**안정성 (repeat ≥ 2):** 첫·두 번째 성공 run의 `line_count`·hash 일치 → `stable_line_count`, `stable_output_hash`.

---

## 6. Go / No-Go 기준

### Go (운영 parser 구현 티켓 진행)

- 일반 문서·**표 포함** 문서에서 **한글 깨짐 없음** (육안 + `contains_korean_ok`)
- 동일 파일 2회 변환 시 **`line_count`·출력 hash 동일**
- 장문이 설정 **timeout**(기본 120s) 내 완료
- PoC 로그·stdout에 **원문 전체·추출 전문 미노출** (스크립트 정책 준수)
- **AGPL** 검토 완료 **또는** “PoC/내부 실험만”으로 명시적 제한 후 법무 승인

### 조건부 Go

- 일부 구형 HWP만 실패 → `UNSUPPORTED_HWP_VERSION` 스킵 정책으로 진행
- 변환기 크래시 빈도 높음 → **converter sidecar**(별도 컨테이너) 설계 후 진행
- timeout 조정·`max_chars` cap 필요

### No-Go

- 한글이 **지속적으로** 깨짐
- 실행마다 **line_count / hash 불일치**
- 대부분 문서에서 변환 실패
- **AGPL** 리스크 미해소 상태에서 운영 반영 요구
- **현재 Python**과 pyhwp **호환 불가** (설치·import·실행 불가)

---

## 7. 결과 기록 양식

### 7.1 환경 기록 (실행 전)

| 항목 | 값 |
|------|-----|
| OS (`/etc/os-release`) | PRETTY_NAME="Ubuntu 26.04 LTS"
NAME="Ubuntu"
VERSION_ID="26.04"
VERSION="26.04 (Resolute Raccoon)"
VERSION_CODENAME=resolute
ID=ubuntu
ID_LIKE=debian
HOME_URL="https://www.ubuntu.com/"
SUPPORT_URL="https://help.ubuntu.com/"
BUG_REPORT_URL="https://bugs.launchpad.net/ubuntu/"
PRIVACY_POLICY_URL="https://www.ubuntu.com/legal/terms-and-policies/privacy-policy"
UBUNTU_CODENAME=resolute
LOGO=ubuntu-logo |
| Python (`python --version`) | Python 3.14.4 |
| pyhwp 버전 (`pip show pyhwp`) | Name: pyhwp
Version: 0.1b15
Summary: hwp file format parser
Home-page: https://github.com/mete0r/pyhwp
Author: mete0r
Author-email: mete0r@sarangbang.or.kr
License: GNU Affero General Public License v3 or later (AGPLv3+)
Location: /home/chjeon/.venv-hwp-poc/lib/python3.14/site-packages
Requires: cryptography, lxml, olefile
Required-by: |
| hwp5txt 경로 (`which hwp5txt`) | /home/chjeon/.venv-hwp-poc/bin/hwp5txt |
| PoC 일시 | 2026-05-15 17:48 |

### 7.2 파일별 결과 (실행 후)

| 파일 | 크기 | 성공 | 소요 ms | 줄 수 | 출력 hash | 한글 품질 | 표 품질 | 오류 |
|------|-----:|:---:|------:|-----:|-----------|-----------|---------|------|
| sample1.hwp | | | | | | | | |
| sample2_table.hwp | | | | | | | | |
| sample3_long.hwp | | | | | | | | |
| sample4_protected.hwp | | | | | | | | |
| sample5_old.hwp | | | | | | | | |

- **성공:** `conversion_success` 또는 최종 run OK  
- **한글 품질:** OK / 깨짐 / 해당 없음 (영문만)  
- **표 품질:** 양호 / 부분 손실 / 심각 손실 / 해당 없음  
- 상세는 `tmp/hwp_poc/output/hwp_poc_report.jsonl` 참고

### 7.3 안정성·의사결정 요약

| 항목 | 결과 |
|------|------|
| stable_line_count (전 파일) | |
| stable_output_hash (전 파일) | |
| AGPL 검토 상태 | |
| **최종 판정** | Go / 조건부 Go / No-Go |
| 비고 | |

---

## 8. PoC 이후 의사결정

| 판정 | 다음 단계 |
|------|-----------|
| **Go** | `hwp_parser.py` + `registry` + `process-pending-documents` 통합 **구현 티켓** |
| **조건부 Go** | sidecar·timeout·max size·에러 코드 정책 설계 후 구현 |
| **No-Go** | `hwp` **UNSUPPORTED** 유지, UI·문서에 HWPX 권장·미지원 안내 강화 |

---

## 9. 실행 예시

**PoC 전용 venv** 또는 임시 환경에서만 수행한다.  
**Windows 개발 PC**에서는 [`hwp_poc_windows_wsl_가이드.md`](./hwp_poc_windows_wsl_가이드.md)의 WSL2 절차를 따른다.

```bash
# 저장소 루트에서
python --version
cat /etc/os-release

# PoC 전용 venv (권장)
python -m venv .venv-hwp-poc
# Linux/macOS:
source .venv-hwp-poc/bin/activate
# Windows:
# .venv-hwp-poc\Scripts\activate

# pyhwp는 PoC 환경에서만 설치 (requirements.txt 변경 금지)
pip install pyhwp

# hwp5txt 확인
hwp5txt --help
which hwp5txt

# 샘플 디렉터리 (Git 커밋 금지)
mkdir -p tmp/hwp_poc/samples
# 여기에 .hwp 파일 복사 (3~5개)

# PoC 실행
python tools/hwp_poc/hwp5txt_poc.py \
  --input-dir tmp/hwp_poc/samples \
  --output-dir tmp/hwp_poc/output \
  --timeout-seconds 120 \
  --repeat 2

# 결과 확인 (전문 출력 대신 요약·JSONL)
cat tmp/hwp_poc/output/hwp_poc_report.jsonl | head
ls -la tmp/hwp_poc/output/
```

**옵션:**

```bash
python tools/hwp_poc/hwp5txt_poc.py \
  --hwp5txt-bin /path/to/hwp5txt \
  --timeout-seconds 300 \
  --repeat 3
```

**산출물:**

| 경로 | 설명 |
|------|------|
| `tmp/hwp_poc/output/<stem>__run1.txt` | 1회차 TXT (**커밋 금지**) |
| `tmp/hwp_poc/output/<stem>__run2.txt` | 2회차 TXT |
| `tmp/hwp_poc/output/hwp_poc_report.jsonl` | run별 JSONL + file_summary |

---

## 10. PoC 스크립트

| 항목 | 내용 |
|------|------|
| 경로 | `tools/hwp_poc/hwp5txt_poc.py` |
| 용도 | 샘플 `.hwp` 순회 → `hwp5txt` subprocess → TXT 저장 → JSONL 리포트 |
| 운영 연동 | **없음** (backend에서 import 하지 않음) |

**CLI 인자:**

| 인자 | 기본값 |
|------|--------|
| `--input-dir` | `tmp/hwp_poc/samples` |
| `--output-dir` | `tmp/hwp_poc/output` |
| `--timeout-seconds` | `120` |
| `--repeat` | `2` |
| `--hwp5txt-bin` | `hwp5txt` |

**보안·로그:**

- `subprocess.run(..., shell=False)` + list 인자
- timeout 적용
- stderr 최대 **500자**만 JSONL에 저장
- 추출 **전문은 stdout에 출력하지 않음** (파일 + hash·줄 수만 요약)
- HWP 원본 파일은 **읽기만**, 수정하지 않음

**hwp5txt 호출:** 우선 **stdout capture**. 실패 시 stderr·exit code로 안내. `--output` 방식은 PoC에서 필요 시 수동 시도 후 문서에 메모.

---

## 11. HWP 라이선스 주의 (pyhwp / AGPLv3+)

- **pyhwp**는 **AGPLv3+** 로 알려져 있다. 사내 **배포·네트워크 서비스(SaaS)** 형태에서 **소스 공개·파생 저작물 의무** 등이 적용될 수 있다.
- **본 PoC는 기술 검증 용도로만** 수행한다. PoC venv에만 설치한다.
- **운영 반영 전** 법무·라이선스 검토 **완료**가 필요하다.
- AGPL이 해소되지 않으면 **No-Go** 또는 상용 변환기·별도 계약 등 **대안**을 검토한다.

---

## 12. 이번 단계에서 하지 말아야 할 것

- pyhwp를 `requirements.txt`에 추가
- 운영 backend import 경로에 pyhwp 연결
- `hwp_parser.py` 구현 · `registry.py` 수정
- `process-pending-documents`에 `hwp` 추가
- Dockerfile / DB / API / frontend 수정
- 샘플 HWP·출력 TXT 커밋
- HWP Automation / COM 사용

---

## 13. 완료 보고 (문서·스크립트 준비 단계)

| 항목 | 상태 |
|------|------|
| PoC 실행 계획 문서 | `docs/07_아키텍처/hwp_poc_실행계획.md` |
| Windows/WSL2 가이드 | `docs/07_아키텍처/hwp_poc_windows_wsl_가이드.md` |
| PoC 스크립트 초안 | `tools/hwp_poc/hwp5txt_poc.py` |
| Git ignore | 루트 `.gitignore`: `tmp/hwp_poc/`, `.venv-hwp-poc/` |
| 운영 코드 영향 | **없음** |
| 실제 PoC 실행 | **실행자가 샘플 준비 후 WSL2에서 수행** (§9, WSL 가이드) |

---

---

## 14. PoC 2차 실행 결과 (sample01–03)

| 파일 | HWP | TXT | 줄 수 | 안정성 | 비고 |
|------|-----|-----|------:|:---:|:---|
| sample01.hwp | ~9.2MB | ~13KB | 289 | ✓ | 본문형, RAG 적합 |
| sample02.hwp | ~90KB | ~206B | 24 | ✓ | 별첨/표 양식, low-text |
| sample03.hwp | ~1.5MB | ~64KB | 1114 | ✓ | 장문 제안요청서 |

- 의존성: `pyhwp` + **`six`**, `lxml`, `olefile`, `cryptography` (명시 설치)
- **최종 판정: Go** → `backend/app/parsers/hwp_parser.py` 구현
- **조건:** AGPL 법무 검토, 운영 Python 3.11/3.12, `HWP_MIN_EXTRACTED_TEXT_LENGTH=50`

---

*문서 버전: 2026-05-15 · internal-ai-search HWP PoC*
