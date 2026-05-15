import styles from "./InfoBox.module.css";

type Props = {
  title?: string;
  children: React.ReactNode;
  variant?: "info" | "success" | "warning";
};

export function InfoBox({ title, children, variant = "info" }: Props) {
  return (
    <div className={[styles.box, styles[variant]].join(" ")}>
      {title ? <strong className={styles.title}>{title}</strong> : null}
      <div className={styles.body}>{children}</div>
    </div>
  );
}
