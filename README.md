# DairyManager — Milk Collection Manager

A desktop app for milk dairies and collection centers (most still run on paper
registers) to record daily milk collection farmer-wise, auto-calculate rates
from fat/SNF readings, and generate payment sheets.

**Tech:** Python + CustomTkinter + SQLite, fully offline-first. Ships as a
one-click Windows `.exe` via `build_exe.bat` (PyInstaller).

## What it does

- **Farmer master** — name, village, phone, bank account + IFSC; hide/show
  (deactivate) farmers without losing their history.
- **Daily collection entry** — farmer (type-to-search), date, Morning/Evening
  shift, litres, fat, SNF. The rate is **auto-computed from a configurable
  rate chart** (fat/SNF slabs) with a live preview before saving.
- **Rate chart editor** — add/edit/delete fat×SNF slabs; a configurable
  default rate covers readings that fall outside every slab so billing never
  blocks.
- **Payment sheets** — pick any period and get per-farmer opening pending,
  litres, gross, paid, and closing pending, with totals. Record payments
  (Cash/UPI/Bank/Cheque, capped at the pending amount) and print the sheet.
- **Farmer statements** — printable per-farmer milk statement for a period
  (collections + payments + opening/closing pending).
- **Dashboard** — today's milk (morning/evening split), farmers served today,
  pending payments, this month's litres; today's entry list with delete.
- **Daily collection report** — printable A4 or 80mm thermal PDF.
- **Backup/restore** — timestamped zip backups (keeps the last 14); restore
  keeps a `.safety-copy` of the current database first.
- **Settings** — dairy name (appears on every report) and default rate.

## How to run

```bash
pip install -r requirements.txt
python main.py
```

Data lives in `dairy_data/dairy.db` (SQLite) next to the script — copy that
folder to move or back up manually.

### Build the Windows .exe

On the shop PC, double-click `build_exe.bat` once. It installs dependencies,
builds `dist\DairyManager.exe` via PyInstaller, and the app then runs
standalone. The `dairy_data\` folder is created next to the `.exe`.

## How the rate calculation works

Each collection stores `rate` and `amount` at write time (rate × litres,
rounded to 2 decimals), so later rate-chart edits never rewrite history.

`find_rate(fat, snf)` picks the slab whose fat **and** SNF ranges both contain
the reading, preferring higher slab floors when ranges overlap. The app ships
with a 6-slab example chart and a Rs 28.00/L default — the dairy owner edits
both on the Rate Chart screen to match their actual purchase rates.

## Project structure

| File | Purpose |
|---|---|
| `main.py` | Entry point — inits the DB, starts the UI |
| `db.py` | SQLite layer: schema, farmers, rate chart, collections, payments, backup/restore |
| `ui.py` | CustomTkinter UI: dashboard, entry, farmers, rate chart, payments, backup |
| `printing.py` | reportlab PDFs: payment sheet, farmer statement, daily report (A4 + 80mm) |
| `requirements.txt` | `customtkinter`, `reportlab` |
| `build_exe.bat` | One-click Windows .exe build |

No AI integration — milk rates are money math and must be deterministic and
auditable; an LLM has no business touching them.

## Interview notes

**What the project is:** DairyManager is an offline desktop app for milk
collection centers. The core loop is: add farmers once → enter each farmer's
milk twice a day with fat/SNF lab readings → the app prices each entry from a
rate chart → at period end, generate a payment sheet showing what each farmer
is owed and record payments against it.

**Key technical decisions (and why):**
- **Desktop app, not web/mobile:** collection centers are single-counter shops
  with unreliable internet; a desktop app with local SQLite works with zero
  infrastructure and is sellable as a one-click `.exe`.
- **SQLite:** the whole dataset (a few thousand rows/year) fits comfortably;
  zero setup, single-file backups, and foreign keys + cascade deletes keep
  farmer/collection/payment rows consistent.
- **Rate stored at write time:** if the owner edits the rate chart next month,
  old bills must not change. Computing `amount = litres × rate` once and
  persisting it makes history immutable and auditable.
- **Slab-based rate chart (not a formula):** real dairies publish discrete
  fat/SNF slab tables, so the data model mirrors the domain instead of
  forcing a formula nobody uses. A configurable default rate guarantees a
  reading is never unbillable.
- **CustomTkinter over Tkinter:** native look on Windows with minimal code;
  the segmented shift button and modern cards are hard to get right with
  plain Tk.
- **reportlab PDFs (not HTML printing):** payment sheets need exact,
  printer-ready layouts including 80mm thermal slips; reportlab gives
  pixel-level control without a browser dependency.

**Trade-offs / limitations:**
- Single-user, single-machine: no sync between multiple counters. (A shared
  SQLite file on a LAN drive works but risks concurrent-write conflicts.)
- No GST/tax handling — milk is typically exempt, but a dairy selling
  processed products would need it.
- Rate slabs are checked for validity but not for overlaps; overlapping slabs
  resolve deterministically (higher floors win) rather than erroring, so the
  owner should keep them disjoint.
- Shift is fixed to Morning/Evening — dairies with three collections would
  need a settings-driven shift list.
- The UI was developed on Linux; the `.exe` path (`build_exe.bat`) is
  untested here and should be built and smoke-tested once on the target
  Windows PC.

**How I'd extend it:**
- Farmer-wise SMS/WhatsApp payment intimations (twilio/wa.me link with the
  statement PDF).
- Milk analyzer (Ekomilk/Lactoscan) serial-port import to skip manual
  fat/SNF typing.
- Multi-counter sync via a lightweight local server or periodic merge.
- Rate chart versioning with effective dates, so future rate changes apply
  automatically from a date instead of manual edits.
- Expense tracking (cattle feed advances, loans) deducted from payment sheets.
