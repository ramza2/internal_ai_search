import { useCallback, useEffect, useState } from "react";
import { getApiErrorMessage } from "@/api/httpClient";
import * as adminApi from "@/api/adminApi";
import { EmptyState } from "@/components/EmptyState";
import { ErrorMessage } from "@/components/ErrorMessage";
import { Loading } from "@/components/Loading";
import {
  Button,
  ConfirmDialog,
  DataTable,
  FilterBar,
  FilterField,
  Input,
  PageHeader,
  PaginationBar,
  RoleBadge,
  SectionCard,
  Select,
  StatusBadge,
} from "@/components/ui";
import type { AdminUserRow } from "@/types/admin";

type ConfirmState = {
  title: string;
  message: string;
  danger?: boolean;
  run: () => Promise<void>;
} | null;

export function UsersPage() {
  const [draftStatus, setDraftStatus] = useState("");
  const [draftRole, setDraftRole] = useState("");
  const [draftKeyword, setDraftKeyword] = useState("");
  const [appliedStatus, setAppliedStatus] = useState("");
  const [appliedRole, setAppliedRole] = useState("");
  const [appliedKeyword, setAppliedKeyword] = useState("");

  const [limit, setLimit] = useState(20);
  const [offset, setOffset] = useState(0);
  const [total, setTotal] = useState(0);
  const [items, setItems] = useState<AdminUserRow[]>([]);

  const [error, setError] = useState("");
  const [opError, setOpError] = useState("");
  const [successMsg, setSuccessMsg] = useState("");
  const [initialLoading, setInitialLoading] = useState(true);
  const [listBusy, setListBusy] = useState(false);
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState<ConfirmState>(null);

  const load = useCallback(async () => {
    setListBusy(true);
    setError("");
    try {
      const res = await adminApi.listAdminUsers({
        status: appliedStatus || undefined,
        role: appliedRole || undefined,
        keyword: appliedKeyword || undefined,
        limit,
        offset,
      });
      setItems(res.items);
      setTotal(res.total);
    } catch (e) {
      setError(getApiErrorMessage(e));
      setItems([]);
      setTotal(0);
    } finally {
      setListBusy(false);
      setInitialLoading(false);
    }
  }, [appliedStatus, appliedRole, appliedKeyword, limit, offset]);

  useEffect(() => {
    void load();
  }, [load]);

  function onSearch() {
    setAppliedStatus(draftStatus);
    setAppliedRole(draftRole);
    setAppliedKeyword(draftKeyword.trim());
    setOffset(0);
  }

  function onResetFilters() {
    setDraftStatus("");
    setDraftRole("");
    setDraftKeyword("");
    setAppliedStatus("");
    setAppliedRole("");
    setAppliedKeyword("");
    setLimit(20);
    setOffset(0);
  }

  async function executeUserOp(
    label: string,
    fn: (id: string) => Promise<{ user: AdminUserRow }>,
    id: string
  ) {
    setOpError("");
    setSuccessMsg("");
    setBusy(true);
    try {
      await fn(id);
      setSuccessMsg(`${label} 처리되었습니다.`);
      await load();
    } catch (e) {
      setOpError(getApiErrorMessage(e));
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

  if (initialLoading && items.length === 0) return <Loading />;

  return (
    <div>
      <PageHeader
        title="사용자 관리"
        description="가입 승인·계정 상태·역할을 관리합니다. 마지막 관리자 보호는 백엔드에서 처리됩니다."
      />
      <ErrorMessage message={error} />
      <ErrorMessage message={opError} />
      {successMsg && <div className="alert alertSuccess">{successMsg}</div>}

      <SectionCard title="필터">
        <FilterBar>
          <FilterField label="상태">
            <Select value={draftStatus} onChange={(e) => setDraftStatus(e.target.value)} disabled={listBusy}>
              <option value="">전체</option>
              <option value="PENDING">PENDING</option>
              <option value="ACTIVE">ACTIVE</option>
              <option value="INACTIVE">INACTIVE</option>
              <option value="LOCKED">LOCKED</option>
            </Select>
          </FilterField>
          <FilterField label="권한">
            <Select value={draftRole} onChange={(e) => setDraftRole(e.target.value)} disabled={listBusy}>
              <option value="">전체</option>
              <option value="USER">USER</option>
              <option value="ADMIN">ADMIN</option>
            </Select>
          </FilterField>
          <FilterField label="키워드" wide>
            <Input
              value={draftKeyword}
              onChange={(e) => setDraftKeyword(e.target.value)}
              placeholder="로그인·이름·이메일"
              disabled={listBusy}
              onKeyDown={(e) => {
                if (e.key === "Enter") onSearch();
              }}
            />
          </FilterField>
          <FilterField label="limit">
            <Select
              value={String(limit)}
              onChange={(e) => {
                setLimit(Number(e.target.value));
                setOffset(0);
              }}
              disabled={listBusy}
            >
              <option value={20}>20</option>
              <option value={50}>50</option>
              <option value={100}>100</option>
            </Select>
          </FilterField>
          <Button type="button" variant="primary" size="sm" onClick={onSearch} disabled={listBusy}>
            조회
          </Button>
          <Button type="button" variant="secondary" size="sm" onClick={onResetFilters} disabled={listBusy}>
            필터 초기화
          </Button>
        </FilterBar>
        <p className="muted" style={{ margin: "0.5rem 0 0" }}>
          총 <strong>{total.toLocaleString("ko-KR")}</strong>명
          {listBusy ? " · 불러오는 중…" : ""}
        </p>
        {/* TODO: 필터·offset을 URL query와 동기화 */}
        <PaginationBar offset={offset} limit={limit} total={total} onOffsetChange={setOffset} disabled={listBusy} />
      </SectionCard>

      <SectionCard title="사용자 목록">
        {items.length === 0 && !listBusy ? (
          <EmptyState title="사용자가 없습니다" description="필터를 완화하거나 다른 페이지를 확인하세요." />
        ) : (
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
                    <StatusBadge status={u.status} />
                  </td>
                  <td>
                    <RoleBadge role={u.role} />
                  </td>
                  <td className="rowActions">
                    {u.status === "PENDING" && (
                      <Button
                        type="button"
                        variant="secondary"
                        size="sm"
                        disabled={busy || listBusy}
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
                      disabled={busy || listBusy}
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
                      disabled={busy || listBusy}
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
                      disabled={busy || listBusy}
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
                      disabled={busy || listBusy}
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
                      disabled={busy || listBusy}
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
        )}
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
