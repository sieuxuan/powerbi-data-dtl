import { useEffect, useMemo, useRef, useState } from "react";
import {
  Bell,
  ChevronLeft,
  ChevronRight,
  Clock3,
  Copy,
  Eye,
  FileSpreadsheet,
  Link2,
  Pencil,
  Play,
  Plus,
  RefreshCcw,
  Save,
  Settings2,
  Trash2,
  UploadCloud,
} from "lucide-react";
import { SYNC_API_URL, syncApi } from "./SyncMonitor.jsx";
import { ConfigActions, DryRunDiffPanel, SetupNoticeToast, UpdateSection } from "./SyncSetupUi.jsx";
import BackupRestore from "./syncSetup/BackupRestore.jsx";
import ConnectionEditor from "./syncSetup/ConnectionEditor.jsx";
import JobEditor from "./syncSetup/JobEditor.jsx";
import Wizard from "./syncSetup/Wizard.jsx";

const DEFAULT_CONFIG = {
  database: {
    host: "localhost",
    port: 5432,
    name: "powerbi_data",
    user: "postgres",
    password: "${PG_PASSWORD}",
    schema: "public",
  },
  schedule: {
    default_cron: "0 6 * * *",
    timezone: "Asia/Ho_Chi_Minh",
    on_startup: false,
  },
  downloads: {
    dir: "./downloads",
    keep_files: false,
  },
  updates: {
    enabled: false,
    repo: "",
    current_version: "1.0.8",
    asset_pattern: "PowerBIDataDTL-portable.zip",
    check_on_startup: true,
    auto_download: false,
    auto_apply: false,
    allow_prerelease: false,
    download_dir: "./downloads/updates",
  },
  api: {
    enabled: true,
    host: "127.0.0.1",
    port: 8765,
    cors_origins: ["http://127.0.0.1:5173", "http://localhost:5173"],
  },
  retry: {
    db: { attempts: 3, delay_seconds: 10 },
    file: { attempts: 2, delay_seconds: 2 },
    onedrive: { attempts: 3, delay_seconds: 30 },
  },
  maintenance: {
    enabled: true,
    sync_log_retention_days: 180,
    downloads_retention_days: 14,
    uploads_retention_days: 365,
    preview_cache_retention_days: 3,
  },
  files: [],
  notifications: {
    windows_toast: false,
    email: {
      enabled: false,
      smtp_host: "",
      smtp_port: 587,
      sender: "",
      password: "",
      recipients: [],
    },
    webhook: {
      enabled: false,
      url: "",
      timeout_seconds: 15,
      statuses: ["success", "failed", "mismatch"],
    },
  },
  logging: {
    level: "INFO",
    file_dir: "./logs",
    max_file_size_mb: 10,
    backup_count: 30,
    log_to_db: true,
  },
};

const IDENTIFIER_PATTERN = /^[A-Za-z_][A-Za-z0-9_]{0,62}$/;
const CRON_VALUE_PATTERN = /^(\*|\?|\d{1,4}|\d{1,4}-\d{1,4}|\d{1,4}\/\d{1,4}|\*\/\d{1,4}|\d{1,4}-\d{1,4}\/\d{1,4})(,(\*|\?|\d{1,4}|\d{1,4}-\d{1,4}|\d{1,4}\/\d{1,4}|\*\/\d{1,4}|\d{1,4}-\d{1,4}\/\d{1,4}))*$/;

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

function defaultConnectionFromDatabase(database = DEFAULT_CONFIG.database) {
  return {
    id: "default",
    name: "PostgreSQL local",
    engine: "postgresql",
    host: database.host || "localhost",
    port: database.port ?? 5432,
    database: database.name || "powerbi_data",
    user: database.user || "postgres",
    password: database.password || "",
    schema: database.schema || "public",
    driver: "ODBC Driver 18 for SQL Server",
    trusted_connection: false,
    encrypt: true,
    trust_server_certificate: true,
  };
}

function normalizeConnection(connection, index = 0, legacyDatabase = DEFAULT_CONFIG.database) {
  const engine = connection?.engine === "sqlserver" ? "sqlserver" : "postgresql";
  const fallback = index === 0 ? defaultConnectionFromDatabase(legacyDatabase) : {
    id: `sql_server_${index + 1}`,
    name: `SQL server ${index + 1}`,
    engine,
    host: "localhost",
    port: engine === "sqlserver" ? 1433 : 5432,
    database: "",
    user: "",
    password: "",
    schema: engine === "sqlserver" ? "dbo" : "public",
    driver: "ODBC Driver 18 for SQL Server",
    trusted_connection: false,
    encrypt: true,
    trust_server_certificate: true,
  };
  return {
    ...fallback,
    ...(connection || {}),
    engine,
    id: String(connection?.id || fallback.id).trim(),
    name: String(connection?.name || fallback.name).trim(),
    host: String(connection?.host || fallback.host).trim(),
    port: toNumber(connection?.port ?? fallback.port, fallback.port),
    database: String(connection?.database || fallback.database).trim(),
    user: String(connection?.user ?? fallback.user).trim(),
    password: String(connection?.password ?? fallback.password),
    schema: String(connection?.schema || fallback.schema).trim(),
    driver: String(connection?.driver || "ODBC Driver 18 for SQL Server"),
    trusted_connection: Boolean(connection?.trusted_connection),
    encrypt: connection?.encrypt ?? true,
    trust_server_certificate: connection?.trust_server_certificate ?? true,
  };
}

function normalizeConnections(value, legacyDatabase = DEFAULT_CONFIG.database) {
  const raw = Array.isArray(value) ? value : [];
  const normalized = raw.map((connection, index) => normalizeConnection(connection, index, legacyDatabase));
  if (!normalized.some((connection) => connection.id === "default")) {
    normalized.unshift(defaultConnectionFromDatabase(legacyDatabase));
  }
  return normalized.length ? normalized : [defaultConnectionFromDatabase(legacyDatabase)];
}

function connectionById(connections, connectionId = "default", fallbackDatabase = DEFAULT_CONFIG.database) {
  const items = Array.isArray(connections) ? connections : [];
  return items.find((connection) => connection.id === connectionId)
    || items[0]
    || defaultConnectionFromDatabase(fallbackDatabase);
}

function connectionOptionLabel(connection) {
  return `${connection.name || connection.id} (${connection.engine})`;
}

function normalizeConfig(config) {
  const data = config && typeof config === "object" ? config : {};
  const database = { ...DEFAULT_CONFIG.database, ...(data.database || {}) };
  const databaseConnections = normalizeConnections(data.database_connections, database);
  const normalized = {
    ...clone(DEFAULT_CONFIG),
    ...data,
    database,
    database_connections: databaseConnections,
    schedule: { ...DEFAULT_CONFIG.schedule, ...(data.schedule || {}) },
    downloads: { ...DEFAULT_CONFIG.downloads, ...(data.downloads || {}) },
    updates: { ...DEFAULT_CONFIG.updates, ...(data.updates || {}) },
    api: { ...DEFAULT_CONFIG.api, ...(data.api || {}) },
    retry: {
      db: { ...DEFAULT_CONFIG.retry.db, ...(data.retry?.db || {}) },
      file: { ...DEFAULT_CONFIG.retry.file, ...(data.retry?.file || {}) },
      onedrive: { ...DEFAULT_CONFIG.retry.onedrive, ...(data.retry?.onedrive || {}) },
    },
    maintenance: { ...DEFAULT_CONFIG.maintenance, ...(data.maintenance || {}) },
    notifications: {
      ...DEFAULT_CONFIG.notifications,
      ...(data.notifications || {}),
      email: {
        ...DEFAULT_CONFIG.notifications.email,
        ...(data.notifications?.email || {}),
      },
      webhook: {
        ...DEFAULT_CONFIG.notifications.webhook,
        ...(data.notifications?.webhook || {}),
      },
    },
    logging: { ...DEFAULT_CONFIG.logging, ...(data.logging || {}) },
    files: Array.isArray(data.files)
      ? data.files.map((file, index) => {
        const connectionId = file?.target?.connection_id || "default";
        const connection = connectionById(databaseConnections, connectionId, database);
        return normalizeFile(file, index, connection?.schema || database.schema, connection?.id || "default");
      })
      : [],
  };
  normalized.api.cors_origins = asStringList(normalized.api.cors_origins);
  normalized.notifications.email.recipients = asStringList(normalized.notifications.email.recipients);
  normalized.notifications.webhook.statuses = asStringList(normalized.notifications.webhook.statuses);
  return normalized;
}

function normalizeFile(file, index, schema = "public", connectionId = "default") {
  return {
    name: file?.name || `Sync job ${index + 1}`,
    enabled: file?.enabled ?? true,
    source: {
      type: file?.source?.type || "local",
      path: file?.source?.path || "",
      share_url: file?.source?.share_url || "",
      download_url: file?.source?.download_url || "",
    },
    target: {
      connection_id: file?.target?.connection_id || connectionId || "default",
      table: file?.target?.table || "new_table",
      schema: file?.target?.schema || schema || "public",
      primary_key: asStringList(file?.target?.primary_key),
    },
    options: {
      sheet: file?.options?.sheet ?? 0,
      header_row: Number(file?.options?.header_row || 0),
      skip_rows: Array.isArray(file?.options?.skip_rows) ? file.options.skip_rows : [],
      usecols: file?.options?.usecols ?? null,
      skip_columns: asStringList(file?.options?.skip_columns),
      encoding: file?.options?.encoding || "utf-8",
      delimiter: file?.options?.delimiter || ",",
      column_renames: normalizeColumnRenames(file?.options?.column_renames),
    },
    sync_mode: file?.sync_mode || "truncate_insert",
    on_column_mismatch: file?.on_column_mismatch || "notify",
    skip_unchanged: file?.skip_unchanged ?? true,
    cron: file?.cron ?? null,
    crons: normalizeCronList(file?.crons, file?.cron),
  };
}

