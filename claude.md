# Claude Code Instructions — Excel → PostgreSQL Auto-Sync

## Vai trò

Bạn đang xây dựng hệ thống **tự động đồng bộ dữ liệu từ Excel/CSV vào PostgreSQL** chạy trên Windows. Đây là dự án Python nằm trong thư mục `sync/` của repo `powerbi-data-dtl`.

---

## Bối cảnh dự án

### Hiện trạng
- Repo đã có web app (Vite + React) ở thư mục gốc — **không chỉnh sửa phần này**
- Chưa có code Python nào — bắt đầu từ đầu trong `sync/`
- User có **PostgreSQL server** đang chạy local
- File Excel nằm trên **OneDrive** (đã sync về máy local) hoặc có share link download

### Yêu cầu nghiệp vụ
1. Tự động import dữ liệu từ **nhiều file Excel/CSV** vào PostgreSQL theo lịch (giờ/ngày)
2. Nếu **cột không khớp** giữa Excel và bảng DB → thông báo + tuỳ chọn xóa bảng cũ và tạo mới
3. Ghi **log chi tiết** mỗi lần sync
4. Gửi **thông báo Windows** (toast notification) về kết quả
5. Hỗ trợ **download file từ OneDrive** share link hoặc đọc từ đường dẫn local

---

## Kiến trúc & Tech Stack

### Cấu trúc mã nguồn
```
sync/
├── main.py                    # Entry point + CLI (argparse)
├── config.yaml                # Cấu hình DB, files, schedule
├── config.example.yaml        # Template mẫu
├── requirements.txt
├── core/
│   ├── __init__.py
│   ├── scheduler.py           # APScheduler — quản lý job theo cron
│   ├── sync_engine.py         # Orchestrator: đọc → compare → import
│   ├── schema_compare.py      # So sánh cột Excel vs cột PostgreSQL
│   ├── db.py                  # PostgreSQL connection pool + COPY bulk insert
│   ├── file_reader.py         # pandas read_excel/read_csv
│   ├── onedrive.py            # Download file từ OneDrive share URL
│   └── notifier.py            # win11toast + optional email
├── logs/
└── downloads/
```

### Dependencies chính
```
pandas>=2.2              # Data processing
python-calamine>=0.3     # Fast Excel engine
psycopg2-binary>=2.9     # PostgreSQL driver (COPY protocol)
apscheduler>=3.10        # Cron-style scheduler
pyyaml>=6.0              # Config parser
win11toast>=0.36         # Windows toast notification
httpx>=0.27              # HTTP client cho OneDrive download
openpyxl>=3.1            # Fallback Excel engine
xlrd>=2.0                # Legacy .xls reader
```

---

## Quy tắc lập trình (BẮT BUỘC)

### 1. Code Style
- **Python 3.11+** — dùng modern syntax (match/case, type unions `X | None`)
- **Type hints** cho tất cả function parameters và return types
- **Docstrings** cho mỗi module, class, và public function
- Tên biến/hàm tiếng Anh, comments có thể tiếng Việt khi cần thiết
- PEP 8 formatting

### 2. Logging — KHÔNG dùng print()
```python
# ✓ Đúng
import logging
logger = logging.getLogger(__name__)
logger.info("Import %d rows into %s", row_count, table_name)

# ✗ Sai
print(f"Import {row_count} rows into {table_name}")
```

### 3. Configuration — KHÔNG hardcode
```python
# ✓ Đúng — đọc từ config
db_config = config["database"]
engine = create_connection(db_config["host"], db_config["port"], ...)

# ✗ Sai — hardcode
conn = psycopg2.connect(host="localhost", port=5432, ...)
```

### 4. Error Handling
- Mỗi file sync trong **try/except riêng** — 1 file lỗi không ảnh hưởng file khác
- Dùng **custom exceptions** cho các lỗi domain-specific:
  ```python
  class SchemaMismatchError(Exception): ...
  class FileDownloadError(Exception): ...
  class DatabaseConnectionError(Exception): ...
  ```
- Log exception **với traceback**: `logger.exception("Failed to sync %s", name)`
- Database operations luôn trong **transaction** — rollback on error

