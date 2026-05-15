import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getApiErrorMessage } from "@/api/httpClient";
import * as answerApi from "@/api/answerApi";
import { FILE_TYPE_FILTER_OPTIONS } from "@/constants/filters";
import { EmptyState } from "@/components/EmptyState";
import { ErrorMessage } from "@/components/ErrorMessage";
import {
  Badge,
  Button,
  CollapsiblePanel,
  DataSourceSelect,
  DataTable,
  FormField,
  Input,
  PageHeader,
  SectionCard,
  Select,
  Textarea,
} from "@/components/ui";
import { useSearchDataSources } from "@/hooks/useSearchDataSources";
import type { AnswerCitation, AnswerRequest, AnswerResponse, ContextPreviewItem } from "@/types/answer";
import type { SearchMode } from "@/types/search";
import { clearRagSession, loadRagSession, saveRagSession } from "@/utils/ragSessionCache";
import { formatScore } from "@/utils/format";
import { getSearchModeLabel } from "@/utils/userFriendlyLabels";
import { parseExtensionsFromInput } from "@/utils/parseExtensionsString";
import styles from "./AnswerPage.module.css";

const INSUFFICIENT_PHRASE = "제공된 문서만으로는 답변하기 어렵습니다.";

export function AnswerPage() {
  const { items: dataSources, loading: dsListLoading, loadError: dsListError } = useSearchDataSources();

  const [query, setQuery] = useState("");
  const [searchMode, setSearchMode] = useState<SearchMode>("vector");
  const [dataSourceId, setDataSourceId] = useState("");
  const [extensionsRaw, setExtensionsRaw] = useState("");
  const [fileType, setFileType] = useState("");
  const [searchLimit, setSearchLimit] = useState(10);
  const [contextLimit, setContextLimit] = useState(5);
  const [answerMinScoreStr, setAnswerMinScoreStr] = useState("0.2");
  const [temperatureStr, setTemperatureStr] = useState("0.2");
  const [maxContextChars, setMaxContextChars] = useState(12000);
  const [minScoreStr, setMinScoreStr] = useState("0");
  const [vectorW, setVectorW] = useState("0.7");
  const [keywordW, setKeywordW] = useState("0.3");
  const [dryRun, setDryRun] = useState(false);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [data, setData] = useState<AnswerResponse | null>(null);

  useEffect(() => {
    const s = loadRagSession();
    if (s) {
      setQuery(s.query);
      setSearchMode(s.searchMode);
      setData(s.data);
      const o = s.answerOptions;
      if (o) {
        if (o.data_source_id != null) setDataSourceId(String(o.data_source_id));
        if (o.search_limit != null) setSearchLimit(o.search_limit);
        if (o.context_limit != null) setContextLimit(o.context_limit);
        if (o.answer_min_score != null) setAnswerMinScoreStr(String(o.answer_min_score));
        if (o.temperature != null) setTemperatureStr(String(o.temperature));
        if (o.max_context_chars != null) setMaxContextChars(o.max_context_chars);
        if (o.min_score != null) setMinScoreStr(String(o.min_score));
        if (o.vector_weight != null) setVectorW(String(o.vector_weight));
        if (o.keyword_weight != null) setKeywordW(String(o.keyword_weight));
        if (o.dry_run != null) setDryRun(o.dry_run);
        if (o.file_type) setFileType(o.file_type);
        if (o.include_extensions?.length) setExtensionsRaw(o.include_extensions.join(", "));
      }
    }
  }, []);

  const answerOptionsPayload = (): Partial<AnswerRequest> => ({
    data_source_id: dataSourceId ? dataSourceId : null,
    search_limit: searchLimit,
    context_limit: contextLimit,
    answer_min_score: Number.parseFloat(answerMinScoreStr) || 0.2,
    temperature: Number.parseFloat(temperatureStr) || 0.2,
    max_context_chars: maxContextChars,
    min_score: Math.min(1, Math.max(0, Number.parseFloat(minScoreStr) || 0)),
    dry_run: dryRun,
    file_type: fileType || null,
    include_extensions: parseExtensionsFromInput(extensionsRaw),
    search_mode: searchMode,
    vector_weight: searchMode === "hybrid" ? Math.min(1, Math.max(0, Number.parseFloat(vectorW) || 0)) : undefined,
    keyword_weight: searchMode === "hybrid" ? Math.min(1, Math.max(0, Number.parseFloat(keywordW) || 0)) : undefined,
  });

  useEffect(() => {
    if (!data) return;
    saveRagSession({
      query,
      searchMode,
      answerOptions: answerOptionsPayload(),
      data,
    });
  }, [
    data,
    query,
    searchMode,
    dataSourceId,
    extensionsRaw,
    fileType,
    searchLimit,
    contextLimit,
    answerMinScoreStr,
    temperatureStr,
    maxContextChars,
    minScoreStr,
    vectorW,
    keywordW,
    dryRun,
  ]);

  function onClearSession() {
    clearRagSession();
    setData(null);
    setError("");
  }

  async function onAsk(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    const body: AnswerRequest = {
      ...answerOptionsPayload(),
      query: query.trim(),
    };
    try {
      const res = await answerApi.answerRequest(body);
      setData(res);
    } catch (err) {
      setError(getApiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  const insufficient = Boolean(
    data && !data.dry_run && (data.answer ?? "").includes(INSUFFICIENT_PHRASE)
  );

  return (
    <div className={styles.wrap}>
      <PageHeader title="AI 질문" description="검색된 문서를 근거로 AI가 답변합니다." />

      <div className="card">
        <form onSubmit={onAsk}>
          <div className={styles.formRow}>
            <Textarea
              style={{ flex: "1 1 280px", minWidth: 0 }}
              placeholder="예: 나주 관련 문서에서 투입 기간은 어떻게 되나요?"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              required
            />
            <div className={styles.controls}>
              <Select
                value={searchMode}
                onChange={(e) => setSearchMode(e.target.value as SearchMode)}
                aria-label="검색 모드"
                disabled={loading}
              >
                <option value="vector">vector — 의미 검색</option>
                <option value="keyword">keyword — 키워드 검색</option>
                <option value="hybrid">hybrid — 하이브리드</option>
              </Select>
            </div>
          </div>
          {searchMode === "keyword" && (
            <div className="alert alertInfo" style={{ marginBottom: "0.75rem" }}>
              임베딩 없이 키워드(ILike) 기반으로 후보를 찾습니다. 의미 유사도는 사용되지 않습니다.
            </div>
          )}
          <div className={styles.infoCallout}>
            <span className={styles.infoIcon} aria-hidden>
              i
            </span>
            <span>
              답변은 인덱싱된 사내 문서만을 근거로 합니다. 고급 옵션에서 검색 범위·컨텍스트·점수 컷을 조정할 수 있습니다.
            </span>
          </div>

          <CollapsiblePanel title="고급 옵션" summary="데이터 소스, 확장자, search_limit, context_limit, temperature, dry_run 등">
            <div className={styles.advGrid}>
              <DataSourceSelect
                value={dataSourceId}
                onChange={setDataSourceId}
                items={dataSources}
                disabled={loading || dsListLoading}
                hint="답변 근거 검색 범위로 사용할 활성 소스입니다."
              />
              {dsListError && (
                <p className="muted" style={{ gridColumn: "1 / -1", margin: 0, fontSize: "0.85rem" }}>
                  데이터 소스 목록을 불러오지 못했습니다. 전체 범위로 질문할 수 있습니다. ({dsListError})
                </p>
              )}
              <FormField label="확장자 (쉼표)">
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
              <FormField label="search_limit">
                <Select value={String(searchLimit)} onChange={(e) => setSearchLimit(Number(e.target.value))} disabled={loading}>
                  <option value={5}>5</option>
                  <option value={10}>10</option>
                  <option value={20}>20</option>
                  <option value={50}>50</option>
                </Select>
              </FormField>
              <FormField label="context_limit">
                <Select value={String(contextLimit)} onChange={(e) => setContextLimit(Number(e.target.value))} disabled={loading}>
                  <option value={3}>3</option>
                  <option value={5}>5</option>
                  <option value={10}>10</option>
                  <option value={20}>20</option>
                </Select>
              </FormField>
              <FormField label="answer_min_score">
                <Input type="number" min={0} max={1} step={0.05} value={answerMinScoreStr} onChange={(e) => setAnswerMinScoreStr(e.target.value)} disabled={loading} />
              </FormField>
              <FormField label="min_score (검색)">
                <Input type="number" min={0} max={1} step={0.01} value={minScoreStr} onChange={(e) => setMinScoreStr(e.target.value)} disabled={loading} />
              </FormField>
              <FormField label="temperature">
                <Input type="number" min={0} max={1} step={0.05} value={temperatureStr} onChange={(e) => setTemperatureStr(e.target.value)} disabled={loading} />
              </FormField>
              <FormField label="max_context_chars">
                <Input type="number" min={1000} max={30000} step={500} value={String(maxContextChars)} onChange={(e) => setMaxContextChars(Number(e.target.value) || 12000)} disabled={loading} />
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
              <label className={styles.check}>
                <input type="checkbox" checked={dryRun} onChange={(e) => setDryRun(e.target.checked)} disabled={loading} />
                대상 확인만 (답변 생성 없이 참고 문서만 확인)
              </label>
            </div>
          </CollapsiblePanel>

          <div className={styles.formFooter}>
            {data && (
              <Button type="button" variant="secondary" size="sm" onClick={onClearSession} disabled={loading}>
                결과 지우기
              </Button>
            )}
            <Button type="submit" variant="primary" loading={loading} disabled={loading}>
              질문하기
            </Button>
          </div>
        </form>
        <ErrorMessage message={error} />
        {loading && <p className="muted">처리 중…</p>}
      </div>

      {data && (
        <>
          {data.dry_run && data.context_preview && data.context_preview.length > 0 ? (
            <SectionCard title="참고 문서 미리보기 (대상 확인)">
              <DataTable>
                <thead>
                  <tr>
                    <th>#</th>
                    <th>파일</th>
                    <th>경로</th>
                    <th>점수</th>
                    <th>라인</th>
                    <th>snippet</th>
                    <th>chars</th>
                  </tr>
                </thead>
                <tbody>
                  {data.context_preview.map((c: ContextPreviewItem) => (
                    <tr key={String(c.chunk_id)}>
                      <td>{c.context_index}</td>
                      <td>{c.filename ?? "—"}</td>
                      <td className="snippet">{c.remote_path ?? "—"}</td>
                      <td>{formatScore(c.score)}</td>
                      <td>
                        {c.start_line ?? "—"} – {c.end_line ?? "—"}
                      </td>
                      <td className="snippet">{c.snippet}</td>
                      <td>{c.preview_chars}</td>
                    </tr>
                  ))}
                </tbody>
              </DataTable>
            </SectionCard>
          ) : (
            <SectionCard title="답변">
              <div className={styles.answerBanner}>
                <Badge variant="primary">문서 근거 기반 답변</Badge>
                <span className="muted" style={{ fontSize: "0.8rem" }}>
                  검색 방식 {getSearchModeLabel(data.search_mode)} · {data.model ?? "—"}
                </span>
              </div>
              {insufficient && (
                <div className={styles.insufficientBox}>
                  근거가 충분하지 않아 답변이 제한되었을 수 있습니다. 아래 참고 문서를 함께 확인하세요.
                </div>
              )}
              <p className={styles.answerBody}>{data.answer ?? data.message}</p>
            </SectionCard>
          )}

          <SectionCard title="참고 문서">
            {data.citations.length === 0 ? (
              <EmptyState title="근거 조각이 없습니다" description="검색 결과가 없거나 점수 컷에 걸렸을 수 있습니다." />
            ) : (
              <div className={styles.citeWrap}>
                <DataTable>
                  <thead>
                    <tr>
                      <th>파일</th>
                      <th>경로</th>
                      <th>소스</th>
                      <th>관련도</th>
                      <th>줄 범위</th>
                      <th>발췌</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {data.citations.map((c: AnswerCitation) => (
                      <tr key={`${c.chunk_id}-${c.rank}`}>
                        <td className={styles.citeFile}>{c.filename ?? "—"}</td>
                        <td className="snippet">{c.remote_path ?? "—"}</td>
                        <td>{c.data_source_name}</td>
                        <td>{formatScore(c.score)}</td>
                        <td>
                          {c.start_line ?? "—"} – {c.end_line ?? "—"}
                        </td>
                        <td className="snippet">{c.snippet}</td>
                        <td>
                          <Link
                            className="btn btnSecondary btnSm"
                            to={`/files/${c.file_id}/preview?chunk_id=${encodeURIComponent(c.chunk_id)}&from=answer`}
                          >
                            미리보기
                          </Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </DataTable>
              </div>
            )}
          </SectionCard>
        </>
      )}
    </div>
  );
}
