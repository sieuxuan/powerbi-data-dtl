import { AlertCircle, CheckCircle2, Download, Eye, RefreshCcw, Save } from "lucide-react";

export function SetupNoticeToast({ error, message }) {
  const text = error || message;
  if (!text) return null;

  return (
    <div className={`setupToast ${error ? "error" : "success"}`} role="status">
      {error ? <AlertCircle size={17} aria-hidden="true" /> : <CheckCircle2 size={17} aria-hidden="true" />}
      <span>{text}</span>
    </div>
  );
}

export function ConfigActions({
  isDirty,
  isLoading,
  isSaving,
  canSave,
  onReload,
  onSave,
  leading = null,
  trailing = null,
}) {
  return (
    <div className="sectionActions configActions">
      {leading}
      {isDirty && <span className="dirtyPill">Đang có thay đổi chưa lưu</span>}
      <button type="button" className="iconButton compact" title="Tải lại cấu hình" onClick={onReload} disabled={isLoading}>
        <RefreshCcw size={16} aria-hidden="true" />
      </button>
      <button type="button" className="primary" onClick={onSave} disabled={!canSave || isSaving}>
        <Save size={16} aria-hidden="true" />
        {isSaving ? "Đang lưu" : "Lưu"}
      </button>
      {trailing}
    </div>
  );
}

export function UpdateSection({
  updateConfig,
  updateInfo,
  isCheckingUpdate,
  isDownloadingUpdate,
  isApplyingUpdate,
  onCheckUpdate,
  onDownloadUpdate,
  onApplyUpdate,
}) {
  const hasUpdate = Boolean(updateInfo?.update_available);
  const hasDownloadedUpdate = Boolean(updateInfo?.downloaded_path);
  const isBusy = isApplyingUpdate || isDownloadingUpdate || isCheckingUpdate;
  const isDownloadDisabled = isBusy || !updateConfig?.enabled || !hasUpdate || hasDownloadedUpdate;
  const isApplyDisabled = isBusy || !updateConfig?.enabled || !hasUpdate || !hasDownloadedUpdate;

  return (
    <section className="setupSection">
      <div className="sectionTitle withAction">
        <div>
          <RefreshCcw size={18} aria-hidden="true" />
          <h3>Cập nhật phần mềm</h3>
        </div>
        <div className="sectionActions">
          <button type="button" className="iconButton compact" title="Kiểm tra lại" onClick={onCheckUpdate} disabled={isCheckingUpdate}>
            <Eye size={15} aria-hidden="true" />
          </button>
          <button type="button" className="secondaryButton" onClick={onDownloadUpdate} disabled={isDownloadDisabled}>
            <Download size={15} aria-hidden="true" />
            {isDownloadingUpdate ? "Đang tải" : hasDownloadedUpdate ? "Đã tải" : "Tải bản mới"}
          </button>
          <button type="button" className="primary" onClick={onApplyUpdate} disabled={isApplyDisabled}>
            <RefreshCcw size={15} aria-hidden="true" />
            {isApplyingUpdate ? "Đang cài" : "Cài & mở lại"}
          </button>
        </div>
      </div>
      <div className="setupGrid">
        <label className="checkField">
          <input type="checkbox" checked={Boolean(updateConfig?.enabled)} onChange={updateConfig?.onEnabledChange} />
          Tự kiểm tra bản mới
        </label>
        <label className="checkField">
          <input type="checkbox" checked={Boolean(updateConfig?.autoDownload)} onChange={updateConfig?.onAutoDownloadChange} />
          Tự tải sẵn khi khởi động
        </label>
      </div>
      {updateConfig?.enabled && isCheckingUpdate && !updateInfo && (
        <div className="testResult info">
          <strong>Đang kiểm tra bản mới...</strong>
        </div>
      )}
      {updateInfo && (
        <div className={`testResult ${updateInfo.error ? "error" : updateInfo.update_available ? "info" : "success"}`}>
          <strong>
            {updateInfo.error
              ? "Không kiểm tra được cập nhật"
              : updateInfo.update_available
                ? `Có bản mới ${updateInfo.latest_version}`
                : `Đang ở bản ${updateInfo.current_version}`}
          </strong>
          {updateInfo.message && <span> · {updateInfo.message}</span>}
          {updateInfo.asset_name && <span> · Gói: {updateInfo.asset_name}</span>}
          {updateInfo.downloaded_path && <span> · Sẵn sàng: {updateInfo.downloaded_path}</span>}
          {updateInfo.release_url && (
            <span>
              {" · "}
              <a href={updateInfo.release_url} target="_blank" rel="noreferrer">GitHub release</a>
            </span>
          )}
        </div>
      )}
    </section>
  );
}

export function DryRunDiffPanel({ result }) {
  if (!result) return null;
  const diff = result.diff || {};
  const newColumns = diff.columns_new || result.missing_in_db || [];
  const missingColumns = diff.columns_missing || result.extra_in_db || [];
  const typeMismatches = diff.type_mismatches || result.type_mismatches || [];
  const actionLabels = {
    create_table: "Tạo bảng mới",
    recreate_table: "Tạo lại bảng",
    skip_import: "Dừng import",
    append: "Append",
    upsert: "Upsert",
    truncate_insert: "Xóa rồi import",
  };

  return (
    <div className="typePreviewPanel dryRunDiffPanel">
      <div className="dryRunSummary">
        <span>
          <b>{diff.rows_to_import ?? result.rows_to_import ?? result.rows ?? 0}</b>
          dòng sẽ import
        </span>
        <span>
          <b>{diff.source_column_count ?? result.columns?.length ?? 0}</b>
          cột nguồn
        </span>
        <span className={diff.has_schema_diff ? "warn" : "ok"}>
          {diff.has_schema_diff ? "Có diff schema" : result.table_exists ? "Schema khớp" : "Sẽ tạo bảng"}
        </span>
        <span>{actionLabels[diff.action] || "Dry run"}</span>
      </div>

      <div className="dryRunDiffGrid">
        <div>
          <strong>Cột mới</strong>
          <small>{newColumns.length ? newColumns.join(", ") : "Không có"}</small>
        </div>
        <div>
          <strong>Cột mất</strong>
          <small>{missingColumns.length ? missingColumns.join(", ") : "Không có"}</small>
        </div>
        <div>
          <strong>Type đổi</strong>
          <small>
            {typeMismatches.length
              ? typeMismatches.map((item) => `${item.column || item.col}: ${item.source_type || item.excel_type} -> ${item.db_type}`).join(", ")
              : "Không có"}
          </small>
        </div>
      </div>

      {result.columns?.length > 0 && (
        <div className="typePreviewGrid">
          {result.columns.slice(0, 12).map((column) => (
            <div className="typePreviewItem" key={column.name}>
              <span>{column.name}</span>
              <b>{column.target_type || column.postgres_type}</b>
              <small>{column.nullable ? "nullable" : "not null"} · {column.pandas_type}</small>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