### 5. Database Best Practices
- Dùng **connection pool** (psycopg2.pool) — không tạo connection mới mỗi lần
- Bulk insert bằng **COPY protocol** (psycopg2 copy_expert) — KHÔNG dùng INSERT từng dòng
- Pattern cho bulk insert:
  ```python
  def copy_dataframe_to_table(conn, df: pd.DataFrame, table_name: str):
      """Bulk insert DataFrame using PostgreSQL COPY protocol."""
      buffer = StringIO()
      df.to_csv(buffer, index=False, header=False, sep='\t', na_rep='\\N')
      buffer.seek(0)
      with conn.cursor() as cur:
          columns = ', '.join([f'"{col}"' for col in df.columns])
          sql = f'COPY "{table_name}" ({columns}) FROM STDIN WITH (FORMAT CSV, DELIMITER E\'\\t\', NULL \'\\N\')'
          cur.copy_expert(sql, buffer)
      conn.commit()
  ```

### 6. Idempotency
- Sync phải **an toàn khi chạy lại** — không tạo duplicate data
- Mặc định dùng **TRUNCATE + INSERT** (xóa sạch rồi import lại)
- Tính **file hash** (MD5) để skip file chưa thay đổi

---

## Flow xử lý chi tiết

### Sync 1 file — sync_engine.py
```
function sync_one_file(file_config):
    1. Log: "Bắt đầu sync {name}..."

    2. LẤY FILE
       - Nếu source.type == "local": kiểm tra file tồn tại
       - Nếu source.type == "onedrive": download về ./downloads/
       - Tính MD5 hash → so sánh với lần sync trước
       - Nếu hash giống → log "Không thay đổi" → return SKIPPED

    3. ĐỌC FILE
       - pandas.read_excel() hoặc read_csv() theo extension
       - Áp dụng options: sheet, header_row, usecols, encoding
       - Clean headers: strip whitespace, lowercase, replace spaces → underscores
       - Remove completely empty rows
       - Log: "Đọc {n} dòng, {m} cột"

    4. KIỂM TRA BẢNG TỒN TẠI
       - Query: SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name = ...)
       - Nếu CHƯA CÓ → tạo bảng mới (infer types từ DataFrame) → nhảy bước 6

    5. SO SÁNH SCHEMA
       - Query information_schema.columns → lấy danh sách cột hiện tại
       - So sánh cột Excel vs cột DB
       - Nếu KHỚP → tiếp bước 6
       - Nếu KHÔNG KHỚP:
           on_column_mismatch == "auto_recreate" → DROP + CREATE TABLE → tiếp bước 6
           on_column_mismatch == "notify" → gửi notification + log WARNING → return MISMATCH
           on_column_mismatch == "skip" → log → return SKIPPED

    6. IMPORT DỮ LIỆU
       - BEGIN TRANSACTION
       - sync_mode == "truncate_insert": TRUNCATE TABLE → COPY FROM STDIN
       - sync_mode == "append": COPY FROM STDIN (không truncate)
       - COMMIT
       - Log: "✓ Import {n} dòng thành công"

    7. GHI LOG VÀO DB
       - INSERT INTO sync_log (job_name, table_name, status, rows_imported, file_hash, ...)

    8. GỬI NOTIFICATION
       - Toast: "✅ [{name}] Import {n} dòng vào {table}"

    CATCH Exception:
       - ROLLBACK
       - Log: "❌ Lỗi: {error}"
       - Ghi sync_log status = 'failed'
       - Toast: "❌ [{name}] Lỗi: {error_message}"
```

### Schema Compare — schema_compare.py
```python
@dataclass
class CompareResult:
    match: bool
    missing_in_db: list[str]      # Cột có trong Excel, không có trong DB
    extra_in_db: list[str]        # Cột có trong DB, không có trong Excel
    type_mismatches: list[dict]   # [{col, excel_type, db_type}]

def compare_schema(conn, table_name: str, df: pd.DataFrame) -> CompareResult:
    """Compare DataFrame columns against existing PostgreSQL table."""
    ...
```

### Type Mapping — khi tạo bảng mới
```python
PANDAS_TO_PG = {
    "int64":           "BIGINT",
    "int32":           "INTEGER",
    "float64":         "DOUBLE PRECISION",
    "float32":         "REAL",
    "bool":            "BOOLEAN",
    "datetime64[ns]":  "TIMESTAMP",
    "object":          "TEXT",
    "string":          "TEXT",
}
```

---

## Config Schema (config.yaml)

