import type { ReactNode } from "react";
import styles from "./Badge.module.css";

export type BadgeVariant = "default" | "primary" | "success" | "warning" | "danger" | "neutral" | "ext";

export function Badge({
  children,
  variant = "default",
  className,
}: {
  children: ReactNode;
  variant?: BadgeVariant;
  className?: string;
}) {
  return (
    <span className={[styles.badge, styles[variant], className].filter(Boolean).join(" ")}>{children}</span>
  );
}
