# internal-ai-search — frontend

Vite + React + TypeScript 기반 웹 UI. 백엔드(FastAPI)와 JWT 인증으로 연동합니다.

## Figma MCP UI 반영 단계

- Cursor **Figma MCP**(`get_design_context`)로 Figma Make 파일 키 `K22EXxnQSYPvcWOmEUuvMQ`의 소스·레이아웃(헤더/사이드바/톤)을 참고했습니다.
- Make 프로젝트는 Tailwind·shadcn 기반이지만, 본 레포는 **도입하지 않고** 동일한 정보 구조를 **CSS 변수 + CSS Module + 공통 `src/components/ui`** 로 이식했습니다.
- 디자인 URL: `https://www.figma.com/make/K22EXxnQSYPvcWOmEUuvMQ/Internal-Knowledge-AI-Search-UI--%EB%B3%B5%EC%82%AC-?p=f&t=fznfbJPE3rXiMl3h-0`

## 현재 UI 구조

- **디자인 토큰:** `src/styles/global.css`의 `:root` 변수(`--color-primary`, `--color-bg`, `--color-surface`, `--color-muted`, `--color-danger`, `--radius-*`, `--shadow-card` 등).
- **공통 UI:** `src/components/ui/` (`Button`, `Input`, `Select`, `Textarea`, `Badge`, `Card`, `CollapsiblePanel`, `PageHeader`, `SectionCard`, `DataTable`, `FilterBar`/`FilterField`, `FormField`, `StatCard`, `ConfirmDialog`, `PaginationBar`, `DataSourceSelect`, `StatusBadge`, `RoleBadge`, `ResultBadge` 등).
- **레이아웃:** `MainLayout` — 좌측 고정 사이드바(`--sidebar-width`), 상단 헤더, 본문 `pageShell`(max-width 1240px). `AuthLayout` — 상단 브랜딩 + 중앙 카드.

## 페이지 목록

| 영역 | 경로 | 설명 |
|------|------|------|
| 공개 | `/login`, `/signup` | 로그인·회원가입 |
| 인증 후 | `/change-password` | 비밀번호 변경(강제 시 안내) |
| 사용자 | `/search`, `/answer`, `/files/:fileId/preview` | 통합 검색, AI 질문, 미리보기 |
| 관리자 | `/admin`, `/admin/data-sources`, `/admin/file-stats`, `/admin/users`, `/admin/action-logs` | 대시보드(파일 통계), 데이터 소스, 파일 통계, 사용자, 작업 로그 |

## 인증·권한 흐름 (유지)

1. `POST /api/auth/login` → `access_token`을 `localStorage`(`internal_ai_search_access_token`)에 저장.
2. 앱 시작 시 `GET /api/auth/me`로 사용자 복구(`BootstrapGate` 등 기존 흐름).
3. `must_change_password === true` → **`/change-password`**.
4. 비밀번호 변경 후 역할에 따라 **`/admin`** 또는 **`/search`**.
5. API **401**(로그인·회원가입·비밀번호 변경 제외) 시 토큰 삭제 후 **`/login`**.
6. `/admin/*`는 `AdminRoute`로 **ADMIN**만. 일반 사용자는 `/search`로 리다이렉트.

## 설치·실행

```bash
cd frontend
npm install
npm run dev
```

기본 개발 서버: `http://localhost:5173`

```bash
npm run build
npm run preview
```

## 환경 변수 (`frontend/.env`)

- **`VITE_API_BASE_URL`**
  - **비워 두기(개발 권장):** `/api`로 요청하고 `vite.config.ts` 프록시가 백엔드로 전달.
  - **절대 URL 지정 시:** 해당 호스트로 직접 호출하며 백엔드 CORS 설정이 필요합니다.

값 변경 후 `npm run dev`를 다시 실행하세요.

## 통합 검색 고급 필터 (`/search`)

- 기본 영역: 검색어 입력 + 검색 실행. **고급 필터**는 `CollapsiblePanel`으로 접었다 펼 수 있습니다.
- **검색 모드:** vector / keyword / hybrid.
- **데이터 소스:** `useSearchDataSources()` → **`GET /api/search/data-sources`** (활성 소스만, URL·자격 증명 미포함). 목록 로드 실패 시 필터는 **전체**만 동작하고 작은 안내 문구를 표시합니다.
- **확장자:** 쉼표 구분 입력 → `include_extensions` 배열로 변환.
- **파일 유형:** DOCUMENT, SOURCE_CODE 등 버킷 선택.
- **limit:** 10 / 20 / 50 / 100.
- **min_score:** 숫자 입력. **hybrid**일 때만 **vector_weight / keyword_weight** 입력란 표시.
- 검색 후 **적용 필터 요약** 문자열, 로딩·에러·빈 결과(`EmptyState`), 미리보기 링크는 기존과 동일한 패턴을 유지합니다.

