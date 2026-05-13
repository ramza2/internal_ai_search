import { useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { getApiErrorMessage } from "@/api/httpClient";
import { ErrorMessage } from "@/components/ErrorMessage";
import { Button, FormField, Input } from "@/components/ui";
import { useAuthStore } from "@/stores/authStore";

export function LoginPage() {
  const navigate = useNavigate();
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const mustChangePassword = useAuthStore((s) => s.mustChangePassword);
  const isAdmin = useAuthStore((s) => s.isAdmin);
  const login = useAuthStore((s) => s.login);
  const authLoading = useAuthStore((s) => s.isLoading);

  const [loginId, setLoginId] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  if (isAuthenticated && !mustChangePassword) {
    return <Navigate to={isAdmin ? "/admin" : "/search"} replace />;
  }
  if (isAuthenticated && mustChangePassword) {
    return <Navigate to="/change-password" replace />;
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await login(loginId.trim(), password);
      const st = useAuthStore.getState();
      if (st.mustChangePassword) {
        navigate("/change-password", { replace: true });
      } else if (st.isAdmin) {
        navigate("/admin", { replace: true });
      } else {
        navigate("/search", { replace: true });
      }
    } catch (err) {
      setError(getApiErrorMessage(err, "로그인에 실패했습니다."));
    }
  }

  return (
    <div>
      <h2 className="pageTitle" style={{ marginBottom: "0.25rem" }}>
        로그인
      </h2>
      <p className="muted" style={{ marginBottom: "1.25rem" }}>
        승인된 계정으로 로그인하세요.
      </p>
      <ErrorMessage message={error} />
      <form className="formGrid" onSubmit={onSubmit} style={{ maxWidth: "100%" }}>
        <FormField label="로그인 ID">
          <Input
            value={loginId}
            onChange={(e) => setLoginId(e.target.value)}
            autoComplete="username"
            required
          />
        </FormField>
        <FormField label="비밀번호">
          <Input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
          />
        </FormField>
        <Button type="submit" variant="primary" fullWidth loading={authLoading}>
          로그인
        </Button>
      </form>
      <p className="muted" style={{ marginTop: "1.25rem", textAlign: "center" }}>
        계정이 없으신가요? <Link to="/signup">회원가입</Link>
      </p>
    </div>
  );
}
