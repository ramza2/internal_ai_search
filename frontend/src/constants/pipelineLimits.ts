/** Server-side upper bound for text/document processing (matches backend _SIZE_MAX). */
export const SERVER_MAX_FILE_BYTES = 256 * 1024 * 1024;
export const SERVER_MAX_FILE_MB = 256;

export type ScanScope = "FULL" | "LIMITED";
