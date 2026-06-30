# UI Redesign — Progress Ledger

Branch: redesign/clean-professional
Base (branch start): see `git merge-base main HEAD`
Design: "Màu sắc = trạng thái" (ink-on-paper chrome, status-only color, mono-for-data, status spine)

## Tasks
- T1: complete (commit a5c8225, build green) — ink+status system, mono data, spine
  Note: JSX tasks implemented inline (no test harness; design fidelity); subagent used for final whole-branch review.
- T2: complete (commit 0ca173c, build green) — top nav shell, ProjectWorkspace, HistoryDropdown, removed dead formatDateTime/RefreshCcw
- T3: complete (commit 51aae8d, build green) — metric cards, status spine, split run buttons, "Lệch cấu trúc"
- T4: complete (commit c34bb09, build green) — numbered stepper, underline tabs, professional copy
- T5: Final review done (opus). Verdict was CHANGES NEEDED → all fixed in commit ac57359.
  Logic-untouched constraint confirmed held. Build green throughout.

## Review findings — resolution
- Important #1 (history delete only 6 / no per-item delete) → FIXED (per-item trash + delete-all over full list + count hint).
- Minor #2 redundant spine rule → FIXED. #3 monitor run-all ink primary → FIXED.
- Minor #4 status-dot a11y → FIXED (aria-label + non-empty checking text). #7 dead CSS (.dragging/.hashCell) → FIXED.
- Minor #8 double history refresh → FIXED (refresh on open only).
- ACCEPTED as-is (intentional): #1 spine 3px (looks better than stated 2px); #5 dense 30-34px buttons in table/toolbar; #6 run.bat/run.ps1 in banner (actionable instruction); #9 status palette reused for wizard-done/test-result success+info (legit success/info semantics).

## Post-review user-requested polish (round 2)
- Font unified: Inter everywhere, monospace only for SQL boxes (dropped mono-for-data thesis per user).
- Header: removed brand title text (kept icon), nav centered via grid 1fr/auto/1fr, status right.
- "Tùy chọn nâng cao" disclosures → bordered/filled clickable bars (≥42px hit area).
- Dropdown items: white-space nowrap (fixes "Bắt buộc đồng bộ lại" wrapping).
- Backend: open_folder uses os.startfile on Windows (reliable Explorer focus) — sync/core/api.py. PY_OK.
