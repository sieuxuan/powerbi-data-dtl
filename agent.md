# PowerBI Data DTL - Agent Notes

## Mục tiêu hiện tại

Ứng dụng chạy offline/local trên Windows để:

- Đọc Excel/CSV, chỉnh header/cột/kiểu dữ liệu và tạo SQL import.
- Cấu hình sync file local hoặc SharePoint/OneDrive public link vào PostgreSQL.
- Chạy sync thủ công hoặc theo lịch cron.
- Theo dõi job/log qua dashboard local.
- UI cấu hình sync đã chia tab và sửa job bằng drawer.

Không deploy cloud. Không cần internet khi dependencies đã có sẵn trên máy.

## Cách chạy ưu tiên

Trên máy Windows mới, chạy một file ở thư mục dự án:

```powershell
.\run.ps1
```

Hoặc double-click:

```bat
run.bat
```

Launcher sẽ:

- Tạo `sync/.venv` nếu chưa có.
- Cài Python packages từ `sync/requirements.txt`.
- Cài Node packages nếu thiếu `node_modules`.
- Tạo `sync/.env` từ `sync/.env.example` nếu chưa có.
- Kiểm tra `sync/config.yaml`.
- Bật Sync API tại `http://127.0.0.1:8765`.
- Bật frontend tại `http://127.0.0.1:5173`.

Nếu máy đã cài đủ dependency và muốn chạy nhanh:

```powershell
.\run.ps1 -NoInstall
```

## Cấu trúc chính

```text
src/
  App.jsx           SQL Import, đọc Excel/CSV, nút Đưa vào Sync
  SyncSetup.jsx     Cấu hình PostgreSQL, job, upload file, test DB/file
  SyncMonitor.jsx   Theo dõi job/log, trigger sync
  styles.css        UI chung

sync/
  main.py           CLI entry
  config.yaml       Cấu hình thật đang chạy
  .env              Biến môi trường local, nhất là PG_PASSWORD
  uploads/          File được upload từ UI
  downloads/        File tải từ SharePoint/OneDrive link
  logs/             File log
  core/
    api.py          FastAPI localhost API
    config.py       Parse/validate config.yaml
    scheduler.py    APScheduler + API runtime
    sync_engine.py  Điều phối sync
    file_reader.py  Đọc Excel/CSV
    db.py           PostgreSQL + import/upsert/log
    onedrive.py     Direct/public link download MVP
```

## Luồng user nên dùng

### 1. Cấu hình PostgreSQL

Vào `Cấu hình Sync`:

- Nhập `Host`, `Port`, `Database`, `User`, `Password`, `Schema`.
- Password có thể nhập trực tiếp để lưu vào `sync/config.yaml`.
- Hoặc giữ `${PG_PASSWORD}` và sửa `sync/.env`.
- Bấm `Test kết nối`.
- Bấm `Lưu PostgreSQL` hoặc `Lưu cấu hình`.

Khi có thay đổi chưa lưu, UI hiển thị banner cảnh báo. Chỉ khi bấm lưu thì `sync/config.yaml` mới đổi.

### 2. Thêm job sync từ màn Cấu hình Sync

Trong `File Sync Jobs`:

- Chọn `Upload file local` để upload file vào `sync/uploads`.
- Hoặc chọn `Dán link SharePoint` nếu có public/direct download link.
- Điền schema/table đích.
- Chọn sync mode:
  - `truncate_insert`: xóa dữ liệu cũ rồi import.
  - `drop_recreate`: tạo lại bảng.
  - `append`: thêm dòng mới.
  - `upsert`: yêu cầu `Primary key`.
- Điền `Dòng header Excel` theo số dòng người dùng thấy: `1` là dòng đầu.
- Trong wizard, bấm `Preview` rồi qua bước `Mapping` để đổi tên cột trước khi lưu job. Mapping này nằm ở `files[].options.column_renames`.
- Bấm `Test file` hoặc `Test link`.
- Bấm `Dry run` để đọc file/link, kiểm tra schema, test quyền ghi và xem kiểu PostgreSQL sẽ tạo, nhưng không import dòng nào.
- Với SharePoint preview, API cache file theo link/hash trong `sync/.preview_cache` để giảm tải lại khi đổi sheet/header.
- Bấm `Lưu cấu hình`.

### 3. Thêm job sync từ SQL Import

Trong `SQL Import`:

- Chọn file Excel/CSV.
- Chỉnh `Tên bảng`, `Dòng header`, tên cột, kiểu dữ liệu, cột xuất.
- Bấm `Đưa vào Sync`.

App sẽ tạo CSV đã chuẩn hóa theo schema hiện tại, upload vào `sync/uploads`, thêm job mới vào `sync/config.yaml`, rồi chuyển sang `Cấu hình Sync`.
Tên cột đã sửa trong SQL Import được giữ trong CSV và ghi kèm vào `column_renames` của job để dễ kiểm tra/sửa lại.

Lưu ý: nút này cần Sync API đang chạy. Nếu báo `Sync API đang tắt`, chạy `run.bat` hoặc `run.ps1`.

### 4. Chạy và theo dõi

Vào `Theo dõi Sync`:

- `Chạy tất cả`
- Chạy từng job
- `Force` để bỏ qua check hash
- Xem trạng thái gần nhất và log từ bảng `sync_log`

Nếu PostgreSQL chưa đúng password, monitor vẫn hiển thị job nhưng log DB có thể rỗng.

## API local

Các endpoint chính:

