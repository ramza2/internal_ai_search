import { Badge, DataTable } from "@/components/ui";
import { formatInt } from "@/utils/format";
import styles from "./PipelineResponseView.module.css";

const MAX_ROWS = 20;

function str(v: unknown): string {
  if (v == null) return "—";
  if (typeof v === "string" || typeof v === "number" || typeof v === "boolean") return String(v);
  return "—";
}

function num(v: unknown): string {
  if (typeof v === "number" && !Number.isNaN(v)) return formatInt(v);
  return "—";
}

function pickMessage(data: Record<string, unknown>): string {
  const m = data.message;
  if (typeof m === "string" && m.trim()) return m;
  const e = data.error;
  if (typeof e === "string" && e.trim()) return e;
  return "—";
}

function pickWarnings(data: Record<string, unknown>): string[] {
  const w = data.warnings;
  if (!Array.isArray(w)) return [];
  return w.filter((x): x is string => typeof x === "string");
}

export function PipelineResponseView({ data }: { data: Record<string, unknown> | null }) {
  if (!data) return null;

  const st = str(data.status);
  const warnings = pickWarnings(data);
  const itemsRaw = data.items;
  const items = Array.isArray(itemsRaw) ? (itemsRaw as Record<string, unknown>[]) : [];
  const shown = items.slice(0, MAX_ROWS);
  const rest = Math.max(0, items.length - shown.length);

  return (
    <div className={styles.wrap}>
      <p className={styles.message}>{pickMessage(data)}</p>
      <div className={styles.summaryGrid}>
        <div className={styles.cell}>
          status <Badge variant={st === "ok" || st === "partial" ? "success" : st === "error" ? "danger" : "neutral"}>{st}</Badge>
        </div>
        {"scan_job_id" in data && data.scan_job_id != null && (
          <div className={styles.cell}>
            scan_job <strong className={styles.mono}>{String(data.scan_job_id).slice(0, 10)}…</strong>
          </div>
        )}
        {"target_count" in data && <div className={styles.cell}>target <strong>{num(data.target_count)}</strong></div>}
        {"target_chunks_count" in data && (
          <div className={styles.cell}>
            target_chunks <strong>{num(data.target_chunks_count)}</strong>
          </div>
        )}
        {"processed_count" in data && <div className={styles.cell}>processed <strong>{num(data.processed_count)}</strong></div>}
        {"processed_chunks_count" in data && (
          <div className={styles.cell}>
            processed_chunks <strong>{num(data.processed_chunks_count)}</strong>
          </div>
        )}
        {"completed_count" in data && <div className={styles.cell}>completed <strong>{num(data.completed_count)}</strong></div>}
        {"chunked_files_count" in data && (
          <div className={styles.cell}>
            chunked_files <strong>{num(data.chunked_files_count)}</strong>
          </div>
        )}
        {"embedded_chunks_count" in data && (
          <div className={styles.cell}>
            embedded_chunks <strong>{num(data.embedded_chunks_count)}</strong>
          </div>
        )}
        {"skipped_count" in data && <div className={styles.cell}>skipped <strong>{num(data.skipped_count)}</strong></div>}
        {"failed_count" in data && <div className={styles.cell}>failed <strong>{num(data.failed_count)}</strong></div>}
        {"failed_chunks_count" in data && (
          <div className={styles.cell}>
            failed_chunks <strong>{num(data.failed_chunks_count)}</strong>
          </div>
        )}
        {"dry_run" in data && (
          <div className={styles.cell}>
            dry_run <strong>{data.dry_run ? "예" : "아니오"}</strong>
          </div>
        )}
        {"processed_items" in data && (
          <div className={styles.cell}>
            processed_items <strong>{num(data.processed_items)}</strong>
          </div>
        )}
      </div>
      {warnings.length > 0 && (
        <ul className={styles.warnings}>
          {warnings.map((w, i) => (
            <li key={i}>{w}</li>
          ))}
        </ul>
      )}
      {shown.length > 0 && (
        <>
          <DataTable>
            <thead>
              <tr>
                <th>파일명</th>
                <th>경로</th>
                <th>확장자</th>
                <th>상태</th>
                <th>reason</th>
                <th>기타</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((row, idx) => (
                <tr key={String(row.file_id ?? row.id ?? idx)}>
                  <td>{str(row.filename)}</td>
                  <td className="snippet">{str(row.remote_path)}</td>
                  <td>{str(row.extension)}</td>
                  <td>{str(row.status ?? row.planned_action)}</td>
                  <td>{str(row.reason)}</td>
                  <td className="snippet muted" style={{ fontSize: "0.75rem" }}>
                    {[
                      row.text_length != null ? `len=${row.text_length}` : "",
                      row.created_chunks != null ? `chunks=${row.created_chunks}` : "",
                      row.target_chunks != null ? `tgt=${row.target_chunks}` : "",
                      row.embedded_chunks != null ? `emb=${row.embedded_chunks}` : "",
                      row.failed_chunks != null ? `fail=${row.failed_chunks}` : "",
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </td>
                </tr>
              ))}
            </tbody>
          </DataTable>
          {rest > 0 && <p className="muted" style={{ marginTop: "0.35rem", fontSize: "0.85rem" }}>외 {rest}건은 생략했습니다.</p>}
        </>
      )}
    </div>
  );
}