## AI 질문 고급 옵션 (`/answer`)

- **고급 옵션** 패널: 검색 모드, 데이터 소스(`GET /api/search/data-sources`와 동일 훅), 확장자, 파일 유형, `search_limit`, `context_limit`, `answer_min_score`, 검색용 `min_score`, `temperature`, `max_context_chars`, hybrid 가중치, **dry_run** 체크박스.
- **keyword** 모드 선택 시: 임베딩 없이 키워드 검색만 쓴다는 짧은 안내 배너.
- **dry_run:** LLM 없이 `context_preview` 테이블로 후보 청크를 확인. 일반 답변과 **근거 부족** 문구는 서로 다른 스타일 박스로 구분.
- 브라우저 세션에 옵션·결과를 저장(`ragSessionCache` v2)해 새로고침 후에도 복원됩니다.

## 작업 로그 (`/admin/action-logs`)

- **필터:** user_id, action_type(선택 상수 + 전체), result, data_source, target_file_id, keyword, from_date, to_date, limit(20/50/100/200).
- **조회** 시에만 적용 필터가 반영되며 offset은 0으로 리셋됩니다. **필터 초기화**로 전부 초기화합니다.
- **PaginationBar:** offset 기반 이전/다음, 현재 페이지·총 건수 표시. `total`으로 마지막 페이지를 계산합니다.
- 상세 JSON은 행 **펼치기**로 유지합니다.

## 사용자 관리 (`/admin/users`)

- 상태·역할·키워드·limit(20/50/100) **조회** 후 목록 로드. **필터 초기화** 지원.
- **PaginationBar** + API `total` 표시. 승인·역할 변경 등 작업 후 **현재 필터·offset**을 유지한 채 목록만 다시 불러옵니다.
- **StatusBadge / RoleBadge**로 상태·역할 표시. 마지막 관리자 보호 등 API 오류는 **ErrorMessage**로 구분 표시(목록 로드 오류와 별도).

## 데이터 소스 API 구분

- **검색·AI 질문:** `useSearchDataSources()` → `GET /api/search/data-sources` — 일반 **USER**도 호출 가능(ACTIVE + 비밀번호 변경 완료). 응답에는 `id`, `name`, `source_type`, `description`, `last_scan_at`, `last_connection_success`만 포함됩니다.
- **관리자 화면** (`DataSourcesPage`, 작업 로그 필터, 파일 통계 소스 선택 등): `useDataSources()` → `GET /api/data-sources` — **ADMIN** 전용 CRUD 목록(기존과 동일).

## 파일 통계 (`/admin/file-stats`)

- **전체:** `GET /api/files/stats` + `include_deleted` 쿼리.
- **특정 소스:** `GET /api/data-sources/{id}/file-stats`.
- 상단에서 소스 선택·삭제 포함 체크박스·새로고침.
- 요약 카드: 전체 항목, 파일 수, 디렉터리 수, 전체 용량, 마지막 동기화(+ 파일 최근 수정 힌트).
- 테이블: 분석 상태·파일 유형·확장자·대용량 TOP. TOP 목록은 확장자 휴리스틱으로 **텍스트 미리보기** 가능 시 `/files/{id}/preview` 링크.

## 타입 (`src/types`)

- `search.ts`, `answer.ts`, `admin.ts`, `dataSource.ts`(`AdminDataSource` 별칭), **`searchDataSource.ts`**(`SearchDataSource`), `file.ts`에 요청/응답 스키마를 맞춰 두었습니다.

## 아직 남은 TODO (프론트)

- **URL query state**와 필터·페이지(offset) 동기화 — 작업 로그·사용자 관리 등에 TODO 주석으로 표시해 두었습니다.
- **차트 라이브러리** 도입(파일 통계 시각화).
- **모바일 햄버거 메뉴** 등 본격 반응형.
- 미리보기 **쿼리 하이라이트** 정밀(offset 기반).
- 백엔드 **소스별 사용자 권한(ACL)** 도입 시 검색용 목록 API에서 행 필터링.
- 데이터 소스 **행 단위 수정** UI — 백엔드 PATCH 연동 후.

## 다음 단계 제안

- React Query 등으로 목록·통계 **캐시/재검증** (선택).
- 차트 라이브러리로 파일 통계 시각화(선택).
- Figma Code Connect 연동 시 `ui` 컴포넌트와 1:1 매핑.