- `GET /api/health`
- `GET /api/config`
- `POST /api/config`
- `POST /api/config/test-db`
- `POST /api/config/test-file`
- `POST /api/config/dry-run-file`
- `POST /api/config/test-webhook`
- `POST /api/config/import-bundle`
- `POST /api/config/preview-bundle`
- `POST /api/files/upload`
- `POST /api/open-folder`
- `GET /api/jobs`
- `GET /api/logs?limit=100`
- `POST /api/jobs/{name}/run?force=false`
- `POST /api/run-all?force=false`

`POST /api/config` validate YAML trước khi ghi và tạo backup `sync/config.yaml.bak`.

## Logic quan trọng

- Header row trong backend là zero-based, nhưng UI hiển thị one-based cho dễ dùng.
- File reader tự bỏ cột trống ở đầu/cuối vùng dữ liệu.
- PostgreSQL client dùng connection pool nội bộ cho tiến trình API/scheduler.
- API job runner lưu progress state (`downloading`, `reading`, `validating`, `importing`, `done`) và Sync Monitor hiển thị khi job chạy.
- `skip_unchanged=true` dùng hash file và lần `success` gần nhất trong `sync_log`.
- Retention cleanup xóa `sync_log`, `downloads`, `uploads`, `.preview_cache` cũ theo `maintenance`.
- SharePoint/OneDrive hiện là MVP direct/public link, chưa có Microsoft Graph OAuth.
- Scheduler/service cần restart sau khi đổi cron; manual run/API dùng config mới ngay.
- Webhook notification gửi `POST` JSON dạng `{ type: "sync_result", result: {...} }` khi `notifications.webhook.enabled=true`.
- Webhook mặc định chỉ gửi status `failed` và `mismatch`; chỉnh trong `notifications.webhook.statuses` nếu cần.

## Lỗi thường gặp

### Không tải được cấu hình / Failed to fetch

Nguyên nhân gần như chắc chắn là Sync API chưa chạy hoặc port `8765` bị chặn/đổi.

Cách xử lý:

```powershell
.\run.ps1
```

Hoặc:

```powershell
cd sync
.\.venv\Scripts\python.exe main.py start
```

### PostgreSQL không lưu

UI chỉ lưu khi bấm `Lưu PostgreSQL` hoặc `Lưu cấu hình`.

Nếu password đang là `${PG_PASSWORD}`, giá trị thật nằm trong `sync/.env`, không hiện trực tiếp trong `sync/config.yaml`.

### Test DB lỗi password

Sửa một trong hai nơi:

- nhập password trực tiếp trong UI rồi lưu;
- hoặc sửa `sync/.env`:

```env
PG_PASSWORD=your_real_password
```

## Đánh giá hệ thống

Đã hoàn thành:

- MVP SQL Import.
- Header row tùy chọn.
- Bỏ cột trống đầu/cuối.
- Sync service backend, scheduler, API, log DB, hash skip, retry.
- Upload file local từ UI.
- SharePoint/OneDrive public/direct link MVP.
- Test database và test file.
- Test quyền ghi PostgreSQL theo schema.
- Wizard 3 bước PostgreSQL -> File/link -> Mapping bảng.
- Preview sheet/header từ backend trước khi lưu job.
- Mapping/rename column từ preview, dùng được cho file local và SharePoint/OneDrive link.
- Mở nhanh thư mục uploads/downloads/logs/exports từ UI qua API local.
- Webhook notification cấu hình trong UI/config.
- Test webhook từ UI.
- Dry run job: đọc file/link, infer PostgreSQL types, so schema, test quyền ghi, không import.
- Import bundle zip từ UI để restore config/.env/uploads.
- Preview bundle trước khi restore.
- Tab hóa Cấu hình Sync: PostgreSQL, Jobs, Thông báo, Backup.
- Drawer edit job thay cho bung inline.
- Preview cache cho SharePoint link và progress state khi chạy job.
- Persistent PostgreSQL connection pool trong mỗi API/scheduler process.
- Retention cleanup cho sync_log/downloads/uploads/preview cache.
- Export config bundle gồm `config.yaml`, `.env`, uploads.
- Portable bundle bằng `build_portable.ps1`, chạy bằng `run-portable.bat` không cần Node/Python cài sẵn.
- Dashboard monitor và trigger run.
- Launcher `run.ps1`/`run.bat` cho Windows.

Giới hạn hiện tại:

- Chưa có Microsoft Graph OAuth cho SharePoint private link.
- Chưa có installer đóng gói `.exe`.
- Chưa có wizard tạo PostgreSQL database/schema nếu database chưa tồn tại.
- Portable bundle cần được build trên máy có internet lần đầu để tải Python embeddable và packages.
- Chưa có menu Backup riêng; hiện Backup & Restore nằm trong Cấu hình Sync.
- Log monitor phụ thuộc PostgreSQL `sync_log`; nếu DB sai credentials thì chỉ xem được job config.

## Gợi ý cải thiện tiếp theo

1. Đóng gói thành installer Windows `.exe` có shortcut desktop và service installer.
2. Thêm SQLite local cache cho log API khi PostgreSQL offline, sau đó flush vào `sync_log`.
3. Thêm import bundle tự động từ UI.
4. Thêm wizard tạo database/schema nếu chưa tồn tại.
5. Thêm Graph OAuth cho SharePoint nội bộ private.
6. Thêm cấu hình retention cho `sync/uploads` để tránh phình dung lượng.
7. Tách Backup & Restore thành menu riêng nếu bundle/import/export bắt đầu dùng thường xuyên.
