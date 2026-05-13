import { useEffect, useState } from "react";
import {
  BrowserRouter,
  Navigate,
  Route,
  Routes,
  useNavigate,
} from "react-router-dom";
import { setUnauthorizedHandler } from "@/api/httpClient";
import { Loading } from "@/components/Loading";
import { AuthLayout } from "@/layouts/AuthLayout";
import { MainLayout } from "@/layouts/MainLayout";
import { AnswerPage } from "@/pages/user/AnswerPage";
import { FilePreviewPage } from "@/pages/user/FilePreviewPage";
import { SearchPage } from "@/pages/user/SearchPage";
import { ChangePasswordPage } from "@/pages/auth/ChangePasswordPage";
import { LoginPage } from "@/pages/auth/LoginPage";
import { SignupPage } from "@/pages/auth/SignupPage";
import { ActionLogsPage } from "@/pages/admin/ActionLogsPage";
import { AdminDashboardPage } from "@/pages/admin/AdminDashboardPage";
import { AdminJobsPage } from "@/pages/admin/AdminJobsPage";
import { DataSourcesPage } from "@/pages/admin/DataSourcesPage";
import { FileStatsPage } from "@/pages/admin/FileStatsPage";
import { UsersPage } from "@/pages/admin/UsersPage";
import { NotFoundPage } from "@/pages/NotFoundPage";
import { AdminRoute } from "@/routes/AdminRoute";
import { ProtectedRoute } from "@/routes/ProtectedRoute";
import { useAuthStore } from "@/stores/authStore";

function HttpAuthBridge() {
  const navigate = useNavigate();
  useEffect(() => {
    setUnauthorizedHandler(() => {
      useAuthStore.getState().clearAuth();
      navigate("/login", { replace: true });
    });
  }, [navigate]);
  return null;
}

function BootstrapGate({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false);
  useEffect(() => {
    useAuthStore.getState().hydrateFromStorage();
    void useAuthStore.getState().fetchMe().finally(() => setReady(true));
  }, []);
  if (!ready) {
    return (
      <div style={{ padding: "2rem" }}>
        <Loading label="세션 확인 중…" />
      </div>
    );
  }
  return <>{children}</>;
}

function RootRedirect() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const isAdmin = useAuthStore((s) => s.isAdmin);
  const must = useAuthStore((s) => s.mustChangePassword);

  if (!isAuthenticated) return <Navigate to="/login" replace />;
  if (must) return <Navigate to="/change-password" replace />;
  if (isAdmin) return <Navigate to="/admin" replace />;
  return <Navigate to="/search" replace />;
}

export function AppRouter() {
  return (
    <BrowserRouter>
      <HttpAuthBridge />
      <BootstrapGate>
        <Routes>
          <Route path="/" element={<RootRedirect />} />

          <Route element={<AuthLayout />}>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/signup" element={<SignupPage />} />
          </Route>

          <Route element={<ProtectedRoute />}>
            <Route element={<AuthLayout />}>
              <Route path="/change-password" element={<ChangePasswordPage />} />
            </Route>

            <Route element={<MainLayout />}>
              <Route path="/search" element={<SearchPage />} />
              <Route path="/answer" element={<AnswerPage />} />
              <Route path="/files/:fileId/preview" element={<FilePreviewPage />} />

              <Route element={<AdminRoute />}>
                <Route path="/admin" element={<AdminDashboardPage />} />
                <Route path="/admin/data-sources" element={<DataSourcesPage />} />
                <Route path="/admin/jobs" element={<AdminJobsPage />} />
                <Route path="/admin/file-stats" element={<FileStatsPage />} />
                <Route path="/admin/users" element={<UsersPage />} />
                <Route path="/admin/action-logs" element={<ActionLogsPage />} />
              </Route>
            </Route>
          </Route>

          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </BootstrapGate>
    </BrowserRouter>
  );
}
