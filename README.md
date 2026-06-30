# PowerBI Data DTL

Web app local để đọc file `.xls`, `.xlsx`, `.xlsm`, `.csv`, `.tsv`, tự suy luận schema và tạo SQL import. Dự án cũng có service Python trong `sync/` để tự động đồng bộ Excel/CSV/OneDrive vào PostgreSQL và theo dõi qua màn hình Sync Monitor.

## Chạy nhanh trên Windows

Chạy một file để bật cả frontend và Sync API:

```powershell
.\run.ps1
```

Hoặc double-click `run.bat`.

Lần sau nếu dependency đã cài đủ:

```powershell
.\run.ps1 -NoInstall
```

Ứng dụng chạy offline/local:

- Frontend: `http://127.0.0.1:5173`
- Sync API: `http://127.0.0.1:8765`

## Tạo portable bundle

Trên máy build có internet, Python/Node:

```powershell
.\build_portable.ps1
```

Bundle được tạo tại:

```text
build\PowerBIDataDTL-portable
build\PowerBIDataDTL-portable.zip
```

Chuyển file zip sang máy khác, giải nén, sửa `sync\.env` hoặc `sync\config.yaml`, rồi chạy:

```bat
run-portable.bat
```

Portable runtime mở app tại `http://127.0.0.1:8765/` và không cần Node.js/Python cài sẵn trên máy chạy. Bundle không copy log, upload, download, `.env` thật hoặc `config.yaml` thật từ máy build; file cấu hình trong bundle được tạo từ template an toàn.

## Chạy thủ công từng phần

```bash
npm install
npm run dev -- --port 5173
```

Mở `http://127.0.0.1:5173`.

## Chạy sync backend

```powershell
cd sync
pip install -r requirements.txt
python main.py check-config
python main.py start
```

Sync API mặc định chạy tại `http://127.0.0.1:8765`. Trong web app, chọn `Cấu hình Sync` để setup job, hoặc `Theo dõi Sync` để xem job, log và chạy sync thủ công.

Nếu UI báo `Failed to fetch` hoặc `Không tải được cấu hình`, Sync API chưa chạy. Chạy lại `run.bat` hoặc `.\run.ps1`.

## Tính năng SQL Import

- Đọc header và giữ đầy đủ cột trong file.
- Tự chọn sheet/vùng dữ liệu có nhiều dòng nhất trong workbook.
- Cho phép đổi dòng làm header sau khi đọc file, hữu ích khi header nằm ở các dòng sau.
- Tự bỏ các cột trống ở đầu/cuối vùng dữ liệu.
- Tự đặt tên bảng, tên cột SQL an toàn.
- Tự suy luận kiểu dữ liệu: số, boolean, ngày, datetime, text.
- Chỉnh sửa tên bảng, tên cột, kiểu dữ liệu, nullable, cột xuất SQL.
- Tạo riêng SQL `CREATE TABLE` và SQL `INSERT INTO` cho PostgreSQL, MySQL, SQL Server, SQLite.
- Với file lớn, chỉ hiển thị preview INSERT 200 dòng; nút `Tải full` mới xuất toàn bộ INSERT theo batch để tránh treo giao diện.
- Lưu dự án vào IndexedDB của trình duyệt và mở lại từ danh sách đã lưu.
- Copy SQL hoặc tải file `.sql`.
- Đọc trực tiếp file Excel cũ `.xls` bằng parser legacy, không cần convert trước.
- `SQL Import` có 2 cửa vào chính: chọn file local hoặc dán link SharePoint/OneDrive/Google Sheet/Excel online; link được backend tải về để tránh CORS.
- Nút `Đưa vào Sync` thêm job sync tương ứng vào `sync/config.yaml`; nếu nguồn là link online thì giữ link để lần sau tải lại dữ liệu mới, nếu nguồn là file local thì tạo CSV chuẩn hóa trong `sync/uploads`.

## Cấu hình Sync trong app

- Màn `Cấu hình Sync` được chia tab: `Jobs & wizard`, `SQL, API, update`, `Thông báo`.
- `SQL, API, update`: nhập PostgreSQL, test kết nối/quyền ghi, cấu hình API local, download, GitHub update, backup/restore, retry/log.
- Bấm `Test quyền ghi` để kiểm tra user có tạo/insert/drop bảng test trong schema đích được không.
- `Lịch chạy`: chọn giờ chạy hằng ngày, mỗi giờ, hoặc nhập cron tùy chỉnh.
- `Thêm job` mở wizard 3 bước: File/link -> Preview -> Mapping bảng; wizard không bắt setup lại SQL.
- Wizard có checklist `Preview file`, `Dry run`; `Preview` dùng cache cho link SharePoint để đổi sheet/header không tải lại link nhiều lần.
- Trong bước `Mapping`, có thể đổi tên cột từ preview trước khi import; mapping này cũng dùng được cho link SharePoint/OneDrive.
- `File Sync Jobs`: chọn `Upload file local` để đưa file vào `sync/uploads`, hoặc `Dán link SharePoint` để dùng link SharePoint/OneDrive public/direct download.
- Sửa job mở dạng drawer bên phải để danh sách job không bị kéo dài.
- Mỗi job có nút `Test file`/`Test link` để đọc thử file, trả số dòng/cột và danh sách cột trước khi lưu/chạy.
- `Dòng header Excel` dùng số dòng dễ hiểu: `1` là dòng đầu tiên, `5` là dòng thứ 5.
- `API & Download` có nút mở nhanh thư mục `uploads`, `downloads`, `logs`, `exports`.
- `Thông báo` hỗ trợ Windows toast, email và webhook POST JSON. Webhook mặc định tắt; chỉ cần bật và dán URL khi có endpoint.
- Có nút `Test webhook`; webhook mặc định gửi `success`, `failed`, `mismatch`.
- Nếu chọn `upsert`, điền `Primary key` rõ ràng, ví dụ `id` hoặc `id, branch_code`.
- Nút `Dry run` đọc file/link, preview kiểu dữ liệu PostgreSQL, so schema và test quyền ghi nhưng không import dữ liệu.
- `Backup & Restore` cho export/import bundle zip gồm `sync/config.yaml`, `sync/.env` và `sync/uploads` để chuyển máy/backup.
- `Retry & Log` có retention cleanup cho `sync_log`, `downloads`, `uploads`, `.preview_cache`.
- `Cập nhật GitHub` kiểm tra GitHub Releases của `sieuxuan/powerbi-data-dtl`; portable có thể tự tải, giải nén, copy file mới và mở lại app, đồng thời giữ nguyên `sync/config.yaml`, `sync/.env`, logs/uploads/downloads.

## Tính năng Sync Monitor

- Xem danh sách job trong `sync/config.yaml`.
- Xem progress khi job chạy: tải file, đọc file, kiểm tra, import, hoàn tất.
- Xem trạng thái lần chạy gần nhất và log trong PostgreSQL `sync_log`.
- Chạy một job hoặc chạy tất cả job từ giao diện.
- Hỗ trợ `truncate_insert`, `drop_recreate`, `append`, `upsert`, skip file không đổi theo hash.

## Cấu hình PostgreSQL

Điền server PostgreSQL trong màn `Cấu hình Sync`, bấm `Test kết nối`, sau đó bấm `Lưu PostgreSQL` hoặc `Lưu cấu hình`.

Nếu dùng `${PG_PASSWORD}`, copy `sync/.env.example` thành `sync/.env` rồi đặt `PG_PASSWORD`. Nếu nhập password trực tiếp trong UI thì password được lưu vào `sync/config.yaml`.
