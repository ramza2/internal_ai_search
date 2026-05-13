import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getApiErrorMessage } from "@/api/httpClient";
import * as answerApi from "@/api/answerApi";
import { EmptyState } from "@/components/EmptyState";
import { ErrorMessage } from "@/components/ErrorMessage";
import { Badge, Button, DataTable, PageHeader, SectionCard, Select, Textarea } from "@/components/ui";
import type { AnswerCitation, AnswerResponse } from "@/types/answer";
import type { SearchMode } from "@/types/search";
import { clearRagSession, loadRagSession, saveRagSession } from "@/utils/ragSessionCache";
import { formatScore } from "@/utils/format";
import styles from "./AnswerPage.module.css";

const MODE_LABEL: Record<SearchMode, string> = {
  vector: "의미 검색",
  keyword: "키워드 검색",
  hybrid: "하이브리드 검색",
};

export function AnswerPage() {
  const [query, setQuery] = useState("");
  const [searchMode, setSearchMode] = useState<SearchMode>("vector");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [data, setData] = useState<AnswerResponse | null>(null);

  useEffect(() => {
    const s = loadRagSession();
    if (s) {
      setQuery(s.query);
      setSearchMode(s.searchMode);
      setData(s.data);
    }
  }, []);

  useEffect(() => {
    if (data) saveRagSession({ query, searchMode, data });
  }, [data, query, searchMode]);

  function onClearSession() {
    clearRagSession();
    setData(null);
    setError("");
  }

  async function onAsk(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await answerApi.answerRequest({
        query: query.trim(),
        search_mode: searchMode,
      });
      setData(res);
    } catch (err) {
      setError(getApiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  const insufficient = (data?.answer ?? "").includes("제공된 문서만으로는 답변하기 어렵습니다.");

  return (
    <div className={styles.wrap}>
      <PageHeader
        title="AI 질문"
        description="검색된 문서를 근거로 AI가 답변합니다."
      />

      <div className="card">
        <form onSubmit={onAsk}>
          <div className={styles.formRow}>
            <Textarea
              style={{ flex: "1 1 280px", minWidth: 0 }}
              placeholder="예: 나주 관련 문서에서 투입 기간은 어떻게 되나요?"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            <div className={styles.controls}>
              <Select
                value={searchMode}
                onChange={(e) => setSearchMode(e.target.value as SearchMode)}
                aria-label="검색 모드"
              >
                <option value="vector">vector — 의미 검색</option>
                <option value="keyword">keyword — 키워드 검색</option>
                <option value="hybrid">hybrid — 하이브리드</option>
              </Select>
            </div>
          </div>
          <div className={styles.infoCallout}>
            <span className={styles.infoIcon} aria-hidden>
              i
            </span>
            <span>
              답변은 인덱싱된 사내 문서만을 근거로 합니다. 근거가 부족하면 답변이 제한될 수 있습니다. 미리보기에서
              돌아올 때는 상단 링크 또는 브라우저 뒤로 가기를 사용하세요.
            </span>
          </div>
          <div className={styles.formFooter}>
            {data && (
              <Button type="button" variant="secondary" size="sm" onClick={onClearSession}>
                결과 지우기
              </Button>
            )}
            <Button type="submit" variant="primary" loading={loading}>
              질문하기
            </Button>
          </div>
        </form>
        <ErrorMessage message={error} />
      </div>

      {data && (
        <>
          <SectionCard title="답변">
            <div className={styles.answerBanner}>
              <Badge variant="primary">문서 근거 기반 답변</Badge>
              <span className="muted" style={{ fontSize: "0.8rem" }}>
                모드 {MODE_LABEL[data.search_mode]} · {data.model ?? "모델 정보 없음"}
              </span>
            </div>
            {insufficient && (
              <div className="alert alertWarning" style={{ marginBottom: "0.75rem" }}>
                근거가 충분하지 않아 답변이 제한되었을 수 있습니다. 아래 citations를 함께 확인하세요.
              </div>
            )}
            <p className={styles.answerBody}>{data.answer ?? data.message}</p>
          </SectionCard>

          <SectionCard title="근거 (citations)">
            {data.citations.length === 0 ? (
              <EmptyState title="근거 조각이 없습니다" description="검색 결과가 없거나 컨텍스트 한도에 걸렸을 수 있습니다." />
            ) : (
              <DataTable>
                <thead>
                  <tr>
                    <th>파일</th>
                    <th>경로</th>
                    <th>소스</th>
                    <th>점수</th>
                    <th>라인</th>
                    <th>snippet</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {data.citations.map((c: AnswerCitation) => (
                    <tr key={`${c.chunk_id}-${c.rank}`}>
                      <td>{c.filename ?? "—"}</td>
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
            )}
          </SectionCard>
        </>
      )}
    </div>
  );
}
