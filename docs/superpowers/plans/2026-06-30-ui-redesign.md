# UI/UX Redesign — Clean Professional Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the entire UI from a plain sidebar-based layout to a clean, professional top-nav B2B SaaS interface without changing any data/logic code.

**Architecture:** Remove the 300px dark sidebar; add a 60px fixed top header with brand + 3 module tabs + API status dot. Rewrite `styles.css` with CSS custom properties. Update JSX in 3 component files for structure, class names, and copy only — zero logic changes.

**Tech Stack:** React 18, Vite, Lucide React icons, Inter font (already loaded), existing CSS (full rewrite)

## Global Constraints

- **Never touch logic code** — functions like `normalizeRows`, `buildColumns`, `inferColumnType`, `generateCreateSql`, `buildInsertSqlChunks`, `syncApi`, `normalizeConfig`, `normalizeFile` and all data helpers stay byte-for-byte identical.
- All 4 source files live in `src/` — `styles.css`, `App.jsx`, `SyncMonitor.jsx`, `SyncSetup.jsx`
- Dev server: `npm run dev` (Vite, port 5173)
- Button min-height: **36px** everywhere (was 42px)
- CSS custom properties prefix: `--` (no Tailwind, no external CSS lib)
- Copy changes are specified exactly in the spec at `docs/superpowers/specs/2026-06-30-ui-redesign-design.md`

---

## File Map

| File | What changes |
|------|-------------|
| `src/styles.css` | Full rewrite — design tokens, new layout, all component styles |
| `src/App.jsx` | Remove sidebar, add top header, update welcome screen, add history dropdown, update button classes + labels |
| `src/SyncMonitor.jsx` | Metric cards, remove hash column, split run buttons, rename labels |
| `src/SyncSetup.jsx` | Underline tabs, numbered stepper wizard, job editor left border, uppercase labels |

---

## Task 1: CSS Foundation — Complete Rewrite of styles.css

**Files:**
- Modify: `src/styles.css` (full rewrite — replace entire contents)

**Produces:** All new CSS classes consumed by Tasks 2-5. If this task is done correctly, the existing JSX will render differently but not break.

- [ ] **Step 1: Replace styles.css with the complete new file**

Open `src/styles.css` and replace the entire contents with:

