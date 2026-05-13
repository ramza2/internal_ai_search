import styles from "./StatCard.module.css";

export function StatCard({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className={styles.card}>
      <p className={styles.label}>{label}</p>
      <p className={styles.value}>{value}</p>
      {hint && <p className={styles.hint}>{hint}</p>}
    </div>
  );
}
