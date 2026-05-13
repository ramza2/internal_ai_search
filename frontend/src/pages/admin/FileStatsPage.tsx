import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getApiErrorMessage } from "@/api/httpClient";
import * as fileApi from "@/api/fileApi";
import { EmptyState } from "@/components/EmptyState";
import { ErrorMessage } from "@/components/ErrorMessage";
import { Loading } from "@/components/Loading";
import {
  Badge,
  Button,
  DataTable,
  FormField,
  PageHeader,
  SectionCard,
  Select,
  StatCard,
} from "@/components/ui";
import { useDataSources } from "@/hooks/useDataSources";
import type { FileStatsResponse } from "@/types/file";
import { formatDateTime, formatInt } from "@/utils/format";
import { isLikelyTextPreviewableExtension } from "@/utils/previewableFile";
import styles from "./FileStatsPage.module.css";

/** "" = 전체 통계, UUID = 해당 소스 */
type ScopeKey = "" | string;

export function FileStatsPage() {
  const { items: dataSources, loading: dsLoading } = useDataSources(true);
  const [scopeKey, setScopeKey] = useState<ScopeKey>("");
  const [includeDeleted, setIncludeDeleted] = useState(false);
  const [data, setData] = useState<FileStatsResponse | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const fetchStats = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = scopeKey
        ? await fileApi.getDataSourceFileStats(scopeKey, { include_deleted: includeDeleted })
        : await fileApi.getFileStats({ include_deleted: includeDeleted });
      setData(res);
    } catch (e) {
      setError(getApiErrorMessage(e));
    } finally {
      setLoading(false);
    }
  }, [scopeKey, includeDeleted]);

  useEffect(() => {
    void fetchStats();
  }, [fetchStats]);

  if (loading && !data) return <Loading />;

  if (error && !data) {
    return (
      <div>
        <PageHeader title="파일 현황 분석" description="인덱싱된 파일 집계입니다." />
        <ErrorMessage message={error} />
        <Button type="button" variant="secondary" size="sm" onClick={() => void fetchStats()}>
          다시 시도
        </Button>
      </div>
    );
  }

  if (!data) {
    return (
      <div>
        <PageHeader title="파일 현황 분석" description="인덱싱된 파일 집계입니다." />
        <EmptyState title="통계를 불러오지 못했습니다" description={error || "알 수 없는 오류"} />
      </div>
    );
  }

  const { summary, by_analysis_status, by_file_type, by_extension, top_largest_files, scope, by_data_source } = data;

  const skippedCount =
    by_analysis_status.find((r) => String(r.status).toUpperCase() === "SKIPPED")?.count ?? 0;

  const syncHint = summary.latest_modified_at
    ? `파일 최근 수정: ${formatDateTime(summary.latest_modified_at)}`
    : undefined;

  return (
    <div>
      <PageHeader
        title="파일 현황 분석"
        description={`범위: ${scope.data_source_name} (${scope.source_type}). 삭제 포함 옵션은 API 파라미터에 따라 달라질 수 있습니다.`}
      />

      <SectionCard title="조회 범위">
        <div className="formGrid" style={{ maxWidth: 480 }}>
          <FormField label="데이터 소스">
            <Select
              value={scopeKey}
              onChange={(e) => setScopeKey(e.target.value as ScopeKey)}
              disabled={loading || dsLoading}
            >
              <option value="">전체 (GET /api/files/stats)</option>
              {dataSources.map((ds) => (
                <option key={ds.id} value={ds.id}>
                  {ds.name}
                </option>
              ))}
            </Select>
          </FormField>
          <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.875rem" }}>
            <input
              type="checkbox"
              checked={includeDeleted}
              onChange={(e) => setIncludeDeleted(e.target.checked)}
              disabled={loading}
            />
            삭제 문서 포함 (include_deleted)
          </label>
          <Button type="button" variant="secondary" size="sm" onClick={() => void fetchStats()} disabled={loading}>
            새로고침
          </Button>
        </div>
        {loading && <p className="muted">불러오는 중…</p>}
        <ErrorMessage message={error} />
      </SectionCard>

      <div className={styles.statGrid}>
        <StatCard label="전체 항목" value={formatInt(summary.total_items)} />
        <StatCard label="파일 수" value={formatInt(summary.total_files)} />
        <StatCard label="디렉터리 수" value={formatInt(summary.total_directories)} />
        <StatCard label="전체 용량" value={summary.total_size_human} hint={formatInt(summary.total_size_bytes) + " bytes"} />
        <StatCard label="마지막 동기화" value={summary.last_synced_at ? formatDateTime(summary.last_synced_at) : "—"} hint={syncHint} />
      </div>

      <SectionCard title="문서 처리·스킵 안내">
        <p className="muted" style={{ marginTop: 0 }}>
          PDF, DOCX, XLSX, PPTX, HWPX 파일이 <code>SKIPPED</code> / <code>UNSUPPORTED_EXTENSION</code> 등으로 남아 있다면,{" "}
          <Link to="/admin/data-sources">데이터 소스</Link> 화면에서 해당 소스의 <strong>문서 처리</strong>를 실행해 텍스트를 추출한 뒤 Chunk·Embedding 단계를
          거치면 검색·RAG 대상으로 전환할 수 있습니다.
        </p>
        <p className="muted" style={{ marginBottom: 0 }}>
          HWP, DOC, XLS, PPT는 아직 미지원입니다. HWP Automation/COM은 사용하지 않습니다.
        </p>
        {skippedCount > 0 && (
          <p style={{ marginTop: "0.65rem", fontSize: "0.875rem" }}>
            현재 조회 범위에서 <strong>SKIPPED</strong> 파일은 <strong>{formatInt(skippedCount)}</strong>건입니다.
          </p>
        )}
      </SectionCard>

      {by_data_source && by_data_source.length > 0 && !scopeKey && (
        <SectionCard title="데이터 소스별 요약">
          <DataTable>
            <thead>
              <tr>
                <th>이름</th>
                <th>유형</th>
                <th>파일</th>
                <th>디렉터리</th>
                <th>용량(bytes)</th>
                <th>마지막 스캔</th>
              </tr>
            </thead>
            <tbody>
              {by_data_source.map((r) => (
                <tr key={r.data_source_id}>
                  <td>{r.data_source_name}</td>
                  <td>
                    <Badge variant="neutral">{r.source_type}</Badge>
                  </td>
                  <td>{formatInt(r.total_files)}</td>
                  <td>{formatInt(r.total_directories)}</td>
                  <td>{formatInt(r.total_size_bytes)}</td>
                  <td>{formatDateTime(r.last_scan_at)}</td>
                </tr>
              ))}
            </tbody>
          </DataTable>
        </SectionCard>
      )}

      <SectionCard title="분석 상태별">
        <DataTable>
          <thead>
            <tr>
              <th>상태</th>
              <th>건수</th>
            </tr>
          </thead>
          <tbody>
            {by_analysis_status.map((r) => (
              <tr key={r.status}>
                <td>
                  <Badge variant="neutral">{r.status}</Badge>
                </td>
                <td>{formatInt(r.count)}</td>
              </tr>
            ))}
          </tbody>
        </DataTable>
      </SectionCard>

      <SectionCard title="파일 유형별">
        <DataTable>
          <thead>
            <tr>
              <th>유형</th>
              <th>건수</th>
              <th>용량(bytes)</th>
            </tr>
          </thead>
          <tbody>
            {by_file_type.map((r) => (
              <tr key={r.file_type}>
                <td>
                  <Badge variant="primary">{r.file_type}</Badge>
                </td>
                <td>{formatInt(r.count)}</td>
                <td>{formatInt(r.total_size_bytes)}</td>
              </tr>
            ))}
          </tbody>
        </DataTable>
      </SectionCard>

      <SectionCard title="확장자별">
        <DataTable>
          <thead>
            <tr>
              <th>확장자</th>
              <th>파일 유형</th>
              <th>건수</th>
              <th>용량(bytes)</th>
            </tr>
          </thead>
          <tbody>
            {by_extension.map((r, i) => (
              <tr key={`${r.extension}-${i}`}>
                <td>{r.extension}</td>
                <td>
                  <Badge variant="neutral">{r.file_type}</Badge>
                </td>
                <td>{formatInt(r.count)}</td>
                <td>{formatInt(r.total_size_bytes)}</td>
              </tr>
            ))}
          </tbody>
        </DataTable>
      </SectionCard>

      <SectionCard title="대용량 파일 TOP">
        <DataTable>
          <thead>
            <tr>
              <th>파일명</th>
              <th>경로</th>
              <th>크기</th>
              <th>수정</th>
              <th style={{ width: "6rem" }} />
            </tr>
          </thead>
          <tbody>
            {top_largest_files.map((r) => {
              const preview = isLikelyTextPreviewableExtension(r.extension);
              return (
                <tr key={r.id}>
                  <td>{r.filename ?? "—"}</td>
                  <td className="snippet">{r.remote_path ?? "—"}</td>
                  <td>{r.size_human ?? formatInt(r.size_bytes)}</td>
                  <td>{formatDateTime(r.last_modified)}</td>
                  <td>
                    {preview ? (
                      <Link className="btn btnSecondary btnSm" to={`/files/${r.id}/preview?from=file-stats`}>
                        미리보기
                      </Link>
                    ) : (
                      <span className="muted" title="텍스트 계열 확장자만 링크 표시">
                        —
                      </span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </DataTable>
      </SectionCard>
    </div>
  );
}
