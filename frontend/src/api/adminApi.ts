import { httpClient } from "@/api/httpClient";
import type {
  ActionLogsListResponse,
  ActionLogsQueryParams,
  AdminUserRow,
  AdminUsersListResponse,
} from "@/types/admin";

export async function listAdminUsers(params: {
  status?: string;
  role?: string;
  keyword?: string;
  limit?: number;
  offset?: number;
}): Promise<AdminUsersListResponse> {
  const { data } = await httpClient.get<AdminUsersListResponse>("/api/admin/users", {
    params,
  });
  return data;
}

export async function approveUser(id: string): Promise<{ user: AdminUserRow }> {
  const { data } = await httpClient.patch<{
    status: string;
    user: AdminUserRow;
  }>(`/api/admin/users/${id}/approve`);
  return { user: data.user };
}

export async function activateUser(id: string): Promise<{ user: AdminUserRow }> {
  const { data } = await httpClient.patch<{
    status: string;
    user: AdminUserRow;
  }>(`/api/admin/users/${id}/activate`);
  return { user: data.user };
}

export async function deactivateUser(id: string): Promise<{ user: AdminUserRow }> {
  const { data } = await httpClient.patch<{
    status: string;
    user: AdminUserRow;
  }>(`/api/admin/users/${id}/deactivate`);
  return { user: data.user };
}

export async function lockUser(id: string): Promise<{ user: AdminUserRow }> {
  const { data } = await httpClient.patch<{
    status: string;
    user: AdminUserRow;
  }>(`/api/admin/users/${id}/lock`);
  return { user: data.user };
}

export async function setUserRole(
  id: string,
  role: "USER" | "ADMIN"
): Promise<{ user: AdminUserRow }> {
  const { data } = await httpClient.patch<{
    status: string;
    user: AdminUserRow;
  }>(`/api/admin/users/${id}/role`, { role });
  return { user: data.user };
}

export async function listActionLogs(params: ActionLogsQueryParams): Promise<ActionLogsListResponse> {
  const { data } = await httpClient.get<ActionLogsListResponse>("/api/admin/action-logs", {
    params,
  });
  return data;
}
