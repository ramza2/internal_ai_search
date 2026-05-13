import styles from "./ErrorMessage.module.css";

export function ErrorMessage({ message }: { message: string }) {
  if (!message) return null;
  return (
    <div className={styles.box} role="alert">
      {message}
    </div>
  );
}
