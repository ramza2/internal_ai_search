import { forwardRef } from "react";
import type { SelectHTMLAttributes } from "react";
import styles from "./Select.module.css";

export type SelectProps = SelectHTMLAttributes<HTMLSelectElement>;

export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select({ className, ...rest }, ref) {
  return <select ref={ref} className={[styles.select, className].filter(Boolean).join(" ")} {...rest} />;
});
