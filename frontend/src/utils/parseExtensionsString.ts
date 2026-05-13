/** 쉼표/공백/세미콜론으로 구분된 확장자 문자열을 API용 소문자 토큰 배열로 변환 */
export function parseExtensionsFromInput(raw: string): string[] | undefined {
  const parts = raw.split(/[,;\s]+/);
  const cleaned: string[] = [];
  const seen = new Set<string>();
  for (const rawTok of parts) {
    let tok = rawTok.trim().toLowerCase();
    if (tok.startsWith(".")) tok = tok.slice(1).trim();
    if (!tok || seen.has(tok)) continue;
    seen.add(tok);
    cleaned.push(tok);
  }
  return cleaned.length > 0 ? cleaned : undefined;
}