```yaml
database:
  host: str          # PostgreSQL host
  port: int          # Default: 5432
  name: str          # Database name
  user: str          # Username
  password: str      # Password (hoặc env var ${PG_PASSWORD})
  schema: str        # Default: "public"

schedule:
  default_cron: str  # Cron expression (e.g., "0 6 * * *")
  timezone: str      # e.g., "Asia/Ho_Chi_Minh"
  on_startup: bool   # Chạy ngay khi khởi động?

files:               # List of file configs
  - name: str                              # Tên hiển thị
    source:
      type: "local" | "onedrive"
      path: str                            # Đường dẫn local
      share_url: str                       # OneDrive share link (nếu type=onedrive)
    target:
      table: str                           # Tên bảng PostgreSQL
      schema: str                          # Schema (default: public)
    options:
      sheet: int | str                     # Sheet index hoặc tên
      header_row: int                      # Dòng header (0-indexed)
      usecols: str | null                  # Cột cần đọc
      encoding: str                        # Encoding CSV
      delimiter: str                       # Delimiter CSV
    sync_mode: str                         # truncate_insert | drop_recreate | append
    on_column_mismatch: str                # notify | auto_recreate | skip
    cron: str | null                       # Override lịch cho file này
    enabled: bool                          # Bật/tắt

notifications:
  windows_toast: bool
  email:
    enabled: bool
    smtp_host: str
    smtp_port: int
    sender: str
    password: str
    recipients: list[str]

logging:
  level: str                               # DEBUG | INFO | WARNING | ERROR
  file_dir: str                            # Thư mục log
  max_file_size_mb: int
  backup_count: int
  log_to_db: bool                          # Ghi vào bảng sync_log?
```

---

## Database Tables tự tạo

### sync_log — Lịch sử sync
```sql
CREATE TABLE IF NOT EXISTS sync_log (
    id              SERIAL PRIMARY KEY,
    job_name        VARCHAR(255) NOT NULL,
    table_name      VARCHAR(255) NOT NULL,
    started_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    finished_at     TIMESTAMP,
    status          VARCHAR(20) NOT NULL,    -- success | failed | skipped | mismatch
    rows_imported   INTEGER DEFAULT 0,
    file_hash       VARCHAR(64),
    file_path       TEXT,
    error_message   TEXT,
    details         JSONB
);

CREATE INDEX IF NOT EXISTS idx_sync_log_table ON sync_log (table_name);
CREATE INDEX IF NOT EXISTS idx_sync_log_status ON sync_log (status);
CREATE INDEX IF NOT EXISTS idx_sync_log_started ON sync_log (started_at DESC);
```

---

## CLI Commands (main.py)

```
python main.py start          # Chạy scheduler daemon
python main.py run-all        # Sync tất cả files 1 lần
python main.py run -n "name"  # Sync 1 file cụ thể
python main.py check-config   # Validate config.yaml
python main.py test-db        # Test kết nối PostgreSQL
python main.py status         # Xem kết quả sync gần nhất
```

---

## Kế hoạch triển khai

### Phase 1 — Core MVP (làm trước)
1. `requirements.txt` + project setup
2. `config.yaml` + `config.example.yaml` + parser/validator
3. `core/db.py` — connection pool, COPY bulk insert, schema query
4. `core/file_reader.py` — đọc Excel/CSV bằng pandas
5. `core/schema_compare.py` — so sánh cột
6. `core/sync_engine.py` — orchestrate sync flow
7. `main.py` — CLI với `run-all` và `run --name`
8. Logging (file + console)
9. Test end-to-end với 1 file Excel thật

### Phase 2 — Scheduling & Notifications
1. `core/scheduler.py` — APScheduler
2. `core/notifier.py` — win11toast
3. File hash tracking (skip unchanged)
4. `sync_log` table
5. `main.py start` command

### Phase 3 — OneDrive & Polish
1. `core/onedrive.py` — download từ share link
2. Email notifications
3. Retry logic (DB connection, file lock, download)
4. `check-config`, `test-db`, `status` commands

---

## Lưu ý quan trọng

> [!IMPORTANT]
> - File agent.md chứa thiết kế chi tiết toàn bộ hệ thống — tham khảo khi cần
> - KHÔNG chỉnh sửa code web app (src/, index.html, package.json)
> - Tất cả code Python nằm trong thư mục `sync/`
> - Config mẫu KHÔNG chứa credentials thật — dùng placeholder
> - Windows-only features (win11toast, registry) cần có fallback cho CI/CD

> [!WARNING]
> - psycopg2-binary chỉ dùng cho development. Production nên build psycopg2 từ source
> - File Excel có thể bị lock khi đang mở trong Excel/OneDrive → cần retry logic
> - OneDrive share link method có thể thay đổi → ưu tiên local file path
