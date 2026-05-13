import { useNavigate } from "react-router-dom";
import { useAuthStore } from "@/stores/authStore";
import styles from "./Header.module.css";

function roleLabel(role: string | undefined): string {
  const r = (role ?? "").toUpperCase();
  if (r === "ADMIN") return "관리자";
  return "일반 사용자";
}

function initials(name: string | null | undefined, loginId: string): string {
  const n = (name ?? "").trim();
  if (n.length >= 2) return n.slice(0, 2);
  if (n.length === 1) return n;
  return loginId.slice(0, 2).toUpperCase();
}

export function Header() {
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);

  return (
    <header className={styles.header}>
      <div className={styles.left}>
        <span className={styles.title}>사내 지식 AI 검색 시스템</span>
      </div>
      <div className={styles.right}>
        {user && (
          <div className={styles.userPill}>
            <span className={styles.userIcon} aria-hidden>
              {initials(user.name, user.login_id)}
            </span>
            <div className={styles.userText}>
              <span className={styles.userName}>{user.name || user.login_id}</span>
              <span className={styles.roleBadge}>{roleLabel(user.role)}</span>
            </div>
          </div>
        )}
        <button
          type="button"
          className={styles.btnGhost}
          onClick={() => {
            logout();
            navigate("/login", { replace: true });
          }}
        >
          로그아웃
        </button>
      </div>
    </header>
  );
}
