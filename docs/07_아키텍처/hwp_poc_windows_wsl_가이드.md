# Windows 개발 PC에서 HWP PoC 실행 가이드

> **대상:** Windows에서 internal-ai-search를 개발하면서 **HWP PoC**를 수행하는 경우  
> **선행 문서:** [`hwp_poc_실행계획.md`](./hwp_poc_실행계획.md), [`hwp_처리방식_검토.md`](./hwp_처리방식_검토.md)  
> **스크립트:** `tools/hwp_poc/hwp5txt_poc.py`  
> **운영 코드·requirements.txt 변경 없음**

---

## 1. 권장 실행 방식

**Windows PowerShell/CMD에서 직접 PoC를 실행하지 말고, WSL2 Ubuntu 등 Linux 환경에서 실행하는 것을 권장합니다.**

| 이유 | 설명 |
|------|------|
| 배포 환경 정합 | 최종 서버는 **Linux/headless**를 전제로 하므로, PoC 결과도 **Linux 기준**이어야 함 |
| 검증 일관성 | `hwp5txt` / pyhwp 동작·인코딩·줄 번호 안정성을 **배포 OS와 동일**하게 확인 |
| 제약 준수 | **HWP Automation / COM**, **Windows 한컴오피스 설치 의존**을 피함 |
| 프로젝트 원칙 | [`hwp_처리방식_검토.md`](./hwp_처리방식_검토.md)와 동일 — headless 가능 방식만 PoC |

Docker Desktop의 Linux 컨테이너에서 실행하는 것도 가능하나, **1차 PoC는 WSL2가 디버깅·파일 복사·로그 확인이 쉬워 권장**합니다.

---

## 2. WSL2 환경 확인

### 2.1 Windows(호스트)에서

```powershell
wsl --status
wsl -l -v
```

- Ubuntu 등 **WSL2** 배포판이 **Running** 인지 확인합니다.
- 없으면: `wsl --install` 또는 Microsoft Store에서 Ubuntu 설치 후 재부팅.

### 2.2 WSL 배포판 안에서

```bash
cat /etc/os-release
python3 --version
which python3
which pip3
```

실행 결과는 [`hwp_poc_실행계획.md`](./hwp_poc_실행계획.md) §7 **환경 기록** 표에 붙여 넣습니다.

---

## 3. WSL2에서 PoC 전용 venv 생성

### 3.1 프로젝트 디렉터리로 이동

**방법 A — Windows 드라이브를 WSL에서 마운트 (간편)**

```bash
# 예: D: 드라이브에 clone한 경우 (경로는 환경에 맞게 수정)
cd /mnt/d/Projects/Cursor/internal_ai_search
```

**방법 B — WSL 홈 디렉터리에 clone (I/O 권장)**

```bash
cd ~
git clone <your-repo-url> internal_ai_search
cd internal_ai_search
```

`/mnt/c`, `/mnt/d` 는 Windows NTFS 위라 **대량 파일 I/O 시 느릴 수 있습니다.** PoC 샘플이 많거나 장문 HWP가 많으면 **방법 B**를 고려하세요.

### 3.2 PoC 전용 가상환경

```bash
python3 -m venv .venv-hwp-poc
source .venv-hwp-poc/bin/activate
python --version
pip install --upgrade pip
pip install pyhwp
```

- **`.venv-hwp-poc/`** 는 루트 `.gitignore`에 등록되어 **커밋되지 않습니다.**
- **`requirements.txt`에는 pyhwp를 추가하지 않습니다** (PoC 전용).

---

## 4. hwp5txt 확인

```bash
which hwp5txt
hwp5txt --help
pip show pyhwp
```

| 증상 | 조치 |
|------|------|
| `hwp5txt: command not found` | venv 활성화 후 `pip install pyhwp` 재실행, `which hwp5txt` 재확인 |
| `pip install` 실패 | §8 **실패 시 점검** 참고 (Python 버전, lxml 등) |
| `--help`는 되나 변환 실패 | 샘플 파일·stderr를 `hwp_poc_report.jsonl`에서 확인 |

---

## 5. 샘플 파일 위치

```bash
mkdir -p tmp/hwp_poc/samples
mkdir -p tmp/hwp_poc/output
```

### Windows에서 HWP 복사

| 방법 | 절차 |
|------|------|
| 탐색기 | Windows에서 `internal_ai_search\tmp\hwp_poc\samples\` 로 `.hwp` 복사 → WSL에서 동일 경로로 보임 (`/mnt/d/.../tmp/hwp_poc/samples/`) |
| WSL `cp` | `cp /mnt/c/Users/<you>/Downloads/sample.hwp tmp/hwp_poc/samples/` |

**주의 (필수):**

- 샘플 **`.hwp`는 Git 커밋 금지** — 원문이 포함됩니다.
- 변환 **`.txt`·`hwp_poc_report.jsonl`도 커밋 금지** — 추출 본문·앞 줄 샘플이 들어갈 수 있습니다.
- 루트 `.gitignore`의 **`tmp/hwp_poc/`**, **`.venv-hwp-poc/`** 가 이를 방지합니다. `git status`로 untracked/ignored 여부를 확인하세요.

---

## 6. PoC 실행

저장소 **루트**에서, **venv 활성화 상태**로:

```bash
python tools/hwp_poc/hwp5txt_poc.py \
  --input-dir tmp/hwp_poc/samples \
  --output-dir tmp/hwp_poc/output \
  --timeout-seconds 120 \
  --repeat 2
