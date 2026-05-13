/** Query params for `POST .../embed-pending-chunks`. */
export type EmbedPendingChunksParams = {
  limit: number;
  batch_size: number;
  reembed: boolean;
  dry_run: boolean;
  include_extensions?: string;
  file_id?: string;
};
