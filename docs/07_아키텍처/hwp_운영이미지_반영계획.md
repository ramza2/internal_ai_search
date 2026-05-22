# HWP 운영 이미지 반영 계획

> **범위:** Linux/headless **운영·Docker 이미지**에서 `hwp5txt` CLI가 동작하도록 **의존성·검증·운영 주의**를 정리한다.  
> **본 문서는 기술 준비이며**, AGPL 법무 승인·운영 HWP **활성화 완료**를 의미하지 **않는다.**  
> **금지:** HWP Automation/COM, Windows 한컴오피스 의존.

**선행:** [`hwp_poc_실행계획.md`](./hwp_poc_실행계획.md), [`hwp_e2e_검증계획.md`](./hwp_e2e_검증계획.md), [`hwp_처리방식_검토.md`](./hwp_처리방식_검토.md)

---

## 1. 배경

| 항목 | 내용 |
|------|------|
| Parser | `backend/app/parsers/hwp_parser.py` — 기본 **`tiered`**: `hwp5html` → flatten → 품질 검사 → `hwp5txt` fallback |
| CLI 출처 | **`pyhwp`** pip 패키지가 **`hwp5txt`**, **`hwp5html`** 엔트리포인트 제공 (추가 pip 패키지 없음) |
| PoC 교훈 | **`pyhwp`만 설치 시 `six` 누락** 등으로 실패 — `six`, `lxml`, `olefile`, `cryptography` **명시 설치** 필요 |
| 환경 | **Linux / headless** 전제 (WSL2 PoC·로컬 E2E 일부 검증됨) |
| 미사용 | HWP Automation/COM, Windows 한컴 |

운영 backend는 pyhwp Python API를 **직접 import하지 않는다.** `HWP_EXTRACTION_STRATEGY=tiered`(기본)일 때 **`hwp5html`과 `hwp5txt`가 PATH에서 실행 가능**해야 한다. `hwp5txt_only` 롤백 시 `hwp5txt`만 필요.

---

## 2. 운영 반영 전제 조건

다음이 충족되기 전 **프로덕션 HWP 활성화를 권장하지 않는다.**

| # | 조건 | 상태 |
|---|------|------|
| 1 | **AGPL 법무 검토** (pyhwp AGPLv3+) | ☐ 미완 — 기록 필수 |
| 2 | **운영 Python 버전** 결정 (권장 **3.11 / 3.12**) | ☐ PoC에 3.14 사용 사례 있음 — 운영과 분리 |
| 3 | **`requirements.txt` HWP 관련 pin** | ☐ TODO — §7 |
| 4 | 이미지 내 `hwp5txt --help` · `hwp5html --help` 성공 | ☐ `docker-compose.dev.yml` 빌드 후 실행 |
| 5 | `python tools/hwp_poc/check_hwp_runtime.py --json` → `status: ok` (전략 `tiered`) | ☐ `hwp5html_found`, `hwp5html_help_ok` 포함 |
| 6 | HWP E2E **조건부 Go 이상** | ☑ compose 내부 DB: [`docker_compose_db_e2e_검증결과.md`](./docker_compose_db_e2e_검증결과.md); ☑ 호스트 외부 DB: [`hwp_e2e_검증결과_docker.md`](./hwp_e2e_검증결과_docker.md) (2026-05-21) |

---

## 3. 필요한 Python 패키지 (`backend/requirements.txt`)

| 패키지 | 역할 |
|--------|------|
| **pyhwp** | HWP v5 파서·**`hwp5txt` CLI** 제공 (AGPLv3+) |
| **six** | pyhwp/구형 의존 호환 — PoC에서 **누락 시 ModuleNotFoundError** |
| **lxml** | XML/XSLT·experimental converter 경로 등 pyhwp 의존 |
| **olefile** | HWP **OLE** 컨테이너 읽기 |
| **cryptography** | pyhwp·암호/압축 관련 경로 + **프로젝트 기존** (Fernet 등) |

설치: `pip install -r backend/requirements.txt` (이미지 빌드 단계에서).

---

## 4. 시스템 패키지 후보 (Debian/Ubuntu 계열)

`lxml` 등 **네이티브 확장 빌드** 또는 런타임 라이브러리에 따라 **일부만** 필요할 수 있다.  
**원칙:** Dockerfile에 아래를 **한꺼번에 고정하기 전**, 최소 apt 집합으로 이미지를 빌드한 뒤 `check_hwp_runtime.py`로 확인하고 **필요한 것만 추가**한다.

| 후보 패키지 | 용도 |
|-------------|------|
| `build-essential` | gcc 등 — 소스 빌드 시 |
| `python3-dev` | Python C 확장 헤더 |
| `libxml2` / `libxml2-dev` | lxml |
| `libxslt1-dev` | XSLT (pyhwp experimental 경로) |
| `zlib1g-dev` | 압축 관련 빌드 |
| `libffi-dev` | cryptography 등 |
| `gcc` | (build-essential에 포함 가능) |