function validateSyncConfig(config) {
  const errors = [];
  const connections = config?.database_connections || [];
  const connectionIds = new Set();
  if (!String(config?.database?.host || "").trim()) errors.push("Thiếu database host.");
  if (!String(config?.database?.name || "").trim()) errors.push("Thiếu database name.");
  if (!String(config?.database?.user || "").trim()) errors.push("Thiếu database user.");
  for (const connection of connections) {
    const id = String(connection?.id || "").trim();
    if (!id) {
      errors.push("Mỗi SQL server cần có id.");
    } else if (!IDENTIFIER_PATTERN.test(id)) {
      errors.push(`SQL server id "${id}" sai định dạng.`);
    } else if (connectionIds.has(id)) {
      errors.push(`SQL server id "${id}" bị trùng.`);
    }
    connectionIds.add(id);
    if (!["postgresql", "sqlserver"].includes(connection?.engine)) errors.push(`Engine của ${id || "SQL server"} không hợp lệ.`);
    if (!String(connection?.host || "").trim()) errors.push(`Thiếu host cho ${id || "SQL server"}.`);
    if (!String(connection?.database || "").trim()) errors.push(`Thiếu database cho ${id || "SQL server"}.`);
    if (!connection?.trusted_connection && !String(connection?.user || "").trim()) errors.push(`Thiếu user cho ${id || "SQL server"}.`);
    if (!String(connection?.schema || "").trim()) errors.push(`Thiếu schema cho ${id || "SQL server"}.`);
  }
  if (!connectionIds.has("default")) errors.push('Cần có SQL server id "default".');
  const jobs = (config?.files || []).map((file, index) => validateJobConfig(file, index, connectionIds));
  const invalidJobs = jobs.filter((job) => job.messages.length).length;
  return {
    errors,
    jobs,
    count: errors.length + jobs.reduce((total, job) => total + job.messages.length, 0),
    hasErrors: Boolean(errors.length || invalidJobs),
  };
}

function validateJobConfig(file, index = 0, connectionIds = null) {
  const messages = [];
  const fields = {};
  const source = file?.source || {};
  const target = file?.target || {};
  const sourceType = source.type === "onedrive" ? "onedrive" : "local";
  const table = String(target.table || "").trim();
  const schema = String(target.schema || "").trim();
  const crons = normalizeCronList(file?.crons, file?.cron);
  const connectionId = String(target.connection_id || "default");

  if (!String(file?.name || "").trim()) {
    fields.name = "Tên job không được để trống.";
    messages.push(fields.name);
  }
  if (sourceType === "local" && !String(source.path || "").trim()) {
    fields.source = "Thiếu đường dẫn file local.";
    messages.push(fields.source);
  }
  if (sourceType === "onedrive" && !String(source.share_url || source.download_url || "").trim()) {
    fields.source = "Thiếu link SharePoint/OneDrive hoặc direct download URL.";
    messages.push(fields.source);
  }
  if (!table) {
    fields.table = "Thiếu bảng đích.";
    messages.push(fields.table);
  } else if (!IDENTIFIER_PATTERN.test(table)) {
    fields.table = "Tên bảng chỉ dùng chữ, số, dấu gạch dưới và không bắt đầu bằng số.";
    messages.push(fields.table);
  }
  if (schema && !IDENTIFIER_PATTERN.test(schema)) {
    fields.schema = "Schema chỉ dùng chữ, số, dấu gạch dưới và không bắt đầu bằng số.";
    messages.push(fields.schema);
  }
  if (connectionIds && !connectionIds.has(connectionId)) {
    fields.connection_id = `Server import "${connectionId}" không tồn tại.`;
    messages.push(fields.connection_id);
  }
  const invalidCron = crons.find((cron) => !isValidCron(cron));
  if (invalidCron) {
    fields.cron = `Cron sai định dạng: ${invalidCron}`;
    messages.push(fields.cron);
  }
  if (file?.sync_mode === "upsert" && !asStringList(target.primary_key).length) {
    fields.primary_key = "Upsert cần primary key.";
    messages.push(fields.primary_key);
  }

  return {
    index,
    fields,
    messages,
  };
}

function isValidCron(value) {
  const cron = String(value || "").trim();
  if (!cron) return true;
  const parts = cron.split(/\s+/);
  return parts.length === 5 && parts.every((part) => CRON_VALUE_PATTERN.test(part));
}

function parseCsvList(value) {
  return String(value || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function asStringList(value) {
  if (Array.isArray(value)) return value.map((item) => String(item).trim()).filter(Boolean);
  if (typeof value === "string") return parseCsvList(value);
  return [];
}

function normalizeCronList(value, legacyCron = null) {
  const crons = asStringList(value);
  if (crons.length) return crons;
  return legacyCron ? [String(legacyCron).trim()].filter(Boolean) : [];
}

function normalizeColumnRenames(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  return Object.fromEntries(
    Object.entries(value)
      .map(([source, target]) => [String(source).trim(), String(target).trim()])
      .filter(([source, target]) => source && target),
  );
}

function parseNumberList(value) {
  return String(value || "")
    .split(",")
    .map((item) => Number(item.trim()))
    .filter((item) => Number.isFinite(item));
}

function formatList(value) {
  return Array.isArray(value) ? value.join(", ") : "";
}

function formatColumnRenames(value) {
  const entries = Object.entries(normalizeColumnRenames(value));
  return entries.map(([source, target]) => `${source} => ${target}`).join("\n");
}

function parseColumnRenamesText(value) {
  const result = {};
  for (const rawLine of String(value || "").split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line) continue;
    const separator = line.includes("=>") ? "=>" : line.includes("=") ? "=" : ":";
    const [source, ...targetParts] = line.split(separator);
    const target = targetParts.join(separator);
    if (source?.trim() && target?.trim()) {
      result[source.trim()] = target.trim();
    }
  }
  return result;
}

function sourceLabel(file) {
  if (file?.source?.type === "onedrive") return "SharePoint/OneDrive";
  return "File local";
}

function sourcePathLabel(file) {
  if (file?.source?.type === "onedrive") return file.source.share_url || file.source.download_url || "Chưa có link";
  return file?.source?.path || "Chưa chọn file";
}

function jobCronLabel(file) {
  const crons = normalizeCronList(file?.crons, file?.cron);
  if (crons.length > 1) return `${crons.length} lịch`;
  return crons.length === 1 ? "1 lịch" : "Chưa đặt lịch";
}

function defaultNewJob(index, schema = "public", connectionId = "default") {
  return normalizeFile({ name: `Sync job ${index + 1}` }, index, schema, connectionId);
}

function selectedPreviewSheet(preview, sheetValue) {
  const sheets = preview?.sheets || [];
  return sheets.find((sheet) => sheet.name === sheetValue || sheet.index === sheetValue || String(sheet.index) === String(sheetValue)) || sheets[0];
}

function parseSheet(value) {
  const text = String(value ?? "").trim();
  if (/^\d+$/.test(text)) return Number(text);
  return text || 0;
}

function toNumber(value, fallback = 0) {
  if (value === "") return "";
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function stripDiacritics(value) {
  return String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/đ/g, "d")
    .replace(/Đ/g, "D");
}

function suggestSyncColumnName(value, fallback, used = null) {
  let name = stripDiacritics(value)
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .replace(/_{2,}/g, "_");
  if (!name || /^\d/.test(name)) name = fallback;
  if (!used) return name;
  let unique = name;
  let suffix = 2;
  while (used.has(unique)) {
    unique = `${name}_${suffix}`;
    suffix += 1;
  }
  used.add(unique);
  return unique;
}

function cleanPreviewHeader(value, index) {
  const text = String(value ?? "").trim();
  return text || `column_${index + 1}`;
}

function previewSourceHeaders(cells) {
  const seen = {};
  return cells.map((cell, index) => {
    const source = cleanPreviewHeader(cell, index);
    seen[source] = (seen[source] || 0) + 1;
    return seen[source] === 1 ? source : `${source}.${seen[source] - 1}`;
  });
}

function trimEmptyPreviewEdges(cells) {
  const copy = [...cells];
  while (copy.length && !String(copy[0] ?? "").trim()) copy.shift();
  while (copy.length && !String(copy[copy.length - 1] ?? "").trim()) copy.pop();
  return copy;
}

function getPreviewHeaderCells(preview, sheetValue, headerRow) {
  const sheet = selectedPreviewSheet(preview, sheetValue);
  const row = sheet?.rows?.[Number(headerRow || 0)] || [];
  return trimEmptyPreviewEdges(row);
}

function buildColumnRenameMap(cells) {
  return Object.fromEntries(
    previewSourceHeaders(cells).map((source, index) => {
      return [source, suggestSyncColumnName(source, `column_${index + 1}`)];
    }),
  );
}

function readFileAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(reader.error || new Error("Không đọc được file."));
    reader.readAsDataURL(file);
  });
}

export async function uploadFileToSync(file) {
  const dataUrl = await readFileAsDataUrl(file);
  return syncApi("/api/files/upload", {
    method: "POST",
    body: JSON.stringify({
      filename: file.name,
      content_base64: dataUrl,
    }),
  });
}

