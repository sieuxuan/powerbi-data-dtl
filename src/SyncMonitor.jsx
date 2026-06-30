import { useEffect, useRef, useState } from "react";
import { Activity, AlertCircle, Pencil, Play, RefreshCcw } from "lucide-react";

export const SYNC_API_URL = import.meta.env.VITE_SYNC_API_URL || "http://127.0.0.1:8765";

function formatDateTime(value) {
  return new Intl.DateTimeFormat("vi-VN", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(new Date(value));
}

function formatSyncDate(value) {
  if (!value) return "Chưa chạy";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Không rõ";
  return formatDateTime(date);
}

function syncStatusLabel(status) {
  const labels = {
    success: "Thành công",
    failed: "Lỗi",
    skipped: "Bỏ qua",
    mismatch: "Lệch schema",
  };
  return labels[status] || status || "Chưa chạy";
}

function progressLabel(state) {
  const labels = {
    starting: "Bắt đầu",
    resolving: "Tìm file",
    downloading: "Tải file",
    hashing: "Tính hash",
    reading: "Đọc file",
    validating: "Kiểm tra",
    importing: "Import",
    done: "Hoàn tất",
  };
  return labels[state] || state || "";
}

function cronLabel(job) {
  const crons = Array.isArray(job.crons) && job.crons.length ? job.crons : [job.cron].filter(Boolean);
  if (crons.length > 1) return `${crons.length} lịch: ${crons.join(" · ")}`;
  return crons[0] || "-";
}

export async function syncApi(path, options = {}) {
  let response;
  try {
    response = await fetch(`${SYNC_API_URL}${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {}),
      },
    });
  } catch (error) {
    throw new Error(`Sync API đang tắt hoặc bị chặn tại ${SYNC_API_URL}. Chạy run.bat hoặc run.ps1 rồi thử lại.`);
  }
  if (!response.ok) {
    const text = await response.text();
    let message = text;
    try {
      const parsed = JSON.parse(text);
      message = parsed.detail || parsed.message || text;
    } catch {
      message = text;
    }
    throw new Error(message || `HTTP ${response.status}`);
  }
  return response.json();
}

export default function SyncMonitor({ onEditJob }) {
  const isMountedRef = useRef(true);
  const [jobs, setJobs] = useState([]);
  const [logs, setLogs] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isOffline, setIsOffline] = useState(false);
  const [message, setMessage] = useState("");

  const runningCount = jobs.filter((job) => job.running).length;
  const latestSuccess = logs.filter((row) => row.status === "success").length;
  const latestFailures = logs.filter((row) => row.status === "failed").length;

  useEffect(() => {
    isMountedRef.current = true;
    refreshSyncData();
    const timer = setInterval(refreshSyncData, 7000);
    return () => {
      isMountedRef.current = false;
      clearInterval(timer);
    };
  }, []);

  async function refreshSyncData() {
    setIsLoading(true);
    try {
      const [jobsData, logsData] = await Promise.all([
        syncApi("/api/jobs"),
        syncApi("/api/logs?limit=100"),
      ]);
      if (!isMountedRef.current) return;
      setJobs(jobsData.jobs || []);
      setLogs(logsData.logs || []);
      setIsOffline(false);
      setMessage("");
    } catch (error) {
      if (!isMountedRef.current) return;
      setIsOffline(true);
      setMessage(`Không kết nối được Sync API: ${error.message}`);
    } finally {
      if (isMountedRef.current) setIsLoading(false);
    }
  }

  async function triggerRunAll(force = false) {
    try {
      const result = await syncApi(`/api/run-all?force=${force ? "true" : "false"}`, { method: "POST" });
      setMessage(result.status === "accepted" ? "Đã gửi lệnh chạy tất cả job." : "Đang có job chạy, lệnh mới được bỏ qua.");
      await refreshSyncData();
    } catch (error) {
      setIsOffline(true);
      setMessage(`Không gửi được lệnh: ${error.message}`);
    }
  }

  async function triggerRunJob(name, force = false) {
    try {
      const result = await syncApi(`/api/jobs/${encodeURIComponent(name)}/run?force=${force ? "true" : "false"}`, { method: "POST" });
      setMessage(result.status === "accepted" ? `Đã gửi lệnh chạy ${name}.` : `${name} đang chạy.`);
      await refreshSyncData();
    } catch (error) {
      setIsOffline(true);
      setMessage(`Không gửi được lệnh: ${error.message}`);
    }
  }

  return (
    <>
      <header className="topbar">
        <div>
          <h2>Sync Monitor</h2>
          <p className="meta">{jobs.length} job cấu hình, {runningCount} đang chạy, {logs.length} log gần nhất</p>
        </div>
        <div className="actions">
          <button type="button" onClick={() => refreshSyncData()}>
            <RefreshCcw size={17} aria-hidden="true" />
            Tải lại
          </button>
          <button type="button" onClick={() => triggerRunAll(false)}>
            <Play size={17} aria-hidden="true" />
            Chạy tất cả
          </button>
          <button type="button" className="primary" title="Chạy lại kể cả khi file chưa thay đổi hash" onClick={() => triggerRunAll(true)}>
            <Play size={17} aria-hidden="true" />
            Chạy lại bỏ qua hash
          </button>
        </div>
      </header>

      {isOffline && (
        <div className="syncBanner error">
          <AlertCircle size={18} aria-hidden="true" />
          <span>{message || "Sync API đang offline."}</span>
        </div>
      )}

      {!isOffline && message && (
        <div className="syncBanner">
          <Activity size={18} aria-hidden="true" />
          <span>{message}</span>
        </div>
      )}

      <div className="syncMetrics">
        <div>
          <span>Jobs</span>
          <strong>{jobs.length}</strong>
        </div>
        <div>
          <span>Đang chạy</span>
          <strong>{runningCount}</strong>
        </div>
        <div>
          <span>Log thành công</span>
          <strong>{latestSuccess}</strong>
        </div>
        <div>
          <span>Log lỗi</span>
          <strong>{latestFailures}</strong>
        </div>
      </div>

      <section className="tablePanel syncTable">
        <table>
          <thead>
            <tr>
              <th>Job</th>
              <th>Nguồn</th>
              <th>Bảng</th>
              <th>Cron</th>
              <th>Trạng thái</th>
              <th>Dòng</th>
              <th>Hoàn tất</th>
              <th>Hash</th>
              <th>Thao tác</th>
            </tr>
          </thead>
          <tbody>
            {jobs.length === 0 && (
              <tr>
                <td colSpan="9">{isLoading ? "Đang tải job..." : "Chưa có job nào trong config."}</td>
              </tr>
            )}
            {jobs.map((job) => {
              const latest = job.last_run || {};
              return (
                <tr key={job.name}>
                  <td>
                    <strong>{job.name}</strong>
                    {latest.error_message && <small className="errorText">{latest.error_message}</small>}
                  </td>
                  <td>{job.source_type}</td>
                  <td>{job.table}</td>
                  <td>{cronLabel(job)}</td>
                  <td>
                    <span className={`statusPill ${latest.status || "idle"}`}>
                      {job.running ? progressLabel(job.progress?.state) || "Đang chạy" : syncStatusLabel(latest.status)}
                    </span>
                  </td>
                  <td>{latest.rows_imported ?? 0}</td>
                  <td>{formatSyncDate(latest.finished_at)}</td>
                  <td className="hashCell">{latest.file_hash || "-"}</td>
                  <td>
                    <div className="rowActions">
                      <button type="button" onClick={() => triggerRunJob(job.name, false)} disabled={job.running}>
                        <Play size={15} aria-hidden="true" />
                      </button>
                      <button type="button" onClick={() => triggerRunJob(job.name, true)} disabled={job.running}>
                        Force
                      </button>
                      <button type="button" onClick={() => onEditJob?.(job.name)} title="Sửa job">
                        <Pencil size={15} aria-hidden="true" />
                        Sửa
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>

      <section className="tablePanel syncTable logsTable">
        <table>
          <thead>
            <tr>
              <th>Thời gian</th>
              <th>Job</th>
              <th>Bảng</th>
              <th>Trạng thái</th>
              <th>Dòng</th>
              <th>Thông điệp</th>
            </tr>
          </thead>
          <tbody>
            {logs.length === 0 && (
              <tr>
                <td colSpan="6">{isLoading ? "Đang tải log..." : "Chưa có log đồng bộ."}</td>
              </tr>
            )}
            {logs.map((row) => (
              <tr key={row.id}>
                <td>{formatSyncDate(row.started_at)}</td>
                <td>{row.job_name}</td>
                <td>{row.table_name}</td>
                <td><span className={`statusPill ${row.status}`}>{syncStatusLabel(row.status)}</span></td>
                <td>{row.rows_imported ?? 0}</td>
                <td>{row.error_message || row.details?.reason || "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </>
  );
}
