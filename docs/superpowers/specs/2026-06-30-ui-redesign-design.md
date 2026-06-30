# UI/UX Redesign — PowerBI Data DTL
**Ngày:** 2026-06-30  
**Phạm vi:** Toàn bộ giao diện React (`src/`)  
**Mục tiêu:** Nâng cấp visual từ "functional nhưng phèn" lên Clean Professional B2B SaaS

---

## 1. Tổng quan định hướng

**Phong cách:** Clean Professional — sáng, card-based, premium B2B (tham khảo Retool, Linear)  
**Navigation:** Chuyển từ sidebar dọc → top navigation ngang  
**Nguyên tắc:** Giữ toàn bộ chức năng, bỏ những phần làm giao diện rối, dùng ngôn ngữ rõ ràng không quá kỹ thuật

---

## 2. Layout & Navigation Shell

### Header cố định (64px)
```
┌────────────────────────────────────────────────────────────────┐
│  ◈ PowerBI DTL  │  Nhập dữ liệu   Cài đặt   Giám sát   │  ●  │
└────────────────────────────────────────────────────────────────┘
```
- Brand mark bên trái: icon `Database` nhỏ + tên app
- 3 tab module ở trung tâm — active state bằng underline teal `3px`, không dùng background pill
- Góc phải: status dot nhỏ (xanh = hệ thống hoạt động, đỏ = mất kết nối)
- Màu header: `#FFFFFF`, `border-bottom: 1px solid #E5E7EB`, `box-shadow` rất nhẹ

### Workspace
- Background: `#F9FAFB`
- Container: `max-width: 1280px`, `margin: 0 auto`, `padding: 28px 32px`
- Cards: `background: #FFFFFF`, `border: 1px solid #E5E7EB`, `border-radius: 12px`

### Toast notification (giữ nguyên vị trí bottom-right)
- Redesign style: `background: #111827`, `color: #F9FAFB`, `border-radius: 10px`, `padding: 12px 16px`

---

## 3. Color System

| Token | Hex | Dùng cho |
|-------|-----|----------|
| `--bg` | `#F9FAFB` | Nền app |
| `--surface` | `#FFFFFF` | Cards, panels |
| `--border` | `#E5E7EB` | Viền card, input |
| `--text-primary` | `#111827` | Tiêu đề, text chính |
| `--text-secondary` | `#6B7280` | Meta, hint, placeholder |
| `--accent` | `#0D9488` | Button primary, tab active |
| `--accent-light` | `#F0FDFA` | Chip active, highlight |
| `--success` | `#059669` | Trạng thái thành công |
| `--error` | `#DC2626` | Lỗi, cảnh báo nghiêm trọng |
| `--warning` | `#D97706` | Cảnh báo thông thường |

---

## 4. Typography

- **Font:** Inter (giữ nguyên)
- **Heading module (h2):** `24px`, `700`, `#111827`
- **Section title (h3):** `15px`, `600`, `#374151`
- **Form label:** `12px`, `600`, `#6B7280`, `text-transform: uppercase`, `letter-spacing: 0.05em`
- **Body:** `14px`, `#374151`
- **Code/SQL:** Cascadia Code / Consolas, `13px`

---

## 5. Đổi tên nhãn giao diện (copy changes)

| Hiện tại | Mới | Lý do |
|----------|-----|-------|
| SQL Import | Nhập dữ liệu | Bớt kỹ thuật |
| Cấu hình Sync | Cài đặt | Gọn, rõ |
| Theo dõi Sync | Giám sát | Chuyên nghiệp hơn |
| Hệ SQL | Loại cơ sở dữ liệu | Rõ hơn |
| Dòng header | Dòng tiêu đề | Bớt kỹ thuật |
| Chạy lại bỏ qua hash | Bắt buộc đồng bộ lại | Người dùng hiểu ngay |
| Đưa vào Sync | Tạo lịch đồng bộ | Mô tả hành động rõ hơn |
| Force (button) | Bắt buộc | Tiếng Việt |
| Cột "Xuất" trong schema | Bao gồm | Rõ ý hơn |
| Cột "Gốc" trong schema | Tên gốc | Đầy đủ hơn |
| File/link khác | Mở file mới | Action rõ ràng |
| Copy SQL | Sao chép SQL | Thuần Việt |
| Tải .sql | Xuất file SQL | Mô tả output rõ |
| Mismatch (pill) | Lệch cấu trúc | Hiểu được ngay |
| Đưa vào Sync | Tạo lịch đồng bộ | Mô tả hành động |

---

## 6. Module: Nhập dữ liệu (SQL Import Builder)

### Màn hình chào (chưa có file)
- Card trắng căn giữa, viền dashed `#D1D5DB`, hover glow teal nhẹ
- Tiêu đề: "Kéo file vào đây hoặc chọn từ máy tính"
- 2 CTA song song: `[Chọn file]` và `[Dán link]`
- Dòng nhỏ bên dưới: "Hỗ trợ .xls, .xlsx, .csv, .tsv · SharePoint · Google Sheet · OneDrive"