**슬림 이미지 1차 시도 예 (문서용):**

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    libxml2 \
    libxslt1.1 \
    && rm -rf /var/lib/apt/lists/*
```

빌드 실패 시 `libxml2-dev`, `libxslt1-dev`, `gcc` 등을 **단계적으로** 추가한다.

---

## 5. Dockerfile · Docker Compose (개발 검증용)

### 5.1 저장소 현황 (2026-05 Docker dev 마일스톤)

| 경로 | 상태 |
|------|------|
| `backend/Dockerfile` | **추가됨** — Python 3.12-slim, `WORKDIR /app`, build context = **저장소 루트** |
| `docker-compose.dev.yml` | **추가됨** — `db`, `db-migrate`, `backend`, `backend-worker` (profile `worker`) |
| `scripts/apply_migrations.py` | baseline + migrations 적용 |
| `docker/db/schema/baseline_schema.sql` | DDL only (schema dump, no data) |
| `backend/.env.example` | Docker·호스트 공통 템플릿 → `backend/.env` |
| `.dockerignore` | **추가됨** — venv, frontend, `tmp/` 등 제외 |
| 루트 `Dockerfile` / `infra/*` | **없음** (운영 배포 compose는 미구성) |

**의미:** 컨테이너에서 **backend + `hwp5txt` runtime** 검증 가능. **운영 배포 승인·AGPL 법무 완료·HWP E2E 완료를 의미하지 않는다.**

### 5.2 `backend/Dockerfile` 요약

- 베이스: `python:3.12-slim-bookworm`
- apt (빌드 안정성): `build-essential`, `gcc`, `python3-dev`, `libxml2`, `libxml2-dev`, `libxslt1-dev`, `zlib1g-dev`, `libffi-dev`
- pip: `backend/requirements.txt` (`pyhwp`, `six`, `lxml`, `olefile`, `cryptography`, …)
- 복사: `backend/app`, `backend/tests`, `tools/`
- `ENV PYTHONPATH=/app` → `uvicorn app.main:app`, `python tools/hwp_poc/check_hwp_runtime.py`
- 기본 `CMD`: uvicorn `:8000`

**Worker**는 동일 이미지에서 `python -m app.worker_main` (`docker-compose.dev.yml` — profile `worker`).

### 5.3 반영 시 최소 변경 체크

- [ ] `requirements.txt`에 HWP pip 패키지 포함 (이미 반영됨)
- [ ] apt: `check_hwp_runtime` 통과할 때까지 최소화
- [ ] `WORKDIR` + `PYTHONPATH`로 `app` 패키지 import
- [ ] `tools/hwp_poc/` 복사 또는 동등한 runtime check 경로
- [ ] **AGPL 법무 승인 전** 프로덕션 태그 배포 금지 (내부/스테이징만)

---

## 6. 이미지 빌드 후 검증 명령

**작업 디렉터리:** 저장소 루트. env: `cp backend/.env.example backend/.env` 후 CHANGE_ME·비밀번호 교체(health/DB용).

### 6.1 Compose 빌드

```bash
docker compose -f docker-compose.dev.yml build backend
```

### 6.2 Runtime check (필수, DB 불필요)

```bash
docker compose -f docker-compose.dev.yml run --rm backend \
  python tools/hwp_poc/check_hwp_runtime.py --json

docker compose -f docker-compose.dev.yml run --rm backend \
  sh -c 'which hwp5txt && hwp5txt --help | head -n 5'
```

**기대:** JSON `"status": "ok"`, `hwp5txt_found: true`, `hwp5txt_help_ok: true`, `imports` 전부 `true`.

### 6.3 Backend API · health (compose DB + host Ollama)

```bash
docker compose --env-file backend/.env -f docker-compose.dev.yml up -d

curl http://localhost:8000/health
curl http://localhost:8000/health/db
curl http://localhost:8000/health/llm
curl http://localhost:8000/health/embedding
curl http://localhost:8000/health/vector-db
```

- **DB:** `DB_HOST=db`, `DB_PORT=5432` (compose override). 호스트 접속: `localhost:5434` (기본).
- **Ollama:** `OLLAMA_BASE_URL=http://host.docker.internal:11434`
- **초기화:** `docker compose ... down -v` 후 `up -d` (volume 삭제)

### 6.4 Worker (profile)

```bash
docker compose -f docker-compose.dev.yml --profile worker up backend-worker
docker compose -f docker-compose.dev.yml --profile worker run --rm backend-worker
```

### 6.5 단독 `docker build` (compose 없이)

```bash
docker build -f backend/Dockerfile -t internal-ai-search-backend:dev .
docker run --rm internal-ai-search-backend:dev \
  python tools/hwp_poc/check_hwp_runtime.py --json
```

### 6.4 배포/CI 게이트 (향후, CI 미구현)

| 단계 | 동작 |
|------|------|
| 이미지 빌드 완료 후 | `check_hwp_runtime.py --json` 실행 |
| `status != ok` | HWP 지원 **비활성** 정책 또는 **배포 중단** (팀 결정) |
| 향후 | 별도 CI job으로 분리 가능 (본 마일스톤에서 CI 파일 생성 안 함) |

---

## 7. requirements 버전 pin 검토

**현재:** `backend/requirements.txt`에 패키지명만 있고 **버전 pin 없음**.

**권장 절차 (운영 이미지·법무 검토와 병행):**

```bash
# HWP runtime이 통과한 venv/컨테이너 안에서
pip freeze | grep -E "pyhwp|six|lxml|olefile|cryptography"
```

**옵션 A:** 위 출력을 기록한 뒤 예: `pyhwp==x.y.z` 형태로 pin (재현성).

**옵션 B (현재):** pin 미적용 — `requirements.txt` 주석에 **「PoC/스테이징 성공 환경 기준 pin 필요」** 유지.

PoC 참고: WSL에서 **Python 3.14**로 성공 사례 있으나, **운영은 3.11/3.12 고정** 권장. pin은 **운영 Python** 환경에서 다시 수집한다.

**주의:** AGPL 검토 전 pin은 **기술 재현성** 목적이며, 법무 승인과 무관하다.

---

## 8. 운영 환경 변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `HWP5TXT_BIN` | `hwp5txt` | 컨테이너에서 `which hwp5txt`로 확인 후 필요 시 절대경로 |
| `HWP_PARSER_TIMEOUT_SECONDS` | `120` | 장문 HWP — 운영 부하에 따라 상향 |
| `HWP_MIN_EXTRACTED_TEXT_LENGTH` | `50` | low-text 양식 → `SKIPPED` / `NO_EXTRACTABLE_TEXT` |

`HWP5TXT_BIN`을 존재하지 않는 경로로 두어 **우회 비활성화하는 방식은 권장하지 않는다** (실패가 `PARSING_FAILED`로 섞임). HWP를 끄려면 §9 참고.

---

## 9. AGPL 주의

- **pyhwp**는 **AGPLv3+** 로 알려져 있다.
- 사내 배포·**네트워크 서비스(SaaS)**·폐쇄 배포 시 **소스 공개·파생 저작물 의무** 등이 적용될 수 있다.
- **본 계획·Docker 예시는 기술적 준비**이며, **법무 검토 완료·운영 활성화 승인을 의미하지 않는다.**
- 법무 검토 **전:** 내부 검증·**스테이징**·**opt-in**(특정 저장소만 `include_extensions=hwp`) 권장.

---

## 10. Rollback / 비활성화 전략

HWP 장애 시 **PDF/DOCX/XLSX/PPTX/HWPX** 파이프라인은 유지한다.

| 방법 | 설명 |
|------|------|
| **기본 확장자에서 제외** | admin enqueue·UI 기본값에서 `hwp` 제거 (코드/설정 PR) |
| **`include_extensions`에서 제외** | Job·동기 API 호출 시 `pdf,docx,...`만 전달 — **HWP만 미처리** |
| **이미 인덱싱된 HWP** | DB row는 유지; 신규 처리만 중단 |
| **비권장** | `HWP5TXT_BIN`을 잘못된 경로로 설정 — `HWP_CONVERTER_NOT_AVAILABLE` / 혼선 |

low-text는 **SKIPPED**로 설계되어 있어 전체 파이프라인 중단 사유가 아니다.

---

## 11. 최종 체크리스트 (운영 이미지 반영 시)

| 항목 | ☐ |
|------|---|
| `check_hwp_runtime.py --json` → `status: ok` (이미지 내) | |
| `hwp5txt --help` 성공 | |
| sample01 / sample03 E2E (본문형) | |
| sample02 → `SKIPPED` / `NO_EXTRACTABLE_TEXT` | |
| AGPL 검토 상태 문서화 (완료 아님 — **진행/미착수/조건부** 기록) | |
| 운영 Python 버전 기록 | |
| `pip freeze` 기반 HWP 패키지 pin | |
| Docker image rebuild 성공 | |
| worker + 동기 API에서 HWP `process-pending-documents` 1건 이상 성공 | |
| HWP 장애 시 non-HWP 문서 처리 회귀 없음 | |

---

## 12. 관련 문서

| 문서 | 용도 |
|------|------|
| [`hwp_e2e_검증계획.md`](./hwp_e2e_검증계획.md) | E2E 수동·API 보조 |
| [`hwp_e2e_검증결과_템플릿.md`](./hwp_e2e_검증결과_템플릿.md) | 결과 기록 |
| [`docker_compose_db_e2e_검증결과.md`](./docker_compose_db_e2e_검증결과.md) | compose **전용 DB** 전체 서비스 E2E (2026-05-21 Go) |
| [`hwp_e2e_검증결과_docker.md`](./hwp_e2e_검증결과_docker.md) | Docker backend + **호스트 외부 DB** HWP E2E (2026-05-21) |
| [`hwp_poc_실행계획.md`](./hwp_poc_실행계획.md) | PoC·Go 판정 |
| [`hwp_처리방식_검토.md`](./hwp_처리방식_검토.md) | 설계·후보 |
| `backend/README.md` | HWP 운영·runtime·Docker 링크 |
| `docs/로컬_실행_명령.md` | uvicorn / worker / frontend |

---

*문서 버전: 2026-05-21 · `backend/Dockerfile`, `docker-compose.dev.yml`, `.env.docker.example` 추가 (개발 검증용; 운영·AGPL·E2E 미완)*