```css
/* ============================
   DESIGN TOKENS
   ============================ */
:root {
  --bg: #F9FAFB;
  --surface: #FFFFFF;
  --border: #E5E7EB;
  --text-primary: #111827;
  --text-secondary: #6B7280;
  --accent: #0D9488;
  --accent-hover: #0F766E;
  --accent-light: #F0FDFA;
  --success-bg: #ECFDF5;
  --success-text: #065F46;
  --error-bg: #FEF2F2;
  --error-text: #991B1B;
  --warning-bg: #FFFBEB;
  --warning-text: #92400E;
  --info-bg: #EFF6FF;
  --info-text: #1D4ED8;
  --radius-sm: 6px;
  --radius-md: 8px;
  --radius-lg: 12px;
  --shadow-sm: 0 1px 2px rgba(0,0,0,0.05);
  --shadow-md: 0 4px 12px rgba(0,0,0,0.08);
}

/* ============================
   RESET + BASE
   ============================ */
*, *::before, *::after { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text-primary); }
:root {
  color-scheme: light;
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
  font-size: 14px;
  line-height: 1.5;
}
button, input, select, textarea { font: inherit; }
button { cursor: pointer; }
button:disabled { cursor: not-allowed; opacity: 0.5; }

/* ============================
   APP SHELL
   ============================ */
.app {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

/* ============================
   HEADER + NAV
   ============================ */
.appHeader {
  position: sticky;
  top: 0;
  z-index: 100;
  height: 60px;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  box-shadow: var(--shadow-sm);
  display: flex;
  align-items: center;
  padding: 0 24px;
  gap: 32px;
}

.appBrand {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
  text-decoration: none;
}

.appBrand svg { color: var(--accent); }
.appBrand span {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-primary);
  white-space: nowrap;
}

.appNav {
  display: flex;
  align-items: stretch;
  gap: 2px;
  flex: 1;
  height: 100%;
}

.appNav button {
  border: 0;
  background: transparent;
  color: var(--text-secondary);
  font-size: 14px;
  font-weight: 600;
  padding: 0 16px;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  border-bottom: 3px solid transparent;
  cursor: pointer;
  white-space: nowrap;
  transition: color 0.15s, border-color 0.15s;
}

.appNav button:hover { color: var(--text-primary); }
.appNav button.active { color: var(--accent); border-bottom-color: var(--accent); }

.appStatus {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-secondary);
  white-space: nowrap;
}

.statusDot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #D1D5DB;
  flex-shrink: 0;
}
.statusDot.online { background: #10B981; }
.statusDot.offline { background: #EF4444; }

/* ============================
   WORKSPACE
   ============================ */
.workspace {
  flex: 1;
  min-width: 0;
  padding: 28px 32px;
  max-width: 1280px;
  width: 100%;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* ============================
   BUTTONS
   ============================ */
.btn {
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface);
  color: var(--text-primary);
  font-size: 13px;
  font-weight: 600;
  min-height: 36px;
  padding: 0 14px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  cursor: pointer;
  white-space: nowrap;
  transition: background 0.12s, border-color 0.12s;
}
.btn:hover { background: #F3F4F6; }
.btn.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
.btn.primary:hover { background: var(--accent-hover); border-color: var(--accent-hover); }
.btn.danger { color: #B91C1C; border-color: #FECACA; }
.btn.danger:hover { background: var(--error-bg); }

/* actions row — reuses .btn pattern */
.actions button {
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface);
  color: var(--text-primary);
  font-size: 13px;
  font-weight: 600;
  min-height: 36px;
  padding: 0 14px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  cursor: pointer;
  white-space: nowrap;
}
.actions button:hover { background: #F3F4F6; }
.actions button.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
.actions button.primary:hover { background: var(--accent-hover); border-color: var(--accent-hover); }

/* Icon-only button */
.iconButton {
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface);
  color: var(--text-secondary);
  min-width: 36px;
  height: 36px;
  padding: 0;
  display: inline-grid;
  place-items: center;
  cursor: pointer;
}
.iconButton:hover { background: #F3F4F6; color: var(--text-primary); }
.iconButton.danger { color: #B91C1C; border-color: #FECACA; }
.iconButton.danger:hover { background: var(--error-bg); }

/* Split button */
.splitBtn { display: inline-flex; align-items: center; }

.splitBtn .splitMain {
  border: 1px solid var(--border);
  border-right: 0;
  border-radius: var(--radius-sm) 0 0 var(--radius-sm);
  background: var(--surface);
  color: var(--text-primary);
  font-size: 13px;
  font-weight: 600;
  min-height: 36px;
  padding: 0 12px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  white-space: nowrap;
}
.splitBtn .splitMain:hover { background: #F3F4F6; }
.splitBtn.primary .splitMain { background: var(--accent); border-color: var(--accent); color: #fff; }
.splitBtn.primary .splitMain:hover { background: var(--accent-hover); }

.splitBtn .splitArrow {
  border: 1px solid var(--border);
  border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
  background: var(--surface);
  color: var(--text-secondary);
  min-width: 28px;
  height: 36px;
  padding: 0;
  display: inline-grid;
  place-items: center;
  cursor: pointer;
}
.splitBtn.primary .splitArrow { background: var(--accent-hover); border-color: var(--accent-hover); color: #fff; }
.splitBtn .splitArrow:hover { background: #F3F4F6; }
.splitBtn.primary .splitArrow:hover { background: #115E59; }

/* Dropdown */
.dropdownWrap { position: relative; display: inline-flex; }

.dropdown {
  position: absolute;
  top: calc(100% + 4px);
  right: 0;
  min-width: 210px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-md);
  z-index: 200;
  overflow: hidden;
}

.dropdown button {
  width: 100%;
  border: 0;
  background: transparent;
  text-align: left;
  padding: 9px 14px;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 0;
}
.dropdown button:hover { background: #F9FAFB; }
.dropdown hr { border: 0; border-top: 1px solid var(--border); margin: 3px 0; }

/* Row action buttons */
.rowActions { display: flex; gap: 5px; align-items: center; }
.rowActions button {
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  min-height: 32px;
  padding: 0 9px;
  background: var(--surface);
  color: var(--text-primary);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  font-weight: 600;
  font-size: 13px;
  cursor: pointer;
}
.rowActions button:hover { background: #F3F4F6; }
.rowActions .splitBtn .splitMain { min-height: 32px; }
.rowActions .splitBtn .splitArrow { height: 32px; }

/* Secondary button (used in setup/wizard) */
.secondaryButton {
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  min-height: 34px;
  padding: 0 12px;
  background: var(--surface);
  color: var(--text-primary);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  font-weight: 600;
  font-size: 13px;
  cursor: pointer;
}
.secondaryButton:hover { background: #F3F4F6; }

.uploadButton {
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface);
  color: var(--text-primary);
  font-size: 13px;
  font-weight: 600;
  min-height: 36px;
  padding: 0 16px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  cursor: pointer;
  width: 100%;
}
.uploadButton:hover { background: #F3F4F6; }

/* ============================
   CARDS + PANELS
   ============================ */
.card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); }

.panel {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: 16px;
  display: grid;
  gap: 14px;
}

/* ============================
   FORMS + LABELS
   ============================ */
label {
  display: grid;
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

input, select, textarea {
  width: 100%;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface);
  color: var(--text-primary);
  font-size: 14px;
}
input, select { min-height: 36px; padding: 0 10px; }
textarea { min-height: 90px; padding: 8px 10px; resize: vertical; }

input:focus, select:focus, textarea:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 3px rgba(13, 148, 136, 0.1);
}

.selectWrap { position: relative; display: block; }
.selectWrap select { appearance: none; padding-right: 32px; }
.selectWrap svg { position: absolute; top: 10px; right: 10px; pointer-events: none; color: var(--text-secondary); }

.checkField {
  min-height: 36px;
  display: flex !important;
  flex-direction: row;
  align-items: center;
  gap: 8px;
  color: var(--text-primary);
  text-transform: none;
  letter-spacing: 0;
  font-size: 14px;
  font-weight: 500;
}
.checkField input { width: 16px; height: 16px; flex: 0 0 auto; accent-color: var(--accent); }
.checkField.compact { font-size: 13px; min-height: 0; }
.checkField.compact input { width: 15px; height: 15px; }

.helperText { margin: 0; color: var(--text-secondary); font-size: 13px; }

/* ============================
   TABS (underline style)
   ============================ */
.tabs {
  display: flex;
  gap: 0;
  border-bottom: 1px solid var(--border);
  overflow-x: auto;
}
.tabs button {
  border: 0;
  background: transparent;
  color: var(--text-secondary);
  font-size: 14px;
  font-weight: 600;
  padding: 10px 16px;
  border-bottom: 3px solid transparent;
  margin-bottom: -1px;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  white-space: nowrap;
  cursor: pointer;
  transition: color 0.15s;
}
.tabs button:hover { color: var(--text-primary); }
.tabs button.active { color: var(--accent); border-bottom-color: var(--accent); }

/* alias for SyncSetup */
.setupTabs { display: flex; gap: 0; border-bottom: 1px solid var(--border); overflow-x: auto; padding-bottom: 0; }
.setupTabs button {
  border: 0;
  background: transparent;
  color: var(--text-secondary);
  font-size: 14px;
  font-weight: 600;
  padding: 10px 16px;
  border-bottom: 3px solid transparent;
  margin-bottom: -1px;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  white-space: nowrap;
  cursor: pointer;
}
.setupTabs button:hover { color: var(--text-primary); }
.setupTabs button.active { color: var(--accent); border-bottom-color: var(--accent); }

/* ============================
   TABLES
   ============================ */
.tablePanel {
  overflow: auto;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
  max-height: calc(100vh - 280px);
}
table { border-collapse: collapse; width: 100%; min-width: 760px; }
th, td {
  border-bottom: 1px solid #F3F4F6;
  padding: 10px 14px;
  text-align: left;
  vertical-align: middle;
  font-size: 13px;
}
th {
  position: sticky;
  top: 0;
  z-index: 1;
  background: #F9FAFB;
  color: var(--text-secondary);
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  border-bottom: 1px solid var(--border);
}
tbody tr:hover td { background: var(--accent-light); }
td input[type="checkbox"] { width: 16px; height: 16px; accent-color: var(--accent); }

.dataPanel td { max-width: 260px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.syncTable { max-height: none; }
.syncTable td strong, .syncTable td small { display: block; }
.syncTable td small { margin-top: 3px; color: var(--text-secondary); font-size: 12px; }
.logsTable { max-height: 360px; }

.hashCell { max-width: 160px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-family: "Cascadia Code", Consolas, monospace; font-size: 12px; color: var(--text-secondary); }
.errorText { color: var(--error-text); font-size: 12px; }

/* ============================
   STATUS PILLS
   ============================ */
.statusPill {
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  min-height: 22px;
  padding: 0 9px;
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
  background: #F3F4F6;
  color: #4B5563;
}
.statusPill.success { background: var(--success-bg); color: var(--success-text); }
.statusPill.failed, .statusPill.mismatch { background: var(--error-bg); color: var(--error-text); }
.statusPill.skipped, .statusPill.idle { background: #F3F4F6; color: #4B5563; }
.statusPill.running { background: var(--info-bg); color: var(--info-text); }

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.35; }
}
.pulseDot {
  width: 6px; height: 6px; border-radius: 50%;
  background: currentColor;
  animation: pulse 1.4s ease-in-out infinite;
  flex-shrink: 0;
}

/* ============================
   WELCOME / UPLOAD
   ============================ */
.welcome {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 48px 0;
}

.uploadCard {
  width: min(520px, 100%);
  background: var(--surface);
  border: 2px dashed #D1D5DB;
  border-radius: var(--radius-lg);
  padding: 48px 40px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 14px;
  text-align: center;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.uploadCard:hover, .uploadCard.dragging {
  border-color: var(--accent);
  box-shadow: 0 0 0 4px rgba(13, 148, 136, 0.08);
}
.uploadCard svg { color: var(--accent); }
.uploadCard h2 { margin: 0; font-size: 18px; font-weight: 700; color: var(--text-primary); }
.uploadCard p { margin: 0; color: var(--text-secondary); font-size: 13px; }
.uploadActions { display: flex; gap: 10px; flex-wrap: wrap; justify-content: center; margin-top: 4px; }

.importLinkInput { width: 100%; min-height: 36px; }
.hiddenInput { display: none; }

/* ============================
   TOPBAR + ACTIONS
   ============================ */
.topbar {
  display: flex;
  gap: 16px;
  align-items: flex-start;
  justify-content: space-between;
  flex-wrap: wrap;
}
.topbarMeta { min-width: 0; }
.eyebrow { margin: 0 0 4px; color: var(--text-secondary); font-size: 12px; font-weight: 500; }
.topbar h2 { margin: 0; font-size: 22px; font-weight: 700; }
.meta, .metaLine { margin: 4px 0 0; color: var(--text-secondary); font-size: 13px; }
.actions { display: flex; gap: 6px; flex-wrap: wrap; align-items: center; flex-shrink: 0; }

/* ============================
   SETTINGS ROW
   ============================ */
.settingsRow {
  display: grid;
  grid-template-columns: minmax(240px, 1fr) 160px 240px;
  gap: 12px;
  align-items: end;
}

/* ============================
   SQL PANEL
   ============================ */
.sqlPanel { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }

.sqlSection {
  min-width: 0;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.sqlHeader {
  min-height: 48px;
  padding: 8px 14px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  background: #F9FAFB;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.sqlHeader h3 { margin: 0; font-size: 11px; font-weight: 700; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.06em; }
.sqlHeader div { display: flex; gap: 6px; flex-wrap: wrap; justify-content: flex-end; }
.sqlHeader button {
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  min-height: 30px;
  padding: 0 10px;
  background: var(--surface);
  color: var(--text-primary);
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-weight: 600;
  font-size: 12px;
  cursor: pointer;
}
.sqlHeader button:hover { background: #F3F4F6; }

.sqlBox {
  flex: 1;
  min-height: 300px;
  resize: vertical;
  padding: 14px 16px;
  font-family: "Cascadia Code", Consolas, monospace;
  font-size: 13px;
  line-height: 1.6;
  border: 0;
  background: var(--surface);
  color: var(--text-primary);
  width: 100%;
}
.sqlBox.split { display: block; min-height: 260px; border: 0; border-radius: 0; }

/* ============================
   SYNC METRICS
   ============================ */
.syncMetrics { display: grid; grid-template-columns: repeat(4, minmax(140px, 1fr)); gap: 12px; }

.metricCard {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 16px 20px;
  display: grid;
  gap: 6px;
}
.metricCard .metricLabel {
  font-size: 11px; font-weight: 700; color: var(--text-secondary);
  text-transform: uppercase; letter-spacing: 0.06em;
}
.metricCard .metricValue {
  font-size: 28px; font-weight: 700; color: var(--text-primary);
  display: flex; align-items: center; gap: 8px;
}
.metricCard.alert { background: var(--error-bg); border-color: #FECACA; }
.metricCard.alert .metricLabel { color: #B91C1C; }
.metricCard.alert .metricValue { color: var(--error-text); }
.metricCard.running .metricLabel { color: var(--accent); }
.metricCard.running .metricValue { color: #0F766E; }

/* ============================
   SYNC BANNERS
   ============================ */
.syncBanner {
  border: 1px solid var(--border); border-radius: var(--radius-md);
  min-height: 44px; padding: 10px 14px; background: var(--surface);
  color: var(--text-primary); display: flex; align-items: center; gap: 10px; font-size: 13px;
}
.syncBanner.error { border-color: #FECACA; background: var(--error-bg); color: var(--error-text); }
.syncBanner.warning { border-color: #FDE68A; background: var(--warning-bg); color: var(--warning-text); }

/* ============================
   SETUP (SyncSetup)
   ============================ */
.setupLayout { display: grid; gap: 16px; }
.setupLoading { min-height: 280px; display: grid; place-items: center; align-content: center; gap: 12px; color: var(--text-secondary); font-weight: 600; }

.setupSection {
  background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius-lg); padding: 20px; display: grid; gap: 16px;
}

.setupGrid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; align-items: end; }
.setupGrid.compact { grid-template-columns: minmax(300px, 1.2fr) minmax(220px, 0.8fr) minmax(220px, 0.8fr); }
.setupGrid label, .jobHeader label, .retryGroup label, .cronEditor { display: grid; gap: 6px; align-content: start; }
.setupGrid .wideField { grid-column: span 2; }

.setupJobs { gap: 14px; display: grid; }

.jobEditor {
  border: 1px solid var(--border); border-radius: var(--radius-lg);
  background: #FAFAFA; padding: 16px; display: grid; gap: 14px;
}
.jobEditor.compact { padding: 12px 14px; }
.jobEditor.editing {
  border-color: var(--accent);
  border-left: 4px solid var(--accent);
  background: var(--surface);
  box-shadow: 0 0 0 1px rgba(13, 148, 136, 0.1);
}
.jobEditor.editing .jobCompactHeader {
  grid-template-columns: minmax(260px, 1.5fr) minmax(180px, 0.8fr) auto 36px;
  align-items: start;
}
.jobEditor.editing .jobSummary span, .jobEditor.editing .jobSummary small { white-space: normal; }
.jobEditor.editing .jobMeta, .jobEditor.editing .rowActions { justify-content: flex-start; }

.sectionTitle { min-height: 28px; display: flex; align-items: center; gap: 8px; color: var(--text-primary); }
.sectionTitle h3 { margin: 0; font-size: 15px; font-weight: 600; }
.sectionTitle.withAction { justify-content: space-between; }
.sectionTitle.withAction > div { display: flex; align-items: center; gap: 8px; }

.jobCompactHeader { display: grid; grid-template-columns: minmax(260px, 1.5fr) minmax(180px, 0.8fr) auto 36px; gap: 10px; align-items: center; }
.jobSummary { min-width: 0; display: grid; gap: 3px; }
.jobSummary strong, .jobSummary span, .jobSummary small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.jobSummary strong { color: var(--text-primary); font-weight: 600; }
.jobSummary span { color: #4B5563; font-size: 13px; }
.jobSummary small { color: var(--text-secondary); font-size: 12px; }

.jobMeta { display: flex; flex-wrap: wrap; align-items: center; gap: 5px; color: var(--text-secondary); font-size: 12px; font-weight: 600; }
.jobNameRow { display: grid; grid-template-columns: minmax(260px, 1fr) 140px; gap: 12px; align-items: end; }
.jobNameRow label { display: grid; gap: 6px; }

.jobHeader { display: grid; grid-template-columns: minmax(240px, 1fr) 140px 36px; gap: 10px; align-items: end; }

.jobSourcePanel, .jobConfigGroup, .advancedPanel {
  border: 1px solid var(--border); border-radius: var(--radius-md);
  background: var(--surface); padding: 14px; display: grid; gap: 12px;
}
.jobConfigGroup h4 { margin: 0; font-size: 11px; font-weight: 700; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.05em; }
.advancedPanel summary { cursor: pointer; color: var(--text-secondary); font-size: 13px; font-weight: 600; }
.advancedPanel[open] summary { margin-bottom: 10px; color: var(--text-primary); }

.sourceModeButtons { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
.sourceModeButtons button, .filePickButton {
  border: 1px solid var(--border); border-radius: var(--radius-sm); min-height: 38px; padding: 0 12px;
  background: #F9FAFB; color: var(--text-primary); display: inline-flex; align-items: center;
  justify-content: center; gap: 8px; font-weight: 600; font-size: 13px; cursor: pointer;
}
.sourceModeButtons button.active { background: var(--accent-light); border-color: var(--accent); color: var(--accent); }
.sourceModeButtons.focusMode { border: 1px solid var(--border); border-radius: var(--radius-md); background: #F9FAFB; padding: 12px; }

.sourceInputRow { display: grid; grid-template-columns: 180px minmax(0, 1fr) 118px 118px; gap: 10px; align-items: end; }
.sourceInputRow.linkMode { grid-template-columns: minmax(0, 1.2fr) minmax(0, 0.9fr) 118px 118px; }
.sourceInputRow.focusRow { grid-template-columns: 210px minmax(0, 1fr); border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--surface); padding: 12px; }
.sourceInputRow.linkMode.focusRow { grid-template-columns: repeat(2, minmax(0, 1fr)); }

.emptyFocus {
  border: 2px dashed var(--border); border-radius: var(--radius-md); background: #F9FAFB;
  min-height: 140px; display: grid; place-items: center; align-content: center;
  gap: 8px; color: var(--text-primary); text-align: center;
}
.emptyFocus span { color: var(--text-secondary); font-size: 13px; }

.filePickButton { position: relative; cursor: pointer; }
.filePickButton input { position: absolute; inset: 0; opacity: 0; cursor: pointer; }
.fileActionButton { position: relative; overflow: hidden; }
.fileActionButton.disabled { cursor: not-allowed; opacity: 0.5; }
.fileActionButton input { position: absolute; inset: 0; opacity: 0; cursor: pointer; }
.actionFileButton { position: relative; overflow: hidden; }
.actionFileButton.disabled { cursor: not-allowed; opacity: 0.5; }
.actionFileButton input { position: absolute; inset: 0; opacity: 0; cursor: pointer; }

.cronControls { display: grid; grid-template-columns: minmax(160px, 0.8fr) minmax(140px, 1fr); gap: 8px; }
.cronListEditor { grid-column: span 2; display: grid; gap: 8px; padding: 10px; border: 1px solid var(--border); border-radius: var(--radius-md); background: #F9FAFB; }
.cronListHeader, .cronListRow { display: flex; align-items: center; gap: 8px; }
.cronListHeader { justify-content: space-between; }
.cronListRow .cronEditor { flex: 1 1 auto; }

.retryGroup { border: 1px solid var(--border); border-radius: var(--radius-md); background: #F9FAFB; padding: 12px; display: grid; gap: 8px; }
.retryGroup strong { font-size: 11px; font-weight: 700; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.05em; display: block; }

/* Wizard stepper (replaces grid buttons) */
.wizardPanel { border-color: var(--accent); box-shadow: 0 0 0 2px rgba(13, 148, 136, 0.08); }
.wizardHeader { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.wizardHeader h3 { margin: 0; font-size: 17px; font-weight: 700; }

.wizardStepper { display: flex; align-items: center; gap: 0; flex-wrap: wrap; }
.wizardStep { display: flex; align-items: center; gap: 8px; font-size: 13px; font-weight: 600; color: var(--text-secondary); cursor: pointer; padding: 6px 4px; }
.wizardStep .stepNum { width: 24px; height: 24px; border-radius: 50%; background: #E5E7EB; color: var(--text-secondary); font-size: 12px; font-weight: 700; display: inline-grid; place-items: center; flex-shrink: 0; }
.wizardStep.active { color: var(--accent); }
.wizardStep.active .stepNum { background: var(--accent); color: #fff; }
.wizardStep.done .stepNum { background: var(--success-bg); color: var(--success-text); }
.wizardConnector { height: 1px; width: 28px; background: var(--border); flex-shrink: 0; margin: 0 2px; }

.wizardChecks { display: flex; flex-wrap: wrap; gap: 6px; }
.wizardChecks span { border-radius: 999px; min-height: 22px; padding: 2px 10px; background: #F3F4F6; color: #4B5563; font-size: 12px; font-weight: 600; }
.wizardChecks span.done { background: var(--success-bg); color: var(--success-text); }
.wizardBody { display: grid; gap: 12px; }
.wizardActions { display: flex; justify-content: flex-end; gap: 8px; flex-wrap: wrap; }
.wizardActions .primary {
  border: 0; border-radius: var(--radius-sm); min-height: 36px; padding: 0 14px;
  background: var(--accent); color: #fff; display: inline-flex; align-items: center;
  gap: 7px; font-weight: 600; font-size: 13px; cursor: pointer;
}
.wizardActions .primary:hover { background: var(--accent-hover); }

/* Preview / mapping panels */
.previewPanel { border: 1px solid var(--border); border-radius: var(--radius-md); background: #F9FAFB; padding: 12px; display: grid; gap: 10px; }
.previewTableWrap { overflow: auto; border: 1px solid var(--border); border-radius: var(--radius-sm); background: var(--surface); }
.previewTableWrap table { min-width: 680px; }
.previewTableWrap td:first-child { width: 42px; color: var(--text-secondary); font-weight: 700; }
.previewHeaderRow td { background: var(--accent-light); color: #065F46; font-weight: 700; }

.columnMappingPanel { border: 1px solid var(--border); border-radius: var(--radius-md); background: #F9FAFB; padding: 12px; display: grid; gap: 10px; }
.columnMappingGrid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
.columnMappingRow { display: grid; grid-template-columns: 86px minmax(120px, 0.8fr) minmax(160px, 1fr); gap: 8px; align-items: center; }
.columnMappingRow.skipped { opacity: 0.6; }
.columnMappingRow span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text-secondary); font-size: 13px; font-weight: 600; }

.typePreviewPanel { border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--surface); padding: 12px; display: grid; gap: 10px; }
.typePreviewPanel strong { font-size: 11px; font-weight: 700; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.05em; }
.typePreviewGrid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; }
.typePreviewItem { border: 1px solid var(--border); border-radius: var(--radius-sm); background: #FAFAFA; padding: 8px; display: grid; gap: 3px; min-width: 0; }
.typePreviewItem span, .typePreviewItem small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.typePreviewItem span { color: var(--text-primary); font-weight: 700; font-size: 13px; }
.typePreviewItem b { color: var(--success-text); font-size: 12px; }
.typePreviewItem small { color: var(--text-secondary); font-size: 12px; }

/* Misc setup */
.bundlePreview { border: 1px solid var(--border); border-radius: var(--radius-md); background: #F9FAFB; padding: 12px; display: grid; gap: 6px; }
.bundlePreview strong, .bundlePreview span, .bundlePreview small { overflow-wrap: anywhere; }

.notificationLayout { display: grid; grid-template-columns: minmax(240px, 0.7fr) minmax(0, 1.3fr); gap: 12px; }
.notificationCard { border: 1px solid var(--border); border-radius: var(--radius-md); background: #F9FAFB; padding: 14px; display: grid; gap: 12px; align-content: start; }
.notificationCard.wide { grid-column: span 2; }
.notificationHeader { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.notificationCard strong { display: block; color: var(--text-primary); font-size: 14px; }
.notificationCard small { display: block; margin-top: 3px; color: var(--text-secondary); }

.testResult { border-radius: var(--radius-sm); padding: 9px 12px; background: #F3F4F6; color: var(--text-secondary); font-size: 13px; overflow-wrap: anywhere; }
.testResult.success { background: var(--success-bg); color: var(--success-text); }
.testResult.error { background: var(--error-bg); color: var(--error-text); }
.testResult.info { background: var(--info-bg); color: var(--info-text); }

.sourceFileList .historyItem { grid-template-columns: minmax(0, 1fr); }
.sourceFileList .historyItem > button:first-child { border-color: var(--border); background: var(--surface); color: var(--text-primary); }
.sourceFileList .historyItem span { color: var(--text-secondary); }

.syncSidePanel { border: 1px solid var(--border); border-radius: var(--radius-md); background: #F9FAFB; padding: 14px; display: grid; gap: 8px; }
.syncSidePanel svg { color: var(--accent); }
.syncSidePanel span, .syncSidePanel small { color: var(--text-secondary); overflow-wrap: anywhere; }

.emptyText { color: var(--text-secondary); font-size: 13px; text-align: center; padding: 24px; }

.folderActions, .backupActions { display: flex; flex-wrap: wrap; gap: 8px; }

/* ============================
   TOAST
   ============================ */
.status {
  position: fixed; right: 20px; bottom: 20px;
  max-width: min(480px, calc(100vw - 40px));
  padding: 12px 16px; border-radius: var(--radius-md);
  background: #111827; color: #F9FAFB; font-size: 13px;
  box-shadow: 0 8px 24px rgba(0,0,0,0.2); z-index: 1000;
}

/* ============================
   RESPONSIVE
   ============================ */
@media (max-width: 1024px) {
  .sqlPanel { grid-template-columns: 1fr; }
}

@media (max-width: 900px) {
  .workspace { padding: 20px; }
  .topbar { flex-direction: column; align-items: stretch; }
  .settingsRow { grid-template-columns: 1fr; }
  .actions { justify-content: flex-start; }
  .syncMetrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .setupGrid, .setupGrid.compact { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .setupGrid .wideField { grid-column: span 2; }
  .jobHeader { grid-template-columns: minmax(0, 1fr) 140px 36px; }
  .jobCompactHeader { grid-template-columns: minmax(0, 1fr); }
  .jobMeta, .jobCompactHeader .rowActions { justify-content: flex-start; }
  .sourceInputRow, .sourceInputRow.linkMode, .columnMappingGrid, .columnMappingRow, .typePreviewGrid { grid-template-columns: 1fr; }
  .sqlHeader { align-items: flex-start; flex-direction: column; }
  .uploadCard { padding: 32px 24px; }
  .appNav button { padding: 0 10px; font-size: 13px; }
}

@media (max-width: 640px) {
  .workspace { padding: 16px; }
  .setupGrid, .setupGrid.compact, .jobHeader, .jobNameRow, .cronControls, .sourceModeButtons { grid-template-columns: 1fr; }
  .setupGrid .wideField { grid-column: auto; }
  .sectionTitle.withAction { align-items: flex-start; flex-direction: column; }
  .wizardHeader, .wizardActions { align-items: flex-start; flex-direction: column; }
  .wizardStepper { flex-direction: column; align-items: flex-start; }
  .wizardConnector { width: 1px; height: 14px; margin: 0 11px; }
  .syncMetrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .appStatus span { display: none; }
  .notificationLayout { grid-template-columns: 1fr; }
  .notificationCard.wide { grid-column: auto; }
}
```

