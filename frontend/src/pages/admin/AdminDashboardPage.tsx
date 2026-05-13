import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getApiErrorMessage } from "@/api/httpClient";
import * as adminApi from "@/api/adminApi";
import { EmptyState } from "@/components/EmptyState";
import { ErrorMessage } from "@/components/ErrorMessage";
import { Loading } from "@/components/Loading";
import {
  Badge,
  Button,
  Card,
  DataTable,
  PageHeader,
  SectionCard,
  StatCard,
  type BadgeVariant,
} from "@/components/ui";
import type { DashboardSummaryResponse } from "@/types/adminDashboard";
import { formatDateTime, formatInt } from "@/utils/format";
import styles from "./AdminDashboardPage.module.css";

const quickLinks = [
  { to: "/admin/data-sources", title: "데이터 소스 설정", desc: "WebDAV 소스 등록·접속 테스트" },
  {
    to: "/admin/data-sources",
    title: "문서 파일 처리",
    desc: "PDF/DOCX/XLSX/PPTX/HWPX 문서를 검색 대상으로 변환합니다. 데이터 소스별로 실행합니다.",
  },
  { to: "/admin/file-stats", title: "파일 현황 분석", desc: "상태·유형·확장자·대용량 파일" },
  { to: "/admin/users", title: "사용자 관리", desc: "승인·잠금·역할" },
  { to: "/admin/action-logs", title: "작업 로그", desc: "감사 로그 조회" },
];

function scanJobStatusVariant(s: string): BadgeVariant {
  switch (s) {
    case "COMPLETED":
      return "success";
    case "RUNNING":
      return "primary";
    case "FAILED":
      return "danger";
    case "PENDING":
      return "warning";
    case "STOPPED":
      return "neutral";
    default:
      return "neutral";
  }
}

function actionResultVariant(r: string): BadgeVariant {
  if (r === "SUCCESS") return "success";
  if (r === "FAIL") return "danger";
  return "neutral";
}

