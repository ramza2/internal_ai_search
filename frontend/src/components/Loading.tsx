import styles from "./Loading.module.css";

export function Loading({ label = "불러오는 중…" }: { label?: string }) {
  return (
    <div className={styles.wrap}>
      <div className={styles.spinner} aria-hidden />
      <span>{label}</span>
    </div>
  );
}
