import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { getApiErrorMessage } from "@/api/httpClient";
import * as authApi from "@/api/authApi";
import { ErrorMessage } from "@/components/ErrorMessage";
import { Button, FormField, Input } from "@/components/ui";

export function SignupPage() {
  const navigate = useNavigate();
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [loginId, setLoginId] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [department, setDepartment] = useState("");

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await authApi.signupRequest({
        login_id: loginId.trim(),
        password,
        name: name.trim(),
        email: email.trim(),
        department: department.trim() || null,
      });
      setDone(true);
    } catch (err) {
      setError(getApiErrorMessage(err, "가입 처리에 실패했습니다."));
    } finally {
      setLoading(false);
    }
  }

  if (done) {
    return (
      <div>
        <h2 className="pageTitle" style={{ marginBottom: "0.5rem" }}>
          가입 신청이 접수되었습니다
        </h2>
        <p className="muted" style={{ lineHeight: 1.6 }}>
          관리자 승인 후 로그인할 수 있습니다. 승인까지 시간이 걸릴 수 있습니다.
        </p>
        <div style={{ marginTop: "1.25rem" }}>
          <Button type="button" variant="primary" fullWidth onClick={() => navigate("/login")}>
            로그인 화면으로
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div>
      <h2 className="pageTitle" style={{ marginBottom: "0.5rem" }}>
        회원가입
      </h2>
      <div className="alert alertInfo" style={{ marginBottom: "1rem" }}>
        관리자 승인 후에만 서비스를 이용할 수 있습니다. 승인 전까지는 로그인되지 않습니다.
      </div>
      <ErrorMessage message={error} />
      <form className="formGrid" onSubmit={onSubmit} style={{ maxWidth: "100%" }}>
        <FormField label="로그인 ID" hint="3자 이상">
          <Input value={loginId} onChange={(e) => setLoginId(e.target.value)} required minLength={3} />
        </FormField>
        <FormField label="비밀번호" hint="8자 이상">
          <Input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={8}
          />
        </FormField>
        <FormField label="이름">
          <Input value={name} onChange={(e) => setName(e.target.value)} required />
        </FormField>
        <FormField label="이메일">
          <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </FormField>
        <FormField label="부서 (선택)">
          <Input value={department} onChange={(e) => setDepartment(e.target.value)} />
        </FormField>
        <Button type="submit" variant="primary" fullWidth loading={loading}>
          가입 신청
        </Button>
      </form>
      <p className="muted" style={{ marginTop: "1rem", textAlign: "center" }}>
        <Link to="/login">로그인으로 돌아가기</Link>
      </p>
    </div>
  );
}
