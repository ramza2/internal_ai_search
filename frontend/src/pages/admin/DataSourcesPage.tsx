import { useEffect, useState } from "react";
import { getApiErrorMessage } from "@/api/httpClient";
import * as dsApi from "@/api/dataSourceApi";
import { ErrorMessage } from "@/components/ErrorMessage";
import { Loading } from "@/components/Loading";
import {
  Badge,
  Button,
  DataTable,
  FormField,
  Input,
  PageHeader,
  SectionCard,
  Select,
  Textarea,
} from "@/components/ui";
import type { DataSource, SourceType } from "@/types/dataSource";
import { formatDateTime } from "@/utils/format";

export function DataSourcesPage() {
  const [items, setItems] = useState<DataSource[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");
  const [msgTone, setMsgTone] = useState<"info" | "success" | "danger">("info");
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({
    name: "",
    source_type: "OWNCLOUD" as SourceType,
    server_url: "",
    webdav_root_path: "",
    username: "",
    credential_secret: "",
    description: "",
  });

  async function load() {
    setLoading(true);
    setError("");
    try {
      const res = await dsApi.listDataSources(true);
      setItems(res.items);
    } catch (e) {
      setError(getApiErrorMessage(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  function setFlash(text: string, tone: typeof msgTone) {
    setMsg(text);
    setMsgTone(tone);
  }

  async function onCreate(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setMsg("");
    try {
      await dsApi.createDataSource({
        name: form.name.trim(),
        source_type: form.source_type,
        server_url: form.server_url.trim(),
        webdav_root_path: form.webdav_root_path.trim() || null,
        username: form.username.trim() || null,
        credential_secret: form.credential_secret || null,
        description: form.description.trim() || null,
      });
      setShowForm(false);
      setForm((f) => ({
        ...f,
        name: "",
        server_url: "",
        webdav_root_path: "",
        username: "",
        credential_secret: "",
        description: "",
      }));
      setFlash("등록되었습니다.", "success");
      await load();
    } catch (e) {
      setFlash(getApiErrorMessage(e), "danger");
    } finally {
      setSaving(false);
    }
  }

  async function testOne(id: string) {
    setMsg("");
    try {
      const { data, status } = await dsApi.testDataSourceConnection(id);
      const ok = status >= 200 && status < 300;
      setMsgTone(ok ? "success" : "danger");
      setFlash(`HTTP ${status}: ${JSON.stringify(data).slice(0, 500)}`, ok ? "success" : "danger");
      await load();
    } catch (e) {
      setFlash(getApiErrorMessage(e), "danger");
    }
  }

  async function toggleActive(ds: DataSource, active: boolean) {
    setMsg("");
    try {
      if (active) await dsApi.activateDataSource(ds.id);
      else await dsApi.deactivateDataSource(ds.id);
      await load();
    } catch (e) {
      setFlash(getApiErrorMessage(e), "danger");
    }
  }

  if (loading) return <Loading />;

  return (
    <div>
      <PageHeader
        title="데이터 소스 설정"
        description="WebDAV 기반 소스를 등록하고 접속을 검증합니다. App Password 등 비밀 값은 저장 후 다시 표시되지 않습니다."
      />
      <ErrorMessage message={error} />
      {msg && (
        <div
          className={`alert ${
            msgTone === "success" ? "alertSuccess" : msgTone === "danger" ? "alertDanger" : "alertInfo"
          }`}
        >
          {msg}
        </div>
      )}

      <SectionCard
        title="등록"
        actions={
          <Button type="button" variant="secondary" size="sm" onClick={() => setShowForm((s) => !s)}>
            {showForm ? "폼 닫기" : "새 데이터 소스"}
          </Button>
        }
      >
        {showForm && (
          <form onSubmit={onCreate} className="formGrid" style={{ maxWidth: 560, marginTop: "0.5rem" }}>
            <FormField label="데이터 소스명">
              <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
            </FormField>
            <FormField label="유형">
              <Select
                value={form.source_type}
                onChange={(e) => setForm({ ...form, source_type: e.target.value as SourceType })}
              >
                <option value="OWNCLOUD">OWNCLOUD</option>
                <option value="NEXTCLOUD">NEXTCLOUD</option>
                <option value="GENERIC_WEBDAV">GENERIC_WEBDAV</option>
                <option value="LOCAL_FOLDER">LOCAL_FOLDER</option>
              </Select>
            </FormField>
            <FormField label="서버 URL">
              <Input value={form.server_url} onChange={(e) => setForm({ ...form, server_url: e.target.value })} required />
            </FormField>
            <FormField label="WebDAV 루트 경로" hint="선택">
              <Input value={form.webdav_root_path} onChange={(e) => setForm({ ...form, webdav_root_path: e.target.value })} />
            </FormField>
            <FormField label="사용자 ID" hint="선택">
              <Input value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} />
            </FormField>
            <FormField label="App Password / 비밀번호" hint="저장 후 서버에서 다시 내려주지 않습니다">
              <Input
                type="password"
                value={form.credential_secret}
                onChange={(e) => setForm({ ...form, credential_secret: e.target.value })}
              />
            </FormField>
            <FormField label="설명" hint="선택">
              <Textarea rows={2} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
            </FormField>
            <Button type="submit" variant="primary" loading={saving}>
              등록
            </Button>
          </form>
        )}
      </SectionCard>

      <SectionCard title="데이터 소스 목록">
        <DataTable>
          <thead>
            <tr>
              <th>이름</th>
              <th>유형</th>
              <th>서버</th>
              <th>루트</th>
              <th>상태</th>
              <th>마지막 테스트</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {items.map((ds) => (
              <tr key={ds.id}>
                <td>{ds.name}</td>
                <td>
                  <Badge variant="neutral">{ds.source_type}</Badge>
                </td>
                <td className="snippet">{ds.server_url}</td>
                <td className="snippet">{ds.webdav_root_path ?? "—"}</td>
                <td>{ds.is_active ? <Badge variant="success">활성</Badge> : <Badge variant="default">비활성</Badge>}</td>
                <td>
                  {formatDateTime(ds.last_connection_test_at)}
                  <div style={{ marginTop: "0.25rem" }}>
                    {ds.last_connection_success === true ? (
                      <Badge variant="success">성공</Badge>
                    ) : ds.last_connection_success === false ? (
                      <Badge variant="danger">실패</Badge>
                    ) : (
                      <span className="muted">—</span>
                    )}
                  </div>
                </td>
                <td className="rowActions">
                  <Button type="button" variant="secondary" size="sm" onClick={() => testOne(ds.id)}>
                    접속 테스트
                  </Button>
                  {ds.is_active ? (
                    <Button type="button" variant="ghost" size="sm" onClick={() => toggleActive(ds, false)}>
                      비활성
                    </Button>
                  ) : (
                    <Button type="button" variant="primary" size="sm" onClick={() => toggleActive(ds, true)}>
                      활성
                    </Button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </DataTable>
      </SectionCard>
    </div>
  );
}
