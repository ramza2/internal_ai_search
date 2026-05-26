import styles from "./ProgressBar.module.css";

type Props = {
  percent: number | null | undefined;
  height?: number;
  maxWidth?: string;
  showLabel?: boolean;
  animate?: boolean;
};

export function ProgressBar({
  percent,
  height = 6,
  maxWidth = "8rem",
  showLabel = false,
  animate = true,
}: Props) {
  const pct = Math.min(100, Math.max(0, Number(percent) || 0));
  return (
    <div className={styles.wrap}>
      <div
        className={styles.track}
        style={{ height, maxWidth }}
        aria-hidden
      >
        <div
          className={`${styles.fill} ${animate ? styles.animate : ""}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      {showLabel && (
        <span className={styles.label}>
          {percent != null ? `${percent}%` : "—"}
        </span>
      )}
    </div>
  );
}
