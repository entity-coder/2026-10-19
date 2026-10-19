"""DairyManager — SQLite data layer.

Tables:
    farmers      farmer master (name, village, phone, bank account, IFSC)
    rate_chart   configurable fat/SNF slabs -> rate per litre
    collections  one row per farmer per shift per day
    payments     payments made to farmers against a milk-supply period
    settings     key/value store (dairy name, fallback default rate, ...)

All dates are stored as 'YYYY-MM-DD' strings so they sort lexicographically.
Money is stored as REAL and rounded to 2 decimals at write time.
"""

import os
import sqlite3
import zipfile
from datetime import date, datetime

APP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dairy_data")
DB_PATH = os.path.join(APP_DIR, "dairy.db")

SHIFTS = ("Morning", "Evening")
PAYMENT_MODES = ("Cash", "UPI", "Bank Transfer", "Cheque")

DEFAULT_RATE_CHART = [
    # (min_fat, max_fat, min_snf, max_snf, rate_per_litre, label)
    (0.0, 3.4, 0.0, 8.4, 26.0, "Low fat / low SNF"),
    (0.0, 3.4, 8.5, 99.0, 28.0, "Low fat / good SNF"),
    (3.5, 4.4, 0.0, 8.4, 30.0, "Medium fat / low SNF"),
    (3.5, 4.4, 8.5, 99.0, 33.0, "Medium fat / good SNF"),
    (4.5, 5.4, 8.5, 99.0, 37.0, "High fat / good SNF"),
    (5.5, 99.0, 8.5, 99.0, 41.0, "Premium fat / good SNF"),
]


def connect(path=DB_PATH):
    """Open a connection with foreign keys enforced."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(path=DB_PATH):
    """Create tables and seed defaults on first run. Idempotent."""
    conn = connect(path)
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS farmers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            village TEXT DEFAULT '',
            phone TEXT DEFAULT '',
            account_no TEXT DEFAULT '',
            ifsc TEXT DEFAULT '',
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS rate_chart (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            min_fat REAL NOT NULL, max_fat REAL NOT NULL,
            min_snf REAL NOT NULL, max_snf REAL NOT NULL,
            rate REAL NOT NULL,
            label TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS collections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            farmer_id INTEGER NOT NULL REFERENCES farmers(id) ON DELETE CASCADE,
            date TEXT NOT NULL,
            shift TEXT NOT NULL,
            liters REAL NOT NULL,
            fat REAL NOT NULL,
            snf REAL NOT NULL,
            rate REAL NOT NULL,
            amount REAL NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_collections_date
            ON collections(date, shift);
        CREATE INDEX IF NOT EXISTS idx_collections_farmer
            ON collections(farmer_id, date);
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            farmer_id INTEGER NOT NULL REFERENCES farmers(id) ON DELETE CASCADE,
            period_start TEXT NOT NULL,
            period_end TEXT NOT NULL,
            amount REAL NOT NULL,
            mode TEXT NOT NULL DEFAULT 'Cash',
            date TEXT NOT NULL,
            note TEXT DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_payments_farmer
            ON payments(farmer_id, period_start);
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """
    )
    # Seed default rate chart + settings once.
    if cur.execute("SELECT COUNT(*) FROM rate_chart").fetchone()[0] == 0:
        cur.executemany(
            "INSERT INTO rate_chart (min_fat, max_fat, min_snf, max_snf, rate, label)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            DEFAULT_RATE_CHART,
        )
    for key, value in (
        ("dairy_name", "Shree Dairy Collection Center"),
        ("default_rate", "28.0"),
        ("village", ""),
    ):
        cur.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
            (key, value),
        )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------- settings
def get_setting(key, default="", path=DB_PATH):
    conn = connect(path)
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default


def set_setting(key, value, path=DB_PATH):
    conn = connect(path)
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?)"
        " ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, str(value)),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------- farmers
def add_farmer(name, village="", phone="", account_no="", ifsc="", path=DB_PATH):
    conn = connect(path)
    cur = conn.execute(
        "INSERT INTO farmers (name, village, phone, account_no, ifsc)"
        " VALUES (?, ?, ?, ?, ?)",
        (name.strip(), village.strip(), phone.strip(), account_no.strip(),
         ifsc.strip()),
    )
    fid = cur.lastrowid
    conn.commit()
    conn.close()
    return fid


