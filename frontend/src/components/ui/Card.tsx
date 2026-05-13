import type { HTMLAttributes, ReactNode } from "react";
import styles from "./Card.module.css";

export function Card({
  children,
  className,
  flat,
  noMargin,
  ...rest
}: HTMLAttributes<HTMLDivElement> & { children: ReactNode; flat?: boolean; noMargin?: boolean }) {
  return (
    <div
      className={[styles.card, flat && styles.flat, noMargin && styles.noMargin, className].filter(Boolean).join(" ")}
      {...rest}
    >
      {children}
    </div>
  );
}
