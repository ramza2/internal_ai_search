import { useId, useState } from "react";
import type { ReactNode } from "react";
import styles from "./CollapsiblePanel.module.css";

export function CollapsiblePanel({
  title,
  summary,
  defaultOpen = false,
  children,
}: {
  title: string;
  summary?: string;
  defaultOpen?: boolean;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const id = useId();
  const panelId = `${id}-panel`;

  return (
    <div className="card" style={{ marginBottom: "1rem" }}>
      <button
        type="button"
        className={styles.head}
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((v) => !v)}
      >
        <span className={styles.title}>{title}</span>
        <span className={styles.chev} aria-hidden>
          {open ? "▲" : "▼"}
        </span>
      </button>
      {summary && <p className={styles.summary}>{summary}</p>}
      {open && (
        <div id={panelId} className={styles.body}>
          {children}
        </div>
      )}
    </div>
  );
}
