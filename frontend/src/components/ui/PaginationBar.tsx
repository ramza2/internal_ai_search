import { Button } from "./Button";
import styles from "./PaginationBar.module.css";

export function PaginationBar({
  offset,
  limit,
  total,
  onOffsetChange,
  disabled,
}: {
  offset: number;
  limit: number;
  total: number;
  onOffsetChange: (next: number) => void;
  disabled?: boolean;
}) {
  const page = Math.floor(offset / limit) + 1;
  const totalPages = Math.max(1, Math.ceil(total / limit));
  const canPrev = offset > 0;
  const canNext = offset + limit < total;

  return (
    <div className={styles.bar}>
      <Button type="button" variant="secondary" size="sm" disabled={disabled || !canPrev} onClick={() => onOffsetChange(Math.max(0, offset - limit))}>
        이전
      </Button>
      <span className={styles.meta}>
        페이지 <strong>{page}</strong> / {totalPages} · 표시 {Math.min(limit, Math.max(0, total - offset))}건 / 총{" "}
        <strong>{total}</strong>건
      </span>
      <Button
        type="button"
        variant="secondary"
        size="sm"
        disabled={disabled || !canNext}
        onClick={() => onOffsetChange(offset + limit)}
      >
        다음
      </Button>
    </div>
  );
}
