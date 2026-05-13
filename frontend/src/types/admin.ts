export interface AdminUserRow {
  id: string;
  login_id: string;
  name: string | null;
  email: string | null;
  department?: string | null;
  role: string;
  status: string;
  must_change_password: boolean;
  last_login_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface AdminUsersListResponse {
  status: string;
  total: number;
  items: AdminUserRow[];
}

export interface ActionLogItem {
  id: string;
  user_id: string | null;
  login_id: string | null;
  user_name: string | null;
  user_role: string | null;
  action_type: string;
  result: string;
  request_url: string | null;
  request_method: string | null;
  search_query: string | null;
  data_source_id: string | null;
  target_file_id: string | null;
  target_file_path: string | null;
  ip_address: string | null;
  user_agent: string | null;
  detail: Record<string, unknown> | null;
  error_message: string | null;
  created_at: string | null;
}

export interface ActionLogsListResponse {
  status: string;
  total: number;
  items: ActionLogItem[];
}
