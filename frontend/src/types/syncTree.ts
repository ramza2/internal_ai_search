/** Query params for `POST .../sync-tree`. */
export type SyncTreeParams = {
  start_path?: string;
  max_depth?: number;
  max_items?: number;
  include_hidden?: boolean;
  apply_exclusions?: boolean;
  detect_deleted?: boolean;
};
