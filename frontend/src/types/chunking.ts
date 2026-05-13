/** Query params for `POST .../chunk-completed-text`. */
export type ChunkCompletedTextParams = {
  limit: number;
  chunk_size: number;
  chunk_overlap: number;
  min_chunk_size: number;
  reprocess: boolean;
  dry_run: boolean;
  include_extensions?: string;
};
