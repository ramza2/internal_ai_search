import { Outlet } from "react-router-dom";
import styles from "./AuthLayout.module.css";

export function AuthLayout() {
  return (
    <div className={styles.wrap}>
      <div className={styles.brand}>
        <h1 className={styles.brandTitle}>사내 지식 AI 검색 시스템</h1>
        <p className={styles.brandDesc}>
          사내 문서·소스코드를 검색하고, 승인된 근거만으로 AI 질의에 답합니다.
        </p>
      </div>
      <div className={styles.card}>
        <Outlet />
      </div>
    </div>
  );
}
