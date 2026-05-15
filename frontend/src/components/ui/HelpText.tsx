import styles from "./HelpText.module.css";

type Props = {
  children: React.ReactNode;
  className?: string;
};

/** 짧은 안내 문구 (단계 설명 등) */
export function HelpText({ children, className }: Props) {
  return <p className={[styles.help, className].filter(Boolean).join(" ")}>{children}</p>;
}
