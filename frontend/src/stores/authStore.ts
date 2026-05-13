import { create } from "zustand";
import * as authApi from "@/api/authApi";
import type { AuthUser } from "@/types/auth";
import { clearStoredToken, getStoredToken, setStoredToken } from "@/utils/tokenStorage";

interface AuthState {
  accessToken: string | null;
  user: AuthUser | null;
  isAuthenticated: boolean;
  isAdmin: boolean;
  mustChangePassword: boolean;
  isLoading: boolean;
  login: (loginId: string, password: string) => Promise<void>;
  logout: () => void;
  fetchMe: () => Promise<void>;
  changePassword: (currentPassword: string, newPassword: string) => Promise<void>;
  setToken: (token: string) => void;
  clearAuth: () => void;
  hydrateFromStorage: () => void;
}

function deriveFlags(user: AuthUser | null, token: string | null) {
  const isAuthenticated = Boolean(token && user);
  const isAdmin = (user?.role ?? "").toUpperCase() === "ADMIN";
  const mustChangePassword = Boolean(user?.must_change_password);
  return { isAuthenticated, isAdmin, mustChangePassword };
}

export const useAuthStore = create<AuthState>((set, get) => ({
  accessToken: null,
  user: null,
  isAuthenticated: false,
  isAdmin: false,
  mustChangePassword: false,
  isLoading: false,

  hydrateFromStorage: () => {
    const t = getStoredToken();
    set({ accessToken: t });
  },

  setToken: (token: string) => {
    setStoredToken(token);
    set({ accessToken: token });
  },

  clearAuth: () => {
    clearStoredToken();
    set({
      accessToken: null,
      user: null,
      isAuthenticated: false,
      isAdmin: false,
      mustChangePassword: false,
    });
  },

  login: async (loginId: string, password: string) => {
    set({ isLoading: true });
    try {
      const data = await authApi.loginRequest(loginId, password);
      setStoredToken(data.access_token);
      const user = data.user;
      const flags = deriveFlags(user, data.access_token);
      set({
        accessToken: data.access_token,
        user,
        ...flags,
        isLoading: false,
      });
    } catch (e) {
      set({ isLoading: false });
      throw e;
    }
  },

  logout: () => {
    get().clearAuth();
  },

  fetchMe: async () => {
    const token = get().accessToken ?? getStoredToken();
    if (!token) {
      set({ user: null, ...deriveFlags(null, null) });
      return;
    }
    set({ isLoading: true, accessToken: token });
    try {
      const data = await authApi.meRequest();
      const user = data.user;
      set({
        user,
        ...deriveFlags(user, token),
        isLoading: false,
      });
    } catch {
      get().clearAuth();
      set({ isLoading: false });
    }
  },

  changePassword: async (currentPassword: string, newPassword: string) => {
    set({ isLoading: true });
    try {
      await authApi.changePasswordRequest(currentPassword, newPassword);
      await get().fetchMe();
      set({ isLoading: false });
    } catch (e) {
      set({ isLoading: false });
      throw e;
    }
  },
}));