export function AdminDashboardPage() {
  const [data, setData] = useState<DashboardSummaryResponse | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  async function load(isRefresh: boolean) {
    setError("");
    if (isRefresh) setRefreshing(true);
    else setLoading(true);
    try {
      const res = await adminApi.getDashboardSummary();
      setData(res);
    } catch (e) {
      setError(getApiErrorMessage(e));
      if (!isRefresh) setData(null);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }

  useEffect(() => {
    void load(false);
  }, []);

  const s = data?.summary;
  const p = data?.problem_items;

  if (loading && !data) return <Loading />;

  return (
    <div>
      <PageHeader
        title="관리자 대시보드"
        description="시스템 수집/분석/검색 상태를 한눈에 확인합니다. (GET /api/admin/dashboard/summary)"
        actions={
          <Button type="button" variant="secondary" size="sm" onClick={() => void load(true)} disabled={refreshing || loading}>
            새로고침
          </Button>
        }
      />
      <ErrorMessage message={error} />
      {!loading && !data && error && (
        <p style={{ marginBottom: "1rem" }}>
          <Button type="button" variant="primary" size="sm" onClick={() => void load(false)}>
            다시 시도
          </Button>
        </p>
      )}

      {refreshing && data && <p className="muted">불러오는 중…</p>}

      {s && (
        <div className={styles.sectionStack}>
          <SectionCard title="사용자">
            <div className={styles.statGrid}>
              <StatCard label="전체 사용자" value={formatInt(s.users.total)} />
              <StatCard label="승인 대기" value={formatInt(s.users.pending)} />
              <StatCard label="활성" value={formatInt(s.users.active)} />
              <StatCard label="비활성" value={formatInt(s.users.inactive)} />
              <StatCard label="잠금" value={formatInt(s.users.locked)} />
              <StatCard label="관리자 수" value={formatInt(s.users.admins)} />
            </div>
          </SectionCard>

          <SectionCard title="데이터 소스">
            <div className={styles.statGrid}>
              <StatCard label="전체" value={formatInt(s.data_sources.total)} />
              <StatCard label="활성" value={formatInt(s.data_sources.active)} />
              <StatCard label="비활성" value={formatInt(s.data_sources.inactive)} />
              <StatCard label="접속 성공" value={formatInt(s.data_sources.connection_success)} />
              <StatCard label="접속 실패" value={formatInt(s.data_sources.connection_failed)} />
              <StatCard label="미테스트" value={formatInt(s.data_sources.never_tested)} />
            </div>
          </SectionCard>

          <SectionCard title="파일 분석">
            <div className={styles.statGrid}>
              <StatCard label="전체 항목" value={formatInt(s.files.total_items)} />
              <StatCard label="파일" value={formatInt(s.files.total_files)} />
              <StatCard label="디렉터리" value={formatInt(s.files.total_directories)} />
              <StatCard label="총 용량" value={s.files.total_size_human} hint={formatInt(s.files.total_size_bytes) + " bytes"} />
              <StatCard label="완료" value={formatInt(s.files.completed)} />
              <StatCard label="대기" value={formatInt(s.files.pending)} />
              <StatCard label="실패" value={formatInt(s.files.failed)} />
              <StatCard label="스킵" value={formatInt(s.files.skipped)} />
              <StatCard label="삭제 표시" value={formatInt(s.files.deleted)} />
            </div>
          </SectionCard>

          <SectionCard title="Chunk / Embedding">
            <div className={styles.statGrid}>
              <StatCard label="전체 chunk" value={formatInt(s.chunks.total_chunks)} />
              <StatCard label="embedding 완료" value={formatInt(s.chunks.embedded_chunks)} />
              <StatCard label="embedding 대기" value={formatInt(s.chunks.pending_embedding_chunks)} />
            </div>
          </SectionCard>

          <SectionCard title="최근 24시간 활동">
            <div className={styles.statGrid}>
              <StatCard label="검색" value={formatInt(s.activity.search_count_24h)} />
              <StatCard label="AI 질문" value={formatInt(s.activity.rag_count_24h)} />
              <StatCard label="로그인" value={formatInt(s.activity.login_count_24h)} />
              <StatCard label="실패 작업" value={formatInt(s.activity.failed_action_count_24h)} />
            </div>
          </SectionCard>

          {p && (
            <SectionCard title="점검·조치 항목">
              <div className={styles.problemGrid}>
                <div className={styles.problemItem}>
                  <span className={styles.problemLabel}>승인 대기 사용자</span>
                  <strong>{formatInt(p.pending_users_count)}</strong>
                  <Link to="/admin/users" className="btn btnSecondary btnSm">
                    사용자 관리
                  </Link>
                </div>
                <div className={styles.problemItem}>
                  <span className={styles.problemLabel}>실패 파일</span>
                  <strong>{formatInt(p.failed_files_count)}</strong>
                  <Link to="/admin/file-stats" className="btn btnSecondary btnSm">
                    파일 통계
                  </Link>
                </div>
                <div className={styles.problemItem}>
                  <span className={styles.problemLabel}>처리 대기 파일</span>
                  <strong>{formatInt(p.pending_files_count)}</strong>
                  <Link to="/admin/file-stats" className="btn btnSecondary btnSm">
                    파일 통계
                  </Link>
                </div>
                <div className={styles.problemItem}>
                  <span className={styles.problemLabel}>임베딩 대기 chunk</span>
                  <strong>{formatInt(p.pending_embedding_chunks_count)}</strong>
                  <Link to="/admin/file-stats" className="btn btnSecondary btnSm">
                    파일 통계
                  </Link>
                </div>
                <div className={styles.problemItem}>
                  <span className={styles.problemLabel}>비활성 데이터 소스</span>
                  <strong>{formatInt(p.inactive_data_sources_count)}</strong>
                  <Link to="/admin/data-sources" className="btn btnSecondary btnSm">
                    데이터 소스
                  </Link>
                </div>
                <div className={styles.problemItem}>
                  <span className={styles.problemLabel}>24h 실패 작업</span>
                  <strong>{formatInt(s.activity.failed_action_count_24h)}</strong>
                  <Link to="/admin/action-logs" className="btn btnSecondary btnSm">
                    작업 로그
                  </Link>
                </div>
              </div>
            </SectionCard>
          )}

          <SectionCard title="최근 스캔 작업">
            {!data?.recent_scan_jobs?.length ? (
              <EmptyState title="스캔 작업 이력이 없습니다" description="동기화·청크·임베딩 작업이 실행되면 여기에 표시됩니다." />
            ) : (
              <DataTable>
                <thead>
                  <tr>
                    <th>소스</th>
                    <th>유형</th>
                    <th>상태</th>
                    <th>진행</th>
                    <th>실패</th>
                    <th>시작</th>
                    <th>종료</th>
                  </tr>
                </thead>
                <tbody>
                  {data.recent_scan_jobs.map((j) => (
                    <tr key={j.id}>
                      <td>{j.data_source_name ?? "—"}</td>
                      <td>
                        <Badge variant="neutral">{j.job_type}</Badge>
                      </td>
                      <td>
                        <Badge variant={scanJobStatusVariant(j.status)}>{j.status}</Badge>
                      </td>
                      <td>
                        {formatInt(j.processed_files)} / {formatInt(j.total_files)}
                      </td>
                      <td>{formatInt(j.failed_files)}</td>
                      <td>{formatDateTime(j.started_at)}</td>
                      <td>{formatDateTime(j.finished_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </DataTable>
            )}
          </SectionCard>

          <SectionCard title="최근 활동 (감사 로그)">
            {!data?.recent_actions?.length ? (
              <EmptyState title="최근 활동이 없습니다" description="검색·로그인 등이 기록되면 표시됩니다." />
            ) : (
              <DataTable>
                <thead>
                  <tr>
                    <th>시각</th>
                    <th>사용자</th>
                    <th>유형</th>
                    <th>결과</th>
                    <th>검색어</th>
                  </tr>
                </thead>
                <tbody>
                  {data.recent_actions.map((a) => (
                    <tr key={a.id}>
                      <td>{formatDateTime(a.created_at)}</td>
                      <td>{a.user_name ?? "—"}</td>
                      <td>
                        <Badge variant="neutral">{a.action_type}</Badge>
                      </td>
                      <td>
                        <Badge variant={actionResultVariant(a.result)}>{a.result}</Badge>
                      </td>
                      <td className="snippet">{a.search_query ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </DataTable>
            )}
          </SectionCard>
        </div>
      )}

      <h2 className={styles.sectionTitle}>바로 가기</h2>
      <div className={styles.linkGrid}>
        {quickLinks.map((l) => (
          <Link key={l.to} to={l.to} className={styles.quickLink}>
            <Card flat noMargin className={styles.quickCard}>
              <h3 className={styles.quickTitle}>{l.title}</h3>
              <p className={styles.quickDesc}>{l.desc}</p>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}
