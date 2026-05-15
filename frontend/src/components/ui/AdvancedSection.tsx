import { useState, type ReactNode } from "react";
import styles from "./AdvancedSection.module.css";

type Props = {
  title?: string;
  summary?: string;
  defaultOpen?: boolean;
  children: ReactNode;
};

/** 개발자·고급 옵션을 접어 두는 영역 */
export function AdvancedSection({
  title = "고급 설정",
  summary = "세부 옵션을 조정할 때 펼쳐 주세요.",
  defaultOpen = false,
  children,
}: Props) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <details
      className={styles.wrap}
      open={open}
      onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}
    >
      <summary className={styles.summary}>
        <span className={styles.title}>{title}</span>
        <span className={styles.hint}>{summary}</span>
      </summary>
      <div className={styles.body}>{children}</div>
    </details>
  );
}
