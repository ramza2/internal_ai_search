# internal-ai-search — frontend

Vite + React + TypeScript 기반 웹 UI. 백엔드(FastAPI)와 JWT 인증으로 연동합니다.

## Figma MCP UI 반영 단계

- Cursor **Figma MCP**(`get_design_context`)로 Figma Make 파일 키 `K22EXxnQSYPvcWOmEUuvMQ`의 소스·레이아웃(헤더/사이드바/톤)을 참고했습니다.
- Make 프로젝트는 Tailwind·shadcn 기반이지만, 본 레포는 **도입하지 않고** 동일한 정보 구조를 **CSS 변수 + CSS Module + 공통 `src/components/ui`** 로 이식했습니다.
- 디자인 URL: `https://www.figma.com/make/K22EXxnQSYPvcWOmEUuvMQ/Internal-Knowledge-AI-Search-UI--%EB%B3%B5%EC%82%AC-?p=f&t=fznfbJPE3rXiMl3h-0`

## 현재 UI 구조

- **디자인 토큰:** `src/styles/global.css`의 `:root` 변수(`--color-primary`, `--color-bg`, `--color-surface`, `--color-muted`, `--color-danger`, `--radius-*`, `--shadow-card` 등).
- **공통 UI:** `src/components/ui/` (`Button`, `Input`, `Select`, `Textarea`, `Badge`, `Card`, `PageHeader`, `SectionCard`, `DataTable`, `FilterBar`/`FilterField`, `FormField`, `StatCard`, `ConfirmDialog`).
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

## 아직 남은 UI TODO

- 검색/답변 **고급 필터** UI(`data_source_id`, `min_score` 등) — API는 이미 있으나 화면 미구현.
- 작업 로그 **기간 필터·페이지네이션**.
- 미리보기 **쿼리 하이라이트** 정밀(offset 기반) — 현재는 highlights 라인 배경 위주.
- Figma와의 **픽셀 단위** 맞춤(타이포 스케일·아이콘 세트 통일).
- 모바일 **햄버거 메뉴** 등 본격 반응형(현재 1024~1440 중심).

## 다음 단계 제안

- React Query 등으로 목록·통계 **캐시/재검증** (선택).
- 차트 라이브러리로 파일 통계 시각화(선택).
- Figma Code Connect 연동 시 `ui` 컴포넌트와 1:1 매핑.
