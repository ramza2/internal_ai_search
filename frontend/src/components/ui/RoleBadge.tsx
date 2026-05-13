import { Badge } from "./Badge";

export function RoleBadge({ role }: { role: string }) {
  const r = role.toUpperCase();
  return <Badge variant={r === "ADMIN" ? "primary" : "neutral"}>{r}</Badge>;
}
