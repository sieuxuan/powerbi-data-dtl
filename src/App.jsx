import { useEffect, useMemo, useRef, useState } from "react";
import {
  Check,
  ChevronDown,
  Clipboard,
  Database,
  Download,
  FileSpreadsheet,
  FolderOpen,
  History,
  Link2,
  RefreshCcw,
  Save,
  Server,
  Settings2,
  Trash2,
  UploadCloud,
} from "lucide-react";
import Papa from "papaparse";
import SyncMonitor, { SYNC_API_URL, syncApi } from "./SyncMonitor.jsx";
import SyncSetup, { uploadFileToSync } from "./SyncSetup.jsx";

const DB_NAME = "sql-import-builder";
const STORE_NAME = "projects";
const MAPPING_PRESETS_KEY = "sql-import-mapping-presets-v1";
const TYPE_INFERENCE_SAMPLE_SIZE = 5000;
const INSERT_PREVIEW_LIMIT = 200;
const INSERT_BATCH_SIZE = 1000;
const DIALECTS = ["PostgreSQL", "MySQL", "SQL Server", "SQLite"];
const TYPE_OPTIONS = {
  PostgreSQL: ["INTEGER", "BIGINT", "NUMERIC", "DOUBLE PRECISION", "BOOLEAN", "DATE", "TIMESTAMP", "TEXT", "VARCHAR"],
  MySQL: ["INT", "BIGINT", "DECIMAL", "DOUBLE", "BOOLEAN", "DATE", "DATETIME", "TEXT", "VARCHAR"],
  "SQL Server": ["INT", "BIGINT", "DECIMAL", "FLOAT", "BIT", "DATE", "DATETIME2", "NVARCHAR(MAX)", "NVARCHAR"],
  SQLite: ["INTEGER", "REAL", "NUMERIC", "TEXT", "BOOLEAN", "DATE", "DATETIME"],
};

function openProjectDb() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, 1);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME, { keyPath: "id" });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function dbTransaction(mode, callback) {
  const db = await openProjectDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, mode);
    const store = tx.objectStore(STORE_NAME);
    const result = callback(store);
    tx.oncomplete = () => {
      db.close();
      resolve(result);
    };
    tx.onerror = () => {
      db.close();
      reject(tx.error);
    };
  });
}

async function getProjects() {
  const db = await openProjectDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, "readonly");
    const store = tx.objectStore(STORE_NAME);
    const request = store.getAll();
    request.onsuccess = () => {
      db.close();
      resolve(request.result.sort((a, b) => new Date(b.updatedAt) - new Date(a.updatedAt)));
    };
    request.onerror = () => {
      db.close();
      reject(request.error);
    };
  });
}

function putProject(project) {
  return dbTransaction("readwrite", (store) => store.put(project));
}

function deleteProject(id) {
  return dbTransaction("readwrite", (store) => store.delete(id));
}

function allowUiUpdate() {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

function stripDiacritics(value) {
  return value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/đ/g, "d").replace(/Đ/g, "D");
}

