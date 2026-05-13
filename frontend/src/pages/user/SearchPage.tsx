import { useState } from "react";
import { Link } from "react-router-dom";
import { getApiErrorMessage } from "@/api/httpClient";
import * as searchApi from "@/api/searchApi";
import { EmptyState } from "@/components/EmptyState";
import { ErrorMessage } from "@/components/ErrorMessage";
import { Loading } from "@/components/Loading";
import { Badge, Button, Input, PageHeader, Select } from "@/components/ui";
import type { SearchMode, SearchResponse, SearchResultItem } from "@/types/search";
import { formatRelevanceDisplay, formatScore } from "@/utils/format";
import styles from "./SearchPage.module.css";

const MODE_LABEL: Record<SearchMode, string> = {
  vector: "의미 검색",
  keyword: "키워드 검색",
  hybrid: "하이브리드 검색",
};

function sourcePillLabel(sourceType: string, dataSourceName: string): string {
  if (sourceType === "internal" || /사내|internal/i.test(dataSourceName)) return "사내 문서";
  return dataSourceName || "문서";
}

export function SearchPage() {
  const [query, setQuery] = useState("");
  const [searchMode, setSearchMode] = useState<SearchMode>("vector");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [data, setData] = useState<SearchResponse | null>(null);

  async function onSearch(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    setData(null);
    try {
      const res = await searchApi.searchRequest({
        query: query.trim(),
        search_mode: searchMode,
        limit: 20,
      });
      setData(res);
    } catch (err) {
      setError(getApiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <PageHeader
        title="통합 검색"
        description="사내 문서와 소스코드를 의미 기반·키워드 기반으로 검색합니다."
      />

      <div className="card">
        <form onSubmit={onSearch}>
          <div className={styles.searchRow}>
            <Input
              className={styles.searchInput}
              placeholder="파일명, 경로, 본문, 코드 내용 검색…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            <Select
              className={styles.modeSelect}
              value={searchMode}
              onChange={(e) => setSearchMode(e.target.value as SearchMode)}
              aria-label="검색 모드"
            >
              <option value="vector">vector — 의미 검색</option>
              <option value="keyword">keyword — 키워드 검색</option>
              <option value="hybrid">hybrid — 하이브리드</option>
            </Select>
            <Button type="submit" variant="primary" loading={loading}>
              검색
            </Button>
          </div>
        </form>
        <ErrorMessage message={error} />
        {loading && <Loading />}
      </div>

      {data && (
        <section>
          <p className={styles.metaLine}>
            총 <strong>{data.total_results}</strong>건 · 모드 <strong>{MODE_LABEL[data.search_mode]}</strong> (
            {String(data.search_mode)})
          </p>
          {data.results.length === 0 ? (
            <EmptyState title="검색 결과가 없습니다" description="검색어를 바꾸거나 모드를 전환해 보세요." />
          ) : (
            <div className={styles.results}>
              {(data.results as SearchResultItem[]).map((r) => {
                const ext = (r.extension || "").replace(/^\./, "").toUpperCase() || "—";
                const previewTo = `/files/${r.file_id}/preview?chunk_id=${encodeURIComponent(r.chunk_id)}&from=search`;
                const reasons = (r.match_reasons ?? []).filter(Boolean).join(", ") || "—";
                return (
                  <article key={`${r.chunk_id}-${r.rank}`} className={styles.resultCard}>
                    <div className={styles.resultMain}>
                      <div className={styles.resultHead}>
                        <span className={styles.pill}>
                          <Badge variant="primary">{sourcePillLabel(r.source_type, r.data_source_name)}</Badge>
                        </span>
                        <Link className={styles.fileLink} to={previewTo}>
                          {r.filename ?? "(이름 없음)"}
                        </Link>
                        {ext !== "—" && <Badge variant="ext">{ext}</Badge>}
                        {r.file_type && (
                          <span title="파일 유형">
                            <Badge variant="neutral">{r.file_type}</Badge>
                          </span>
                        )}
                        <span className="muted" style={{ fontSize: "0.8rem" }}>
                          관련도 <strong>{formatRelevanceDisplay(r.final_score)}</strong>
                        </span>
                      </div>
                      <p className={styles.path}>{r.remote_path ?? "—"}</p>
                      <p className={styles.snippet}>{r.snippet}</p>
                      <p className={styles.scoreLine}>
                        score {formatScore(r.score)} · final {formatScore(r.final_score)} · vec{" "}
                        {formatScore(r.vector_score)} · kw {formatScore(r.keyword_score)}
                      </p>
                      <p className={styles.reasons}>match: {reasons}</p>
                      <p className={styles.reasons}>
                        라인 {r.start_line ?? "—"} – {r.end_line ?? "—"} · 소스 {r.data_source_name}
                      </p>
                    </div>
                    <div className={styles.resultActions}>
                      <Link to={previewTo} className="btn btnSecondary btnSm" style={{ textAlign: "center" }}>
                        미리보기
                      </Link>
                      <Button
                        variant="ghost"
                        size="sm"
                        type="button"
                        onClick={async () => {
                          const path = r.remote_path ?? "";
                          if (!path) return;
                          try {
                            await navigator.clipboard.writeText(path);
                          } catch {
                            /* ignore */
                          }
                        }}
                      >
                        경로 복사
                      </Button>
                    </div>
                  </article>
                );
              })}
            </div>
          )}
        </section>
      )}
    </div>
  );
}