def update_farmer(fid, name, village, phone, account_no, ifsc, path=DB_PATH):
    conn = connect(path)
    conn.execute(
        "UPDATE farmers SET name=?, village=?, phone=?, account_no=?, ifsc=?"
        " WHERE id=?",
        (name.strip(), village.strip(), phone.strip(), account_no.strip(),
         ifsc.strip(), fid),
    )
    conn.commit()
    conn.close()


def set_farmer_active(fid, active, path=DB_PATH):
    conn = connect(path)
    conn.execute("UPDATE farmers SET active=? WHERE id=?", (1 if active else 0, fid))
    conn.commit()
    conn.close()


def list_farmers(active_only=True, path=DB_PATH):
    conn = connect(path)
    sql = "SELECT * FROM farmers"
    if active_only:
        sql += " WHERE active=1"
    sql += " ORDER BY name COLLATE NOCASE"
    rows = conn.execute(sql).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def search_farmers(query, path=DB_PATH):
    conn = connect(path)
    like = f"%{query.strip()}%"
    rows = conn.execute(
        "SELECT * FROM farmers WHERE active=1"
        " AND (name LIKE ? OR village LIKE ? OR phone LIKE ?)"
        " ORDER BY name COLLATE NOCASE",
        (like, like, like),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_farmer(fid, path=DB_PATH):
    conn = connect(path)
    row = conn.execute("SELECT * FROM farmers WHERE id=?", (fid,)).fetchone()
    conn.close()
    return dict(row) if row else None


# -------------------------------------------------------------- rate chart
def list_rate_chart(path=DB_PATH):
    conn = connect(path)
    rows = conn.execute(
        "SELECT * FROM rate_chart ORDER BY min_fat, min_snf").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_rate_slab(min_fat, max_fat, min_snf, max_snf, rate, label="", path=DB_PATH):
    if min_fat > max_fat or min_snf > max_snf or rate < 0:
        raise ValueError("Invalid slab: ranges must be ordered and rate >= 0")
    conn = connect(path)
    cur = conn.execute(
        "INSERT INTO rate_chart (min_fat, max_fat, min_snf, max_snf, rate, label)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (min_fat, max_fat, min_snf, max_snf, rate, label),
    )
    sid = cur.lastrowid
    conn.commit()
    conn.close()
    return sid


def update_rate_slab(sid, min_fat, max_fat, min_snf, max_snf, rate, label="",
                     path=DB_PATH):
    if min_fat > max_fat or min_snf > max_snf or rate < 0:
        raise ValueError("Invalid slab: ranges must be ordered and rate >= 0")
    conn = connect(path)
    conn.execute(
        "UPDATE rate_chart SET min_fat=?, max_fat=?, min_snf=?, max_snf=?,"
        " rate=?, label=? WHERE id=?",
        (min_fat, max_fat, min_snf, max_snf, rate, label, sid),
    )
    conn.commit()
    conn.close()


def delete_rate_slab(sid, path=DB_PATH):
    conn = connect(path)
    conn.execute("DELETE FROM rate_chart WHERE id=?", (sid,))
    conn.commit()
    conn.close()


def find_rate(fat, snf, path=DB_PATH):
    """Rate per litre for a (fat, SNF) pair.

    Picks the slab containing both values, preferring higher slab floors
    (the most specific/higher-quality slab wins). If nothing matches, the
    configurable default_rate setting is used so billing never blocks.
    """
    conn = connect(path)
    row = conn.execute(
        "SELECT rate FROM rate_chart"
        " WHERE min_fat <= ? AND max_fat >= ?"
        "   AND min_snf <= ? AND max_snf >= ?"
        " ORDER BY min_fat DESC, min_snf DESC LIMIT 1",
        (fat, fat, snf, snf),
    ).fetchone()
    default = conn.execute(
        "SELECT value FROM settings WHERE key='default_rate'").fetchone()
    conn.close()
    if row:
        return float(row["rate"])
    return float(default["value"]) if default else 28.0


# ------------------------------------------------------------- collections
def add_collection(farmer_id, day, shift, liters, fat, snf, path=DB_PATH):
    if liters <= 0:
        raise ValueError("Liters must be positive")
    if fat < 0 or snf < 0:
        raise ValueError("Fat and SNF cannot be negative")
    if shift not in SHIFTS:
        raise ValueError(f"Shift must be one of {SHIFTS}")
    rate = find_rate(fat, snf, path)
    amount = round(liters * rate, 2)
    conn = connect(path)
    cur = conn.execute(
        "INSERT INTO collections (farmer_id, date, shift, liters, fat, snf,"
        " rate, amount) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (farmer_id, day, shift, liters, fat, snf, rate, amount),
    )
    cid = cur.lastrowid
    conn.commit()
    conn.close()
    return cid, rate, amount


def update_collection(cid, liters, fat, snf, path=DB_PATH):
    if liters <= 0:
        raise ValueError("Liters must be positive")
    rate = find_rate(fat, snf, path)
    amount = round(liters * rate, 2)
    conn = connect(path)
    conn.execute(
        "UPDATE collections SET liters=?, fat=?, snf=?, rate=?, amount=?"
        " WHERE id=?",
        (liters, fat, snf, rate, amount, cid),
    )
    conn.commit()
    conn.close()
    return rate, amount


def delete_collection(cid, path=DB_PATH):
    conn = connect(path)
    conn.execute("DELETE FROM collections WHERE id=?", (cid,))
    conn.commit()
    conn.close()


def list_collections(day=None, farmer_id=None, start=None, end=None,
                     path=DB_PATH):
    conn = connect(path)
    sql = ("SELECT c.*, f.name AS farmer_name, f.village FROM collections c"
           " JOIN farmers f ON f.id = c.farmer_id WHERE 1=1")
    params = []
    if day:
        sql += " AND c.date = ?"
        params.append(day)
    if farmer_id:
        sql += " AND c.farmer_id = ?"
        params.append(farmer_id)
    if start:
        sql += " AND c.date >= ?"
        params.append(start)
    if end:
        sql += " AND c.date <= ?"
        params.append(end)
    sql += " ORDER BY c.date, c.shift, f.name COLLATE NOCASE"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def today_iso():
    return date.today().isoformat()


# -------------------------------------------------------------- dashboard
def dashboard_stats(day=None, path=DB_PATH):
    day = day or today_iso()
    conn = connect(path)
    liters_today = conn.execute(
        "SELECT COALESCE(SUM(liters),0) FROM collections WHERE date=?",
        (day,)).fetchone()[0]
    liters_morning = conn.execute(
        "SELECT COALESCE(SUM(liters),0) FROM collections"
        " WHERE date=? AND shift='Morning'", (day,)).fetchone()[0]
    farmers_today = conn.execute(
        "SELECT COUNT(DISTINCT farmer_id) FROM collections WHERE date=?",
        (day,)).fetchone()[0]
    active_farmers = conn.execute(
        "SELECT COUNT(*) FROM farmers WHERE active=1").fetchone()[0]
    gross_all = conn.execute(
        "SELECT COALESCE(SUM(amount),0) FROM collections").fetchone()[0]
    paid_all = conn.execute(
        "SELECT COALESCE(SUM(amount),0) FROM payments").fetchone()[0]
    month_start = day[:8] + "01"
    liters_month = conn.execute(
        "SELECT COALESCE(SUM(liters),0) FROM collections WHERE date>=?",
        (month_start,)).fetchone()[0]
    conn.close()
    return {
        "day": day,
        "liters_today": round(liters_today, 2),
        "liters_morning": round(liters_morning, 2),
        "liters_evening": round(liters_today - liters_morning, 2),
        "farmers_today": farmers_today,
        "active_farmers": active_farmers,
        "pending_payments": round(gross_all - paid_all, 2),
        "liters_month": round(liters_month, 2),
    }


# ------------------------------------------------------- payment sheets
def payment_sheet(start, end, path=DB_PATH):
    """Per-farmer totals for a milk-supply period.

    Each row: opening pending (gross before start minus payments whose
    period ended before start), period liters/gross, paid in this exact
    period, pending at end of period. Payments are attributed to the
    milk-supply period they were recorded against (period_start/period_end),
    not their calendar date, so late payments for old milk still clear
    the opening balance.
    """
    conn = connect(path)
    farmers = [dict(r) for r in conn.execute(
        "SELECT * FROM farmers WHERE active=1 ORDER BY name COLLATE NOCASE")]
    rows = []
    for f in farmers:
        fid = f["id"]
        gross_before = conn.execute(
            "SELECT COALESCE(SUM(amount),0) FROM collections"
            " WHERE farmer_id=? AND date<?", (fid, start)).fetchone()[0]
        paid_before = conn.execute(
            "SELECT COALESCE(SUM(amount),0) FROM payments"
            " WHERE farmer_id=? AND period_end<?", (fid, start)).fetchone()[0]
        opening = round(gross_before - paid_before, 2)
        agg = conn.execute(
            "SELECT COALESCE(SUM(liters),0), COALESCE(SUM(amount),0),"
            " COUNT(*) FROM collections WHERE farmer_id=? AND date>=? AND date<=?",
            (fid, start, end)).fetchone()
        paid = conn.execute(
            "SELECT COALESCE(SUM(amount),0) FROM payments"
            " WHERE farmer_id=? AND period_start=? AND period_end=?",
            (fid, start, end)).fetchone()[0]
        gross = round(agg[1], 2)
        pending = round(opening + gross - paid, 2)
        rows.append({
            "farmer_id": fid,
            "name": f["name"],
            "village": f["village"],
            "phone": f["phone"],
            "account_no": f["account_no"],
            "ifsc": f["ifsc"],
            "opening": opening,
            "liters": round(agg[0], 2),
            "entries": agg[2],
            "gross": gross,
            "paid": round(paid, 2),
            "pending": pending,
        })
    conn.close()
    rows = [r for r in rows if r["entries"] or r["opening"] or r["paid"]]
    total = {
        "opening": round(sum(r["opening"] for r in rows), 2),
        "liters": round(sum(r["liters"] for r in rows), 2),
        "gross": round(sum(r["gross"] for r in rows), 2),
        "paid": round(sum(r["paid"] for r in rows), 2),
        "pending": round(sum(r["pending"] for r in rows), 2),
        "farmers": len(rows),
    }
    return rows, total


def record_payment(farmer_id, period_start, period_end, amount, mode, day,
                   note="", path=DB_PATH):
    if amount <= 0:
        raise ValueError("Payment amount must be positive")
    if mode not in PAYMENT_MODES:
        raise ValueError(f"Mode must be one of {PAYMENT_MODES}")
    conn = connect(path)
    cur = conn.execute(
        "INSERT INTO payments (farmer_id, period_start, period_end, amount,"
        " mode, date, note) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (farmer_id, period_start, period_end, round(amount, 2), mode, day,
         note.strip()),
    )
    pid = cur.lastrowid
    conn.commit()
    conn.close()
    return pid


