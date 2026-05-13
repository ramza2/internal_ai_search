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

/** 짧은 구간(파이프라인 단계 소요 등) 표시: `950ms`, `3.2s`, `1m 12s` */
export function formatDuration(ms: number | null | undefined): string {
  if (ms == null || Number.isNaN(ms) || ms < 0) return "—";
  if (ms < 1000) return `${Math.round(ms)}ms`;
  const sec = ms / 1000;
  if (sec < 60) {
    const rounded = Math.round(sec * 10) / 10;
    if (Number.isInteger(rounded)) return `${rounded}s`;
    return `${rounded.toFixed(1)}s`;
  }
  const m = Math.floor(sec / 60);
  const s = Math.round(sec - m * 60);
  return `${m}m ${s}s`;
}
