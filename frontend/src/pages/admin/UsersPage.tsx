import { useEffect, useState } from "react";
import { getApiErrorMessage } from "@/api/httpClient";
import * as adminApi from "@/api/adminApi";
import { ErrorMessage } from "@/components/ErrorMessage";
import { Loading } from "@/components/Loading";
import {
  Badge,
  Button,
  ConfirmDialog,
  DataTable,
  FilterBar,
  FilterField,
  Input,
  PageHeader,
  SectionCard,
  Select,
} from "@/components/ui";
import type { AdminUserRow } from "@/types/admin";

function statusVariant(s: string): "default" | "success" | "warning" | "danger" {
  switch (s) {
    case "ACTIVE":
      return "success";
    case "PENDING":
      return "warning";
    case "LOCKED":
      return "danger";
    default:
      return "default";
  }
}

function roleVariant(r: string): "primary" | "neutral" {
  return r === "ADMIN" ? "primary" : "neutral";
}

type ConfirmState = {
  title: string;
  message: string;
  danger?: boolean;
  run: () => Promise<void>;
} | null;

export function UsersPage() {
  const [items, setItems] = useState<AdminUserRow[]>([]);
  const [status, setStatus] = useState("");
  const [role, setRole] = useState("");
  const [keyword, setKeyword] = useState("");
  const [appliedKeyword, setAppliedKeyword] = useState("");
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState<ConfirmState>(null);

  async function load() {
    setLoading(true);
    setError("");
    try {
      const res = await adminApi.listAdminUsers({
        status: status || undefined,
        role: role || undefined,
        keyword: appliedKeyword || undefined,
        limit: 100,
        offset: 0,
      });
      setItems(res.items);
    } catch (e) {
      setError(getApiErrorMessage(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [status, role, appliedKeyword]);

  async function executeUserOp(
    label: string,
    fn: (id: string) => Promise<{ user: AdminUserRow }>,
    id: string
  ) {
    setMsg("");
    setBusy(true);
    try {
      await fn(id);
      setMsg(`${label} 처리되었습니다.`);
      await load();
    } catch (e) {
      setMsg(getApiErrorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  function askConfirm(
    title: string,
    message: string,
    danger: boolean | undefined,
    label: string,
    fn: (id: string) => Promise<{ user: AdminUserRow }>,
    id: string
  ) {
    setConfirm({
      title,
      message,
      danger,
      run: async () => {
        setConfirm(null);
        await executeUserOp(label, fn, id);
      },
    });
  }

  if (loading) return <Loading />;

  return (
    <div>
      <PageHeader
        title="사용자 관리"
        description="가입 승인·계정 상태·역할을 관리합니다. 마지막 관리자 보호는 백엔드에서 처리됩니다."
      />
      <ErrorMessage message={error} />
      {msg && <div className="alert alertInfo">{msg}</div>}

      <SectionCard title="필터">
        <FilterBar>
          <FilterField label="상태">
            <Select value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">전체</option>
              <option value="PENDING">PENDING</option>
              <option value="ACTIVE">ACTIVE</option>
              <option value="INACTIVE">INACTIVE</option>
              <option value="LOCKED">LOCKED</option>
            </Select>
          </FilterField>
          <FilterField label="권한">
            <Select value={role} onChange={(e) => setRole(e.target.value)}>
              <option value="">전체</option>
              <option value="USER">USER</option>
              <option value="ADMIN">ADMIN</option>
            </Select>
          </FilterField>
          <FilterField label="키워드" wide>
            <Input
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              placeholder="로그인·이름·이메일"
              onKeyDown={(e) => {
                if (e.key === "Enter") setAppliedKeyword(keyword.trim());
              }}
            />
          </FilterField>
          <Button type="button" variant="primary" size="sm" onClick={() => setAppliedKeyword(keyword.trim())}>
            조회
          </Button>
        </FilterBar>
      </SectionCard>

      <SectionCard title="사용자 목록">
        <DataTable>
          <thead>
            <tr>
              <th>로그인</th>
              <th>이름</th>
              <th>상태</th>
              <th>역할</th>
              <th>작업</th>
            </tr>
          </thead>
          <tbody>
            {items.map((u) => (
              <tr key={u.id}>
                <td>{u.login_id}</td>
                <td>{u.name ?? "—"}</td>
                <td>
                  <Badge variant={statusVariant(u.status)}>{u.status}</Badge>
                </td>
                <td>
                  <Badge variant={roleVariant(u.role)}>{u.role}</Badge>
                </td>
                <td className="rowActions">
                  {u.status === "PENDING" && (
                    <Button
                      type="button"
                      variant="secondary"
                      size="sm"
                      disabled={busy}
                      onClick={() =>
                        askConfirm("승인", `${u.login_id} 계정을 승인합니다.`, false, "승인", adminApi.approveUser, u.id)
                      }
                    >
                      승인
                    </Button>
                  )}
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    disabled={busy}
                    onClick={() =>
                      askConfirm("활성화", `${u.login_id} 계정을 활성화합니다.`, false, "활성", adminApi.activateUser, u.id)
                    }
                  >
                    활성
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    disabled={busy}
                    onClick={() =>
                      askConfirm(
                        "비활성화",
                        `${u.login_id} 계정을 비활성화합니다. 해당 사용자는 로그인할 수 없게 됩니다.`,
                        true,
                        "비활성",
                        adminApi.deactivateUser,
                        u.id
                      )
                    }
                  >
                    비활성
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    disabled={busy}
                    onClick={() =>
                      askConfirm(
                        "잠금",
                        `${u.login_id} 계정을 잠급니다. 로그인이 차단됩니다.`,
                        true,
                        "잠금",
                        adminApi.lockUser,
                        u.id
                      )
                    }
                  >
                    잠금
                  </Button>
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    disabled={busy}
                    onClick={() =>
                      askConfirm(
                        "역할 ADMIN",
                        `${u.login_id}에게 관리자 권한을 부여합니다.`,
                        true,
                        "역할 ADMIN",
                        (id) => adminApi.setUserRole(id, "ADMIN"),
                        u.id
                      )
                    }
                  >
                    ADMIN
                  </Button>
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    disabled={busy}
                    onClick={() =>
                      askConfirm(
                        "역할 USER",
                        `${u.login_id}의 역할을 일반 사용자로 변경합니다.`,
                        false,
                        "역할 USER",
                        (id) => adminApi.setUserRole(id, "USER"),
                        u.id
                      )
                    }
                  >
                    USER
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </DataTable>
      </SectionCard>

      <ConfirmDialog
        open={Boolean(confirm)}
        title={confirm?.title ?? ""}
        message={confirm?.message ?? ""}
        danger={confirm?.danger}
        onCancel={() => setConfirm(null)}
        onConfirm={() => {
          void confirm?.run();
        }}
      />
    </div>
  );
}
