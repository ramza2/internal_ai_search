export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleString("ko-KR");
  } catch {
    return iso;
  }
}

export function formatScore(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  return n.toFixed(4);
}

/** 0~1 구간이면 백분율 문자열, 그 외에는 소수 표기 */
export function formatRelevanceDisplay(finalScore: number | null | undefined): string {
  if (finalScore == null || Number.isNaN(finalScore)) return "—";
  if (finalScore >= 0 && finalScore <= 1) return `${Math.round(finalScore * 100)}%`;
  return formatScore(finalScore);
}

export function formatInt(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  return Math.round(n).toLocaleString("ko-KR");
}
