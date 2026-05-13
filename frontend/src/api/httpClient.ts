import axios, { type AxiosError } from "axios";
import { clearStoredToken, getStoredToken } from "@/utils/tokenStorage";

const rawBase = import.meta.env.VITE_API_BASE_URL;
const baseURL = (rawBase && String(rawBase).trim()) || "";

export const httpClient = axios.create({
  baseURL: baseURL || undefined,
  headers: { "Content-Type": "application/json" },
  validateStatus: (s) => s >= 200 && s < 300,
});

let onUnauthorized: () => void = () => {
  window.location.assign("/login");
};

export function setUnauthorizedHandler(fn: () => void): void {
  onUnauthorized = fn;
}

httpClient.interceptors.request.use((config) => {
  const token = getStoredToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

function shouldIgnore401Logout(url: string): boolean {
  return (
    url.includes("/api/auth/login") ||
    url.includes("/api/auth/signup") ||
    url.includes("/api/auth/change-password")
  );
}

httpClient.interceptors.response.use(
  (res) => res,
  (error: AxiosError) => {
    const status = error.response?.status;
    const url = error.config?.url ?? "";
    if (status === 401 && !shouldIgnore401Logout(url)) {
      clearStoredToken();
      onUnauthorized();
    }
    return Promise.reject(error);
  }
);

export function getApiErrorMessage(
  err: unknown,
  fallback = "요청에 실패했습니다."
): string {
  if (axios.isAxiosError(err)) {
    const data = err.response?.data as Record<string, unknown> | undefined;
    if (data && typeof data.message === "string") return data.message;
    if (typeof err.message === "string" && err.message !== "Error")
      return err.message;
  }
  if (err instanceof Error) return err.message;
  return fallback;
}
