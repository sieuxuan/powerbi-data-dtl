# Excel to PostgreSQL Sync

Phase 1-3 MVP cho he thong dong bo Excel/CSV/OneDrive vao PostgreSQL.

## Cai dat

```powershell
cd sync
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Cau hinh

Sua `config.yaml`, dat thong tin PostgreSQL va danh sach file can sync.
Co the dung bien moi truong trong dang `${PG_PASSWORD}`.
Neu muon tach thong tin server ra ngoai YAML, copy `.env.example` thanh `.env` va dien:

```text
PG_HOST=192.168.1.10
PG_PORT=5432
PG_DATABASE=powerbi_data
PG_USER=postgres
PG_PASSWORD=your_password
```

Trong `files[].options.header_row`, dung so 0-indexed: `0` la dong dau tien, `4` la dong thu 5 lam header.
Dung `files[].options.column_renames` de doi ten cot sau khi doc header, vi du:

```yaml
options:
  header_row: 3
  skip_columns:
    - "Cot khong import"
  column_renames:
    "Ma KH": "ma_kh"
    "Doanh thu": "doanh_thu"
```

`sync_mode: upsert` bat buoc co `target.primary_key`.
OneDrive MVP chi ho tro `download_url` hoac public `share_url`.

## Lenh CLI

```powershell
python main.py check-config
python main.py test-db
python main.py run-all --force
python main.py run --name "Bao cao doanh thu" --force
python main.py status
python main.py start
python main.py service install
python main.py service start
python main.py service stop
python main.py service remove
```

## Quy trinh su dung nhanh

1. Sua `config.yaml`: dien `database`, dat `files[].enabled=true`, kiem tra `source.path` hoac OneDrive `share_url`.
2. Chay `python main.py check-config` de bat loi cau hinh.
3. Chay `python main.py test-db` de kiem tra PostgreSQL va tao `sync_log`.
4. Chay thu `python main.py run-all --force`.
5. Chay nen bang `python main.py start` hoac cai Windows Service bang `python main.py service install`.

## API dashboard

Khi `api.enabled=true`, `python main.py start` mo API tai:

```text
http://127.0.0.1:8765
```

Endpoints:

- `GET /api/health`
- `GET /api/jobs`
- `GET /api/logs?limit=100`
- `POST /api/config/dry-run-file`
- `POST /api/config/test-webhook`
- `POST /api/config/import-bundle`
- `POST /api/config/preview-bundle`
- `POST /api/files/fetch-link`
- `POST /api/open-folder`
- `POST /api/update/check`
- `POST /api/update/download`
- `POST /api/update/apply`
- `POST /api/jobs/{name}/run?force=false`
- `POST /api/run-all?force=false`

Frontend Vite doc API URL tu `VITE_SYNC_API_URL`, fallback `http://127.0.0.1:8765`.

## Hanh vi chinh

- Scheduler APScheduler theo cron tung file hoac `schedule.default_cron`.
- Moi job co the dung nhieu lich qua `files[].crons`; neu khong co `crons` thi fallback ve `files[].cron`, roi `schedule.default_cron`.
- Khi chay bang `python main.py start` hoac `run-portable.bat`, runtime tu reload scheduler khi `sync/config.yaml` thay doi nen khong can restart de ap dung cron moi.
- Ghi `sync_log` vao PostgreSQL va dung hash de skip file khong doi.
- Ho tro `truncate_insert`, `drop_recreate`, `append`, `upsert`.
- Gui Windows toast, email summary va webhook neu bat trong config. Webhook mac dinh gui `success`, `failed` va `mismatch`.
- Dry run doc file, infer PostgreSQL type, so schema va test quyen ghi nhung khong import du lieu.
- API cache preview SharePoint trong `.preview_cache`, tra progress job cho dashboard va dung PostgreSQL connection pool trong tien trinh chay nen.
- Link online ho tro SharePoint/OneDrive, Google Sheets public/export, Google Drive file/direct download bang backend de tranh CORS.
- `maintenance` cau hinh retention cho `sync_log`, `downloads`, `uploads`, `.preview_cache`.
- `updates` kiem tra GitHub Releases khi scheduler khoi dong; neu `auto_download=true` thi tai asset portable moi hon `current_version`; neu `auto_apply=true` trong portable thi giai nen, copy file moi va mo lai app, giu nguyen `sync/config.yaml`, `sync/.env`, logs/uploads/downloads.
- Windows Service mac dinh: `PowerBIDataDTLSync`.
