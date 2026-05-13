import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { getApiErrorMessage } from "@/api/httpClient";
import * as searchApi from "@/api/searchApi";
import { FILE_TYPE_FILTER_OPTIONS } from "@/constants/filters";
import { EmptyState } from "@/components/EmptyState";
import { ErrorMessage } from "@/components/ErrorMessage";
import {
  Badge,
  Button,
  CollapsiblePanel,
  DataSourceSelect,
  FormField,
  Input,
  PageHeader,
  Select,
} from "@/components/ui";
import { useSearchDataSources } from "@/hooks/useSearchDataSources";
import type { SearchMode, SearchRequest, SearchResponse, SearchResultItem } from "@/types/search";
import { parseExtensionsFromInput } from "@/utils/parseExtensionsString";
import { clearSearchSession, loadSearchSession, saveSearchSession } from "@/utils/searchSessionCache";
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

function buildSummaryLines(req: SearchRequest, scopeName?: string): string[] {
  const lines: string[] = [];
  lines.push(`모드: ${MODE_LABEL[(req.search_mode ?? "vector") as SearchMode]} (${req.search_mode ?? "vector"})`);
  lines.push(`소스: ${scopeName ?? (req.data_source_id ? req.data_source_id : "전체")}`);
  lines.push(`limit: ${req.limit ?? 20} · min_score: ${req.min_score ?? 0}`);
  if (req.include_extensions?.length) lines.push(`확장자: ${req.include_extensions.join(", ")}`);
  if (req.file_type) lines.push(`파일 유형: ${req.file_type}`);
  if (req.search_mode === "hybrid") {
    lines.push(`가중치: vector ${req.vector_weight ?? 0.7} / keyword ${req.keyword_weight ?? 0.3}`);
  }
  return lines;
}

