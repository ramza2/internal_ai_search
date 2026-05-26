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

/** ISO 문자열 → "N초 전", "N분 전" 등 상대 시간 */
export function formatRelativeTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "—";
  const diff = Math.max(0, Date.now() - t);
  if (diff < 5_000) return "방금";
  if (diff < 60_000) return `${Math.floor(diff / 1000)}초 전`;
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}분 전`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}시간 전`;
  return `${Math.floor(diff / 86_400_000)}일 전`;
}

/** started_at → "1m 23s" 형태의 경과 시간 (실시간 표시용) */
export function formatElapsed(startedIso: string | null | undefined): string {
  if (!startedIso) return "—";
  const t = new Date(startedIso).getTime();
  if (Number.isNaN(t)) return "—";
  const ms = Math.max(0, Date.now() - t);
  return formatDuration(ms);
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
