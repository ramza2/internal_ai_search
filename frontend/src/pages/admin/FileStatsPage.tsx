import { useEffect, useState } from "react";
import { getApiErrorMessage } from "@/api/httpClient";
import * as fileApi from "@/api/fileApi";
import { ErrorMessage } from "@/components/ErrorMessage";
import { Loading } from "@/components/Loading";
import { Badge, DataTable, PageHeader, SectionCard, StatCard } from "@/components/ui";
import type { FileStatsResponse } from "@/types/file";
import { formatDateTime, formatInt } from "@/utils/format";
import styles from "./FileStatsPage.module.css";

export function FileStatsPage() {
  const [data, setData] = useState<FileStatsResponse | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError("");
      try {
        const res = await fileApi.getFileStats();
        if (!cancelled) setData(res);
      } catch (e) {
        if (!cancelled) setError(getApiErrorMessage(e));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (loading) return <Loading />;
  if (error) return <ErrorMessage message={error} />;
  if (!data) return null;

  const { summary, by_analysis_status, by_file_type, by_extension, top_largest_files, scope, by_data_source } = data;

  return (
    <div>
      <PageHeader
        title="파일 현황 분석"
        description={`범위: ${scope.data_source_name} (${scope.source_type}). 집계는 SQL 기반입니다.`}
      />

      <div className={styles.statGrid}>
        <StatCard label="전체 항목" value={formatInt(summary.total_items)} />
        <StatCard label="파일 수" value={formatInt(summary.total_files)} />
        <StatCard label="디렉터리 수" value={formatInt(summary.total_directories)} />
        <StatCard label="총 용량" value={summary.total_size_human} hint={formatDateTime(summary.latest_modified_at)} />
      </div>

      {by_data_source && by_data_source.length > 0 && (
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
            </tr>
          </thead>
          <tbody>
            {top_largest_files.map((r) => (
              <tr key={r.id}>
                <td>{r.filename ?? "—"}</td>
                <td className="snippet">{r.remote_path ?? "—"}</td>
                <td>{r.size_human ?? formatInt(r.size_bytes)}</td>
                <td>{formatDateTime(r.last_modified)}</td>
              </tr>
            ))}
          </tbody>
        </DataTable>
      </SectionCard>
    </div>
  );
}