### Topbar khi có project
```
sales_q2.xlsx / Sheet1                    [Mở lại ▾] [Lưu] [Sao chép SQL] [Tạo lịch đồng bộ] [↓ Xuất file SQL]
12.430 dòng · 8 cột · 6 cột được xuất
```
- Button height: `36px` (giảm từ `42px`)
- "Xuất file SQL" là primary button (teal solid), còn lại secondary (border only, no background)
- "Mở lại ▾": dropdown compact hiện 5 project gần nhất từ IndexedDB

### Settings row
- Label uppercase 12px
- "TÊN BẢNG" / "DÒNG TIÊU ĐỀ" / "LOẠI CƠ SỞ DỮ LIỆU"

### Tabs
- Underline style: `Cột & kiểu dữ liệu ━  Dữ liệu mẫu  SQL`
- Active: underline `3px solid #0D9488`, text `#111827`
- Inactive: text `#6B7280`

### Schema table
- Zebra stripe nhạt (`#F9FAFB` trên row lẻ)
- Bỏ border dọc giữa các cột
- Header cột: "Tên gốc" / "Tên cột trong bảng" / "Kiểu dữ liệu" / "Cho phép trống" / "Bao gồm"

### SQL tab
- Hai panel song song (CREATE TABLE | Chèn dữ liệu) trên màn hình rộng
- Stack dọc trên mobile
- Gộp Copy + Tải thành split button `[↓ Xuất ▾]` → dropdown: "Xuất CREATE TABLE" / "Xuất INSERT dữ liệu" / "Xuất tất cả"

---

## 7. Module: Cài đặt (Sync Setup)

- Giữ cấu trúc tab hiện tại
- Tabs đổi sang underline style thống nhất
- Job editor đang active: `border-left: 4px solid #0D9488` — visual cue rõ
- Wizard steps: đổi từ grid 3 cột → numbered stepper ngang
  ```
  ① Chọn nguồn  →  ② Cấu hình bảng  →  ③ Đặt lịch
  ```
- Form labels: uppercase 12px
- "Advanced" section: đặt cuối, label "Tùy chọn nâng cao ›"

---

## 8. Module: Giám sát (Sync Monitor)

### Metric cards (4 cards ngang)
```
┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
│ TÁC VỤ  │ │ĐANG CHẠY │ │THÀNH CÔNG│ │   LỖI    │
│    5     │ │   2 ●    │ │   48     │ │    1     │
└──────────┘ └──────────┘ └──────────┘ └──────────┘
```
- Card "Đang chạy" > 0: dot pulse animation teal
- Card "Lỗi" > 0: background `#FEF2F2`, text đỏ — alert ngay

### Bảng tác vụ
- **Bỏ cột "Hash"** — ít dùng, làm bảng chật
- Cột giữ lại: Tác vụ / Nguồn / Bảng / Lịch / Trạng thái / Số dòng / Hoàn tất / Thao tác
- Row actions: gộp "Chạy" + "Force" → split button `[▶ Chạy ▾]` dropdown "Bắt buộc đồng bộ lại"

### Header actions
- Gộp: `[▶ Đồng bộ tất cả ▾]` dropdown có "Bắt buộc đồng bộ lại"
- Giữ: `[Tải lại]`

### Status pills (mới)
| Status | Background | Text |
|--------|-----------|------|
| Thành công | `#ECFDF5` | `#065F46` |
| Lỗi | `#FEF2F2` | `#991B1B` |
| Bỏ qua | `#F3F4F6` | `#4B5563` |
| Lệch cấu trúc | `#FFFBEB` | `#92400E` |
| Đang chạy | `#EFF6FF` | `#1D4ED8` |
| Chưa chạy | `#F3F4F6` | `#6B7280` |

---

## 9. Những thứ bị loại bỏ khỏi UI

| Bỏ | Thay bằng |
|----|-----------|
| Sidebar dọc 300px | Top navigation |
| History list trong sidebar | Dropdown "Mở lại ▾" trên toolbar |
| Nút "Chạy lại bỏ qua hash" riêng | Tùy chọn trong split button |
| Cột Hash trong jobs table | Không hiển thị (vẫn có trong log) |
| Button min-height 42px | 36px — gọn hơn |
| Label tiếng kỹ thuật | Ngôn ngữ rõ ràng (xem bảng mục 5) |

---

## 10. Files thay đổi

| File | Thay đổi |
|------|---------|
| `src/styles.css` | Viết lại toàn bộ — CSS variables, layout mới |
| `src/App.jsx` | Bỏ sidebar, thêm top nav header, restructure layout |
| `src/SyncMonitor.jsx` | Metric cards, split buttons, bỏ cột hash, label mới |
| `src/SyncSetup.jsx` | Underline tabs, stepper wizard, label uppercase |

Logic xử lý dữ liệu trong `App.jsx` (parse, inference, SQL gen) **không thay đổi**.
