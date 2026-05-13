import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { getApiErrorMessage } from "@/api/httpClient";
import { ErrorMessage } from "@/components/ErrorMessage";
import { Button, FormField, Input } from "@/components/ui";
import { useAuthStore } from "@/stores/authStore";

const MIN_LEN = 8;

export function ChangePasswordPage() {
  const navigate = useNavigate();
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const mustChangePassword = useAuthStore((s) => s.mustChangePassword);
  const changePassword = useAuthStore((s) => s.changePassword);
  const authLoading = useAuthStore((s) => s.isLoading);

  const [current, setCurrent] = useState("");
  const [next1, setNext1] = useState("");
  const [next2, setNext2] = useState("");
  const [error, setError] = useState("");

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (next1 !== next2) {
      setError("새 비밀번호 확인이 일치하지 않습니다.");
      return;
    }
    if (next1.length < MIN_LEN) {
      setError(`새 비밀번호는 최소 ${MIN_LEN}자 이상이어야 합니다.`);
      return;
    }
    try {
      await changePassword(current, next1);
      const st = useAuthStore.getState();
      if (st.isAdmin) navigate("/admin", { replace: true });
      else navigate("/search", { replace: true });
    } catch (err) {
      setError(getApiErrorMessage(err, "비밀번호 변경에 실패했습니다."));
    }
  }

  return (
    <div>
      <h2 className="pageTitle" style={{ marginBottom: "0.5rem" }}>
        비밀번호 변경
      </h2>
      {mustChangePassword && (
        <div className="alert alertDanger" style={{ marginBottom: "1rem" }}>
          보안 정책에 따라 비밀번호를 변경해야 합니다. 변경 완료 전까지 다른 메뉴를 이용할 수 없습니다.
        </div>
      )}
      {!mustChangePassword && (
        <p className="muted" style={{ marginBottom: "1rem" }}>
          최초 로그인 또는 정책에 따라 비밀번호를 변경할 수 있습니다.
        </p>
      )}
      <ErrorMessage message={error} />
      <form className="formGrid" onSubmit={onSubmit} style={{ maxWidth: "100%" }}>
        <FormField label="현재 비밀번호">
          <Input
            type="password"
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
            required
          />
        </FormField>
        <FormField label="새 비밀번호">
          <Input
            type="password"
            value={next1}
            onChange={(e) => setNext1(e.target.value)}
            required
            minLength={MIN_LEN}
          />
        </FormField>
        <FormField label="새 비밀번호 확인">
          <Input
            type="password"
            value={next2}
            onChange={(e) => setNext2(e.target.value)}
            required
            minLength={MIN_LEN}
          />
        </FormField>
        <Button type="submit" variant="primary" fullWidth loading={authLoading}>
          변경하고 계속
        </Button>
      </form>
    </div>
  );
}
