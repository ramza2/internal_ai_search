import type { ReactNode } from "react";
import { Card } from "./Card";
import styles from "./SectionCard.module.css";

export function SectionCard({
  title,
  actions,
  children,
  className,
}: {
  title: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <Card className={className}>
      <div className={styles.head}>
        <h2 className={styles.title}>{title}</h2>
        {actions}
      </div>
      {children}
    </Card>
  );
}
