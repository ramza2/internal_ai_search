import { httpClient } from "@/api/httpClient";
import type { LoginResponse, MeResponse, SignupResponse } from "@/types/auth";

export async function loginRequest(
  loginId: string,
  password: string
): Promise<LoginResponse> {
  const { data } = await httpClient.post<LoginResponse>("/api/auth/login", {
    login_id: loginId,
    password,
  });
  return data;
}

export async function signupRequest(body: {
  login_id: string;
  password: string;
  name: string;
  email: string;
  department?: string | null;
}): Promise<SignupResponse> {
  const { data } = await httpClient.post<SignupResponse>("/api/auth/signup", body);
  return data;
}

export async function meRequest(): Promise<MeResponse> {
  const { data } = await httpClient.get<MeResponse>("/api/auth/me");
  return data;
}

export async function changePasswordRequest(
  currentPassword: string,
  newPassword: string
): Promise<{ status: string; message: string }> {
  const { data } = await httpClient.post<{ status: string; message: string }>(
    "/api/auth/change-password",
    {
      current_password: currentPassword,
      new_password: newPassword,
    }
  );
  return data;
}