- [ ] **Step 2: Verify dev server compiles**

```
npm run dev
```

Expected: Server starts, no CSS parse errors in terminal. The app loads (sidebar will still render from old JSX — that's fine for now).

- [ ] **Step 3: Commit**

```bash
git add src/styles.css
git commit -m "style: rewrite CSS with design tokens, Clean Professional system"
```

---

## Task 2: App Shell — Remove Sidebar, Add Top Header

**Files:**
- Modify: `src/App.jsx`

**What changes:** Remove `<section className="sidebar">` and all its contents. Add `<header className="appHeader">` with brand, 3 module tabs, and API status dot. Change `.app` from sidebar+workspace grid to flex column. Add a lightweight API status ping. Move file `<input>` out of workspace into a hidden global.

**Interfaces:**
- Consumes: `activeMode` state, `setActiveMode`, `SYNC_API_URL` from SyncMonitor import
- Produces: New shell that Tasks 3-5 render inside

- [ ] **Step 1: Add API status ping hook at the top of the `App()` function body**

Find the `export default function App()` block. After the existing `useState` declarations, add:

```jsx
const [apiOnline, setApiOnline] = useState(null);

useEffect(() => {
  let alive = true;
  async function ping() {
    try {
      await fetch(`${SYNC_API_URL}/api/health`, { signal: AbortSignal.timeout(3000) });
      if (alive) setApiOnline(true);
    } catch {
      if (alive) setApiOnline(false);
    }
  }
  ping();
  const timer = setInterval(ping, 15000);
  return () => { alive = false; clearInterval(timer); };
}, []);
```

- [ ] **Step 2: Replace the entire `return (...)` JSX in `App()`**

The `return` starts at line ~872 with `<main className="app">`. Replace it entirely with the following (keep all event handlers and state — only the JSX structure changes):

```jsx
return (
  <>
    <input
      ref={fileInputRef}
      className="hiddenInput"
      type="file"
      accept=".xls,.xlsx,.xlsm,.csv,.tsv,text/csv"
      onChange={(event) => handleFile(event.target.files?.[0])}
    />

    <div className="app">
      <header className="appHeader">
        <div className="appBrand">
          <Database size={20} aria-hidden="true" />
          <span>PowerBI Data DTL</span>
        </div>

        <nav className="appNav" aria-label="Điều hướng chính">
          <button
            type="button"
            className={activeMode === "builder" ? "active" : ""}
            onClick={() => setActiveMode("builder")}
          >
            <FileSpreadsheet size={16} aria-hidden="true" />
            Nhập dữ liệu
          </button>
          <button
            type="button"
            className={activeMode === "setup" ? "active" : ""}
            onClick={() => setActiveMode("setup")}
          >
            <Settings2 size={16} aria-hidden="true" />
            Cài đặt
          </button>
          <button
            type="button"
            className={activeMode === "sync" ? "active" : ""}
            onClick={() => setActiveMode("sync")}
          >
            <Server size={16} aria-hidden="true" />
            Giám sát
          </button>
        </nav>

        <div className="appStatus">
          <div className={`statusDot ${apiOnline === true ? "online" : apiOnline === false ? "offline" : ""}`} />
          <span>{apiOnline === true ? "Hệ thống hoạt động" : apiOnline === false ? "Mất kết nối" : ""}</span>
        </div>
      </header>

      <section className="workspace">
        {activeMode === "setup" ? (
          <SyncSetup notice={setupNotice} focusJobName={setupFocusJob?.name} focusToken={setupFocusJob?.token} />
        ) : activeMode === "sync" ? (
          <SyncMonitor onEditJob={editSyncJob} />
        ) : !project ? (
          /* Welcome screen — Task 3 fills this */
          <div className="welcome">
            <div className="uploadCard">
              <FolderOpen size={36} aria-hidden="true" />
              <h2>Chọn file để bắt đầu</h2>
              <p>Hỗ trợ .xls, .xlsx, .csv, .tsv · SharePoint · Google Sheet · OneDrive</p>
              <div className="uploadActions">
                <button type="button" className="btn" onClick={() => { setImportSourceMode("file"); fileInputRef.current?.click(); }}>
                  <UploadCloud size={16} aria-hidden="true" />
                  Chọn file
                </button>
                <button type="button" className="btn" onClick={() => { setImportSourceMode("link"); setTimeout(() => linkInputRef.current?.focus(), 0); }}>
                  <Link2 size={16} aria-hidden="true" />
                  Dán link
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
                  onKeyDown={(event) => { if (event.key === "Enter") handleImportLink(); }}
                />
              )}
            </div>
          </div>
        ) : (
          /* Project workspace — Task 4 fills this */
          <ProjectWorkspace
            project={project}
            projects={projects}
            activeTab={activeTab}
            previewRows={previewRows}
            includedColumns={includedColumns}
            copied={copied}
            message={message}
            importSourceMode={importSourceMode}
            isReadingLink={isReadingLink}
            onTabChange={setActiveTab}
            onPatchProject={patchProject}
            onPatchColumn={patchColumn}
            onSave={saveCurrentProject}
            onCopyFull={copyFullSql}
            onCopyText={copyText}
            onDownloadFull={downloadFullSql}
            onDownloadCreate={() => downloadSql(project.createSql, "create_table")}
            onDownloadInsert={downloadFullInsertSql}
            onAddToSync={addCurrentProjectToSync}
            onLoadProject={loadProject}
            onRemoveProject={removeProject}
            onRefreshProjects={refreshProjects}
            onClearProject={() => setProject(null)}
            onChangeDialect={changeDialect}
            onChangeHeaderRow={changeHeaderRow}
          />
        )}
        {activeMode === "builder" && message && <div className="status">{message}</div>}
      </section>
    </div>
  </>
);
```

> Note: `ProjectWorkspace` is an inline component defined in the next task. For now this step just establishes the shell structure.

- [ ] **Step 3: Verify shell renders**

```
npm run dev
```

Open http://localhost:5173 — you should see the white top header with 3 tabs. No sidebar. Console may show `ProjectWorkspace is not defined` — that's expected, fix it in Task 3.

- [ ] **Step 4: Commit**

```bash
git add src/App.jsx
git commit -m "feat: replace sidebar with top navigation header"
```

---

## Task 3: Builder — Welcome Screen, History Dropdown, Project Workspace

**Files:**
- Modify: `src/App.jsx`

**What changes:** Extract the project workspace JSX into an inline `ProjectWorkspace` component inside the same file. Redesign the welcome upload card. Add "Mở lại ▾" history dropdown.

- [ ] **Step 1: Add `ProjectWorkspace` component above `export default function App()`**

Insert this entire block just above the `export default function App()` line:

```jsx
function HistoryDropdown({ projects, onLoad, onRemove, onRefresh }) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef(null);

  useEffect(() => {
    function handleClick(e) {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const recent = projects.slice(0, 6);

  return (
    <div className="dropdownWrap" ref={wrapRef}>
      <button type="button" className="btn" onClick={() => { setOpen((o) => !o); onRefresh(); }}>
        <History size={15} aria-hidden="true" />
        Mở lại
        <ChevronDown size={13} aria-hidden="true" />
      </button>
      {open && (
        <div className="dropdown" style={{ minWidth: 260 }}>
          {recent.length === 0 && (
            <div style={{ padding: "12px 14px", color: "var(--text-secondary)", fontSize: 13 }}>
              Chưa có file nào được lưu.
            </div>
          )}
          {recent.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => { onLoad(item.id); setOpen(false); }}
              style={{ flexDirection: "column", alignItems: "flex-start", gap: 2 }}
            >
              <span style={{ fontWeight: 600, fontSize: 13 }}>{item.name}</span>
              <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>{item.fileName}</span>
            </button>
          ))}
          {recent.length > 0 && (
            <>
              <hr />
              <button
                type="button"
                onClick={() => { recent.forEach((item) => onRemove(item.id)); setOpen(false); }}
                style={{ color: "var(--error-text)", fontSize: 12 }}
              >
                <Trash2 size={13} aria-hidden="true" />
                Xóa tất cả lịch sử
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}

function ProjectWorkspace({
  project, projects, activeTab, previewRows, includedColumns, copied, message,
  onTabChange, onPatchProject, onPatchColumn, onSave, onCopyFull, onCopyText,
  onDownloadFull, onDownloadCreate, onDownloadInsert, onAddToSync, onLoadProject,
  onRemoveProject, onRefreshProjects, onClearProject, onChangeDialect, onChangeHeaderRow,
}) {
  const [sqlDropOpen, setSqlDropOpen] = useState(false);
  const sqlDropRef = useRef(null);

  useEffect(() => {
    function handleClick(e) {
      if (sqlDropRef.current && !sqlDropRef.current.contains(e.target)) setSqlDropOpen(false);
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const TYPE_OPTIONS_LOCAL = {
    PostgreSQL: ["INTEGER", "BIGINT", "NUMERIC", "DOUBLE PRECISION", "BOOLEAN", "DATE", "TIMESTAMP", "TEXT", "VARCHAR"],
    MySQL: ["INT", "BIGINT", "DECIMAL", "DOUBLE", "BOOLEAN", "DATE", "DATETIME", "TEXT", "VARCHAR"],
    "SQL Server": ["INT", "BIGINT", "DECIMAL", "FLOAT", "BIT", "DATE", "DATETIME2", "NVARCHAR(MAX)", "NVARCHAR"],
    SQLite: ["INTEGER", "REAL", "NUMERIC", "TEXT", "BOOLEAN", "DATE", "DATETIME"],
  };

  return (
    <>
      <header className="topbar">
        <div className="topbarMeta">
          <p className="eyebrow">{project.fileName}{project.sheetName ? ` / ${project.sheetName}` : ""}</p>
          <h2>{project.name}</h2>
          <p className="metaLine">
            {project.rows.length.toLocaleString("vi-VN")} dòng · {project.columns.length} cột · {includedColumns.length} cột được xuất
          </p>
        </div>
        <div className="actions">
          <button type="button" onClick={onClearProject}>
            <FolderOpen size={15} aria-hidden="true" />
            Mở file mới
          </button>
          <HistoryDropdown
            projects={projects}
            onLoad={onLoadProject}
            onRemove={onRemoveProject}
            onRefresh={onRefreshProjects}
          />
          <button type="button" onClick={onSave}>
            <Save size={15} aria-hidden="true" />
            Lưu
          </button>
          <button type="button" onClick={onCopyFull}>
            {copied ? <Check size={15} aria-hidden="true" /> : <Clipboard size={15} aria-hidden="true" />}
            {copied ? "Đã sao chép" : "Sao chép SQL"}
          </button>
          <button type="button" onClick={onAddToSync}>
            <UploadCloud size={15} aria-hidden="true" />
            Tạo lịch đồng bộ
          </button>
          {/* SQL export split button */}
          <div className="splitBtn primary" ref={sqlDropRef} style={{ position: "relative" }}>
            <button type="button" className="splitMain" onClick={onDownloadFull}>
              <Download size={15} aria-hidden="true" />
              Xuất file SQL
            </button>
            <button
              type="button"
              className="splitArrow"
              aria-label="Thêm tùy chọn xuất"
              onClick={() => setSqlDropOpen((o) => !o)}
            >
              <ChevronDown size={13} aria-hidden="true" />
            </button>
            {sqlDropOpen && (
              <div className="dropdown">
                <button type="button" onClick={() => { onDownloadCreate(); setSqlDropOpen(false); }}>
                  <Database size={14} aria-hidden="true" />
                  Xuất CREATE TABLE
                </button>
                <button type="button" onClick={() => { onDownloadInsert(); setSqlDropOpen(false); }}>
                  <Download size={14} aria-hidden="true" />
                  Xuất INSERT dữ liệu
                </button>
                <hr />
                <button type="button" onClick={() => { onDownloadFull(); setSqlDropOpen(false); }}>
                  <Download size={14} aria-hidden="true" />
                  Xuất tất cả
                </button>
              </div>
            )}
          </div>
        </div>
      </header>

      <div className="settingsRow">
        <label>
          Tên bảng
          <input
            value={project.tableName}
            onChange={(event) => onPatchProject({ tableName: event.target.value || "import_data" })}
          />
        </label>
        <label>
          Dòng tiêu đề
          <input
            type="number"
            min="1"
            max={Math.max(project.rawRows?.length || 1, 1)}
            value={(project.headerRowIndex ?? 0) + 1}
            disabled={!project.rawRows?.length}
            onChange={(event) => onChangeHeaderRow(event.target.value)}
          />
        </label>
        <label>
          Loại cơ sở dữ liệu
          <span className="selectWrap">
            <select value={project.dialect} onChange={(event) => onChangeDialect(event.target.value)}>
              {["PostgreSQL", "MySQL", "SQL Server", "SQLite"].map((d) => <option key={d}>{d}</option>)}
            </select>
            <ChevronDown size={15} aria-hidden="true" />
          </span>
        </label>
      </div>

      <nav className="tabs" aria-label="Chế độ xem">
        <button type="button" className={activeTab === "schema" ? "active" : ""} onClick={() => onTabChange("schema")}>
          <Settings2 size={15} aria-hidden="true" />
          Cột & kiểu dữ liệu
        </button>
        <button type="button" className={activeTab === "data" ? "active" : ""} onClick={() => onTabChange("data")}>
          <FileSpreadsheet size={15} aria-hidden="true" />
          Dữ liệu mẫu
        </button>
        <button type="button" className={activeTab === "sql" ? "active" : ""} onClick={() => onTabChange("sql")}>
          <Database size={15} aria-hidden="true" />
          SQL
        </button>
      </nav>

      {activeTab === "schema" && (
        <div className="tablePanel">
          <table>
            <thead>
              <tr>
                <th>Tên gốc</th>
                <th>Tên cột trong bảng</th>
                <th>Kiểu dữ liệu</th>
                <th>Cho phép trống</th>
                <th>Bao gồm</th>
              </tr>
            </thead>
            <tbody>
              {project.columns.map((column) => (
                <tr key={column.id}>
                  <td>{column.sourceName}</td>
                  <td>
                    <input value={column.name} onChange={(event) => onPatchColumn(column.id, { name: event.target.value })} />
                  </td>
                  <td>
                    <select value={column.type} onChange={(event) => onPatchColumn(column.id, { type: event.target.value })}>
                      {TYPE_OPTIONS_LOCAL[project.dialect].map((type) => <option key={type}>{type}</option>)}
                      {!TYPE_OPTIONS_LOCAL[project.dialect].includes(column.type) && <option>{column.type}</option>}
                    </select>
                  </td>
                  <td>
                    <input type="checkbox" checked={column.nullable} onChange={(event) => onPatchColumn(column.id, { nullable: event.target.checked })} />
                  </td>
                  <td>
                    <input type="checkbox" checked={column.include} onChange={(event) => onPatchColumn(column.id, { include: event.target.checked })} />
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
              <h3>Tạo bảng</h3>
              <div>
                <button type="button" onClick={() => onCopyText(project.createSql)}>
                  <Clipboard size={13} aria-hidden="true" />
                  Sao chép
                </button>
                <button type="button" onClick={onDownloadCreate}>
                  <Download size={13} aria-hidden="true" />
                  Tải xuống
                </button>
              </div>
            </div>
            <textarea className="sqlBox split" value={project.createSql} readOnly spellCheck="false" />
          </section>
          <section className="sqlSection">
            <div className="sqlHeader">
              <h3>Chèn dữ liệu</h3>
              <div>
                <button type="button" onClick={() => onCopyText(project.insertPreviewSql)}>
                  <Clipboard size={13} aria-hidden="true" />
                  Sao chép
                </button>
                <button type="button" onClick={onDownloadInsert}>
                  <Download size={13} aria-hidden="true" />
                  Tải toàn bộ
                </button>
              </div>
            </div>
            <textarea className="sqlBox split" value={project.insertPreviewSql} readOnly spellCheck="false" />
          </section>
        </div>
      )}
    </>
  );
}
```

- [ ] **Step 2: Remove `TYPE_OPTIONS` constant from top of file**

The constant `TYPE_OPTIONS` (lines ~30-35 in original) is now used only inside `ProjectWorkspace` as `TYPE_OPTIONS_LOCAL`. Delete the top-level `TYPE_OPTIONS` constant and the `DIALECTS` array (both unused after this change).

- [ ] **Step 3: Update the welcome screen in `App()` return to use the new `uploadCard` structure**

In the `App()` return JSX from Task 2, the welcome screen placeholder is already correct. Verify it looks like:

```jsx
<div className="welcome">
  <div className="uploadCard">
    <FolderOpen size={36} aria-hidden="true" />
    <h2>Chọn file để bắt đầu</h2>
    <p>Hỗ trợ .xls, .xlsx, .csv, .tsv · SharePoint · Google Sheet · OneDrive</p>
    <div className="uploadActions">
      <button type="button" className="btn" onClick={() => { setImportSourceMode("file"); fileInputRef.current?.click(); }}>
        <UploadCloud size={16} aria-hidden="true" /> Chọn file
      </button>
      <button type="button" className="btn" disabled={isReadingLink} onClick={() => {
        setImportSourceMode("link");
        if (importLink.trim()) { handleImportLink(); }
        else { setTimeout(() => linkInputRef.current?.focus(), 0); }
      }}>
        <Link2 size={16} aria-hidden="true" />
        {isReadingLink ? "Đang đọc..." : "Dán link"}
      </button>
    </div>
    {importSourceMode === "link" && (
      <input
        ref={linkInputRef}
        className="importLinkInput"
        value={importLink}
        placeholder="Dán link SharePoint, OneDrive, Google Sheet, Excel Online..."
        onChange={(event) => setImportLink(event.target.value)}
        onPaste={(event) => { const pasted = event.clipboardData.getData("text"); if (pasted) setTimeout(() => handleImportLink(pasted), 0); }}
        onKeyDown={(event) => { if (event.key === "Enter") handleImportLink(); }}
      />
    )}
  </div>
</div>
```

- [ ] **Step 4: Verify builder works end-to-end**

```
npm run dev
```

- Open http://localhost:5173 → "Nhập dữ liệu" tab active
- Upload an .xlsx or .csv file → file parses, columns appear
- Check "Dòng tiêu đề" label (not "Dòng header")
- Check "Loại cơ sở dữ liệu" label (not "Hệ SQL")
- Schema table headers: "Tên gốc" / "Tên cột trong bảng" / "Kiểu dữ liệu" / "Cho phép trống" / "Bao gồm"
- SQL tab: two panels side by side
- "Xuất file SQL ▾" split button → dropdown shows 3 options
- "Mở lại ▾" dropdown → shows saved projects

- [ ] **Step 5: Commit**

```bash
git add src/App.jsx
git commit -m "feat: redesign builder welcome screen, topbar, workspace layout"
```

---

## Task 4: Sync Monitor — Metrics, Remove Hash, Split Buttons

**Files:**
- Modify: `src/SyncMonitor.jsx`

**What changes:** Replace the 4 metric `<div>` cards with `.metricCard` structure. Remove the "Hash" column from the jobs table. Replace separate "Chạy" + "Force" buttons with a split button. Replace top-level "Chạy lại bỏ qua hash" button with split button. Rename Vietnamese labels.

- [ ] **Step 1: Add split button state for each job row**

In `SyncMonitor`, the component needs per-row dropdown state. Add a single state for which row's dropdown is open:

```jsx
const [openRunDrop, setOpenRunDrop] = useState(null); // job name or null
const [openAllDrop, setOpenAllDrop] = useState(false);
const allDropRef = useRef(null);

useEffect(() => {
  function handleClick(e) {
    if (allDropRef.current && !allDropRef.current.contains(e.target)) setOpenAllDrop(false);
    setOpenRunDrop(null);
  }
  document.addEventListener("mousedown", handleClick);
  return () => document.removeEventListener("mousedown", handleClick);
}, []);
```

Add `useRef` to the import at the top of the file (it's already imported — just add `useRef` if missing).

- [ ] **Step 2: Replace the header JSX**

Replace:
```jsx
<header className="topbar">
  <div>
    <h2>Sync Monitor</h2>
    <p className="meta">{jobs.length} job cấu hình, {runningCount} đang chạy, {logs.length} log gần nhất</p>
  </div>
  <div className="actions">
    <button type="button" onClick={() => refreshSyncData()}>
      <RefreshCcw size={17} aria-hidden="true" />
      Tải lại
    </button>
    <button type="button" onClick={() => triggerRunAll(false)}>
      <Play size={17} aria-hidden="true" />
      Chạy tất cả
    </button>
    <button type="button" className="primary" title="Chạy lại kể cả khi file chưa thay đổi hash" onClick={() => triggerRunAll(true)}>
      <Play size={17} aria-hidden="true" />
      Chạy lại bỏ qua hash
    </button>
  </div>
</header>
```

With:
```jsx
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
    <div className="splitBtn" ref={allDropRef} style={{ position: "relative" }}>
      <button type="button" className="splitMain" onClick={() => triggerRunAll(false)}>
        <Play size={15} aria-hidden="true" />
        Đồng bộ tất cả
      </button>
      <button
        type="button"
        className="splitArrow"
        aria-label="Thêm tùy chọn"
        onClick={() => setOpenAllDrop((o) => !o)}
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
```

- [ ] **Step 3: Replace the 4 metric divs**

Replace the entire `<div className="syncMetrics">` block:

```jsx
<div className="syncMetrics">
  <div className={`metricCard${runningCount > 0 ? " running" : ""}`}>
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
  <div className="metricCard">
    <div className="metricLabel">Thành công</div>
    <div className="metricValue">{latestSuccess}</div>
  </div>
  <div className={`metricCard${latestFailures > 0 ? " alert" : ""}`}>
    <div className="metricLabel">Lỗi</div>
    <div className="metricValue">{latestFailures}</div>
  </div>
</div>
```

- [ ] **Step 4: Update the jobs table — remove Hash column, add split run button**

Replace the entire jobs `<section className="tablePanel syncTable">` block:

```jsx
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
        const isDropOpen = openRunDrop === job.name;
        return (
          <tr key={job.name}>
            <td>
              <strong>{job.name}</strong>
              {latest.error_message && <small className="errorText">{latest.error_message}</small>}
            </td>
            <td>{job.source_type}</td>
            <td>{job.table}</td>
            <td>{cronLabel(job)}</td>
            <td>
              <span className={`statusPill ${job.running ? "running" : (latest.status || "idle")}`}>
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
                    onClick={() => setOpenRunDrop(isDropOpen ? null : job.name)}
                  >
                    <ChevronDown size={12} aria-hidden="true" />
                  </button>
                  {isDropOpen && (
                    <div className="dropdown">
                      <button type="button" onClick={() => { triggerRunJob(job.name, true); setOpenRunDrop(null); }}>
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
```

- [ ] **Step 5: Update the logs table header labels**

Replace the logs table `<thead>`:
```jsx
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
```

- [ ] **Step 6: Update `syncStatusLabel` function for new copy**

Replace the `syncStatusLabel` function:
```jsx
function syncStatusLabel(status) {
  const labels = {
    success: "Thành công",
    failed: "Lỗi",
    skipped: "Bỏ qua",
    mismatch: "Lệch cấu trúc",
  };
  return labels[status] || status || "Chưa chạy";
}
```

- [ ] **Step 7: Add missing imports to SyncMonitor.jsx**

Ensure `ChevronDown` and `useRef` are imported. The top of the file should include:
```jsx
import { useEffect, useRef, useState } from "react";
import { Activity, AlertCircle, ChevronDown, Pencil, Play, RefreshCcw } from "lucide-react";
```

- [ ] **Step 8: Verify Sync Monitor**

```
npm run dev
```

- Click "Giám sát" tab → monitor loads
- 4 metric cards show (Tác vụ / Đang chạy / Thành công / Lỗi)
- Jobs table has 8 columns (no Hash column)
- "Đồng bộ tất cả ▾" split button → dropdown shows "Bắt buộc đồng bộ lại"
- Row "Chạy ▾" split button → dropdown shows "Bắt buộc đồng bộ lại"
- Status pills: "Thành công" / "Lỗi" / "Lệch cấu trúc"

- [ ] **Step 9: Commit**

```bash
git add src/SyncMonitor.jsx
git commit -m "feat: redesign sync monitor — metric cards, split buttons, remove hash column"
```

---

## Task 5: Sync Setup — Underline Tabs, Numbered Stepper, Labels

**Files:**
- Modify: `src/SyncSetup.jsx`

**What changes:** The `setupTabs` CSS already matches underline style from Task 1. Replace the wizard `wizardSteps` grid buttons with a `wizardStepper` numbered stepper. Update the job editor `editing` class behavior (CSS already handles left border). Rename "Advanced" label to "Tùy chọn nâng cao ›".

- [ ] **Step 1: Find and update the wizard steps JSX in SyncSetup.jsx**

Search for `wizardSteps` in `SyncSetup.jsx`. Replace the `<div className="wizardSteps">` block (which contains 3 buttons with numbered spans) with:

```jsx
<div className="wizardStepper">
  {[
    { key: "source", label: "Chọn nguồn" },
    { key: "target", label: "Cấu hình bảng" },
    { key: "schedule", label: "Đặt lịch" },
  ].map((step, index, arr) => {
    const stepKeys = ["source", "target", "schedule"];
    const currentIndex = stepKeys.indexOf(wizardStep);
    const thisIndex = stepKeys.indexOf(step.key);
    const isDone = thisIndex < currentIndex;
    const isActive = step.key === wizardStep;
    return (
      <div key={step.key} style={{ display: "contents" }}>
        <button
          type="button"
          className={`wizardStep${isActive ? " active" : isDone ? " done" : ""}`}
          onClick={() => setWizardStep(step.key)}
        >
          <span className="stepNum">{isDone ? "✓" : index + 1}</span>
          {step.label}
        </button>
        {index < arr.length - 1 && <div className="wizardConnector" />}
      </div>
    );
  })}
</div>
```

> Note: `wizardStep` and `setWizardStep` are the existing state variables in SyncSetup for the wizard — check their actual names in the file and adjust if different (they may be named `activeWizardStep` or similar).

- [ ] **Step 2: Update all `advancedPanel` summary labels**

Search for `<summary>` tags inside `<details className="advancedPanel">`. Replace any summary text like "Nâng cao" or "Advanced" with:

```jsx
<summary>Tùy chọn nâng cao</summary>
```

- [ ] **Step 3: Verify Sync Setup**

```
npm run dev
```

- Click "Cài đặt" tab → setup loads
- Tabs are underline style (not pill/background)
- Wizard header shows numbered stepper: `① Chọn nguồn → ② Cấu hình bảng → ③ Đặt lịch`
- Click a wizard step number → navigates to that step
- Editing a job → left border teal `4px` appears on the card
- Advanced section label reads "Tùy chọn nâng cao"

- [ ] **Step 4: Commit**

```bash
git add src/SyncSetup.jsx
git commit -m "feat: redesign sync setup — numbered stepper, underline tabs, labels"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Task |
|-----------------|------|
| Top header 60px, white, brand + 3 tabs | Task 2 |
| Status dot API ping | Task 2 |
| Accent #0D9488 (teal) | Task 1 |
| Form labels uppercase 12px | Task 1 |
| Tabs underline style | Task 1 |
| Welcome uploadCard | Task 3 |
| "Mở lại ▾" history dropdown | Task 3 |
| Button min-height 36px | Task 1 |
| SQL tab side-by-side | Task 1 + Task 3 |
| Split "Xuất file SQL" button | Task 3 |
| Schema table renamed headers | Task 3 |
| Settings row renamed labels | Task 3 |
| Metric cards with alert/running states | Task 4 |
| Remove hash column | Task 4 |
| Split run buttons in monitor | Task 4 |
| "Lệch cấu trúc" status label | Task 4 |
| Numbered stepper wizard | Task 5 |
| Job editor left border on edit | Task 1 (CSS) |
| "Tùy chọn nâng cao" label | Task 5 |
| Copy changes (all 15 items) | Tasks 2-5 |

**Placeholder scan:** No TBDs or TODOs found.

**Type consistency:** `HistoryDropdown` and `ProjectWorkspace` are defined before `App()` in same file — no import needed. All props passed match parameter names.
