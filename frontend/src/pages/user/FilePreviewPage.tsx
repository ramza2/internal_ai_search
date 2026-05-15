import { useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { getApiErrorMessage } from "@/api/httpClient";
import * as fileApi from "@/api/fileApi";
import { ErrorMessage } from "@/components/ErrorMessage";
import { Loading } from "@/components/Loading";
import { Badge, PageHeader, SectionCard } from "@/components/ui";
import type { FilePreviewResponse } from "@/types/file";
import { formatDateTime } from "@/utils/format";
import styles from "./FilePreviewPage.module.css";

function linesToHighlight(highlights: Array<Record<string, unknown>>): Set<number> {
  const s = new Set<number>();
  for (const h of highlights) {
    if (h && typeof h.line === "number") s.add(h.line);
  }
  return s;
}

export function FilePreviewPage() {
  const { fileId } = useParams<{ fileId: string }>();
  const [sp] = useSearchParams();
  const chunkId = sp.get("chunk_id") || undefined;
  const query = sp.get("query") || undefined;
  const from = sp.get("from");

  const [data, setData] = useState<FilePreviewResponse | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!fileId) return;
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError("");
      try {
        const res = await fileApi.getFilePreview(fileId, { chunk_id: chunkId, query });
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
  }, [fileId, chunkId, query]);

  const hlLines = useMemo(
    () => (data?.highlights ? linesToHighlight(data.highlights as Array<Record<string, unknown>>) : new Set()),
    [data]
  );

  if (!fileId) return <ErrorMessage message="file_id가 없습니다." />;

  if (loading) return <Loading />;
  if (error) return <ErrorMessage message={error} />;
  if (!data) return null;

  const { file, preview } = data;
  const ext = (file.extension ?? "").replace(/^\./, "").toUpperCase() || "—";

  return (
    <div>
      <div className={styles.toolbar}>
        {from === "answer" && (
          <Link to="/answer" className="btn btnSecondary btnSm">
            ← AI 질문으로 돌아가기
          </Link>
        )}
        {from === "search" && (
          <Link to="/search" className="btn btnSecondary btnSm">
            ← 통합 검색으로 돌아가기
          </Link>
        )}
        {!from && (
          <>
            <Link to="/search" className="btn btnSecondary btnSm">
              통합 검색
            </Link>
            <Link to="/answer" className="btn btnSecondary btnSm">
              AI 질문
            </Link>
          </>
        )}
      </div>

      <PageHeader title="파일 미리보기" description={file.remote_path ?? ""} />

      <SectionCard title="파일 정보">
        <div className={styles.metaGrid}>
          <div>
            <span className={styles.metaLabel}>파일명</span>
            <p className={styles.metaValue}>{file.filename ?? "—"}</p>
          </div>
          <div>
            <span className={styles.metaLabel}>데이터 소스</span>
            <p className={styles.metaValue}>{file.data_source_name}</p>
          </div>
          <div>
            <span className={styles.metaLabel}>확장자</span>
            <p className={styles.metaValue}>
              {ext !== "—" ? <Badge variant="ext">{ext}</Badge> : "—"}
            </p>
          </div>
          <div>
            <span className={styles.metaLabel}>분석 상태</span>
            <p className={styles.metaValue}>
              <Badge variant="neutral">{file.analysis_status}</Badge>
            </p>
          </div>
          <div>
            <span className={styles.metaLabel}>원본 수정 시각</span>
            <p className={styles.metaValue}>{formatDateTime(file.last_modified)}</p>
          </div>
          <div>
            <span className={styles.metaLabel}>마지막 인덱싱</span>
            <p className={styles.metaValue}>{formatDateTime(file.last_indexed_at)}</p>
          </div>
        </div>
        <p className="muted" style={{ marginTop: "0.75rem", fontSize: "0.8rem" }}>
          <strong>WebDAV URL</strong> {file.open_info.webdav_url}
        </p>
      </SectionCard>

      <SectionCard title="본문 미리보기">
        <p className="muted" style={{ marginTop: 0, marginBottom: "0.75rem", fontSize: "0.8rem" }}>
          줄 {preview.start_line ?? "—"} – {preview.end_line ?? "—"}
          {preview.chunk_id ? ` · 검색 단위 ${preview.chunk_id}` : ""}
          {preview.is_truncated ? " · 일부만 표시" : ""}
        </p>
        <div className={styles.lineGrid}>
          {preview.lines.map((line) => {
            const hl = hlLines.has(line.line);
            return (
              <div key={line.line} className={`${styles.lineRow} ${hl ? styles.lineRowHl : ""}`}>
                <span className="muted">{line.line}</span>
                <span>{line.text}</span>
              </div>
            );
          })}
        </div>
      </SectionCard>
    </div>
  );
}
