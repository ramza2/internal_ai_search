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
import {
  getJobStatusBadgeVariant,
  getJobStatusLabel,
  getJobTypeLabel,
  getPipelineStepLabel,
} from "@/utils/userFriendlyLabels";
import styles from "./AdminDashboardPage.module.css";

const quickLinks = [
  { to: "/admin/data-sources", title: "저장소 설정", desc: "WebDAV 저장소 등록·접속 확인" },
  {
    to: "/admin/data-sources",
    title: "검색 반영 실행",
    desc: "저장소별로 파일 수집·내용 추출·검색 인덱스까지 한 번에 실행합니다.",
  },
  { to: "/admin/jobs", title: "작업 목록", desc: "수집·추출·검색 반영 작업의 진행 상태와 실패 내역" },
  { to: "/admin/file-stats", title: "파일 현황", desc: "상태·유형·확장자·대용량 파일" },
  { to: "/admin/users", title: "사용자 관리", desc: "승인·잠금·역할" },
  { to: "/admin/action-logs", title: "활동 기록", desc: "검색·로그인 등 감사 로그" },
];

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
        description="사용자·저장소·파일 처리·검색 반영·최근 작업 현황을 한눈에 확인합니다."
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
              <StatCard label="승인 대기 사용자" value={formatInt(s.users.pending)} />
              <StatCard label="활성" value={formatInt(s.users.active)} />
              <StatCard label="비활성" value={formatInt(s.users.inactive)} />
              <StatCard label="잠금" value={formatInt(s.users.locked)} />
              <StatCard label="관리자 수" value={formatInt(s.users.admins)} />
            </div>
          </SectionCard>

          <SectionCard title="저장소">
            <div className={styles.statGrid}>
              <StatCard label="등록된 저장소" value={formatInt(s.data_sources.total)} />
              <StatCard label="사용 중" value={formatInt(s.data_sources.active)} />
              <StatCard label="사용 중지" value={formatInt(s.data_sources.inactive)} />
              <StatCard label="접속 확인 성공" value={formatInt(s.data_sources.connection_success)} />
              <StatCard label="접속 확인 실패" value={formatInt(s.data_sources.connection_failed)} />
              <StatCard label="미확인" value={formatInt(s.data_sources.never_tested)} />
            </div>
          </SectionCard>

          <SectionCard title="파일 수집·내용 추출 현황">
            <div className={styles.statGrid}>
              <StatCard label="전체 항목" value={formatInt(s.files.total_items)} />
              <StatCard label="파일" value={formatInt(s.files.total_files)} />
              <StatCard label="폴더" value={formatInt(s.files.total_directories)} />
              <StatCard label="총 용량" value={s.files.total_size_human} />
              <StatCard label="처리 완료" value={formatInt(s.files.completed)} />
              <StatCard label="처리 대기" value={formatInt(s.files.pending)} />
              <StatCard label="처리 실패" value={formatInt(s.files.failed)} />
              <StatCard label="건너뜀" value={formatInt(s.files.skipped)} />
            </div>
          </SectionCard>

          <SectionCard title="검색 반영 현황">
            <div className={styles.statGrid}>
              <StatCard label="검색 단위(전체)" value={formatInt(s.chunks.total_chunks)} />
              <StatCard label="검색 인덱스 완료" value={formatInt(s.chunks.embedded_chunks)} />
              <StatCard label="검색 인덱스 생성 대기" value={formatInt(s.chunks.pending_embedding_chunks)} />
            </div>
          </SectionCard>

          <SectionCard title="최근 24시간 활동">
            <div className={styles.statGrid}>
              <StatCard label="검색" value={formatInt(s.activity.search_count_24h)} />
              <StatCard label="AI 질문" value={formatInt(s.activity.rag_count_24h)} />
              <StatCard label="로그인" value={formatInt(s.activity.login_count_24h)} />
              <StatCard label="실패한 활동" value={formatInt(s.activity.failed_action_count_24h)} />
            </div>
          </SectionCard>

          <SectionCard title="전체 검색 반영 작업">
            <div className={styles.statGrid}>
              <StatCard label="진행 중" value={formatInt(data?.pipelines?.running ?? 0)} />
              <StatCard label="대기 중" value={formatInt(data?.pipelines?.pending ?? 0)} />
              <StatCard label="24시간 내 실패" value={formatInt(data?.pipelines?.failed_24h ?? 0)} />
              <StatCard label="24시간 내 완료" value={formatInt(data?.pipelines?.completed_24h ?? 0)} />
            </div>
            <p className="muted" style={{ marginTop: "0.5rem", fontSize: "0.82rem" }}>
              단계별 진행률·상세는 <Link to="/admin/jobs">작업 목록</Link>에서 확인할 수 있습니다.
            </p>
            {!data?.recent_pipeline_jobs?.length ? (
              <p className="muted" style={{ marginTop: "0.65rem", fontSize: "0.85rem" }}>
                최근 전체 검색 반영 작업이 없습니다.
              </p>
            ) : (
              <DataTable>
                <thead>
                  <tr>
                    <th>저장소</th>
                    <th>상태</th>
                    <th>진행률</th>
                    <th>현재 단계</th>
                    <th>시작 시간</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {data.recent_pipeline_jobs.map((j) => (
                    <tr key={j.id}>
                      <td>{j.data_source_name ?? "—"}</td>
                      <td>
                        <Badge variant={getJobStatusBadgeVariant(j.status)}>{getJobStatusLabel(j.status)}</Badge>
                      </td>
                      <td>{formatInt(Math.round(j.progress_percent))}%</td>
                      <td className="snippet">{getPipelineStepLabel(j.current_step)}</td>
                      <td>{formatDateTime(j.started_at)}</td>
                      <td>
                        <Link to="/admin/jobs" className="btn btnSecondary btnSm">
                          상세 보기
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </DataTable>
            )}
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
                  <span className={styles.problemLabel}>처리 실패 파일</span>
                  <strong>{formatInt(p.failed_files_count)}</strong>
                  <Link to="/admin/file-stats" className="btn btnSecondary btnSm">
                    파일 현황
                  </Link>
                </div>
                <div className={styles.problemItem}>
                  <span className={styles.problemLabel}>처리 대기 파일</span>
                  <strong>{formatInt(p.pending_files_count)}</strong>
                  <Link to="/admin/file-stats" className="btn btnSecondary btnSm">
                    파일 현황
                  </Link>
                </div>
                <div className={styles.problemItem}>
                  <span className={styles.problemLabel}>검색 인덱스 생성 대기</span>
                  <strong>{formatInt(p.pending_embedding_chunks_count)}</strong>
                  <Link to="/admin/file-stats" className="btn btnSecondary btnSm">
                    파일 현황
                  </Link>
                </div>
                <div className={styles.problemItem}>
                  <span className={styles.problemLabel}>사용 중지된 저장소</span>
                  <strong>{formatInt(p.inactive_data_sources_count)}</strong>
                  <Link to="/admin/data-sources" className="btn btnSecondary btnSm">
                    저장소 설정
                  </Link>
                </div>
                <div className={styles.problemItem}>
                  <span className={styles.problemLabel}>24시간 내 실패 활동</span>
                  <strong>{formatInt(s.activity.failed_action_count_24h)}</strong>
                  <Link to="/admin/action-logs" className="btn btnSecondary btnSm">
                    활동 기록
                  </Link>
                </div>
              </div>
            </SectionCard>
          )}

          <SectionCard title="최근 작업">
            {!data?.recent_scan_jobs?.length ? (
              <EmptyState title="최근 작업이 없습니다" description="파일 수집·추출·검색 반영 작업이 실행되면 여기에 표시됩니다." />
            ) : (
              <DataTable>
                <thead>
                  <tr>
                    <th>저장소</th>
                    <th>작업 종류</th>
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
                        <div>{getJobTypeLabel(j.job_type)}</div>
                        <div className="muted" style={{ fontSize: "0.7rem" }} title={j.job_type}>
                          {j.job_type}
                        </div>
                      </td>
                      <td>
                        <Badge variant={getJobStatusBadgeVariant(j.status)}>{getJobStatusLabel(j.status)}</Badge>
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

          <SectionCard title="최근 활동">
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
          <Link key={l.to + l.title} to={l.to} className={styles.quickLink}>
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