function parseDailyCron(value) {
  const parts = String(value || "").trim().split(/\s+/);
  if (parts.length !== 5) return null;
  const [minute, hour, day, month, weekday] = parts;
  if (day !== "*" || month !== "*" || weekday !== "*") return null;
  if (!/^\d+$/.test(minute) || !/^\d+$/.test(hour)) return null;
  const h = Number(hour);
  const m = Number(minute);
  if (h < 0 || h > 23 || m < 0 || m > 59) return null;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

function makeDailyCron(timeValue) {
  const [hour = "6", minute = "0"] = String(timeValue || "06:00").split(":");
  return `${Number(minute) || 0} ${Number(hour) || 0} * * *`;
}

function detectCronMode(value) {
  if (parseDailyCron(value)) return "daily";
  if (String(value || "").trim() === "0 * * * *") return "hourly";
  return "custom";
}

function CronEditor({ label, value, onChange }) {
  const mode = detectCronMode(value);
  const dailyTime = parseDailyCron(value) || "06:00";

  function changeMode(nextMode) {
    if (nextMode === "daily") onChange(makeDailyCron(dailyTime));
    if (nextMode === "hourly") onChange("0 * * * *");
    if (nextMode === "custom") onChange(value || "0 6 * * *");
  }

  return (
    <label className="cronEditor">
      {label}
      <div className="cronControls">
        <select value={mode} onChange={(event) => changeMode(event.target.value)}>
          <option value="daily">Hằng ngày theo giờ</option>
          <option value="hourly">Mỗi giờ</option>
          <option value="custom">Cron tuỳ chỉnh</option>
        </select>
        {mode === "daily" && (
          <input type="time" value={dailyTime} onChange={(event) => onChange(makeDailyCron(event.target.value))} />
        )}
        {mode === "custom" && (
          <input value={value || ""} placeholder="0 6 * * *" onChange={(event) => onChange(event.target.value)} />
        )}
      </div>
    </label>
  );
}

function ConnectionSelect({ value, connections, onChange }) {
  return (
    <select value={value || "default"} onChange={(event) => onChange(event.target.value)}>
      {(connections || []).map((connection) => (
        <option key={connection.id} value={connection.id}>{connectionOptionLabel(connection)}</option>
      ))}
    </select>
  );
}

function CronListEditor({ label, value, onChange }) {
  const crons = normalizeCronList(value);

  function patchCron(index, nextValue) {
    onChange(crons.map((cron, cronIndex) => (cronIndex === index ? nextValue : cron)).filter(Boolean));
  }

  function addCron() {
    onChange([...crons, makeDailyCron("06:00")]);
  }

  function removeCron(index) {
    onChange(crons.filter((_, cronIndex) => cronIndex !== index));
  }

  return (
    <div className="cronListEditor">
      <div className="cronListHeader">
        <strong>{label}</strong>
        <button type="button" className="secondaryButton" onClick={addCron}>
          <Plus size={15} aria-hidden="true" />
          Thêm lịch
        </button>
      </div>
      {crons.length === 0 && <small>Chưa đặt lịch. Job chỉ chạy thủ công.</small>}
      {crons.map((cron, index) => (
        <div className="cronListRow" key={`cron-${index}`}>
          <CronEditor label={`Lịch ${index + 1}`} value={cron} onChange={(nextValue) => patchCron(index, nextValue)} />
          <button type="button" className="iconButton danger" title="Xóa lịch" onClick={() => removeCron(index)}>
            <Trash2 size={15} aria-hidden="true" />
          </button>
        </div>
      ))}
      {crons.length > 0 && (
        <button type="button" className="secondaryButton" onClick={() => onChange([])}>
          Xóa toàn bộ lịch
        </button>
      )}
    </div>
  );
}

export default function SyncSetup({ notice = "", focusJobName = "", focusToken = 0, addJobToken = 0, setupTab: controlledSetupTab = "", onSetupTabChange = null }) {
  const [configData, setConfigData] = useState(null);
  const [configPath, setConfigPath] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [isImportingBundle, setIsImportingBundle] = useState(false);
  const [testingDbId, setTestingDbId] = useState("");
  const [testingWriteId, setTestingWriteId] = useState("");
  const [isTestingWebhook, setIsTestingWebhook] = useState(false);
  const [isCheckingUpdate, setIsCheckingUpdate] = useState(false);
  const [isDownloadingUpdate, setIsDownloadingUpdate] = useState(false);
  const [isApplyingUpdate, setIsApplyingUpdate] = useState(false);
  const [isDirty, setIsDirty] = useState(false);
  const [localSetupTab, setLocalSetupTab] = useState("jobs");
  const [editingJobIndex, setEditingJobIndex] = useState(-1);
  const [editingJobMode, setEditingJobMode] = useState("details");
  const [uploadingJobIndex, setUploadingJobIndex] = useState(null);
  const [testingFileIndex, setTestingFileIndex] = useState(null);
  const [dryRunningJobIndex, setDryRunningJobIndex] = useState(null);
  const [jobFeedback, setJobFeedback] = useState({});
  const [wizardOpen, setWizardOpen] = useState(false);
  const [wizardStep, setWizardStep] = useState(1);
  const [wizardJob, setWizardJob] = useState(null);
  const [wizardPreview, setWizardPreview] = useState(null);
  const [wizardMessage, setWizardMessage] = useState("");
  const [wizardDryRun, setWizardDryRun] = useState(null);
  const [isWizardBusy, setIsWizardBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [pendingBundle, setPendingBundle] = useState(null);
  const [updateInfo, setUpdateInfo] = useState(null);
  const handledFocusTokenRef = useRef(null);
  const updateAutoCheckRef = useRef("");
  const handledAddJobTokenRef = useRef(null);
  const noticeTimerRef = useRef(null);
  const enabledJobs = useMemo(
    () => (configData?.files || []).filter((file) => file.enabled).length,
    [configData],
  );
  const validation = useMemo(() => validateSyncConfig(configData), [configData]);
  const setupTab = controlledSetupTab || localSetupTab;
  const isTestingWrite = Boolean(testingWriteId);

  function setSetupTab(tab) {
    if (onSetupTabChange) {
      onSetupTabChange(tab);
    } else {
      setLocalSetupTab(tab);
    }
  }

  useEffect(() => {
    loadConfig();
  }, []);

  useEffect(() => {
    if (notice) setMessage(notice);
  }, [notice]);

  useEffect(() => {
    const noticeText = error || message;
    if (noticeTimerRef.current) window.clearTimeout(noticeTimerRef.current);
    if (!noticeText) return undefined;
    noticeTimerRef.current = window.setTimeout(() => {
      if (error) {
        setError("");
      } else {
        setMessage("");
      }
    }, error ? 6500 : 4200);
    return () => {
      if (noticeTimerRef.current) window.clearTimeout(noticeTimerRef.current);
    };
  }, [error, message]);

  useEffect(() => {
    if (!configData?.files?.length || !focusJobName) return;
    if (handledFocusTokenRef.current === focusToken) return;
    const index = configData.files.findIndex((file) => file.name === focusJobName);
    if (index >= 0) {
      handledFocusTokenRef.current = focusToken;
      setSetupTab("jobs");
      setEditingJobIndex(index);
      setEditingJobMode("details");
      setMessage(`Đang sửa job ${focusJobName}.`);
    }
  }, [configData, focusJobName, focusToken]);

  useEffect(() => {
    if (!configData || !addJobToken || handledAddJobTokenRef.current === addJobToken) return;
    handledAddJobTokenRef.current = addJobToken;
    addJob();
  }, [configData, addJobToken]);

  useEffect(() => {
    if (setupTab !== "system" || !configData?.updates?.enabled) return;
    const updateKey = [
      configData.updates.repo || "",
      configData.updates.current_version || "",
      configData.updates.asset_pattern || "",
    ].join("|");
    if (updateAutoCheckRef.current === updateKey) return;
    updateAutoCheckRef.current = updateKey;
    checkUpdate("check", { silent: true });
  }, [
    setupTab,
    configData?.updates?.enabled,
    configData?.updates?.repo,
    configData?.updates?.current_version,
    configData?.updates?.asset_pattern,
  ]);

  async function loadConfig() {
    setIsLoading(true);
    setError("");
    try {
      const data = await syncApi("/api/config");
      setConfigPath(data.path || "");
      setConfigData(normalizeConfig(data.config));
      setIsDirty(false);
      if (!notice) setMessage("");
    } catch (loadError) {
      setConfigData(null);
      setError(`Không tải được cấu hình: ${loadError.message}`);
    } finally {
      setIsLoading(false);
    }
  }

  async function saveConfig() {
    if (!configData) return;
    await persistConfig(configData, "Đã lưu cấu hình.");
  }

  async function persistConfig(nextConfig, successMessage = "Đã lưu cấu hình.") {
    const validationResult = validateSyncConfig(nextConfig);
    if (validationResult.hasErrors) {
      const firstJobError = validationResult.jobs.find((job) => job.messages.length);
      if (firstJobError) {
        setSetupTab("jobs");
        setEditingJobIndex(firstJobError.index);
      }
      setError(`Chưa thể lưu: còn ${validationResult.count} lỗi cấu hình cần sửa.`);
      throw new Error("Config validation failed");
    }
    setIsSaving(true);
    setError("");
    try {
      const result = await syncApi("/api/config", {
        method: "POST",
        body: JSON.stringify(nextConfig),
      });
      setConfigData(normalizeConfig(nextConfig));
      setIsDirty(false);
      setMessage(successMessage || result.message || "Đã lưu cấu hình.");
      return result;
    } catch (saveError) {
      setError(`Không lưu được cấu hình: ${saveError.message}`);
      throw saveError;
    } finally {
      setIsSaving(false);
    }
  }

  async function testDatabase(connectionId = "default") {
    if (!configData) return;
    setTestingDbId(connectionId);
    setError("");
    try {
      const result = await syncApi("/api/config/test-db", {
        method: "POST",
        body: JSON.stringify({ config: configData, connection_id: connectionId }),
      });
      setMessage(result.message || "Kết nối SQL server thành công.");
    } catch (testError) {
      setError(`Test database lỗi: ${testError.message}`);
    } finally {
      setTestingDbId("");
    }
  }

  async function testWritePermission(connectionId = "default", schema = null) {
    if (!configData) return;
    const connection = connectionById(configData.database_connections, connectionId, configData.database);
    setTestingWriteId(connection?.id || connectionId || "default");
    setError("");
    try {
      const result = await syncApi("/api/config/test-write", {
        method: "POST",
        body: JSON.stringify({
          config: configData,
          connection_id: connection?.id || "default",
          schema: schema || connection?.schema || "public",
        }),
      });
      setMessage(result.message || "User có quyền ghi vào schema.");
    } catch (testError) {
      setError(`Test quyền ghi lỗi: ${testError.message}`);
    } finally {
      setTestingWriteId("");
    }
  }

  async function exportBundle() {
    setError("");
    try {
      const response = await fetch(`${SYNC_API_URL}/api/config/export-bundle?include_uploads=true`);
      if (!response.ok) throw new Error(await response.text());
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      const disposition = response.headers.get("content-disposition") || "";
      const match = disposition.match(/filename="?([^"]+)"?/);
      link.href = url;
      link.download = match?.[1] || "powerbi-data-dtl-config.zip";
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      setMessage("Đã export bundle cấu hình.");
    } catch (exportError) {
      setError(`Export bundle lỗi: ${exportError.message}`);
    }
  }

  async function importBundle(file) {
    if (!file) return;
    setIsImportingBundle(true);
    setError("");
    try {
      const dataUrl = await readFileAsDataUrl(file);
      const preview = await syncApi("/api/config/preview-bundle", {
        method: "POST",
        body: JSON.stringify({ content_base64: dataUrl }),
      });
      setPendingBundle({ fileName: file.name, dataUrl, preview, mode: "merge_jobs" });
      setMessage(`Đã đọc bundle ${file.name}. Kiểm tra preview rồi xác nhận import.`);
    } catch (importError) {
      setError(`Preview bundle lỗi: ${importError.message}`);
    } finally {
      setIsImportingBundle(false);
    }
  }

  async function confirmImportBundle() {
    if (!pendingBundle) return;
    setIsImportingBundle(true);
    setError("");
    try {
      const result = await syncApi("/api/config/import-bundle", {
        method: "POST",
        body: JSON.stringify({
          content_base64: pendingBundle.dataUrl,
          mode: pendingBundle.mode || "merge_jobs",
        }),
      });
      setPendingBundle(null);
      const isMerge = result.mode === "merge_jobs";
      setMessage(
        isMerge
          ? `Đã import thêm ${result.jobs_added || 0} job từ bundle. Khôi phục ${result.uploads || 0} file uploads.`
          : `Đã ghi đè cấu hình từ bundle. Khôi phục ${result.uploads || 0} file uploads.`
      );
      await loadConfig();
    } catch (importError) {
      setError(`Import bundle lỗi: ${importError.message}`);
    } finally {
      setIsImportingBundle(false);
    }
  }

  async function openAppFolder(folder) {
    setError("");
    try {
      const result = await syncApi("/api/open-folder", {
        method: "POST",
        body: JSON.stringify({ folder }),
      });
      setMessage(`Đã mở thư mục: ${result.path}`);
    } catch (openError) {
      setError(`Không mở được thư mục: ${openError.message}`);
    }
  }

  async function testWebhook() {
    if (!configData) return;
    setIsTestingWebhook(true);
    setError("");
    try {
      const result = await syncApi("/api/config/test-webhook", {
        method: "POST",
        body: JSON.stringify({ config: configData }),
      });
      setMessage(result.message || "Đã gửi test webhook.");
    } catch (testError) {
      setError(`Test webhook lỗi: ${testError.message}`);
    } finally {
      setIsTestingWebhook(false);
    }
  }

  async function checkUpdate(action = "check", options = {}) {
    if (!configData) return;
    const silent = Boolean(options.silent);
    const setBusy = action === "apply" ? setIsApplyingUpdate : action === "download" ? setIsDownloadingUpdate : setIsCheckingUpdate;
    setBusy(true);
    setError("");
    try {
      const endpoint = action === "apply" ? "/api/update/apply" : action === "download" ? "/api/update/download" : "/api/update/check";
      const result = await syncApi(endpoint, {
        method: "POST",
        body: JSON.stringify({ config: configData }),
      });
      setUpdateInfo(result);
      if (action === "apply") {
        setMessage(result.message || "Đang áp dụng bản cập nhật. Ứng dụng sẽ tự mở lại.");
      } else if (action === "download") {
        setMessage(result.downloaded_path ? `Bản cập nhật đã sẵn sàng tại ${result.downloaded_path}.` : "Không có bản mới để tải.");
      } else if (!silent || result.update_available) {
        setMessage(result.update_available ? `Có bản mới ${result.latest_version}.` : "Đang dùng bản mới nhất.");
      }
    } catch (updateError) {
      setUpdateInfo({
        configured: Boolean(configData?.updates?.enabled),
        update_available: false,
        current_version: configData?.updates?.current_version || "",
        message: updateError.message,
        error: true,
      });
      if (!silent) setError(`Kiểm tra cập nhật lỗi: ${updateError.message}`);
    } finally {
      setBusy(false);
    }
  }

  function runUpdatePrimaryAction() {
    checkUpdate("apply");
  }

  async function uploadJobFile(index, file) {
    if (!file) return;
    setUploadingJobIndex(index);
    setError("");
    setJobFeedback((current) => ({ ...current, [index]: { type: "info", text: "Đang upload file..." } }));
    try {
      const result = await uploadFileToSync(file);
      patchJob(index, (job) => ({
        ...job,
        name: job.name?.startsWith("Sync job") ? file.name.replace(/\.[^.]+$/, "") : job.name,
        source: { type: "local", path: result.path, share_url: "", download_url: "" },
      }));
      setJobFeedback((current) => ({
        ...current,
        [index]: { type: "success", text: `Đã upload ${result.filename} vào ${result.path}.` },
      }));
    } catch (uploadError) {
      setJobFeedback((current) => ({
        ...current,
        [index]: { type: "error", text: `Upload lỗi: ${uploadError.message}` },
      }));
    } finally {
      setUploadingJobIndex(null);
    }
  }

  async function testJobFile(index) {
    if (!configData?.files?.[index]) return;
    setTestingFileIndex(index);
    setError("");
    setJobFeedback((current) => ({ ...current, [index]: { type: "info", text: "Đang đọc thử file..." } }));
    try {
      const result = await syncApi("/api/config/test-file", {
        method: "POST",
        timeoutMs: 120000,
        body: JSON.stringify({ config: configData, file: configData.files[index] }),
      });
      const columnPreview = (result.columns || []).slice(0, 6).join(", ");
      setJobFeedback((current) => ({
        ...current,
        [index]: {
          type: "success",
          text: `${result.sampled ? `Đọc mẫu ${result.rows} dòng` : `${result.rows} dòng`}, ${result.column_count} cột. ${columnPreview ? `Cột: ${columnPreview}` : ""}`,
        },
      }));
    } catch (testError) {
      setJobFeedback((current) => ({
        ...current,
        [index]: { type: "error", text: `Test file lỗi: ${testError.message}` },
      }));
    } finally {
      setTestingFileIndex(null);
    }
  }

  async function dryRunJob(index) {
    if (!configData?.files?.[index]) return;
    setDryRunningJobIndex(index);
    setError("");
    setJobFeedback((current) => ({ ...current, [index]: { type: "info", text: "Đang dry run..." } }));
    try {
      const result = await syncApi("/api/config/dry-run-file", {
        method: "POST",
        body: JSON.stringify({ config: configData, file: configData.files[index] }),
      });
      const typePreview = (result.columns || [])
        .slice(0, 5)
        .map((column) => `${column.name}:${column.target_type || column.postgres_type}`)
        .join(", ");
      setJobFeedback((current) => ({
        ...current,
        [index]: {
          type: result.schema_match || !result.table_exists ? "success" : "error",
          text: `${result.sampled ? `Mẫu ${result.rows} dòng` : `${result.rows} dòng`}, ${result.columns?.length || 0} cột. Bảng ${result.table_exists ? "đã tồn tại" : "chưa có"}. Schema ${result.schema_match ? "khớp" : "chưa khớp"}. ${typePreview}`,
          dryRun: result,
        },
      }));
    } catch (dryRunError) {
      setJobFeedback((current) => ({
        ...current,
        [index]: { type: "error", text: `Dry run lỗi: ${dryRunError.message}` },
      }));
    } finally {
      setDryRunningJobIndex(null);
    }
  }

  function patchSection(section, patch) {
    setIsDirty(true);
    setConfigData((current) => ({
      ...current,
      [section]: {
        ...(current?.[section] || {}),
        ...patch,
      },
    }));
  }

  function patchNested(section, nestedKey, patch) {
    setIsDirty(true);
    setConfigData((current) => ({
      ...current,
      [section]: {
        ...(current?.[section] || {}),
        [nestedKey]: {
          ...(current?.[section]?.[nestedKey] || {}),
          ...patch,
        },
      },
    }));
  }

  function patchRetry(name, patch) {
    setIsDirty(true);
    setConfigData((current) => ({
      ...current,
      retry: {
        ...(current?.retry || {}),
        [name]: {
          ...(current?.retry?.[name] || {}),
          ...patch,
        },
      },
    }));
  }

  function syncLegacyDatabaseFromDefault(config) {
    const defaultConnection = (config?.database_connections || []).find((connection) => connection.id === "default");
    if (!defaultConnection || defaultConnection.engine !== "postgresql") return config;
    return {
      ...config,
      database: {
        ...(config?.database || {}),
        host: defaultConnection.host,
        port: defaultConnection.port,
        name: defaultConnection.database,
        user: defaultConnection.user,
        password: defaultConnection.password,
        schema: defaultConnection.schema,
      },
    };
  }

  function connectionUsageCount(connectionId, sourceConfig = configData) {
    return (sourceConfig?.files || []).filter((file) => (file.target?.connection_id || "default") === connectionId).length;
  }

  function addConnection(engine = "postgresql") {
    setIsDirty(true);
    setConfigData((current) => {
      const existing = current?.database_connections || [];
      const prefix = engine === "sqlserver" ? "sqlserver" : "postgres";
      let index = existing.length + 1;
      let id = `${prefix}_${index}`;
      const ids = new Set(existing.map((connection) => connection.id));
      while (ids.has(id)) {
        index += 1;
        id = `${prefix}_${index}`;
      }
      const connection = normalizeConnection({
        id,
        name: engine === "sqlserver" ? `SQL Server ${index}` : `PostgreSQL ${index}`,
        engine,
        port: engine === "sqlserver" ? 1433 : 5432,
        schema: engine === "sqlserver" ? "dbo" : "public",
      }, index, current?.database);
      return { ...current, database_connections: [...existing, connection] };
    });
  }

  function patchConnection(index, patch) {
    setIsDirty(true);
    setConfigData((current) => {
      const connections = [...(current?.database_connections || [])];
      const currentConnection = connections[index] || normalizeConnection({}, index, current?.database);
      const nextEngine = patch.engine || currentConnection.engine;
      const nextConnection = normalizeConnection({
        ...currentConnection,
        ...patch,
        port: patch.engine && patch.engine !== currentConnection.engine ? (nextEngine === "sqlserver" ? 1433 : 5432) : (patch.port ?? currentConnection.port),
        schema: patch.engine && patch.engine !== currentConnection.engine ? (nextEngine === "sqlserver" ? "dbo" : "public") : (patch.schema ?? currentConnection.schema),
      }, index, current?.database);
      connections[index] = nextConnection;
      return syncLegacyDatabaseFromDefault({ ...current, database_connections: connections });
    });
  }

  function removeConnection(index) {
    const connection = configData?.database_connections?.[index];
    if (!connection) return;
    const usage = connectionUsageCount(connection.id);
    if (usage > 0) {
      setError(`Không thể xóa ${connection.name}: đang được ${usage} job sử dụng.`);
      return;
    }
    if ((configData?.database_connections || []).length <= 1) {
      setError("Cần giữ lại ít nhất một SQL server.");
      return;
    }
    if (!window.confirm(`Xóa SQL server "${connection.name}"?`)) return;
    setIsDirty(true);
    setConfigData((current) => ({
      ...current,
      database_connections: (current?.database_connections || []).filter((_, connectionIndex) => connectionIndex !== index),
    }));
  }

  function selectJobConnection(index, connectionId) {
    const connection = connectionById(configData?.database_connections, connectionId, configData?.database);
    patchJobNested(index, "target", {
      connection_id: connectionId,
      schema: connection?.schema || "public",
    });
  }

  function selectWizardConnection(connectionId) {
    const connection = connectionById(configData?.database_connections, connectionId, configData?.database);
    patchWizardNested("target", {
      connection_id: connectionId,
      schema: connection?.schema || "public",
    });
  }

  function addJob() {
    const files = configData?.files || [];
    const connection = connectionById(configData?.database_connections, "default", configData?.database);
    setSetupTab("jobs");
    setWizardJob(defaultNewJob(files.length, connection.schema, connection.id));
    setWizardPreview(null);
    setWizardMessage("");
    setWizardDryRun(null);
    setWizardStep(1);
    setWizardOpen(true);
  }

  function removeJob(index) {
    const name = configData?.files?.[index]?.name || `Job ${index + 1}`;
    if (!window.confirm(`Xóa tác vụ "${name}"?`)) return;
    setIsDirty(true);
    setEditingJobIndex((current) => {
      if (current !== index) return current > index ? current - 1 : current;
      return -1;
    });
    setConfigData((current) => ({
      ...current,
      files: (current?.files || []).filter((_, fileIndex) => fileIndex !== index),
    }));
  }

  function copyJob(index) {
    setIsDirty(true);
    setSetupTab("jobs");
    setConfigData((current) => {
      const files = [...(current?.files || [])];
      const sourceJob = files[index];
      if (!sourceJob) return current;
      const existingNames = new Set(files.map((file) => file.name));
      const baseName = `${sourceJob.name || `Job ${index + 1}`} copy`;
      let name = baseName;
      let suffix = 2;
      while (existingNames.has(name)) {
        name = `${baseName} ${suffix}`;
        suffix += 1;
      }
      const copied = normalizeFile({ ...clone(sourceJob), name, enabled: false }, files.length, current?.database?.schema);
      files.splice(index + 1, 0, copied);
      setEditingJobIndex(index + 1);
      setEditingJobMode("details");
      setMessage(`Đã copy job "${sourceJob.name}". Bản copy đang tắt để tránh chạy trùng.`);
      return { ...current, files };
    });
  }

  function openJobEditor(index, mode = "details") {
    setEditingJobMode(mode);
    setEditingJobIndex(index);
  }

  async function toggleJobEnabled(index) {
    if (!configData?.files?.[index]) return;
    const files = [...(configData.files || [])];
    const nextEnabled = !files[index].enabled;
    files[index] = { ...files[index], enabled: nextEnabled };
    const nextConfig = { ...configData, files };
    try {
      await persistConfig(nextConfig, nextEnabled ? "Đã bật và lưu tác vụ." : "Đã tắt và lưu tác vụ.");
    } catch {
      // persistConfig has already shown the error.
    }
  }

  function patchJob(index, updater) {
    setIsDirty(true);
    setConfigData((current) => {
      const files = [...(current?.files || [])];
      const currentFile = files[index] || normalizeFile({}, index, current?.database?.schema);
      files[index] = typeof updater === "function" ? updater(currentFile) : { ...currentFile, ...updater };
      return { ...current, files };
    });
  }

  function patchJobNested(index, section, patch) {
    patchJob(index, (file) => ({
      ...file,
      [section]: {
        ...(file[section] || {}),
        ...patch,
      },
    }));
  }

  function changeSourceType(index, value) {
    patchJob(index, (file) => ({
      ...file,
      source: value === "local"
        ? { type: "local", path: file.source?.path || "", share_url: "", download_url: "" }
        : { type: "onedrive", path: "", share_url: file.source?.share_url || "", download_url: file.source?.download_url || "" },
    }));
  }

  function patchWizardJob(updater) {
    setWizardJob((current) => (typeof updater === "function" ? updater(current) : { ...current, ...updater }));
  }

  function patchWizardNested(section, patch) {
    patchWizardJob((job) => ({
      ...job,
      [section]: {
        ...(job?.[section] || {}),
        ...patch,
      },
    }));
  }

  function changeWizardSourceType(value) {
    patchWizardJob((job) => ({
      ...job,
      source: value === "local"
        ? { type: "local", path: job?.source?.path || "", share_url: "", download_url: "" }
        : { type: "onedrive", path: "", share_url: job?.source?.share_url || "", download_url: job?.source?.download_url || "" },
    }));
    setWizardPreview(null);
  }

  async function uploadWizardFile(file) {
    if (!file || !wizardJob) return;
    setIsWizardBusy(true);
    setWizardMessage("Đang upload file...");
    try {
      const result = await uploadFileToSync(file);
      const tableName = file.name.replace(/\.[^.]+$/, "").replace(/[^\w]+/g, "_").toLowerCase() || "new_table";
      patchWizardJob((job) => ({
        ...job,
        name: job?.name?.startsWith("Sync job") ? file.name.replace(/\.[^.]+$/, "") : job.name,
        source: { type: "local", path: result.path, share_url: "", download_url: "" },
        target: { ...(job.target || {}), table: tableName },
      }));
      setWizardMessage(`Đã upload ${result.filename}.`);
    } catch (uploadError) {
      setWizardMessage(`Upload lỗi: ${uploadError.message}`);
    } finally {
      setIsWizardBusy(false);
    }
  }

  async function previewWizardFile() {
    if (!configData || !wizardJob) return;
    setIsWizardBusy(true);
    setWizardMessage("Đang đọc preview...");
    try {
      const result = await syncApi("/api/config/preview-file", {
        method: "POST",
        body: JSON.stringify({ config: configData, file: wizardJob }),
      });
      setWizardPreview(result);
      const firstSheet = result.sheets?.[0];
      if (firstSheet) {
        const headerRow = Math.max(0, Number(firstSheet.suggested_header_row || 1) - 1);
        const sheetValue = firstSheet.name === "CSV" ? 0 : firstSheet.name;
        patchWizardNested("options", {
          sheet: sheetValue,
          header_row: headerRow,
          column_renames: buildColumnRenameMap(getPreviewHeaderCells(result, sheetValue, headerRow)),
          skip_columns: [],
        });
      }
      setWizardMessage("Đã đọc preview. Chọn sheet/header rồi sang bước Mapping.");
    } catch (previewError) {
      setWizardMessage(`Preview lỗi: ${previewError.message}`);
    } finally {
      setIsWizardBusy(false);
    }
  }

  async function saveWizardJob() {
    if (!configData || !wizardJob) return;
    const validationResult = validateJobConfig(wizardJob, 0);
    if (validationResult.messages.length) {
      setWizardMessage(`Cần kiểm tra lại: ${validationResult.messages[0]}`);
      return;
    }
    const nextConfig = {
      ...configData,
      files: [...(configData.files || []), wizardJob],
    };
    try {
      await persistConfig(nextConfig, `Đã thêm và lưu job ${wizardJob.name}.`);
      setEditingJobIndex(nextConfig.files.length - 1);
      setWizardOpen(false);
      setWizardJob(null);
    } catch {
      // persistConfig has already surfaced the error.
    }
  }

  async function dryRunWizardJob() {
    if (!configData || !wizardJob) return;
    setIsWizardBusy(true);
    setWizardMessage("Đang dry run job mới...");
    try {
      const result = await syncApi("/api/config/dry-run-file", {
        method: "POST",
        body: JSON.stringify({ config: configData, file: wizardJob }),
      });
      setWizardDryRun(result);
      setWizardMessage(`${result.sampled ? `Mẫu ${result.rows} dòng` : `${result.rows} dòng`}, ${result.columns?.length || 0} cột. Schema ${result.schema_match ? "khớp" : result.table_exists ? "chưa khớp" : "sẽ tạo mới"}.`);
    } catch (dryRunError) {
      setWizardMessage(`Dry run lỗi: ${dryRunError.message}`);
    } finally {
      setIsWizardBusy(false);
    }
  }

  function patchWizardColumnRename(source, target) {
    const nextRenames = { ...(wizardJob?.options?.column_renames || {}) };
    if (String(target || "").trim()) {
      nextRenames[source] = target;
    } else {
      delete nextRenames[source];
    }
    patchWizardNested("options", {
      column_renames: nextRenames,
    });
  }

  function patchWizardColumnSkipped(source, skipped) {
    const current = asStringList(wizardJob?.options?.skip_columns);
    const nextSkipped = skipped
      ? Array.from(new Set([...current, source]))
      : current.filter((column) => column !== source);
    patchWizardNested("options", {
      skip_columns: nextSkipped,
    });
  }

  function patchWizardPreviewOptions(patch) {
    const nextSheet = patch.sheet ?? wizardJob?.options?.sheet;
    const nextHeaderRow = patch.header_row ?? wizardJob?.options?.header_row ?? 0;
    patchWizardNested("options", {
      ...patch,
      column_renames: buildColumnRenameMap(getPreviewHeaderCells(wizardPreview, nextSheet, nextHeaderRow)),
      skip_columns: [],
    });
  }

  if (isLoading && !configData) {
    return (
      <div className="setupLoading">
        <RefreshCcw size={24} aria-hidden="true" />
        Đang tải cấu hình sync...
      </div>
    );
  }

  return (
    <>
      <SetupNoticeToast error={error} message={message} />

      {configData && (
        <div className="setupLayout">
          {setupTab === "jobs" && wizardOpen && wizardJob && (
            <Wizard onClose={() => setWizardOpen(false)}>
              <div className="wizardStepper">
                {[
                  { step: 1, label: "Chọn nguồn" },
                  { step: 2, label: "Xem trước" },
                  { step: 3, label: "Ghép cột" },
                ].map((item, index, arr) => (
                  <div key={item.step} style={{ display: "contents" }}>
                    <button
                      type="button"
                      className={`wizardStep${wizardStep === item.step ? " active" : wizardStep > item.step ? " done" : ""}`}
                      onClick={() => setWizardStep(item.step)}
                    >
                      <span className="stepNum">{wizardStep > item.step ? "✓" : item.step}</span>
                      {item.label}
                    </button>
                    {index < arr.length - 1 && <div className="wizardConnector" />}
                  </div>
                ))}
              </div>
              {wizardMessage && <div className="testResult info">{wizardMessage}</div>}

              {wizardStep === 1 && (
                <div className="wizardBody">
                  <div className="sourceModeButtons focusMode" role="group" aria-label="Chọn nguồn file wizard">
                    <button type="button" className={wizardJob.source?.type !== "onedrive" ? "active" : ""} onClick={() => changeWizardSourceType("local")}>
                      <UploadCloud size={16} aria-hidden="true" />
                      Upload file local
                    </button>
                    <button type="button" className={wizardJob.source?.type === "onedrive" ? "active" : ""} onClick={() => changeWizardSourceType("sharepoint")}>
                      <Link2 size={16} aria-hidden="true" />
                      Dán link SharePoint
                    </button>
                  </div>

                  {wizardJob.source?.type === "onedrive" ? (
                    <div className="sourceInputRow linkMode focusRow">
                      <label>
                        Link share
                        <input value={wizardJob.source?.share_url || ""} placeholder="https://...sharepoint.com/..." onChange={(event) => patchWizardNested("source", { share_url: event.target.value })} />
                      </label>
                      <label>
                        Direct download URL
                        <input value={wizardJob.source?.download_url || ""} placeholder="Tuỳ chọn nếu đã có link tải trực tiếp" onChange={(event) => patchWizardNested("source", { download_url: event.target.value })} />
                      </label>
                    </div>
                  ) : (
                    <div className="sourceInputRow focusRow">
                      <label className="filePickButton">
                        <FileSpreadsheet size={17} aria-hidden="true" />
                        Chọn file
                        <input type="file" accept=".xls,.xlsx,.xlsm,.xlsb,.csv,.tsv,text/csv" onChange={(event) => uploadWizardFile(event.target.files?.[0])} />
                      </label>
                      <label>
                        Đường dẫn file
                        <input value={wizardJob.source?.path || ""} placeholder="./uploads/report.xlsx hoặc D:/Data/report.xlsx" onChange={(event) => patchWizardNested("source", { path: event.target.value })} />
                      </label>
                    </div>
                  )}

                  <div className="wizardActions">
                    <button type="button" className="secondaryButton" onClick={previewWizardFile} disabled={isWizardBusy}>
                      <Eye size={16} aria-hidden="true" />
                      {isWizardBusy ? "Đang preview" : "Preview file"}
                    </button>
                    <button type="button" className="primary" onClick={() => setWizardStep(2)} disabled={!wizardPreview}>
                      Tiếp
                      <ChevronRight size={16} aria-hidden="true" />
                    </button>
                  </div>
                </div>
              )}

              {wizardStep === 2 && (
                <div className="wizardBody">
                  {!wizardPreview?.sheets?.length && (
                    <div className="emptyFocus">
                      <FileSpreadsheet size={24} aria-hidden="true" />
                      <strong>Chưa có preview</strong>
                      <span>Quay lại bước File/link để chọn file, hoặc bấm đọc lại nếu file vừa thay đổi.</span>
                      <button type="button" className="secondaryButton" onClick={previewWizardFile} disabled={isWizardBusy}>
                        <Eye size={16} aria-hidden="true" />
                        {isWizardBusy ? "Đang preview" : "Đọc preview"}
                      </button>
                    </div>
                  )}

                  {wizardPreview?.sheets?.length > 0 && (
                    <div className="previewPanel">
                      <div className="setupGrid compact">
                        <label>
                          Sheet
                          <select
                            value={selectedPreviewSheet(wizardPreview, wizardJob.options?.sheet)?.name || ""}
                            onChange={(event) => {
                              const selected = wizardPreview.sheets.find((sheet) => sheet.name === event.target.value);
                              patchWizardPreviewOptions({
                                sheet: selected?.name === "CSV" ? 0 : selected?.name || event.target.value,
                                header_row: Math.max(0, Number(selected?.suggested_header_row || 1) - 1),
                              });
                            }}
                          >
                            {wizardPreview.sheets.map((sheet) => (
                              <option key={sheet.name} value={sheet.name}>{sheet.name}</option>
                            ))}
                          </select>
                        </label>
                        <label>
                          Dòng header
                          <input
                            type="number"
                            min="1"
                            value={Number(wizardJob.options?.header_row || 0) + 1}
                            onChange={(event) => patchWizardPreviewOptions({ header_row: Math.max(0, Number(event.target.value || 1) - 1) })}
                          />
                        </label>
                        <label>
                          Bỏ qua dòng
                          <input value={formatList(wizardJob.options?.skip_rows)} placeholder="0, 1, 2" onChange={(event) => patchWizardNested("options", { skip_rows: parseNumberList(event.target.value) })} />
                        </label>
                        <label>
                          Cột đọc
                          <input value={wizardJob.options?.usecols || ""} placeholder="A:K hoặc cột1,cột2" onChange={(event) => patchWizardNested("options", { usecols: event.target.value || null })} />
                        </label>
                        <label>
                          Bỏ cột sau header
                          <input value={formatList(wizardJob.options?.skip_columns)} placeholder="buyer.1, note" onChange={(event) => patchWizardNested("options", { skip_columns: parseCsvList(event.target.value) })} />
                        </label>
                        <label>
                          Encoding CSV
                          <input value={wizardJob.options?.encoding || ""} onChange={(event) => patchWizardNested("options", { encoding: event.target.value })} />
                        </label>
                        <label>
                          Delimiter CSV
                          <input value={wizardJob.options?.delimiter || ""} onChange={(event) => patchWizardNested("options", { delimiter: event.target.value })} />
                        </label>
                      </div>
                      <div className="previewTableWrap">
                        <table>
                          <tbody>
                            {selectedPreviewSheet(wizardPreview, wizardJob.options?.sheet).rows.slice(0, 8).map((row, rowIndex) => (
                              <tr key={`preview-${rowIndex}`} className={rowIndex === Number(wizardJob.options?.header_row || 0) ? "previewHeaderRow" : ""}>
                                <td>{rowIndex + 1}</td>
                                {row.slice(0, 8).map((cell, cellIndex) => <td key={cellIndex}>{cell}</td>)}
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}

                  <div className="wizardActions">
                    <button type="button" className="secondaryButton" onClick={() => setWizardStep(1)}>
                      <ChevronLeft size={16} aria-hidden="true" />
                      Quay lại
                    </button>
                    <button type="button" className="primary" onClick={() => setWizardStep(3)} disabled={!wizardPreview?.sheets?.length}>
                      Tiếp
                      <ChevronRight size={16} aria-hidden="true" />
                    </button>
                  </div>
                </div>
              )}

              {wizardStep === 3 && (
                <div className="wizardBody">
                  <div className="setupGrid">
                    <label>
                      Tên job
                      <input value={wizardJob.name || ""} onChange={(event) => patchWizardJob({ name: event.target.value })} />
                    </label>
                    <label>
                      Server import
                      <ConnectionSelect
                        value={wizardJob.target?.connection_id || "default"}
                        connections={configData.database_connections}
                        onChange={selectWizardConnection}
                      />
                    </label>
                    <label>
                      Schema đích
                      <input value={wizardJob.target?.schema || ""} onChange={(event) => patchWizardNested("target", { schema: event.target.value })} />
                    </label>
                    <label>
                      Bảng đích
                      <input value={wizardJob.target?.table || ""} onChange={(event) => patchWizardNested("target", { table: event.target.value })} />
                    </label>
                    <label>
                      Chế độ sync
                      <select value={wizardJob.sync_mode || "truncate_insert"} onChange={(event) => patchWizardJob({ sync_mode: event.target.value })}>
                        <option value="truncate_insert">Xóa dữ liệu rồi import</option>
                        <option value="drop_recreate">Tạo lại bảng</option>
                        <option value="append">Thêm dòng mới, không xóa dữ liệu cũ</option>
                        <option value="upsert">Upsert theo khóa</option>
                      </select>
                    </label>
                    <label>
                      Primary key
                      <input value={formatList(wizardJob.target?.primary_key)} onChange={(event) => patchWizardNested("target", { primary_key: parseCsvList(event.target.value) })} />
                    </label>
                    <CronListEditor
                      label="Lịch riêng"
                      value={wizardJob.crons}
                      onChange={(value) => patchWizardJob({ crons: value, cron: value[0] || null })}
                    />
                  </div>
                  {wizardPreview?.sheets?.length > 0 && (
                    <div className="columnMappingPanel">
                      <div className="sectionTitle">
                        <FileSpreadsheet size={18} aria-hidden="true" />
                        <h3>Đổi tên cột trước khi import</h3>
                      </div>
                      <div className="columnMappingGrid">
                        {previewSourceHeaders(getPreviewHeaderCells(wizardPreview, wizardJob.options?.sheet, wizardJob.options?.header_row)).map((source, columnIndex) => {
                          const skipped = asStringList(wizardJob.options?.skip_columns).includes(source);
                          const suggestedName = suggestSyncColumnName(source, `column_${columnIndex + 1}`);
                          return (
                            <div className={`columnMappingRow ${skipped ? "skipped" : ""}`} key={`${source}-${columnIndex}`}>
                              <label className="checkField compact">
                                <input
                                  type="checkbox"
                                  checked={!skipped}
                                  onChange={(event) => patchWizardColumnSkipped(source, !event.target.checked)}
                                />
                                Import
                              </label>
                              <span title={source}>{source}</span>
                              <input
                                value={wizardJob.options?.column_renames?.[source] ?? suggestedName}
                                placeholder={suggestedName}
                                onChange={(event) => patchWizardColumnRename(source, event.target.value)}
                              />
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}
                  {wizardDryRun?.columns?.length > 0 && (
                    <DryRunDiffPanel result={wizardDryRun} />
                  )}
                  <div className="wizardActions">
                    <button type="button" className="secondaryButton" onClick={() => testWritePermission(wizardJob.target?.connection_id || "default", wizardJob.target?.schema)} disabled={isTestingWrite}>
                      <Play size={16} aria-hidden="true" />
                      Test quyền ghi bảng
                    </button>
                    <button type="button" className="secondaryButton" onClick={dryRunWizardJob} disabled={isWizardBusy}>
                      <Eye size={16} aria-hidden="true" />
                      Dry run
                    </button>
                    <button type="button" className="secondaryButton" onClick={() => setWizardStep(2)}>
                      <ChevronLeft size={16} aria-hidden="true" />
                      Quay lại
                    </button>
                    <button type="button" className="primary" onClick={saveWizardJob} disabled={isSaving}>
                      <Save size={16} aria-hidden="true" />
                      Lưu job
                    </button>
                  </div>
                </div>
              )}
            </Wizard>
          )}

          {setupTab === "system" && (
          <>
          <ConnectionEditor
            configData={configData}
            validation={validation}
            isDirty={isDirty}
            isLoading={isLoading}
            isSaving={isSaving}
            testingDbId={testingDbId}
            testingWriteId={testingWriteId}
            onReload={loadConfig}
            onSave={saveConfig}
            onAddConnection={addConnection}
            onPatchConnection={patchConnection}
            onRemoveConnection={removeConnection}
            onTestDatabase={testDatabase}
            onTestWrite={testWritePermission}
            connectionUsageCount={connectionUsageCount}
            toNumber={toNumber}
          />
          </>
          )}

          {setupTab === "jobs" && (
          <>
          <section className="setupSection setupJobs">
            <div className="sectionTitle withAction">
              <div>
                <Link2 size={18} aria-hidden="true" />
                <h3>File Sync Jobs</h3>
              </div>
              <ConfigActions
                isDirty={isDirty}
                isLoading={isLoading}
                isSaving={isSaving}
                canSave={Boolean(configData) && !validation.hasErrors}
                onReload={loadConfig}
                onSave={saveConfig}
                trailing={(
                  <button type="button" className="secondaryButton" onClick={addJob}>
                    <Plus size={16} aria-hidden="true" />
                    Thêm job
                  </button>
                )}
              />
            </div>

            {configData.files.length === 0 && <p className="emptyText">Chưa có job nào. Bấm Thêm job để cấu hình file đầu tiên.</p>}

            {configData.files.map((file, index) => {
              const sourceMode = file.source?.type === "onedrive" ? "sharepoint" : "local";
              const isEditing = editingJobIndex === index;
              const scheduleOnly = isEditing && editingJobMode === "schedule";
              const jobErrors = validation.jobs[index]?.fields || {};
              const jobErrorMessages = validation.jobs[index]?.messages || [];
              return (
                <JobEditor key={`job-${index}`} isEditing={isEditing}>
                  <div className="jobCompactHeader">
                    <div className="jobSummary">
                      {isEditing ? (
                        <input
                          className="jobTitleInput"
                          value={file.name || ""}
                          placeholder={`Job ${index + 1}`}
                          onChange={(event) => patchJob(index, { name: event.target.value })}
                        />
                      ) : (
                        <strong>{file.name || `Job ${index + 1}`}</strong>
                      )}
                      {!isEditing && (
                        <>
                          <span>
                            {sourceLabel(file)} · {connectionById(configData.database_connections, file.target?.connection_id || "default", configData.database).name} · {file.target?.schema || "public"}.{file.target?.table || "new_table"}
                          </span>
                          <small>{sourcePathLabel(file)}</small>
                          {jobErrorMessages.length > 0 && <small className="fieldError">{jobErrorMessages[0]}</small>}
                        </>
                      )}
                    </div>
                    <div className="jobMeta">
                      <button
                        type="button"
                        className={`jobToggleButton ${file.enabled ? "enabled" : "disabled"}`}
                        onClick={() => toggleJobEnabled(index)}
                        title={file.enabled ? "Bấm để tắt job" : "Bấm để bật job"}
                      >
                        <span />
                        {file.enabled ? "Đang bật" : "Đang tắt"}
                      </button>
                      <span className="jobScheduleText">{jobCronLabel(file)}</span>
                    </div>
                    <div className="rowActions">
                      {!isEditing && (
                        <>
                          <button type="button" onClick={() => openJobEditor(index, "details")}>
                            <Pencil size={15} aria-hidden="true" />
                            Sửa
                          </button>
                          <button type="button" onClick={() => openJobEditor(index, "schedule")}>
                            <Clock3 size={15} aria-hidden="true" />
                            Lịch
                          </button>
                        </>
                      )}
                      {isEditing && (
                        <button type="button" className="primary" onClick={saveConfig} disabled={isSaving || validation.hasErrors}>
                          <Save size={15} aria-hidden="true" />
                          {isSaving ? "Đang lưu" : "Lưu"}
                        </button>
                      )}
                      {!isEditing && (
                        <button type="button" onClick={() => copyJob(index)}>
                          <Copy size={15} aria-hidden="true" />
                          Copy
                        </button>
                      )}
                    </div>
                    {isEditing && (
                      <button type="button" className="modalCloseButton" aria-label="Đóng" onClick={() => setEditingJobIndex(-1)}>
                        ×
                      </button>
                    )}
                    {!isEditing && (
                      <button type="button" className="iconButton danger jobDeleteButton" title="Xóa job" onClick={() => removeJob(index)}>
                        <Trash2 size={16} aria-hidden="true" />
                      </button>
                    )}
                  </div>

                  {jobFeedback[index] && (
                    <>
                      <div className={`testResult ${jobFeedback[index].type}`}>
                        {jobFeedback[index].text}
                      </div>
                      {jobFeedback[index].dryRun?.columns?.length > 0 && (
                        <DryRunDiffPanel result={jobFeedback[index].dryRun} />
                      )}
                    </>
                  )}

                  {isEditing && (
                    <>
                  {jobErrorMessages.length > 0 && (
                    <div className="validationPanel">
                      {jobErrorMessages.map((item) => <span key={item}>{item}</span>)}
                    </div>
                  )}
                  {!scheduleOnly && (
                    <>
                  <div className="jobSourcePanel">
                    <div className="sourceModeButtons" role="group" aria-label="Chọn nguồn file">
                      <button type="button" className={sourceMode === "local" ? "active" : ""} onClick={() => changeSourceType(index, "local")}>
                        <UploadCloud size={16} aria-hidden="true" />
                        Upload file local
                      </button>
                      <button type="button" className={sourceMode === "sharepoint" ? "active" : ""} onClick={() => changeSourceType(index, "sharepoint")}>
                        <Link2 size={16} aria-hidden="true" />
                        Dán link SharePoint
                      </button>
                    </div>

                    {sourceMode === "local" ? (
                      <div className="sourceInputRow">
                        <label className="filePickButton">
                          <FileSpreadsheet size={17} aria-hidden="true" />
                          {uploadingJobIndex === index ? "Đang upload" : "Chọn file"}
                          <input
                            type="file"
                            accept=".xls,.xlsx,.xlsm,.xlsb,.csv,.tsv,text/csv"
                            onChange={(event) => uploadJobFile(index, event.target.files?.[0])}
                          />
                        </label>
                        <label>
                          Đường dẫn file
                          <input value={file.source?.path || ""} placeholder="./uploads/report.xlsx hoặc D:/Data/report.xlsx" onChange={(event) => patchJobNested(index, "source", { path: event.target.value })} />
                          {jobErrors.source && <small className="fieldError">{jobErrors.source}</small>}
                        </label>
                        <button type="button" className="secondaryButton" onClick={() => testJobFile(index)} disabled={testingFileIndex === index}>
                          <Play size={16} aria-hidden="true" />
                          {testingFileIndex === index ? "Đang test" : "Test file"}
                        </button>
                        <button type="button" className="secondaryButton" onClick={() => dryRunJob(index)} disabled={dryRunningJobIndex === index}>
                          <Eye size={16} aria-hidden="true" />
                          {dryRunningJobIndex === index ? "Đang dry run" : "Dry run"}
                        </button>
                      </div>
                    ) : (
                      <div className="sourceInputRow linkMode">
                        <label>
                          Link share SharePoint/OneDrive
                          <input value={file.source?.share_url || ""} placeholder="https://...sharepoint.com/..." onChange={(event) => patchJobNested(index, "source", { share_url: event.target.value })} />
                          {jobErrors.source && <small className="fieldError">{jobErrors.source}</small>}
                        </label>
                        <label>
                          Direct download URL
                          <input value={file.source?.download_url || ""} placeholder="Tuỳ chọn nếu đã có link tải trực tiếp" onChange={(event) => patchJobNested(index, "source", { download_url: event.target.value })} />
                        </label>
                        <button type="button" className="secondaryButton" onClick={() => testJobFile(index)} disabled={testingFileIndex === index}>
                          <Play size={16} aria-hidden="true" />
                          {testingFileIndex === index ? "Đang test" : "Test link"}
                        </button>
                        <button type="button" className="secondaryButton" onClick={() => dryRunJob(index)} disabled={dryRunningJobIndex === index}>
                          <Eye size={16} aria-hidden="true" />
                          {dryRunningJobIndex === index ? "Đang dry run" : "Dry run"}
                        </button>
                      </div>
                    )}
                  </div>

                  <div className="jobConfigGroup">
                    <h4>Đích import</h4>
                    <div className="setupGrid">
                      <label>
                        Server import
                        <ConnectionSelect
                          value={file.target?.connection_id || "default"}
                          connections={configData.database_connections}
                          onChange={(connectionId) => selectJobConnection(index, connectionId)}
                        />
                        {jobErrors.connection_id && <small className="fieldError">{jobErrors.connection_id}</small>}
                      </label>
                      <label>
                        Schema đích
                        <input value={file.target?.schema || ""} onChange={(event) => patchJobNested(index, "target", { schema: event.target.value })} />
                        {jobErrors.schema && <small className="fieldError">{jobErrors.schema}</small>}
                      </label>
                      <label>
                        Bảng đích
                        <input value={file.target?.table || ""} onChange={(event) => patchJobNested(index, "target", { table: event.target.value })} />
                        {jobErrors.table && <small className="fieldError">{jobErrors.table}</small>}
                      </label>
                      <label>
                        Chế độ sync
                        <select value={file.sync_mode || "truncate_insert"} onChange={(event) => patchJob(index, { sync_mode: event.target.value })}>
                          <option value="truncate_insert">Xóa dữ liệu rồi import</option>
                          <option value="drop_recreate">Tạo lại bảng</option>
                          <option value="append">Thêm dòng mới, không xóa dữ liệu cũ</option>
                          <option value="upsert">Upsert theo khóa</option>
                        </select>
                      </label>
                      <label>
                        Primary key
                        <input value={formatList(file.target?.primary_key)} placeholder="id, code" onChange={(event) => patchJobNested(index, "target", { primary_key: parseCsvList(event.target.value) })} />
                        {jobErrors.primary_key && <small className="fieldError">{jobErrors.primary_key}</small>}
                      </label>
                      <label>
                        Khi lệch schema
                        <select value={file.on_column_mismatch || "notify"} onChange={(event) => patchJob(index, { on_column_mismatch: event.target.value })}>
                          <option value="notify">Báo lỗi và dừng</option>
                          <option value="auto_recreate">Tự tạo lại bảng</option>
                          <option value="skip">Bỏ qua job</option>
                        </select>
                      </label>
                      <label className="checkField">
                        <input type="checkbox" checked={Boolean(file.skip_unchanged)} onChange={(event) => patchJob(index, { skip_unchanged: event.target.checked })} />
                        Bỏ qua nếu file không đổi
                      </label>
                    </div>
                  </div>

                    </>
                  )}

                  <div className="jobConfigGroup scheduleGroup">
                    <h4>Lịch chạy</h4>
                    <CronListEditor
                      label="Lịch riêng của job"
                      value={file.crons}
                      onChange={(value) => patchJob(index, { crons: value, cron: value[0] || null })}
                    />
                    {jobErrors.cron && <small className="fieldError">{jobErrors.cron}</small>}
                  </div>

                  {!scheduleOnly && (
                  <details className="advancedPanel" open>
                    <summary>Đọc file</summary>
                    <div className="setupGrid">
                      <label>
                        Sheet
                        <input value={file.options?.sheet ?? 0} onChange={(event) => patchJobNested(index, "options", { sheet: parseSheet(event.target.value) })} />
                      </label>
                      <label>
                        Dòng header Excel
                        <input
                          type="number"
                          min="1"
                          value={Number(file.options?.header_row || 0) + 1}
                          onChange={(event) => patchJobNested(index, "options", { header_row: Math.max(0, Number(event.target.value || 1) - 1) })}
                        />
                      </label>
                      <label>
                        Bỏ qua dòng
                        <input value={formatList(file.options?.skip_rows)} placeholder="0, 1, 2" onChange={(event) => patchJobNested(index, "options", { skip_rows: parseNumberList(event.target.value) })} />
                      </label>
                      <label>
                        Cột đọc
                        <input value={file.options?.usecols || ""} placeholder="A:K hoặc cột1,cột2" onChange={(event) => patchJobNested(index, "options", { usecols: event.target.value || null })} />
                      </label>
                      <label>
                        Bỏ cột sau header
                        <input value={formatList(file.options?.skip_columns)} placeholder="buyer.1, note" onChange={(event) => patchJobNested(index, "options", { skip_columns: parseCsvList(event.target.value) })} />
                      </label>
                      <label>
                        Delimiter CSV
                        <input value={file.options?.delimiter || ""} onChange={(event) => patchJobNested(index, "options", { delimiter: event.target.value })} />
                      </label>
                      <label className="wideField compactRenameField">
                        Đổi tên cột
                        <textarea
                          rows="2"
                          className="compactTextarea"
                          value={formatColumnRenames(file.options?.column_renames)}
                          placeholder={"Mã KH => ma_kh\nDoanh thu => doanh_thu"}
                          onChange={(event) => patchJobNested(index, "options", { column_renames: parseColumnRenamesText(event.target.value) })}
                        />
                      </label>
                    </div>
                  </details>
                  )}
                    </>
                  )}
                </JobEditor>
              );
            })}
          </section>
          </>
          )}

          {setupTab === "system" && (
          <>
          <UpdateSection
            updateConfig={{
              enabled: configData.updates.enabled,
              autoDownload: configData.updates.auto_download || configData.updates.auto_apply,
              onEnabledChange: (event) => patchSection("updates", { enabled: event.target.checked }),
              onAutoDownloadChange: (event) => patchSection("updates", { auto_download: event.target.checked, auto_apply: false }),
            }}
            updateInfo={updateInfo}
            isCheckingUpdate={isCheckingUpdate}
            isDownloadingUpdate={isDownloadingUpdate}
            isApplyingUpdate={isApplyingUpdate}
            onCheckUpdate={() => checkUpdate("check")}
            onRunPrimaryAction={runUpdatePrimaryAction}
          />

          <BackupRestore
            pendingBundle={pendingBundle}
            isImportingBundle={isImportingBundle}
            onExportBundle={exportBundle}
            onImportBundle={importBundle}
            onOpenExports={() => openAppFolder("exports")}
            onSetPendingBundle={setPendingBundle}
            onConfirmImportBundle={confirmImportBundle}
          />
          </>
          )}

          {setupTab === "notify" && (
          <section className="setupSection">
            <div className="sectionTitle withAction">
              <div>
                <Bell size={18} aria-hidden="true" />
                <h3>Thông báo</h3>
              </div>
              <ConfigActions
                isDirty={isDirty}
                isLoading={isLoading}
                isSaving={isSaving}
                canSave={Boolean(configData) && !validation.hasErrors}
                onReload={loadConfig}
                onSave={saveConfig}
              />
            </div>
            <div className="notificationLayout">
              <div className="notificationCard inlineCard">
                <div>
                  <strong>Windows toast</strong>
                  <small>Thông báo nhanh trên desktop khi chạy foreground.</small>
                </div>
                <label className="checkField">
                  <input type="checkbox" checked={Boolean(configData.notifications.windows_toast)} onChange={(event) => patchSection("notifications", { windows_toast: event.target.checked })} />
                  Bật toast
                </label>
              </div>

              <div className="notificationCard wide">
                <div className="notificationHeader">
                  <div>
                    <strong>Webhook</strong>
                    <small>Gửi POST JSON tới Teams/Slack/n8n/endpoint nội bộ.</small>
                  </div>
                  <label className="checkField">
                    <input type="checkbox" checked={Boolean(configData.notifications.webhook.enabled)} onChange={(event) => patchNested("notifications", "webhook", { enabled: event.target.checked })} />
                    Bật webhook
                  </label>
                </div>
                <div className="setupGrid">
                  <label className="wideField">
                    Webhook URL
                    <input value={configData.notifications.webhook.url || ""} placeholder="https://..." onChange={(event) => patchNested("notifications", "webhook", { url: event.target.value })} />
                  </label>
                  <button type="button" className="secondaryButton" onClick={testWebhook} disabled={isTestingWebhook}>
                    <Play size={16} aria-hidden="true" />
                    {isTestingWebhook ? "Đang test" : "Test webhook"}
                  </button>
                  <details className="advancedPanel wideField">
                    <summary>Tùy chọn nâng cao</summary>
                    <div className="setupGrid">
                      <label>
                        Timeout giây
                        <input type="number" min="1" value={configData.notifications.webhook.timeout_seconds ?? ""} onChange={(event) => patchNested("notifications", "webhook", { timeout_seconds: toNumber(event.target.value, 15) })} />
                      </label>
                      <label>
                        Gửi khi
                        <select
                          value={formatList(configData.notifications.webhook.statuses) === "success, failed, mismatch" ? "all" : formatList(configData.notifications.webhook.statuses) === "failed, mismatch" ? "errors" : "custom"}
                          onChange={(event) => patchNested("notifications", "webhook", {
                            statuses: event.target.value === "all" ? ["success", "failed", "mismatch"] : event.target.value === "errors" ? ["failed", "mismatch"] : configData.notifications.webhook.statuses,
                          })}
                        >
                          <option value="all">Thành công và lỗi</option>
                          <option value="errors">Chỉ lỗi</option>
                          <option value="custom">Tùy chỉnh</option>
                        </select>
                      </label>
                      <label className="wideField">
                        Statuses
                        <input value={formatList(configData.notifications.webhook.statuses)} placeholder="success, failed, mismatch" onChange={(event) => patchNested("notifications", "webhook", { statuses: parseCsvList(event.target.value) })} />
                      </label>
                    </div>
                  </details>
                </div>
              </div>

              <details className="notificationCard wide advancedPanel">
                <summary>Email SMTP</summary>
                <div className="notificationHeader">
                  <div>
                    <strong>Email SMTP</strong>
                    <small>Kênh cảnh báo ổn định hơn khi chạy Windows Service.</small>
                  </div>
                  <label className="checkField">
                    <input type="checkbox" checked={Boolean(configData.notifications.email.enabled)} onChange={(event) => patchNested("notifications", "email", { enabled: event.target.checked })} />
                    Bật email
                  </label>
                </div>
                <div className="setupGrid">
                  <label>
                    SMTP host
                    <input value={configData.notifications.email.smtp_host || ""} onChange={(event) => patchNested("notifications", "email", { smtp_host: event.target.value })} />
                  </label>
                  <label>
                    SMTP port
                    <input type="number" min="1" value={configData.notifications.email.smtp_port ?? ""} onChange={(event) => patchNested("notifications", "email", { smtp_port: toNumber(event.target.value, 587) })} />
                  </label>
                  <label>
                    Sender
                    <input value={configData.notifications.email.sender || ""} onChange={(event) => patchNested("notifications", "email", { sender: event.target.value })} />
                  </label>
                  <label>
                    SMTP password
                    <input type="password" autoComplete="off" value={configData.notifications.email.password || ""} onChange={(event) => patchNested("notifications", "email", { password: event.target.value })} />
                  </label>
                  <label className="wideField">
                    Recipients
                    <input value={formatList(configData.notifications.email.recipients)} placeholder="admin@company.com, bi@company.com" onChange={(event) => patchNested("notifications", "email", { recipients: parseCsvList(event.target.value) })} />
                  </label>
                </div>
              </details>
            </div>
          </section>
          )}

          {setupTab === "system" && (
          <section className="setupSection">
            <div className="sectionTitle">
              <Settings2 size={18} aria-hidden="true" />
              <h3>Nâng cao</h3>
            </div>
            <details className="advancedPanel">
              <summary>Retry, log và dọn dữ liệu cũ</summary>
              <div className="setupGrid">
                {[
                  ["db", "Database"],
                  ["file", "File đọc"],
                  ["onedrive", "SharePoint/OneDrive"],
                ].map(([key, label]) => (
                  <div className="retryGroup" key={key}>
                    <strong>{label}</strong>
                    <label>
                      Số lần thử
                      <input type="number" min="1" value={configData.retry[key]?.attempts ?? ""} onChange={(event) => patchRetry(key, { attempts: toNumber(event.target.value, 1) })} />
                    </label>
                    <label>
                      Giây chờ
                      <input type="number" min="0" value={configData.retry[key]?.delay_seconds ?? ""} onChange={(event) => patchRetry(key, { delay_seconds: toNumber(event.target.value, 0) })} />
                    </label>
                  </div>
                ))}
                <label>
                  Log level
                  <select value={configData.logging.level || "INFO"} onChange={(event) => patchSection("logging", { level: event.target.value })}>
                    <option>DEBUG</option>
                    <option>INFO</option>
                    <option>WARNING</option>
                    <option>ERROR</option>
                    <option>CRITICAL</option>
                  </select>
                </label>
                <label>
                  Thư mục log
                  <input value={configData.logging.file_dir || ""} onChange={(event) => patchSection("logging", { file_dir: event.target.value })} />
                </label>
                <label>
                  MB mỗi file log
                  <input type="number" min="1" value={configData.logging.max_file_size_mb ?? ""} onChange={(event) => patchSection("logging", { max_file_size_mb: toNumber(event.target.value, 10) })} />
                </label>
                <label>
                  Số file backup
                  <input type="number" min="0" value={configData.logging.backup_count ?? ""} onChange={(event) => patchSection("logging", { backup_count: toNumber(event.target.value, 30) })} />
                </label>
                <label className="checkField">
                  <input type="checkbox" checked={Boolean(configData.logging.log_to_db)} onChange={(event) => patchSection("logging", { log_to_db: event.target.checked })} />
                  Lưu log vào PostgreSQL
                </label>
                <label className="checkField">
                  <input type="checkbox" checked={Boolean(configData.maintenance.enabled)} onChange={(event) => patchSection("maintenance", { enabled: event.target.checked })} />
                  Tự cleanup dữ liệu cũ
                </label>
                <label>
                  Giữ sync_log ngày
                  <input type="number" min="1" value={configData.maintenance.sync_log_retention_days ?? ""} onChange={(event) => patchSection("maintenance", { sync_log_retention_days: toNumber(event.target.value, 180) })} />
                </label>
                <label>
                  Giữ downloads ngày
                  <input type="number" min="1" value={configData.maintenance.downloads_retention_days ?? ""} onChange={(event) => patchSection("maintenance", { downloads_retention_days: toNumber(event.target.value, 14) })} />
                </label>
                <label>
                  Giữ uploads ngày
                  <input type="number" min="1" value={configData.maintenance.uploads_retention_days ?? ""} onChange={(event) => patchSection("maintenance", { uploads_retention_days: toNumber(event.target.value, 365) })} />
                </label>
                <label>
                  Giữ preview cache ngày
                  <input type="number" min="1" value={configData.maintenance.preview_cache_retention_days ?? ""} onChange={(event) => patchSection("maintenance", { preview_cache_retention_days: toNumber(event.target.value, 3) })} />
                </label>
              </div>
            </details>
          </section>
          )}
        </div>
      )}
    </>
  );
}
