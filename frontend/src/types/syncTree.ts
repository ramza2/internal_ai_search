import type { ScanScope } from "@/constants/pipelineLimits";

/** Query params for `POST .../sync-tree` (synchronous; LIMITED only). */
export type SyncTreeParams = {
  start_path?: string;
  scan_scope?: ScanScope;
  max_depth?: number;
  max_items?: number;
  include_hidden?: boolean;
  apply_exclusions?: boolean;
  detect_deleted?: boolean;
};
