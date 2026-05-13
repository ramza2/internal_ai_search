import { Badge } from "./Badge";

export function ResultBadge({ result }: { result: string }) {
  const r = result.toUpperCase();
  return <Badge variant={r === "SUCCESS" ? "success" : r === "FAIL" ? "danger" : "neutral"}>{r}</Badge>;
}
