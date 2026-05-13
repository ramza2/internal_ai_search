import { forwardRef } from "react";
import type { TextareaHTMLAttributes } from "react";
import styles from "./Textarea.module.css";

export type TextareaProps = TextareaHTMLAttributes<HTMLTextAreaElement>;

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(function Textarea(
  { className, ...rest },
  ref
) {
  return <textarea ref={ref} className={[styles.textarea, className].filter(Boolean).join(" ")} {...rest} />;
});
