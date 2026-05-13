export type SourceType =
  | "OWNCLOUD"
  | "NEXTCLOUD"
  | "GENERIC_WEBDAV"
  | "LOCAL_FOLDER";

export interface DataSource {
  id: string;
  name: string;
  source_type: string;
  server_url: string;
  webdav_root_path: string | null;
  username: string | null;
  has_credential: boolean;
  description: string | null;
  is_active: boolean;
  last_connection_test_at: string | null;
  last_connection_success: boolean | null;
  last_connection_message: string | null;
  last_scan_at: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface DataSourceListResponse {
  items: DataSource[];
  total: number;
}

export interface DataSourceCreateBody {
  name: string;
  source_type: SourceType | string;
  server_url: string;
  webdav_root_path?: string | null;
  username?: string | null;
  credential_secret?: string | null;
  description?: string | null;
  is_active?: boolean;
}
