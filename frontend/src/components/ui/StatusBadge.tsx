import { Badge } from "./Badge";

const STATUS_MAP: Record<string, "default" | "success" | "warning" | "danger" | "neutral"> = {
  PENDING: "warning",
  ACTIVE: "success",
  INACTIVE: "default",
  LOCKED: "danger",
};

export function StatusBadge({ status }: { status: string }) {
  const v = STATUS_MAP[status] ?? "neutral";
  return <Badge variant={v}>{status}</Badge>;
}