function cleanSqlName(value, fallback, used = new Set()) {
  const raw = String(value ?? "").trim();
  const base = stripDiacritics(raw)
    .replace(/[^\w]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .toLowerCase();
  let name = base || fallback;
  if (/^\d/.test(name)) name = `col_${name}`;
  let candidate = name;
  let index = 2;
  while (used.has(candidate)) {
    candidate = `${name}_${index}`;
    index += 1;
  }
  used.add(candidate);
  return candidate;
}

function parseDate(value) {
  if (value instanceof Date && !Number.isNaN(value.getTime())) return value;
  if (typeof value === "number" && value > 25569 && value < 80000) {
    return new Date(Math.round((value - 25569) * 86400 * 1000));
  }
  const text = String(value ?? "").trim();
  if (!text) return null;
  const isoLike = /^\d{4}[-/]\d{1,2}[-/]\d{1,2}(?:[ tT]\d{1,2}:\d{2}(?::\d{2})?)?$/;
  const dmyLike = /^\d{1,2}[-/]\d{1,2}[-/]\d{4}(?:[ tT]\d{1,2}:\d{2}(?::\d{2})?)?$/;
  if (!isoLike.test(text) && !dmyLike.test(text)) return null;
  let parsed;
  if (dmyLike.test(text)) {
    const [datePart, timePart = "00:00:00"] = text.split(/[ tT]/);
    const [day, month, year] = datePart.split(/[-/]/).map(Number);
    const [hour = 0, minute = 0, second = 0] = timePart.split(":").map(Number);
    parsed = new Date(year, month - 1, day, hour, minute, second);
  } else {
    parsed = new Date(text.replace(/\//g, "-"));
  }
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function normalizeNumber(value) {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  const text = String(value ?? "").trim();
  if (!text) return null;
  const cleaned = text.replace(/\s/g, "");
  const hasComma = cleaned.includes(",");
  const hasDot = cleaned.includes(".");
  let candidate = cleaned;
  if (hasComma && hasDot) {
    candidate = cleaned.lastIndexOf(",") > cleaned.lastIndexOf(".")
      ? cleaned.replace(/\./g, "").replace(",", ".")
      : cleaned.replace(/,/g, "");
  } else if (hasComma) {
    if (/^-?\d{1,3}(,\d{3})+$/.test(cleaned)) {
      candidate = cleaned.replace(/,/g, "");
    } else {
      candidate = cleaned.replace(",", ".");
    }
  } else if (hasDot && /^-?\d{1,3}(\.\d{3})+$/.test(cleaned)) {
    candidate = cleaned.replace(/\./g, "");
  }
  if (!/^-?\d+(\.\d+)?$/.test(candidate)) return null;
  const number = Number(candidate);
  return Number.isFinite(number) ? number : null;
}

function normalizeBoolean(value) {
  if (typeof value === "boolean") return value;
  const text = String(value ?? "").trim().toLowerCase();
  if (["true", "yes", "y", "1", "co", "có"].includes(text)) return true;
  if (["false", "no", "n", "0", "khong", "không"].includes(text)) return false;
  return null;
}

function inferColumnType(values, dialect) {
  const filled = values.filter((value) => value !== null && value !== undefined && String(value).trim() !== "");
  if (filled.length === 0) return dialect === "SQL Server" ? "NVARCHAR(MAX)" : "TEXT";

  const booleans = filled.map(normalizeBoolean);
  if (booleans.every((value) => value !== null)) return dialect === "SQL Server" ? "BIT" : "BOOLEAN";

  const numbers = filled.map(normalizeNumber);
  if (numbers.every((value) => value !== null)) {
    const integers = numbers.every(Number.isInteger);
    let maxAbs = 0;
    for (const value of numbers) {
      const absolute = Math.abs(value);
      if (absolute > maxAbs) maxAbs = absolute;
    }
    if (integers) {
      if (maxAbs > 2147483647 || maxAbs < -2147483648) return "BIGINT";
      return dialect === "MySQL" ? "INT" : "INTEGER";
    }
    const decimalPlaces = filled.reduce((max, value) => {
      const text = String(value).replace(",", ".");
      const places = text.includes(".") ? text.split(".").pop().replace(/\D/g, "").length : 0;
      return Math.max(max, Math.min(places, 8));
    }, 0);
    const precision = Math.min(Math.max(18, decimalPlaces + 10), 38);
    if (dialect === "SQLite") return "REAL";
    if (dialect === "PostgreSQL") return `NUMERIC(${precision},${decimalPlaces || 2})`;
    if (dialect === "SQL Server") return `DECIMAL(${precision},${decimalPlaces || 2})`;
    return `DECIMAL(${precision},${decimalPlaces || 2})`;
  }

  const dates = filled.map(parseDate);
  if (dates.every((value) => value !== null)) {
    const hasTime = filled.some((value) => /[ tT]\d{1,2}:\d{2}/.test(String(value)));
    if (hasTime) return dialect === "PostgreSQL" ? "TIMESTAMP" : dialect === "SQL Server" ? "DATETIME2" : "DATETIME";
    return "DATE";
  }

  let maxLength = 0;
  for (const value of filled) {
    const length = String(value).length;
    if (length > maxLength) maxLength = length;
  }
  if (dialect === "SQL Server") return maxLength <= 255 ? `NVARCHAR(${Math.max(maxLength, 32)})` : "NVARCHAR(MAX)";
  if (maxLength <= 255 && dialect !== "SQLite") return `VARCHAR(${Math.max(maxLength, 32)})`;
  return "TEXT";
}

function hasValue(value) {
  return value !== null && value !== undefined && String(value).trim() !== "";
}

function toRowArray(row) {
  if (Array.isArray(row)) return row;
  if (row === null || row === undefined) return [];
  if (row instanceof Date) return [row];
  if (typeof row === "object") {
    if (Array.isArray(row.values)) {
      return row.values.slice(1);
    }
    const numericKeys = Object.keys(row)
      .filter((key) => /^\d+$/.test(key))
      .sort((a, b) => Number(a) - Number(b));
    if (numericKeys.length) {
      return numericKeys.map((key) => row[key]);
    }
    return Object.values(row);
  }
  return [row];
}

function trimTrailingEmptyCells(row) {
  const copy = [...row];
  while (copy.length && !hasValue(copy[copy.length - 1])) {
    copy.pop();
  }
  return copy;
}

function countFilledCells(row) {
  return row.reduce((count, cell) => count + (hasValue(cell) ? 1 : 0), 0);
}

function findHeaderIndex(rows) {
  const counts = [];
  let maxFilled = 0;
  for (const row of rows) {
    const count = countFilledCells(row);
    counts.push(count);
    if (count > maxFilled) maxFilled = count;
  }
  if (maxFilled === 0) return -1;
  const minLikelyHeaderWidth = Math.max(1, Math.ceil(maxFilled * 0.6));
  for (let index = 0; index < rows.length; index += 1) {
    if (counts[index] < minLikelyHeaderWidth) continue;
    const nextRows = counts.slice(index + 1, index + 8);
    const hasDataAfter = nextRows.some((count) => count >= Math.max(1, Math.ceil(counts[index] * 0.35)));
    if (hasDataAfter) return index;
  }
  return counts.findIndex((count) => count > 0);
}

function normalizeRows(rawRows, options = {}) {
  const sourceRows = Array.isArray(rawRows) ? rawRows : [rawRows];
  const rowsAsArrays = [];
  for (const row of sourceRows) {
    rowsAsArrays.push(trimTrailingEmptyCells(toRowArray(row)));
  }
  const requestedHeaderIndex = Number.isInteger(options.headerRowIndex) ? options.headerRowIndex : null;
  const headerIndex = requestedHeaderIndex === null
    ? findHeaderIndex(rowsAsArrays)
    : Math.min(Math.max(requestedHeaderIndex, 0), Math.max(rowsAsArrays.length - 1, 0));
  if (headerIndex < 0) return { headers: [], rows: [], headerRowIndex: -1 };
  const candidateRows = trimEmptyEdgeColumns(rowsAsArrays.slice(headerIndex));
  const maxWidth = candidateRows.reduce((max, row) => Math.max(max, row.length), 0);
  if (maxWidth === 0) return { headers: [], rows: [], headerRowIndex: -1 };
  const firstRow = candidateRows[0] || [];
  const hasHeader = firstRow.some(hasValue);
  const usedHeaderNames = new Set();
  const headers = Array.from({ length: maxWidth }, (_, index) => {
    const original = hasHeader ? String(firstRow[index] ?? "").trim() : "";
    let displayName = original || `Cột ${index + 1}`;
    let unique = displayName;
    let suffix = 2;
    while (usedHeaderNames.has(unique.toLowerCase())) {
      unique = `${displayName} ${suffix}`;
      suffix += 1;
    }
    usedHeaderNames.add(unique.toLowerCase());
    return unique;
  });
  const rows = candidateRows.slice(hasHeader ? 1 : 0)
    .filter((row) => row.some(hasValue))
    .map((row) => Array.from({ length: maxWidth }, (_, index) => row[index] ?? ""));
  return { headers, rows, headerRowIndex: headerIndex, rawRows: sourceRows };
}

function trimEmptyEdgeColumns(rows) {
  if (!rows.length) return rows;
  const maxWidth = rows.reduce((max, row) => Math.max(max, row.length), 0);
  let first = 0;
  let last = maxWidth - 1;
  while (first <= last && rows.every((row) => !hasValue(row[first]))) first += 1;
  while (last >= first && rows.every((row) => !hasValue(row[last]))) last -= 1;
  if (first > last) return [];
  return rows.map((row) => row.slice(first, last + 1));
}

function buildColumns(headers, rows, dialect) {
  const used = new Set();
  const sampleRows = rows.length > TYPE_INFERENCE_SAMPLE_SIZE ? rows.slice(0, TYPE_INFERENCE_SAMPLE_SIZE) : rows;
  return headers.map((header, index) => {
    const sampleValues = sampleRows.map((row) => row[index]);
    return {
      id: crypto.randomUUID(),
      sourceName: header,
      name: cleanSqlName(header, `column_${index + 1}`, used),
      type: inferColumnType(sampleValues, dialect),
      nullable: rows.some((row) => !hasValue(row[index])),
      include: true,
    };
  });
}

function quoteIdentifier(name, dialect) {
  if (dialect === "MySQL") return `\`${name.replace(/`/g, "``")}\``;
  if (dialect === "SQL Server") return `[${name.replace(/]/g, "]]")}]`;
  return `"${name.replace(/"/g, '""')}"`;
}

function formatDateValue(value, type) {
  const date = parseDate(value);
  if (!date) return String(value ?? "");
  const yyyy = date.getFullYear();
  const mm = String(date.getMonth() + 1).padStart(2, "0");
  const dd = String(date.getDate()).padStart(2, "0");
  const hh = String(date.getHours()).padStart(2, "0");
  const mi = String(date.getMinutes()).padStart(2, "0");
  const ss = String(date.getSeconds()).padStart(2, "0");
  if (/TIME|DATETIME/i.test(type)) return `${yyyy}-${mm}-${dd} ${hh}:${mi}:${ss}`;
  return `${yyyy}-${mm}-${dd}`;
}

function sqlLiteral(value, column, dialect) {
  if (value === null || value === undefined || String(value).trim() === "") return "NULL";
  const type = column.type.toUpperCase();
  if (/INT|NUMERIC|DECIMAL|DOUBLE|FLOAT|REAL/.test(type)) {
    const number = normalizeNumber(value);
    return number === null ? "NULL" : String(number);
  }
  if (/BOOL|BIT/.test(type)) {
    const bool = normalizeBoolean(value);
    if (bool === null) return "NULL";
    if (dialect === "PostgreSQL") return bool ? "TRUE" : "FALSE";
    return bool ? "1" : "0";
  }
  if (/DATE|TIME/.test(type)) {
    return `'${formatDateValue(value, type).replace(/'/g, "''")}'`;
  }
  return `'${String(value).replace(/'/g, "''")}'`;
}

function getIncludedColumns(columns) {
  return columns
    .map((column, index) => ({ ...column, sourceIndex: index }))
    .filter((column) => column.include);
}

function generateCreateSql({ tableName, columns, dialect }) {
  const included = columns.filter((column) => column.include);
  const table = quoteIdentifier(tableName, dialect);
  const defs = included.map((column) => {
    const nullable = column.nullable ? "" : " NOT NULL";
    return `  ${quoteIdentifier(column.name, dialect)} ${column.type}${nullable}`;
  });
  return `CREATE TABLE ${table} (\n${defs.join(",\n")}\n);`;
}

function buildInsertSqlChunks({ tableName, columns, rows, dialect }, options = {}) {
  const included = getIncludedColumns(columns);
  const limit = options.limit ?? rows.length;
  const rowLimit = Math.min(rows.length, limit);
  const table = quoteIdentifier(tableName, dialect);
  const names = included.map((column) => quoteIdentifier(column.name, dialect)).join(", ");
  if (!rowLimit) {
    return ["-- File không có dòng dữ liệu để INSERT."];
  }

  const chunks = [];
  for (let start = 0; start < rowLimit; start += INSERT_BATCH_SIZE) {
    const end = Math.min(start + INSERT_BATCH_SIZE, rowLimit);
    const batchRows = [];
    for (let rowIndex = start; rowIndex < end; rowIndex += 1) {
      const row = rows[rowIndex];
      const literals = included.map((column) => sqlLiteral(row[column.sourceIndex], column, dialect));
      batchRows.push(`(${literals.join(", ")})`);
    }
    chunks.push(`INSERT INTO ${table} (${names}) VALUES\n${batchRows.join(",\n")};\n`);
    if (end < rowLimit) chunks.push("\n");
  }

  if (options.preview && rows.length > rowLimit) {
    chunks.push(`\n-- Đang xem trước ${rowLimit.toLocaleString("vi-VN")} / ${rows.length.toLocaleString("vi-VN")} dòng. Bấm "Tải full" để xuất toàn bộ dữ liệu.`);
  }
  return chunks;
}

function generateInsertSql(project, options) {
  return buildInsertSqlChunks(project, options).join("");
}

function generateSqlParts(project) {
  const create = generateCreateSql(project);
  const insertPreview = generateInsertSql(project, { limit: INSERT_PREVIEW_LIMIT, preview: true });
  return {
    createSql: create,
    insertPreviewSql: insertPreview,
    sqlPreview: `${create}\n\n${insertPreview}`,
  };
}

function withSqlParts(project) {
  return { ...project, ...generateSqlParts(project) };
}

function scoreParsedSheet(parsed) {
  let filledCells = 0;
  for (const row of parsed.rows) {
    filledCells += countFilledCells(row);
  }
  return (parsed.rows.length * 1000) + (parsed.headers.length * 50) + filledCells;
}

async function readWorkbookFile(file) {
  const XLSX = await import("@e965/xlsx");
  const buffer = await file.arrayBuffer();
  const workbook = XLSX.read(buffer, { type: "array", cellDates: true, dense: false });
  const candidates = workbook.SheetNames.map((sheetName) => {
    const worksheet = workbook.Sheets[sheetName];
    const rawRows = XLSX.utils.sheet_to_json(worksheet, {
      header: 1,
      raw: true,
      defval: "",
      blankrows: false,
    });
    const parsed = normalizeRows(rawRows);
    return { sheetName, rawRows, ...parsed, score: scoreParsedSheet(parsed) };
  }).sort((a, b) => b.score - a.score);
  const best = candidates.find((candidate) => candidate.headers.length > 0);
  if (!best) {
    throw new Error("Không tìm thấy vùng dữ liệu trong workbook.");
  }
  return best;
}

async function readFile(file) {
  const extension = file.name.split(".").pop().toLowerCase();
  if (["xls", "xlsx", "xlsm"].includes(extension)) {
    return readWorkbookFile(file);
  }
  const text = await file.text();
  const parsed = Papa.parse(text, {
    delimiter: extension === "tsv" ? "\t" : "",
    skipEmptyLines: "greedy",
  });
  if (parsed.errors.length) {
    throw new Error(parsed.errors[0].message);
  }
  const normalized = normalizeRows(parsed.data);
  return { sheetName: null, rawRows: parsed.data, ...normalized };
}

function buildProject(fileName, parsed, dialect = "PostgreSQL") {
  const rows = parsed.rows;
  const used = new Set();
  const baseName = fileName.replace(/\.[^.]+$/, "") || "import_data";
  const tableName = cleanSqlName(baseName, "import_data", used);
  const columns = buildColumns(parsed.headers, rows, dialect);
  const project = {
    id: crypto.randomUUID(),
    name: baseName,
    fileName,
    sheetName: parsed.sheetName,
    tableName,
    dialect,
    columns,
    rows,
    rawRows: parsed.rawRows || [],
    headerRowIndex: parsed.headerRowIndex,
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  };
  return withSqlParts(project);
}

function formatDateTime(value) {
  return new Intl.DateTimeFormat("vi-VN", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(new Date(value));
}

function escapeCsvValue(value) {
  if (value === null || value === undefined) return "";
  const text = value instanceof Date ? value.toISOString() : String(value);
  if (/[",\r\n]/.test(text)) return `"${text.replace(/"/g, '""')}"`;
  return text;
}

function buildSyncCsvFile(project) {
  const columns = project.columns.filter((column) => column.include);
  const columnIndexes = columns.map((column) => project.columns.findIndex((candidate) => candidate.id === column.id));
  const lines = [
    columns.map((column) => escapeCsvValue(column.name)).join(","),
    ...project.rows.map((row) => columnIndexes.map((index) => escapeCsvValue(row[index])).join(",")),
  ];
  const blob = new Blob([lines.join("\r\n")], { type: "text/csv;charset=utf-8" });
  return new File([blob], `${project.tableName || "sync_import"}.csv`, { type: "text/csv" });
}

function fileFromBase64(contentBase64, filename, type = "application/octet-stream") {
  const binary = atob(contentBase64);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return new File([bytes], filename || "linked_import.xlsx", { type });
}

function makeUniqueJobName(files, baseName) {
  const used = new Set((files || []).map((file) => file.name));
  let name = baseName || "Sync import";
  let index = 2;
  while (used.has(name)) {
    name = `${baseName} ${index}`;
    index += 1;
  }
  return name;
}

function mappingPresetKey(fileName) {
  return String(fileName || "")
    .replace(/\.[^.]+$/, "")
    .trim()
    .toLowerCase();
}

function loadMappingPresets() {
  try {
    return JSON.parse(localStorage.getItem(MAPPING_PRESETS_KEY) || "{}");
  } catch {
    return {};
  }
}

function saveMappingPreset(project) {
  const key = mappingPresetKey(project?.fileName);
  if (!key || !project?.columns?.length) return;
  const presets = loadMappingPresets();
  presets[key] = {
    updatedAt: new Date().toISOString(),
    columns: project.columns.map((column) => ({
      sourceName: column.sourceName,
      name: column.name,
      type: column.type,
      nullable: column.nullable,
      include: column.include,
    })),
  };
  localStorage.setItem(MAPPING_PRESETS_KEY, JSON.stringify(presets));
}

function applyMappingPreset(project) {
  const preset = loadMappingPresets()[mappingPresetKey(project?.fileName)];
  if (!preset?.columns?.length) return project;
  const bySource = new Map(preset.columns.map((column) => [column.sourceName, column]));
  const usedNames = new Set();
  const columns = project.columns.map((column, index) => {
    const saved = bySource.get(column.sourceName);
    if (!saved) {
      return {
        ...column,
        name: cleanSqlName(column.name, `column_${index + 1}`, usedNames),
      };
    }
    return {
      ...column,
      name: cleanSqlName(saved.name || column.name, `column_${index + 1}`, usedNames),
      type: saved.type || column.type,
      nullable: saved.nullable ?? column.nullable,
      include: saved.include ?? column.include,
    };
  });
  return withSqlParts({ ...project, columns, mappingPresetApplied: true });
}

export default function App() {
  const fileInputRef = useRef(null);
  const linkInputRef = useRef(null);
  const [project, setProject] = useState(null);
  const [projects, setProjects] = useState([]);
  const [message, setMessage] = useState("");
  const [importSourceMode, setImportSourceMode] = useState("file");
  const [importLink, setImportLink] = useState("");
  const [isReadingLink, setIsReadingLink] = useState(false);
  const [activeTab, setActiveTab] = useState("schema");
  const [activeMode, setActiveMode] = useState("builder");
  const [setupNotice, setSetupNotice] = useState("");
  const [setupFocusJob, setSetupFocusJob] = useState(null);
  const [copied, setCopied] = useState(false);

  const previewRows = useMemo(() => (project?.rows || []).slice(0, 60), [project]);
  const includedColumns = useMemo(() => project?.columns.filter((column) => column.include) || [], [project]);

  useEffect(() => {
    refreshProjects().catch((error) => setMessage(`Không tải được danh sách đã lưu: ${error.message}`));
  }, []);

  async function refreshProjects() {
    const all = await getProjects();
    setProjects(all);
  }

  async function loadFileIntoProject(file, metadata = {}) {
    if (!file) return;
    setMessage("Đang đọc file...");
    await allowUiUpdate();
    try {
      const parsed = await readFile(file);
      const next = applyMappingPreset({ ...buildProject(file.name, parsed), ...metadata });
      setProject(next);
      setActiveTab("schema");
      setMessage(`Đã đọc ${parsed.rows.length.toLocaleString("vi-VN")} dòng và ${parsed.headers.length} cột.${next.mappingPresetApplied ? " Đã áp mapping preset." : ""}`);
      await refreshProjects();
    } catch (error) {
      setMessage(`Không đọc được file: ${error.message}`);
    }
  }

  async function handleFile(file) {
    await loadFileIntoProject(file);
  }

  async function handleImportLink(urlOverride = "") {
    const url = String(urlOverride || importLink).trim();
    if (!url) return;
    setIsReadingLink(true);
    setImportLink(url);
    setMessage("Đang tải file từ link online...");
    await allowUiUpdate();
    try {
      const result = await syncApi("/api/files/fetch-link", {
        method: "POST",
        body: JSON.stringify({ url }),
      });
      const file = fileFromBase64(result.content_base64, result.filename);
      await loadFileIntoProject(file, {
        sourceLink: url,
        sourceKind: result.source_kind || "online",
      });
    } catch (error) {
      setMessage(`Không đọc được link: ${error.message}. Link Google Sheet/SharePoint cần được chia sẻ quyền xem hoặc tải xuống.`);
    } finally {
      setIsReadingLink(false);
    }
  }

  function patchProject(patch) {
    setProject((current) => {
      const next = { ...current, ...patch, updatedAt: new Date().toISOString() };
      return withSqlParts(next);
    });
  }

  function patchColumn(id, patch) {
    setProject((current) => {
      const next = {
        ...current,
        columns: current.columns.map((column) => (column.id === id ? { ...column, ...patch } : column)),
        updatedAt: new Date().toISOString(),
      };
      return withSqlParts(next);
    });
  }

  async function saveCurrentProject() {
    if (!project) return;
    const saved = withSqlParts({ ...project, updatedAt: new Date().toISOString() });
    await putProject(saved);
    saveMappingPreset(saved);
    setProject(saved);
    await refreshProjects();
    setMessage("Đã lưu dự án vào trình duyệt.");
  }

  async function loadProject(id) {
    const selected = projects.find((item) => item.id === id);
    if (selected) {
      setProject(withSqlParts(selected));
      setActiveTab("schema");
      setMessage(`Đã mở lại ${selected.name}.`);
    }
  }

  async function removeProject(id) {
    await deleteProject(id);
    if (project?.id === id) setProject(null);
    await refreshProjects();
    setMessage("Đã xóa dự án đã lưu.");
  }

  function changeDialect(dialect) {
    setProject((current) => {
      const next = {
        ...current,
        dialect,
        columns: buildColumns(current.columns.map((column) => column.sourceName), current.rows, dialect),
        updatedAt: new Date().toISOString(),
      };
      return withSqlParts(next);
    });
  }

  function changeHeaderRow(rowNumber) {
    const nextHeaderRowIndex = Math.max(0, Number(rowNumber) - 1);
    setProject((current) => {
      if (!current?.rawRows?.length) return current;
      const parsed = normalizeRows(current.rawRows, { headerRowIndex: nextHeaderRowIndex });
      const next = {
        ...current,
        columns: buildColumns(parsed.headers, parsed.rows, current.dialect),
        rows: parsed.rows,
        headerRowIndex: parsed.headerRowIndex,
        updatedAt: new Date().toISOString(),
      };
      return withSqlParts(next);
    });
    setActiveTab("schema");
    setMessage(`Đã chọn dòng ${nextHeaderRowIndex + 1} làm header.`);
  }

  async function copyText(text) {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1400);
  }

  async function copyFullSql() {
    if (!project) return;
    setMessage("Đang tạo SQL đầy đủ để copy...");
    await allowUiUpdate();
    await copyText(`${project.createSql}\n\n${generateInsertSql(project)}`);
    setMessage("Đã copy SQL đầy đủ.");
  }

  function downloadChunks(chunks, suffix) {
    if (!project || !chunks?.length) return;
    const blob = new Blob(chunks, { type: "text/sql;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${project.tableName || "import"}_${suffix}.sql`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  function downloadSql(text, suffix) {
    downloadChunks([text], suffix);
  }

  function downloadFullSql() {
    if (!project) return;
    setMessage("Đang tạo file SQL đầy đủ...");
    setTimeout(() => {
      downloadChunks([project.createSql, "\n\n", ...buildInsertSqlChunks(project)], "full");
      setMessage("Đã tạo file SQL đầy đủ.");
    }, 0);
  }

  async function addCurrentProjectToSync() {
    if (!project) return;
    setMessage("Đang đưa dữ liệu hiện tại vào Sync...");
    await allowUiUpdate();
    try {
      const configResponse = await syncApi("/api/config");
      const uploadResult = project.sourceLink ? null : await uploadFileToSync(buildSyncCsvFile(project));
      const nextConfig = configResponse.config || {};
      const files = Array.isArray(nextConfig.files) ? [...nextConfig.files] : [];
      files.push({
        name: makeUniqueJobName(files, project.name || project.tableName),
        source: project.sourceLink
          ? {
            type: "onedrive",
            share_url: project.sourceLink,
          }
          : {
            type: "local",
            path: uploadResult.path,
          },
        target: {
          table: project.tableName || "import_data",
          schema: nextConfig.database?.schema || "public",
          primary_key: [],
        },
        options: {
          sheet: project.sheetName || 0,
          header_row: project.headerRowIndex || 0,
          skip_rows: [],
          usecols: null,
          skip_columns: project.sourceLink
            ? project.columns.filter((column) => !column.include).map((column) => column.sourceName)
            : [],
          encoding: "utf-8",
          delimiter: ",",
          column_renames: Object.fromEntries(
            project.columns
              .filter((column) => column.include)
              .map((column) => [project.sourceLink ? column.sourceName : column.name, column.name]),
          ),
        },
        sync_mode: "truncate_insert",
        on_column_mismatch: "notify",
        skip_unchanged: true,
        cron: null,
        enabled: true,
      });
      nextConfig.files = files;
      await syncApi("/api/config", {
        method: "POST",
        body: JSON.stringify(nextConfig),
      });
      saveMappingPreset(project);
      setSetupNotice(`Đã thêm job sync cho bảng ${project.tableName}.`);
      setActiveMode("setup");
      setMessage(`Đã thêm job sync cho bảng ${project.tableName}.`);
    } catch (syncError) {
      setMessage(`Không thêm được vào Sync: ${syncError.message}`);
    }
  }

  function downloadFullInsertSql() {
    if (!project) return;
    setMessage("Đang tạo file INSERT đầy đủ...");
    setTimeout(() => {
      downloadChunks(buildInsertSqlChunks(project), "insert_data_full");
      setMessage("Đã tạo file INSERT đầy đủ.");
    }, 0);
  }

  function editSyncJob(name) {
    setSetupFocusJob({ name, token: Date.now() });
    setActiveMode("setup");
  }

  return (
    <main className="app">
      <section className="sidebar">
        <div className="brand">
          <Database aria-hidden="true" />
          <div>
            <h1>PowerBI Data DTL</h1>
            <p>Import, cấu hình, theo dõi sync</p>
          </div>
        </div>

        <nav className="modeNav" aria-label="Chế độ làm việc">
          <button type="button" className={activeMode === "builder" ? "active" : ""} onClick={() => setActiveMode("builder")}>
            <FileSpreadsheet size={17} aria-hidden="true" />
            SQL Import
          </button>
          <button type="button" className={activeMode === "setup" ? "active" : ""} onClick={() => setActiveMode("setup")}>
            <Settings2 size={17} aria-hidden="true" />
            Cấu hình Sync
          </button>
          <button type="button" className={activeMode === "sync" ? "active" : ""} onClick={() => setActiveMode("sync")}>
            <Server size={17} aria-hidden="true" />
            Theo dõi Sync
          </button>
        </nav>

        {activeMode === "builder" && (
          <>
        <div className="historyHeader">
          <span><History size={16} aria-hidden="true" /> Đã lưu</span>
          <button type="button" className="iconButton" title="Tải lại danh sách" onClick={refreshProjects}>
            <RefreshCcw size={16} aria-hidden="true" />
          </button>
        </div>

        <div className="historyList">
          {projects.length === 0 && <p className="emptyText">Chưa có dự án nào được lưu.</p>}
          {projects.map((item) => (
            <div className="historyItem" key={item.id}>
              <button type="button" onClick={() => loadProject(item.id)}>
                <strong>{item.name}</strong>
                <span>{item.fileName}</span>
                <small>{formatDateTime(item.updatedAt)}</small>
              </button>
              <button type="button" className="iconButton danger" title="Xóa project" onClick={() => removeProject(item.id)}>
                <Trash2 size={16} aria-hidden="true" />
              </button>
            </div>
          ))}
        </div>
          </>
        )}
      </section>

      <section className="workspace">
        {activeMode === "builder" && (
          <input
            ref={fileInputRef}
            className="hiddenInput"
            type="file"
            accept=".xls,.xlsx,.xlsm,.csv,.tsv,text/csv"
            onChange={(event) => handleFile(event.target.files?.[0])}
          />
        )}
        {activeMode === "setup" ? (
          <SyncSetup notice={setupNotice} focusJobName={setupFocusJob?.name} focusToken={setupFocusJob?.token} />
        ) : activeMode === "sync" ? (
          <SyncMonitor onEditJob={editSyncJob} />
        ) : !project ? (
          <div className="welcome">
            <FolderOpen size={42} aria-hidden="true" />
            <h2>Chọn một file để bắt đầu</h2>
            <p>Hệ thống sẽ đọc header, giữ đầy đủ cột, suy luận kiểu dữ liệu và tạo query SQL import có thể chỉnh sửa.</p>
            <div className="importSourcePanel">
              <div className="importTwoButtons" role="group" aria-label="Chọn nguồn SQL Import">
                <button type="button" className={importSourceMode === "file" ? "active" : ""} onClick={() => {
                  setImportSourceMode("file");
                  fileInputRef.current?.click();
                }}>
                  <UploadCloud size={16} aria-hidden="true" />
                  File
                </button>
                <button type="button" className={importSourceMode === "link" ? "active" : ""} onClick={() => {
                  setImportSourceMode("link");
                  if (importLink.trim()) {
                    handleImportLink();
                  } else {
                    setTimeout(() => linkInputRef.current?.focus(), 0);
                  }
                }} disabled={isReadingLink}>
                  <Link2 size={16} aria-hidden="true" />
                  {isReadingLink ? "Đang đọc" : "Dán link"}
                </button>
              </div>
              {importSourceMode === "link" && (
                <input
                  ref={linkInputRef}
                  className="importLinkInput"
                  value={importLink}
                  placeholder="Dán link SharePoint, OneDrive, Google Sheet, Excel Online..."
                  onChange={(event) => setImportLink(event.target.value)}
                  onPaste={(event) => {
                    const pasted = event.clipboardData.getData("text");
                    if (pasted) setTimeout(() => handleImportLink(pasted), 0);
                  }}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") handleImportLink();
                  }}
                />
              )}
              <small>.xls, .xlsx, .xlsm, .csv, .tsv, SharePoint/OneDrive, Google Sheet</small>
            </div>
          </div>
        ) : (
          <>
            <header className="topbar">
              <div>
                <p className="eyebrow">{project.fileName}{project.sheetName ? ` / ${project.sheetName}` : ""}</p>
                <h2>{project.name}</h2>
                <p className="meta">{project.rows.length.toLocaleString("vi-VN")} dòng, {project.columns.length} cột, {includedColumns.length} cột xuất SQL</p>
              </div>
              <div className="actions">
                <button type="button" onClick={() => setProject(null)}>
                  <FolderOpen size={17} aria-hidden="true" />
                  File/link khác
                </button>
                <button type="button" onClick={saveCurrentProject}>
                  <Save size={17} aria-hidden="true" />
                  Lưu
                </button>
                <button type="button" onClick={copyFullSql}>
                  {copied ? <Check size={17} aria-hidden="true" /> : <Clipboard size={17} aria-hidden="true" />}
                  {copied ? "Đã copy" : "Copy SQL"}
                </button>
                <button type="button" onClick={addCurrentProjectToSync}>
                  <UploadCloud size={17} aria-hidden="true" />
                  Đưa vào Sync
                </button>
                <button type="button" className="primary" onClick={downloadFullSql}>
                  <Download size={17} aria-hidden="true" />
                  Tải .sql
                </button>
              </div>
            </header>

            <div className="settingsRow">
              <label>
                Tên bảng
                <input value={project.tableName} onChange={(event) => patchProject({ tableName: event.target.value || "import_data" })} />
              </label>
              <label>
                Dòng header
                <input
                  type="number"
                  min="1"
                  max={Math.max(project.rawRows?.length || 1, 1)}
                  value={(project.headerRowIndex ?? 0) + 1}
                  disabled={!project.rawRows?.length}
                  onChange={(event) => changeHeaderRow(event.target.value)}
                />
              </label>
              <label>
                Hệ SQL
                <span className="selectWrap">
                  <select value={project.dialect} onChange={(event) => changeDialect(event.target.value)}>
                    {DIALECTS.map((dialect) => <option key={dialect}>{dialect}</option>)}
                  </select>
                  <ChevronDown size={16} aria-hidden="true" />
                </span>
              </label>
            </div>

            <nav className="tabs" aria-label="Các chế độ xem">
              <button type="button" className={activeTab === "schema" ? "active" : ""} onClick={() => setActiveTab("schema")}>
                <Settings2 size={16} aria-hidden="true" />
                Cột & kiểu dữ liệu
              </button>
              <button type="button" className={activeTab === "data" ? "active" : ""} onClick={() => setActiveTab("data")}>
                <FileSpreadsheet size={16} aria-hidden="true" />
                Dữ liệu mẫu
              </button>
              <button type="button" className={activeTab === "sql" ? "active" : ""} onClick={() => setActiveTab("sql")}>
                <Database size={16} aria-hidden="true" />
                SQL
              </button>
            </nav>

            {activeTab === "schema" && (
              <div className="tablePanel">
                <table>
                  <thead>
                    <tr>
                      <th>Gốc</th>
                      <th>Tên cột SQL</th>
                      <th>Kiểu dữ liệu</th>
                      <th>Null</th>
                      <th>Xuất</th>
                    </tr>
                  </thead>
                  <tbody>
                    {project.columns.map((column) => (
                      <tr key={column.id}>
                        <td>{column.sourceName}</td>
                        <td>
                          <input value={column.name} onChange={(event) => patchColumn(column.id, { name: event.target.value })} />
                        </td>
                        <td>
                          <select value={column.type} onChange={(event) => patchColumn(column.id, { type: event.target.value })}>
                            {TYPE_OPTIONS[project.dialect].map((type) => <option key={type}>{type}</option>)}
                            {!TYPE_OPTIONS[project.dialect].includes(column.type) && <option>{column.type}</option>}
                          </select>
                        </td>
                        <td>
                          <input type="checkbox" checked={column.nullable} onChange={(event) => patchColumn(column.id, { nullable: event.target.checked })} />
                        </td>
                        <td>
                          <input type="checkbox" checked={column.include} onChange={(event) => patchColumn(column.id, { include: event.target.checked })} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {activeTab === "data" && (
              <div className="tablePanel dataPanel">
                <table>
                  <thead>
                    <tr>{project.columns.map((column) => <th key={column.id}>{column.sourceName}</th>)}</tr>
                  </thead>
                  <tbody>
                    {previewRows.map((row, rowIndex) => (
                      <tr key={`${rowIndex}-${row.join("|")}`}>
                        {project.columns.map((column, colIndex) => <td key={column.id}>{String(row[colIndex] ?? "")}</td>)}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {activeTab === "sql" && (
              <div className="sqlPanel">
                <section className="sqlSection">
                  <div className="sqlHeader">
                    <h3>SQL tạo bảng</h3>
                    <div>
                      <button type="button" onClick={() => copyText(project.createSql)}>
                        <Clipboard size={16} aria-hidden="true" />
                        Copy
                      </button>
                      <button type="button" onClick={() => downloadSql(project.createSql, "create_table")}>
                        <Download size={16} aria-hidden="true" />
                        Tải
                      </button>
                    </div>
                  </div>
                  <textarea className="sqlBox split" value={project.createSql} readOnly spellCheck="false" />
                </section>
                <section className="sqlSection">
                  <div className="sqlHeader">
                    <h3>SQL insert dữ liệu</h3>
                    <div>
                      <button type="button" onClick={() => copyText(project.insertPreviewSql)}>
                        <Clipboard size={16} aria-hidden="true" />
                        Copy preview
                      </button>
                      <button type="button" onClick={downloadFullInsertSql}>
                        <Download size={16} aria-hidden="true" />
                        Tải full
                      </button>
                    </div>
                  </div>
                  <textarea className="sqlBox split" value={project.insertPreviewSql} readOnly spellCheck="false" />
                </section>
              </div>
            )}
          </>
        )}

        {activeMode === "builder" && message && <div className="status">{message}</div>}
      </section>
    </main>
  );
}