```

옵션 예:

```bash
python tools/hwp_poc/hwp5txt_poc.py \
  --hwp5txt-bin "$(which hwp5txt)" \
  --timeout-seconds 300 \
  --repeat 3
```

---

## 7. 결과 확인

```bash
ls -la tmp/hwp_poc/output
head -n 5 tmp/hwp_poc/output/hwp_poc_report.jsonl
```

**하지 말 것:**

- `cat tmp/hwp_poc/output/*.txt` 로 **전문을 터미널에 길게 출력** (민감 정보·로그 노출)
- 추출 TXT를 채팅·이슈·PR에 붙여넣기

**할 것:**

- 스크립트 stdout **요약**(파일별 성공/줄 수/stable 여부)
- JSONL의 `line_count`, `sha256_of_output_text`, `first_5_lines`, `stderr_summary`만 보고서에 반영
- 표·한글 품질은 TXT 파일을 **로컬에서만** 열어 육안 확인 후 [`hwp_poc_실행계획.md`](./hwp_poc_실행계획.md) §7 표에 기입

---

## 8. 실패 시 점검

| 항목 | 확인 방법 | 흔한 원인 |
|------|-----------|-----------|
| `hwp5txt` 없음 | `which hwp5txt` | venv 미활성, pyhwp 미설치 |
| pyhwp 설치 실패 | `pip install pyhwp` 로그 | Python 버전 비호환, 네트워크 |
| Python 호환 | `python --version`, pyhwp 문서 | 구버전 pyhwp ↔ 최신 Python |
| lxml / cryptography / olefile | `pip install` 오류 메시지 | `apt install python3-dev libxml2-dev libxslt1-dev` 등 (Ubuntu) |
| 한글 깨짐 | TXT 로컬 확인, `contains_korean_ok` in JSONL | 인코딩, 손상 파일 |
| line_count / hash 불일치 | JSONL `stable_*` 필드 | 비결정적 변환기 → **No-Go** 후보 |
| timeout | `elapsed_ms`, `--timeout-seconds` 증가 | 장문 HWP |
| 암호/보호 문서 | `error_message`, `stderr_summary` | 예상된 실패 — 별도 코드 정책 |

WSL에서 시스템 패키지가 필요할 때 (예시, Ubuntu):

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip libxml2-dev libxslt1-dev zlib1g-dev
```

---

## 9. PoC 결과를 기존 문서에 반영

[`hwp_poc_실행계획.md`](./hwp_poc_실행계획.md) **§7 결과 기록 양식**에 아래를 기입합니다.

| 항목 | 기록 위치 |
|------|-----------|
| OS | `cat /etc/os-release` (WSL) |
| Python 버전 | `python --version` (`.venv-hwp-poc` 활성화 후) |
| pyhwp 버전 | `pip show pyhwp` → Version |
| hwp5txt 경로 | `which hwp5txt` |
| 파일별 성공·줄 수·hash | §7.2 표 + `hwp_poc_report.jsonl` |
| 한글·표 품질 | §7.2 표 (육안) |
| 오류 | §7.2 표 / JSONL `error_message` |
| Go / No-Go | §7.3 **최종 판정** |

---

## 10. Git 안전장치 (요약)

루트 `.gitignore`:

```gitignore
# HWP PoC local samples and extracted text outputs
tmp/hwp_poc/

# HWP PoC-only virtualenv
.venv-hwp-poc/
```

PoC 전후 확인:

```bash
git status
# tmp/hwp_poc/ 아래 파일이 tracked 되면 안 됨
```

---

## 11. 라이선스·운영 경계

- **pyhwp (AGPLv3+)** 는 PoC venv에서만 사용. **법무 검토 전 운영 requirements에 넣지 않음.**
- 본 가이드는 **기술 검증**용이며, Windows 한컴/COM 방식은 **사용하지 않음.**

---

## 12. 관련 문서

| 문서 | 용도 |
|------|------|
| [`hwp_처리방식_검토.md`](./hwp_처리방식_검토.md) | HWP 처리 후보·권장 방향 |
| [`hwp_poc_실행계획.md`](./hwp_poc_실행계획.md) | PoC 범위·Go/No-Go·결과 표 |
| `tools/hwp_poc/hwp5txt_poc.py` | 자동 변환·JSONL 리포트 |

---

*문서 버전: 2026-05-15 · Windows + WSL2 PoC 실행*
