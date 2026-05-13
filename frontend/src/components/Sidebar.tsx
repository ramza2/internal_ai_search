import { NavLink } from "react-router-dom";
import { useAuthStore } from "@/stores/authStore";
import styles from "./Sidebar.module.css";

function IconSearch({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <circle cx="11" cy="11" r="7" />
      <path d="M21 21l-4.35-4.35" />
    </svg>
  );
}

function IconChat({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
    </svg>
  );
}

function IconLayout({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <rect x="3" y="3" width="7" height="9" rx="1" />
      <rect x="14" y="3" width="7" height="5" rx="1" />
      <rect x="14" y="12" width="7" height="9" rx="1" />
      <rect x="3" y="16" width="7" height="5" rx="1" />
    </svg>
  );
}

function IconSettings({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <circle cx="12" cy="12" r="3" />
      <path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42" />
    </svg>
  );
}

function IconChart({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <path d="M3 3v18h18" />
      <path d="M7 16l4-4 4 4 5-6" />
    </svg>
  );
}

function IconUsers({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
      <circle cx="9" cy="7" r="4" />
      <path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" />
    </svg>
  );
}

function IconFileText({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <path d="M14 2v6h6M16 13H8M16 17H8M10 9H8" />
    </svg>
  );
}

export function Sidebar() {
  const isAdmin = useAuthStore((s) => s.isAdmin);

  return (
    <aside className={styles.sidebar}>
      <nav className={styles.nav}>
        <div className={styles.sectionLabel}>사용자 메뉴</div>
        <NavLink to="/search" className={({ isActive }) => `${styles.link} ${isActive ? styles.active : ""}`}>
          <IconSearch className={styles.icon} />
          통합 검색
        </NavLink>
        <NavLink to="/answer" className={({ isActive }) => `${styles.link} ${isActive ? styles.active : ""}`}>
          <IconChat className={styles.icon} />
          AI 질문
        </NavLink>

        {isAdmin && (
          <div className={styles.adminBlock}>
            <div className={styles.sectionLabel}>관리자 메뉴</div>
            <NavLink to="/admin" end className={({ isActive }) => `${styles.link} ${isActive ? styles.active : ""}`}>
              <IconLayout className={styles.icon} />
              관리자 대시보드
            </NavLink>
            <NavLink
              to="/admin/data-sources"
              className={({ isActive }) => `${styles.link} ${isActive ? styles.active : ""}`}
            >
              <IconSettings className={styles.icon} />
              데이터 소스 설정
            </NavLink>
            <NavLink
              to="/admin/file-stats"
              className={({ isActive }) => `${styles.link} ${isActive ? styles.active : ""}`}
            >
              <IconChart className={styles.icon} />
              파일 현황 분석
            </NavLink>
            <NavLink to="/admin/users" className={({ isActive }) => `${styles.link} ${isActive ? styles.active : ""}`}>
              <IconUsers className={styles.icon} />
              사용자 관리
            </NavLink>
            <NavLink
              to="/admin/action-logs"
              className={({ isActive }) => `${styles.link} ${isActive ? styles.active : ""}`}
            >
              <IconFileText className={styles.icon} />
              작업 로그
            </NavLink>
          </div>
        )}
      </nav>
    </aside>
  );
}