def list_payments(farmer_id=None, start=None, end=None, path=DB_PATH):
    conn = connect(path)
    sql = ("SELECT p.*, f.name AS farmer_name FROM payments p"
           " JOIN farmers f ON f.id = p.farmer_id WHERE 1=1")
    params = []
    if farmer_id:
        sql += " AND p.farmer_id=?"
        params.append(farmer_id)
    if start:
        sql += " AND p.date>=?"
        params.append(start)
    if end:
        sql += " AND p.date<=?"
        params.append(end)
    sql += " ORDER BY p.date DESC, f.name COLLATE NOCASE"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------- backup
def backup_db(dest_dir=None, path=DB_PATH):
    """Copy the live DB into a timestamped zip. Returns the zip path."""
    dest_dir = dest_dir or os.path.join(APP_DIR, "backups")
    os.makedirs(dest_dir, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_path = os.path.join(dest_dir, f"dairymanager_backup_{stamp}.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(path, arcname="dairy.db")
    # Keep only the 14 newest backups.
    zips = sorted(f for f in os.listdir(dest_dir) if f.endswith(".zip"))
    for old in zips[:-14]:
        os.remove(os.path.join(dest_dir, old))
    return zip_path


def restore_db(zip_path, path=DB_PATH):
    """Restore dairy.db from a backup zip, keeping a safety copy first."""
    if not zipfile.is_zipfile(zip_path):
        raise ValueError("Not a valid backup zip")
    safety = path + ".safety-copy"
    if os.path.exists(path):
        with open(path, "rb") as src, open(safety, "wb") as dst:
            dst.write(src.read())
    with zipfile.ZipFile(zip_path) as z:
        names = z.namelist()
        if "dairy.db" not in names:
            raise ValueError("Backup zip does not contain dairy.db")
        with z.open("dairy.db") as src, open(path, "wb") as dst:
            dst.write(src.read())
    # Sanity-check the restored file is a readable DB.
    conn = sqlite3.connect(path)
    try:
        conn.execute("SELECT COUNT(*) FROM farmers").fetchone()
    finally:
        conn.close()
    return safety if os.path.exists(safety) else None
