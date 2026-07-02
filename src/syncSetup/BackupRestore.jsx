import { Archive, FolderOpen, Save, UploadCloud } from "lucide-react";

export default function BackupRestore({
  pendingBundle,
  isImportingBundle,
  onExportBundle,
  onImportBundle,
  onOpenExports,
  onSetPendingBundle,
  onConfirmImportBundle,
}) {
  return (
    <section className="setupSection">
      <div className="sectionTitle">
        <Archive size={18} aria-hidden="true" />
        <h3>Backup & Restore</h3>
      </div>
      <div className="backupActions">
        <button type="button" className="secondaryButton" onClick={onExportBundle}>
          <Archive size={16} aria-hidden="true" />
          Export config bundle
        </button>
        <label className={`secondaryButton fileActionButton ${isImportingBundle ? "disabled" : ""}`}>
          <UploadCloud size={16} aria-hidden="true" />
          {isImportingBundle ? "Đang import" : "Import bundle zip"}
          <input
            type="file"
            accept=".zip,application/zip"
            disabled={isImportingBundle}
            onChange={(event) => onImportBundle(event.target.files?.[0])}
          />
        </label>
        <button type="button" className="secondaryButton" onClick={onOpenExports}>
          <FolderOpen size={16} aria-hidden="true" />
          Mở exports
        </button>
      </div>
      <p className="helperText">Bundle có thể thêm job vào cấu hình hiện tại hoặc ghi đè toàn bộ khi cần chuyển sang máy mới. Config cũ luôn được backup trước khi import.</p>
      {pendingBundle && (
        <div className="bundlePreview">
          <strong>{pendingBundle.fileName}</strong>
          <span>Config: {pendingBundle.preview.has_config ? "có" : "không"} · .env: {pendingBundle.preview.has_env ? "có" : "không"} · Uploads: {pendingBundle.preview.uploads_count || 0} · Jobs: {pendingBundle.preview.jobs_count ?? "?"}</span>
          {pendingBundle.preview.job_names?.length > 0 && (
            <small>Job trong bundle: {pendingBundle.preview.job_names.slice(0, 4).join(", ")}{pendingBundle.preview.job_names.length > 4 ? "..." : ""}</small>
          )}
          {pendingBundle.preview.database && (
            <small>DB: {pendingBundle.preview.database.host}/{pendingBundle.preview.database.name} · schema {pendingBundle.preview.database.schema}</small>
          )}
          {pendingBundle.preview.config_error && <small className="errorText">{pendingBundle.preview.config_error}</small>}
          <div className="bundleImportModes" role="radiogroup" aria-label="Cách import bundle">
            <label className="checkField">
              <input
                type="radio"
                name="bundleImportMode"
                checked={pendingBundle.mode === "merge_jobs"}
                onChange={() => onSetPendingBundle((bundle) => bundle ? { ...bundle, mode: "merge_jobs" } : bundle)}
              />
              Chỉ thêm job từ bundle
            </label>
            <label className="checkField">
              <input
                type="radio"
                name="bundleImportMode"
                checked={pendingBundle.mode === "replace"}
                onChange={() => onSetPendingBundle((bundle) => bundle ? { ...bundle, mode: "replace" } : bundle)}
              />
              Ghi đè toàn bộ setting
            </label>
          </div>
          <div className="rowActions">
            <button type="button" onClick={onConfirmImportBundle} disabled={isImportingBundle || !pendingBundle.preview.has_config || pendingBundle.preview.config_error}>
              <Save size={15} aria-hidden="true" />
              Xác nhận import
            </button>
            <button type="button" onClick={() => onSetPendingBundle(null)}>Hủy</button>
          </div>
        </div>
      )}
    </section>
  );
}