export function SearchPage() {
  const { items: dataSources, loading: dsListLoading, loadError: dsListError } = useSearchDataSources();

  const [query, setQuery] = useState("");
  const [searchMode, setSearchMode] = useState<SearchMode>("vector");
  const [dataSourceId, setDataSourceId] = useState("");
  const [extensionsRaw, setExtensionsRaw] = useState("");
  const [fileType, setFileType] = useState<string>("");
  const [limit, setLimit] = useState(20);
  const [minScoreStr, setMinScoreStr] = useState("0");
  const [vectorW, setVectorW] = useState("0.7");
  const [keywordW, setKeywordW] = useState("0.3");

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [data, setData] = useState<SearchResponse | null>(null);
  const [lastRequest, setLastRequest] = useState<SearchRequest | null>(null);

  useEffect(() => {
    const s = loadSearchSession();
    if (!s) return;
    setQuery(s.query);
    setSearchMode(s.searchMode);
    setDataSourceId(s.dataSourceId);
    setExtensionsRaw(s.extensionsRaw);
    setFileType(s.fileType);
    setLimit(s.limit);
    setMinScoreStr(s.minScoreStr);
    setVectorW(s.vectorW);
    setKeywordW(s.keywordW);
    setLastRequest(s.lastRequest);
    setData(s.data);
  }, []);

  useEffect(() => {
    if (!data || !lastRequest) return;
    saveSearchSession({
      query,
      searchMode,
      dataSourceId,
      extensionsRaw,
      fileType,
      limit,
      minScoreStr,
      vectorW,
      keywordW,
      lastRequest,
      data,
    });
  }, [
    data,
    lastRequest,
    query,
    searchMode,
    dataSourceId,
    extensionsRaw,
    fileType,
    limit,
    minScoreStr,
    vectorW,
    keywordW,
  ]);

  function onClearSession() {
    clearSearchSession();
    setData(null);
    setLastRequest(null);
    setError("");
  }

  const summaryText = useMemo(() => {
    if (!lastRequest || !data) return "";
    const scope = data.data_source_scope?.data_source_name;
    return buildSummaryLines(lastRequest, scope).join(" · ");
  }, [lastRequest, data]);

  async function onSearch(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    const minScore = Math.min(1, Math.max(0, Number.parseFloat(minScoreStr) || 0));
    const body: SearchRequest = {
      query: query.trim(),
      search_mode: searchMode,
      limit,
      min_score: minScore,
    };
    const ext = parseExtensionsFromInput(extensionsRaw);
    if (ext) body.include_extensions = ext;
    if (fileType) body.file_type = fileType;
    if (dataSourceId) body.data_source_id = dataSourceId;
    if (searchMode === "hybrid") {
      body.vector_weight = Math.min(1, Math.max(0, Number.parseFloat(vectorW) || 0));
      body.keyword_weight = Math.min(1, Math.max(0, Number.parseFloat(keywordW) || 0));
    }
    setLastRequest(body);
    try {
      const res = await searchApi.searchRequest(body);
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
              required
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
            <Button type="submit" variant="primary" loading={loading} disabled={loading}>
              검색
            </Button>
            {data && (
              <Button type="button" variant="secondary" size="sm" onClick={onClearSession} disabled={loading}>
                결과 지우기
              </Button>
            )}
          </div>
        </form>

        <CollapsiblePanel title="고급 필터" summary="데이터 소스, 확장자, 파일 유형, 점수, hybrid 가중치 등">
          <div className={styles.filterGrid}>
            <DataSourceSelect
              value={dataSourceId}
              onChange={setDataSourceId}
              items={dataSources}
              disabled={loading || dsListLoading}
              hint="검색 범위로 사용할 활성 소스입니다."
            />
            {dsListError && (
              <p className="muted" style={{ gridColumn: "1 / -1", margin: 0, fontSize: "0.85rem" }}>
                데이터 소스 목록을 불러오지 못했습니다. 전체 소스로 검색할 수 있습니다. ({dsListError})
              </p>
            )}
            <FormField label="확장자 (쉼표 구분)" hint="예: md, py, sql">
              <Input value={extensionsRaw} onChange={(e) => setExtensionsRaw(e.target.value)} disabled={loading} />
            </FormField>
            <FormField label="파일 유형">
              <Select value={fileType} onChange={(e) => setFileType(e.target.value)} disabled={loading}>
                {FILE_TYPE_FILTER_OPTIONS.map((o) => (
                  <option key={o.label} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </Select>
            </FormField>
            <FormField label="결과 개수 (limit)">
              <Select
                value={String(limit)}
                onChange={(e) => setLimit(Number.parseInt(e.target.value, 10))}
                disabled={loading}
              >
                <option value="10">10</option>
                <option value="20">20</option>
                <option value="50">50</option>
                <option value="100">100</option>
              </Select>
            </FormField>
            <FormField label="min_score (0~1)" hint="검색 API와 동일">
              <Input
                type="number"
                min={0}
                max={1}
                step={0.01}
                value={minScoreStr}
                onChange={(e) => setMinScoreStr(e.target.value)}
                disabled={loading}
              />
            </FormField>
            {searchMode === "hybrid" && (
              <>
                <FormField label="vector_weight">
                  <Input type="number" min={0} max={1} step={0.05} value={vectorW} onChange={(e) => setVectorW(e.target.value)} disabled={loading} />
                </FormField>
                <FormField label="keyword_weight">
                  <Input type="number" min={0} max={1} step={0.05} value={keywordW} onChange={(e) => setKeywordW(e.target.value)} disabled={loading} />
                </FormField>
              </>
            )}
          </div>
        </CollapsiblePanel>

        <ErrorMessage message={error} />
        {loading && <p className="muted">검색 중…</p>}
      </div>

      {data && (
        <section>
          <p className={styles.metaLine}>
            총 <strong>{data.total_results}</strong>건 · 응답 모드 <strong>{String(data.search_mode)}</strong>
          </p>
          {lastRequest && (
            <div className="alert alertInfo" style={{ fontSize: "0.85rem" }}>
              적용 필터: {summaryText}
            </div>
          )}
          {data.results.length === 0 ? (
            <EmptyState title="검색 결과가 없습니다" description="필터를 완화하거나 검색어를 바꿔 보세요." />
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
                        score {formatScore(r.score)} · final {formatScore(r.final_score)} · vec {formatScore(r.vector_score)} · kw{" "}
                        {formatScore(r.keyword_score)}
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
