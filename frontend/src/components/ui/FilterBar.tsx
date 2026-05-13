import type { ReactNode } from "react";
import styles from "./FilterBar.module.css";

export function FilterBar({ children }: { children: ReactNode }) {
  return <div className={styles.bar}>{children}</div>;
}

export function FilterField({
  label,
  children,
  wide,
}: {
  label: string;
  children: ReactNode;
  wide?: boolean;
}) {
  return (
    <div className={styles.field}>
      <span className={styles.label}>{label}</span>
      <div className={wide ? styles.fieldControlWide : styles.fieldControl}>{children}</div>
    </div>
  );
}
