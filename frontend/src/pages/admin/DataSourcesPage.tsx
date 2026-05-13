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
import { DocumentProcessModal } from "./DocumentProcessModal";
import { PipelineRunModal } from "./pipeline/PipelineRunModal";

export function DataSourcesPage() {
  const [items, setItems] = useState<DataSource[]>([]);
  const [loading, setLoading] = useState(true);
  const [listBusy, setListBusy] = useState(false);
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");
  const [msgTone, setMsgTone] = useState<"info" | "success" | "danger">("info");
  const [showForm, setShowForm] = useState(false);
  const [testingId, setTestingId] = useState<string | null>(null);
  const [docModalSource, setDocModalSource] = useState<DataSource | null>(null);
  const [pipelineSource, setPipelineSource] = useState<DataSource | null>(null);
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

  async function load(opts?: { initial?: boolean }) {
    const initial = opts?.initial ?? false;
    if (initial) setLoading(true);
    else setListBusy(true);
    setError("");
    try {
      const res = await dsApi.listDataSources(true);
      setItems(res.items);
    } catch (e) {
      setError(getApiErrorMessage(e));
    } finally {
      if (initial) setLoading(false);
      else setListBusy(false);
    }
  }

  useEffect(() => {
    void load({ initial: true });
  }, []);

  function setFlash(text: string, tone: typeof msgTone) {
    setMsg(text);
    setMsgTone(tone);
  }

  async function onCreate(e: React.FormEvent) {
    e.preventDefault();
    if (form.source_type === "LOCAL_FOLDER") {
      setFlash("LOCAL_FOLDER 유형은 아직 지원하지 않습니다. (추후 지원 예정)", "danger");
      return;
    }
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
    setTestingId(id);
    try {
      const { data, status } = await dsApi.testDataSourceConnection(id);
      const ok = status >= 200 && status < 300;
      setMsgTone(ok ? "success" : "danger");
      setFlash(`HTTP ${status}: ${JSON.stringify(data).slice(0, 500)}`, ok ? "success" : "danger");
      await load();
    } catch (e) {
      setFlash(getApiErrorMessage(e), "danger");
    } finally {
      setTestingId(null);
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
        actions={
          <Button type="button" variant="secondary" size="sm" loading={listBusy} onClick={() => void load()} disabled={loading}>
            목록 새로고침
          </Button>
        }
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
            {showForm ? "폼 닫기" : "데이터 소스 추가"}
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
                <option value="LOCAL_FOLDER">LOCAL_FOLDER (추후 지원)</option>
              </Select>
            </FormField>
            {form.source_type === "LOCAL_FOLDER" && (
              <p className="muted" style={{ gridColumn: "1 / -1", margin: 0 }}>
                LOCAL_FOLDER는 추후 지원 예정입니다. WebDAV 계열 유형을 선택해 주세요.
              </p>
            )}
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
            <Button type="submit" variant="primary" loading={saving} disabled={saving || form.source_type === "LOCAL_FOLDER"}>
              등록
            </Button>
          </form>
        )}
      </SectionCard>

      <SectionCard title="데이터 소스 목록">
        <p className="muted" style={{ marginTop: 0 }}>
          {/* TODO: 행 단위 수정·삭제 UI — 백엔드 PATCH/DELETE 연동 후 구현 */}
          목록에서 이름·URL 등을 바꾸는 수정 기능은 추후 제공 예정입니다.
        </p>
        <DataTable>
          <thead>
            <tr>
              <th>이름</th>
              <th>유형</th>
              <th>서버</th>
              <th>루트</th>
              <th>상태</th>
              <th>마지막 테스트</th>
              <th style={{ minWidth: "14rem" }} />
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
                    {testingId === ds.id ? (
                      <span className="muted">테스트 중…</span>
                    ) : ds.last_connection_success === true ? (
                      <Badge variant="success">성공</Badge>
                    ) : ds.last_connection_success === false ? (
                      <Badge variant="danger">실패</Badge>
                    ) : (
                      <span className="muted">—</span>
                    )}
                  </div>
                  {ds.last_connection_message && (
                    <div className="snippet muted" style={{ marginTop: "0.35rem", maxWidth: "18rem", fontSize: "0.75rem" }}>
                      {ds.last_connection_message}
                    </div>
                  )}
                </td>
                <td className="rowActions">
                  <Button type="button" variant="secondary" size="sm" onClick={() => setPipelineSource(ds)}>
                    파이프라인 실행
                  </Button>
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    onClick={() => setDocModalSource(ds)}
                  >
                    문서 처리
                  </Button>
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    onClick={() => testOne(ds.id)}
                    loading={testingId === ds.id}
                    disabled={testingId !== null && testingId !== ds.id}
                  >
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

      {docModalSource && (
        <DocumentProcessModal dataSource={docModalSource} onClose={() => setDocModalSource(null)} />
      )}
      {pipelineSource && (
        <PipelineRunModal
          dataSource={pipelineSource}
          onClose={() => setPipelineSource(null)}
          onRefresh={() => void load()}
        />
      )}
    </div>
  );
}
