import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getApiErrorMessage } from "@/api/httpClient";
import * as fileApi from "@/api/fileApi";
import { ErrorMessage } from "@/components/ErrorMessage";
import { Loading } from "@/components/Loading";
import { Card, PageHeader, StatCard } from "@/components/ui";
import type { FileStatsResponse } from "@/types/file";
import { formatDateTime } from "@/utils/format";
import styles from "./AdminDashboardPage.module.css";

const quickLinks = [
  { to: "/admin/data-sources", title: "데이터 소스 설정", desc: "WebDAV 소스 등록·접속 테스트" },
  { to: "/admin/file-stats", title: "파일 현황 분석", desc: "상태·유형·확장자·대용량 파일" },
  { to: "/admin/users", title: "사용자 관리", desc: "승인·잠금·역할" },
  { to: "/admin/action-logs", title: "작업 로그", desc: "감사 로그 조회" },
];

export function AdminDashboardPage() {
  const [stats, setStats] = useState<FileStatsResponse | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError("");
      try {
        const res = await fileApi.getFileStats();
        if (!cancelled) setStats(res);
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

  const summary = stats?.summary;

  return (
    <div>
      <PageHeader
        title="관리자 대시보드"
        description="전체 파일 통계와 주요 관리 메뉴로 이동합니다. 지표는 GET /api/files/stats 기준입니다."
      />
      <ErrorMessage message={error} />
      {loading && <Loading />}

      {!loading && stats && summary && (
        <div className={styles.statGrid}>
          <StatCard label="전체 항목 (파일+디렉터리)" value={summary.total_items.toLocaleString("ko-KR")} />
          <StatCard label="파일 수" value={summary.total_files.toLocaleString("ko-KR")} />
          <StatCard label="디렉터리 수" value={summary.total_directories.toLocaleString("ko-KR")} />
          <StatCard
            label="총 용량"
            value={summary.total_size_human}
            hint={summary.last_synced_at ? `마지막 동기 ${formatDateTime(summary.last_synced_at)}` : undefined}
          />
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
