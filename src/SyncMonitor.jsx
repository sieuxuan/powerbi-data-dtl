import { useEffect, useRef, useState } from "react";
import { Activity, AlertCircle, ChevronDown, Pencil, Play, RefreshCcw } from "lucide-react";

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
    mismatch: "Lệch cấu trúc",
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
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), options.timeoutMs || 30000);
  let response;
  try {
    response = await fetch(`${SYNC_API_URL}${path}`, {
      ...options,
      signal: options.signal || controller.signal,
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {}),
      },
    });
  } catch (error) {
    const reason = error?.name === "AbortError" ? "quá thời gian chờ" : error?.message;
    throw new Error(`Không gọi được Sync API tại ${SYNC_API_URL}${reason ? ` (${reason})` : ""}. Kiểm tra run.bat/run.ps1 và thử tải lại trang.`);
  } finally {
    window.clearTimeout(timeout);
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
  const [health, setHealth] = useState(null);
  const [openRunDrop, setOpenRunDrop] = useState(null);
  const [openAllDrop, setOpenAllDrop] = useState(false);
  const allDropRef = useRef(null);

  const runningCount = jobs.filter((job) => job.running).length;
  const latestSuccess = logs.filter((row) => row.status === "success").length;
  const latestFailures = logs.filter((row) => row.status === "failed").length;
  const scheduler = health?.scheduler;
  const schedulerOffline = !isOffline && scheduler && !scheduler.running;

  useEffect(() => {
    function handleClick(event) {
      if (allDropRef.current && !allDropRef.current.contains(event.target)) setOpenAllDrop(false);
      setOpenRunDrop(null);
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

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
      const [jobsData, logsData, healthData] = await Promise.all([
        syncApi("/api/jobs"),
        syncApi("/api/logs?limit=100"),
        syncApi("/api/health"),
      ]);
      if (!isMountedRef.current) return;
      setJobs(jobsData.jobs || []);
      setLogs(logsData.logs || []);
      setHealth(healthData);
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
        <div className="topbarMeta">
          <h2>Giám sát đồng bộ</h2>
          <p className="metaLine">{jobs.length} tác vụ · {runningCount} đang chạy · {logs.length} lần ghi gần nhất</p>
        </div>
        <div className="actions">
          <button type="button" className="btn" onClick={() => refreshSyncData()}>
            <RefreshCcw size={15} aria-hidden="true" />
            Tải lại
          </button>
          <div className="splitBtn primary" ref={allDropRef} style={{ position: "relative" }}>
            <button type="button" className="splitMain" onClick={() => triggerRunAll(false)}>
              <Play size={15} aria-hidden="true" />
              Đồng bộ tất cả
            </button>
            <button
              type="button"
              className="splitArrow"
              aria-label="Thêm tùy chọn đồng bộ"
              onClick={() => setOpenAllDrop((value) => !value)}
            >
              <ChevronDown size={13} aria-hidden="true" />
            </button>
            {openAllDrop && (
              <div className="dropdown">
                <button type="button" onClick={() => { triggerRunAll(true); setOpenAllDrop(false); }}>
                  <Play size={14} aria-hidden="true" />
                  Bắt buộc đồng bộ lại
                </button>
              </div>
            )}
          </div>
        </div>
      </header>

      {isOffline && (
        <div className="syncBanner error">
          <AlertCircle size={18} aria-hidden="true" />
          <span>{message || "Không kết nối được dịch vụ đồng bộ."}</span>
        </div>
      )}

      {schedulerOffline && (
        <div className="syncBanner warning">
          <AlertCircle size={18} aria-hidden="true" />
          <span>Dịch vụ đang chạy nhưng bộ hẹn lịch chưa bật. Mở ứng dụng bằng run.bat/run.ps1 để các tác vụ tự chạy theo lịch.</span>
        </div>
      )}

      {!isOffline && message && (
        <div className="syncBanner">
          <Activity size={18} aria-hidden="true" />
          <span>{message}</span>
        </div>
      )}

      <div className="syncMetrics">
        <div className="metricCard">
          <div className="metricLabel">Tác vụ</div>
          <div className="metricValue">{jobs.length}</div>
        </div>
        <div className={`metricCard${runningCount > 0 ? " running" : ""}`}>
          <div className="metricLabel">Đang chạy</div>
          <div className="metricValue">
            {runningCount}
            {runningCount > 0 && <span className="pulseDot" />}
          </div>
        </div>
        <div className="metricCard ok">
          <div className="metricLabel">Thành công</div>
          <div className="metricValue">{latestSuccess}</div>
        </div>
        <div className={`metricCard${latestFailures > 0 ? " alert" : ""}`}>
          <div className="metricLabel">Lỗi</div>
          <div className="metricValue">{latestFailures}</div>
        </div>
      </div>

      <section className="tablePanel syncTable">
        <table>
          <thead>
            <tr>
              <th>Tác vụ</th>
              <th>Nguồn</th>
              <th>Bảng dữ liệu</th>
              <th>Lịch chạy</th>
              <th>Trạng thái</th>
              <th>Số dòng</th>
              <th>Hoàn tất lúc</th>
              <th>Thao tác</th>
            </tr>
          </thead>
          <tbody>
            {jobs.length === 0 && (
              <tr>
                <td colSpan="8">{isLoading ? "Đang tải..." : "Chưa có tác vụ nào được cấu hình."}</td>
              </tr>
            )}
            {jobs.map((job) => {
              const latest = job.last_run || {};
              const statusClass = job.running ? "running" : (latest.status || "idle");
              const isDropOpen = openRunDrop === job.name;
              return (
                <tr key={job.name} className={`jobRow ${statusClass}`}>
                  <td>
                    <strong>{job.name}</strong>
                    {latest.error_message && <small className="errorText">{latest.error_message}</small>}
                  </td>
                  <td>{job.source_type}</td>
                  <td>{job.table}</td>
                  <td>{cronLabel(job)}</td>
                  <td>
                    <span className={`statusPill ${statusClass}`}>
                      {job.running
                        ? <><span className="pulseDot" />{progressLabel(job.progress?.state) || "Đang chạy"}</>
                        : syncStatusLabel(latest.status)}
                    </span>
                  </td>
                  <td>{latest.rows_imported ?? 0}</td>
                  <td>{formatSyncDate(latest.finished_at)}</td>
                  <td>
                    <div className="rowActions">
                      <div className="splitBtn" style={{ position: "relative" }}>
                        <button
                          type="button"
                          className="splitMain"
                          disabled={job.running}
                          onClick={() => triggerRunJob(job.name, false)}
                        >
                          <Play size={13} aria-hidden="true" />
                          Chạy
                        </button>
                        <button
                          type="button"
                          className="splitArrow"
                          disabled={job.running}
                          aria-label="Thêm tùy chọn chạy"
                          onMouseDown={(event) => event.stopPropagation()}
                          onClick={() => setOpenRunDrop(isDropOpen ? null : job.name)}
                        >
                          <ChevronDown size={12} aria-hidden="true" />
                        </button>
                        {isDropOpen && (
                          <div className="dropdown">
                            <button
                              type="button"
                              onMouseDown={(event) => event.stopPropagation()}
                              onClick={() => { triggerRunJob(job.name, true); setOpenRunDrop(null); }}
                            >
                              <Play size={13} aria-hidden="true" />
                              Bắt buộc đồng bộ lại
                            </button>
                          </div>
                        )}
                      </div>
                      <button type="button" onClick={() => onEditJob?.(job.name)} title="Chỉnh sửa tác vụ">
                        <Pencil size={13} aria-hidden="true" />
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
              <th>Tác vụ</th>
              <th>Bảng dữ liệu</th>
              <th>Trạng thái</th>
              <th>Số dòng</th>
              <th>Thông tin</th>
            </tr>
          </thead>
          <tbody>
            {logs.length === 0 && (
              <tr>
                <td colSpan="6">{isLoading ? "Đang tải..." : "Chưa có lịch sử đồng bộ."}</td>
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
