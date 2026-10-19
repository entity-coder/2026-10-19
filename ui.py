"""DairyManager — CustomTkinter desktop UI.

Screens: Dashboard, New Entry (collection), Farmers, Rate Chart,
Payments (period sheets + pay + printable PDFs), Backup/Settings.
Runs offline; all data lives in dairy_data/dairy.db (SQLite).
"""

import os
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk

import db
import printing

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")


def open_file(path):
    """Open a file with the OS default program (best effort)."""
    try:
        if hasattr(os, "startfile"):          # Windows
            os.startfile(path)                # noqa: S606 (local file)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])  # noqa: S603,S607
        else:
            subprocess.Popen(["xdg-open", path])  # noqa: S603,S607
    except Exception:
        pass


def num(value, label):
    """Parse a float entry value, raising a friendly error."""
    try:
        return float(str(value).strip())
    except ValueError:
        raise ValueError(f"{label} must be a number")


class ScrollTable(ctk.CTkScrollableFrame):
    """Lightweight read-only table: bold header + grid rows."""

    def __init__(self, parent, headers, widths=None, **kwargs):
        super().__init__(parent, **kwargs)
        self._headers = headers
        widths = widths or [1] * len(headers)
        self._widths = widths
        for i, h in enumerate(headers):
            lbl = ctk.CTkLabel(self, text=h, font=ctk.CTkFont(weight="bold"))
            lbl.grid(row=0, column=i, padx=6, pady=(4, 8), sticky="w")
            self.grid_columnconfigure(i, weight=widths[i])
        self._row = 1

    def add_row(self, cells, bold_last=False):
        for i, c in enumerate(cells):
            font = ctk.CTkFont(weight="bold") if bold_last and i == 0 else None
            lbl = ctk.CTkLabel(self, text=str(c), font=font, anchor="w")
            lbl.grid(row=self._row, column=i, padx=6, pady=2, sticky="w")
        self._row += 1
        return self._row - 1

    def clear(self):
        for w in self.winfo_children():
            w.destroy()
        self._row = 0
        # re-add header
        for i, h in enumerate(self._headers):
            lbl = ctk.CTkLabel(self, text=h, font=ctk.CTkFont(weight="bold"))
            lbl.grid(row=0, column=i, padx=6, pady=(4, 8), sticky="w")
            self.grid_columnconfigure(i, weight=self._widths[i])
        self._row = 1


class Dialog(ctk.CTkToplevel):
    """Simple modal form dialog. fields = [(key, label, default)]."""

    def __init__(self, parent, title, fields, on_save, dropdowns=None):
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.on_save = on_save
        self.vars = {}
        self.transient(parent)
        self.grab_set()
        frm = ctk.CTkFrame(self)
        frm.pack(padx=16, pady=16, fill="both", expand=True)
        dropdowns = dropdowns or {}
        for i, (key, label, default) in enumerate(fields):
            ctk.CTkLabel(frm, text=label).grid(
                row=i, column=0, padx=8, pady=6, sticky="w")
            if key in dropdowns:
                var = ctk.StringVar(value=default)
                w = ctk.CTkOptionMenu(frm, variable=var,
                                      values=dropdowns[key], width=220)
            else:
                var = ctk.StringVar(value=default)
                w = ctk.CTkEntry(frm, textvariable=var, width=220)
            w.grid(row=i, column=1, padx=8, pady=6, sticky="ew")
            self.vars[key] = var
        btns = ctk.CTkFrame(frm, fg_color="transparent")
        btns.grid(row=len(fields), column=0, columnspan=2, pady=(10, 0))
        ctk.CTkButton(btns, text="Save", command=self._save).pack(
            side="left", padx=6)
        ctk.CTkButton(btns, text="Cancel", fg_color="gray",
                      command=self.destroy).pack(side="left", padx=6)
        self.bind("<Return>", lambda _e: self._save())
        self.bind("<Escape>", lambda _e: self.destroy())

    def _save(self):
        try:
            self.on_save({k: v.get() for k, v in self.vars.items()})
        except Exception as exc:  # show friendly error, keep dialog open
            messagebox.showerror("Error", str(exc), parent=self)
            return
        self.destroy()


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("DairyManager — Milk Collection")
        self.geometry("1080x700")
        self.minsize(900, 600)

        self.sidebar = ctk.CTkFrame(self, width=180, corner_radius=0)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)
        ctk.CTkLabel(self.sidebar, text="DairyManager",
                     font=ctk.CTkFont(size=18, weight="bold")).pack(
            pady=(16, 4), padx=12)
        self.dairy_lbl = ctk.CTkLabel(
            self.sidebar, text=db.get_setting("dairy_name"),
            font=ctk.CTkFont(size=11), wraplength=150)
        self.dairy_lbl.pack(pady=(0, 12), padx=12)

        self.nav_buttons = {}
        for key, label in [("dashboard", "Dashboard"),
                           ("entry", "New Entry"),
                           ("farmers", "Farmers"),
                           ("rates", "Rate Chart"),
                           ("payments", "Payments"),
                           ("backup", "Backup")]:
            b = ctk.CTkButton(self.sidebar, text=label, anchor="w",
                              fg_color="transparent", text_color=("black", "white"),
                              command=lambda k=key: self.show(k))
            b.pack(fill="x", padx=10, pady=3)
            self.nav_buttons[key] = b

        self.status = ctk.CTkLabel(self.sidebar, text="", wraplength=150,
                                   font=ctk.CTkFont(size=11))
        self.status.pack(side="bottom", pady=12, padx=12)

        self.content = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.content.pack(side="right", fill="both", expand=True,
                          padx=12, pady=12)
        self._screen = None
        self.show("dashboard")

    # ------------------------------------------------------------- shell
    def say(self, msg):
        self.status.configure(text=msg)
        self.after(6000, lambda: self.status.configure(text=""))

    def show(self, key):
        if self._screen is not None:
            self._screen.destroy()
        for k, b in self.nav_buttons.items():
            b.configure(fg_color="#1f6feb" if k == key else "transparent")
        builders = {
            "dashboard": self.build_dashboard,
            "entry": self.build_entry,
            "farmers": self.build_farmers,
            "rates": self.build_rates,
            "payments": self.build_payments,
            "backup": self.build_backup,
        }
        self._screen = builders[key]()
        self._screen.pack(fill="both", expand=True)

    def _title(self, parent, text):
        ctk.CTkLabel(parent, text=text,
                     font=ctk.CTkFont(size=20, weight="bold")).pack(
            anchor="w", pady=(0, 12))

    def _cards(self, parent, stats):
        """Row of stat cards: [(label, value), ...]."""
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=(0, 12))
        for label, value in stats:
            card = ctk.CTkFrame(row, corner_radius=10)
            card.pack(side="left", fill="x", expand=True, padx=6)
            ctk.CTkLabel(card, text=label,
                         font=ctk.CTkFont(size=12)).pack(pady=(10, 0))
            ctk.CTkLabel(card, text=value,
                         font=ctk.CTkFont(size=22, weight="bold")).pack(
                pady=(0, 10))

    # --------------------------------------------------------- dashboard
    def build_dashboard(self):
        f = ctk.CTkFrame(self.content, fg_color="transparent")
        self._title(f, "Dashboard")
        s = db.dashboard_stats()
        self._cards(f, [
            ("Today's milk", f"{s['liters_today']:.1f} L"),
            ("Farmers today", str(s["farmers_today"])),
            ("Pending payments", f"Rs {s['pending_payments']:.2f}"),
            ("This month", f"{s['liters_month']:.1f} L"),
        ])
        ctk.CTkLabel(f, text=f"Today ({s['day']}): "
                     f"Morning {s['liters_morning']:.1f} L · "
                     f"Evening {s['liters_evening']:.1f} L",
                     font=ctk.CTkFont(size=13)).pack(anchor="w", pady=(0, 8))
        top = ctk.CTkFrame(f, fg_color="transparent")
        top.pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(top, text="Today's entries",
                     font=ctk.CTkFont(size=15, weight="bold")).pack(side="left")
        ctk.CTkButton(top, text="Daily report (A4)", width=150,
                      command=lambda: self.print_daily("A4")).pack(
            side="right", padx=4)
        ctk.CTkButton(top, text="Daily report (80mm)", width=160,
                      command=lambda: self.print_daily("80mm")).pack(
            side="right", padx=4)
        tbl = ScrollTable(f, ["Farmer", "Village", "Shift", "Litres",
                              "Fat", "SNF", "Rate", "Amount", ""],
                          widths=[3, 2, 1, 1, 1, 1, 1, 1, 1])
        tbl.pack(fill="both", expand=True)
        for c in db.list_collections(day=s["day"]):
            r = tbl.add_row([c["farmer_name"], c["village"], c["shift"],
                             f"{c['liters']:.2f}", f"{c['fat']:.1f}",
                             f"{c['snf']:.1f}", f"{c['rate']:.2f}",
                             f"Rs {c['amount']:.2f}", ""])
            ctk.CTkButton(tbl, text="Delete", width=60, fg_color="#c0392b",
                          command=lambda cid=c["id"]: self.delete_entry(cid)
                          ).grid(row=r, column=8, padx=4, pady=2)
        return f

    def delete_entry(self, cid):
        if messagebox.askyesno("Delete", "Delete this collection entry?"):
            db.delete_collection(cid)
            self.say("Entry deleted.")
            self.show("dashboard")

    def print_daily(self, paper):
        day = db.today_iso()
        cols = db.list_collections(day=day)
        if not cols:
            self.say("No entries today — nothing to print.")
            return
        summary = {
            "liters": sum(c["liters"] for c in cols),
            "morning": sum(c["liters"] for c in cols
                           if c["shift"] == "Morning"),
            "evening": sum(c["liters"] for c in cols
                           if c["shift"] == "Evening"),
            "farmers": len({c["farmer_id"] for c in cols}),
            "value": sum(c["amount"] for c in cols),
        }
        path = printing.daily_report_pdf(day, cols, summary, paper=paper)
        self.say(f"Saved: {path}")
        open_file(path)

    # ------------------------------------------------------------- entry
    def build_entry(self):
        f = ctk.CTkFrame(self.content, fg_color="transparent")
        self._title(f, "New Collection Entry")
        form = ctk.CTkFrame(f)
        form.pack(fill="x", pady=(0, 10))

        farmers = db.list_farmers()
        self._farmer_map = {f"{x['name']} ({x['village']})"
                            .strip(): x["id"] for x in farmers}
        names = sorted(self._farmer_map)

        ctk.CTkLabel(form, text="Farmer (type to search)").grid(
            row=0, column=0, padx=10, pady=8, sticky="w")
        self.farmer_var = ctk.StringVar()
        self.farmer_box = ctk.CTkComboBox(form, variable=self.farmer_var,
                                         values=names, width=300)
        self.farmer_box.grid(row=0, column=1, padx=10, pady=8, sticky="ew")
        self.farmer_box.bind("<KeyRelease>", self._filter_farmers)

        ctk.CTkLabel(form, text="Date (YYYY-MM-DD)").grid(
            row=1, column=0, padx=10, pady=8, sticky="w")
        self.date_var = ctk.StringVar(value=db.today_iso())
        ctk.CTkEntry(form, textvariable=self.date_var, width=300).grid(
            row=1, column=1, padx=10, pady=8, sticky="ew")

        ctk.CTkLabel(form, text="Shift").grid(row=2, column=0, padx=10,
                                             pady=8, sticky="w")
        self.shift_var = ctk.StringVar(value="Morning")
        ctk.CTkSegmentedButton(form, variable=self.shift_var,
                               values=list(db.SHIFTS)).grid(
            row=2, column=1, padx=10, pady=8, sticky="w")

        self.liters_var = ctk.StringVar()
        self.fat_var = ctk.StringVar()
        self.snf_var = ctk.StringVar()
        for i, (lbl, var) in enumerate([("Litres", self.liters_var),
                                        ("Fat", self.fat_var),
                                        ("SNF", self.snf_var)]):
            ctk.CTkLabel(form, text=lbl).grid(row=3 + i, column=0,
                                             padx=10, pady=8, sticky="w")
            e = ctk.CTkEntry(form, textvariable=var, width=300)
            e.grid(row=3 + i, column=1, padx=10, pady=8, sticky="ew")
            var.trace_add("write", lambda *_a: self._preview_rate())
            e.bind("<Return>", lambda _e: self.save_entry())

        self.rate_preview = ctk.CTkLabel(
            form, text="Rate: —", font=ctk.CTkFont(size=14, weight="bold"))
        self.rate_preview.grid(row=6, column=0, columnspan=2,
                               padx=10, pady=8, sticky="w")
        ctk.CTkButton(form, text="Save Entry", width=200,
                      command=self.save_entry).grid(
            row=7, column=0, columnspan=2, padx=10, pady=(4, 12))
        form.grid_columnconfigure(1, weight=1)

        if not farmers:
            ctk.CTkLabel(
                f, text="No farmers yet — add one on the Farmers screen first.",
                text_color="#c0392b").pack(anchor="w", pady=6)
        return f

    def _filter_farmers(self, _event=None):
        q = self.farmer_var.get().lower()
        names = [n for n in self._farmer_map if q in n.lower()]
        self.farmer_box.configure(values=sorted(names) or
                                  sorted(self._farmer_map))

    def _preview_rate(self):
        try:
            fat = num(self.fat_var.get(), "Fat")
            snf = num(self.snf_var.get(), "SNF")
            liters = num(self.liters_var.get(), "Litres")
            rate = db.find_rate(fat, snf)
            self.rate_preview.configure(
                text=f"Rate: Rs {rate:.2f}/L   →   Rs {liters * rate:.2f}")
        except ValueError:
            self.rate_preview.configure(text="Rate: —")

    def save_entry(self):
        try:
            key = self.farmer_var.get().strip()
            if key not in self._farmer_map:
                # try a case-insensitive match in case the user typed a name
                matches = [k for k in self._farmer_map
                           if k.lower() == key.lower()]
                if not matches:
                    raise ValueError("Pick a farmer from the list")
                key = matches[0]
            fid = self._farmer_map[key]
            day = self.date_var.get().strip()
            if len(day) != 10 or day[4] != "-" or day[7] != "-":
                raise ValueError("Date must be YYYY-MM-DD")
            liters = num(self.liters_var.get(), "Litres")
            fat = num(self.fat_var.get(), "Fat")
            snf = num(self.snf_var.get(), "SNF")
            _cid, rate, amount = db.add_collection(
                fid, day, self.shift_var.get(), liters, fat, snf)
        except ValueError as exc:
            messagebox.showerror("Cannot save", str(exc))
            return
        self.say(f"Saved: {liters:.2f} L @ Rs {rate:.2f} = Rs {amount:.2f}")
        self.liters_var.set("")
        self.fat_var.set("")
        self.snf_var.set("")

    # ------------------------------------------------------------ farmers
    def build_farmers(self):
        f = ctk.CTkFrame(self.content, fg_color="transparent")
        self._title(f, "Farmers")
        top = ctk.CTkFrame(f, fg_color="transparent")
        top.pack(fill="x", pady=(0, 8))
        self.fq = ctk.StringVar()
        se = ctk.CTkEntry(top, textvariable=self.fq, width=260,
                          placeholder_text="Search name / village / phone")
        se.pack(side="left", padx=(0, 8))
        se.bind("<KeyRelease>", lambda _e: self._refresh_farmer_table())
        ctk.CTkButton(top, text="+ Add Farmer",
                      command=self.farmer_dialog).pack(side="left")
        self.farmer_tbl = ScrollTable(
            f, ["Name", "Village", "Phone", "Account / IFSC", "Active", ""],
            widths=[3, 2, 2, 3, 1, 2])
        self.farmer_tbl.pack(fill="both", expand=True)
        self._refresh_farmer_table()
        return f

    def _refresh_farmer_table(self):
        q = self.fq.get().strip()
        farmers = db.search_farmers(q) if q else db.list_farmers(active_only=False)
        self.farmer_tbl.clear()
        for x in farmers:
            r = self.farmer_tbl.add_row([
                x["name"], x["village"], x["phone"],
                f"{x['account_no']} / {x['ifsc']}".strip(" /"),
                "Yes" if x["active"] else "No", ""])
            btns = ctk.CTkFrame(self.farmer_tbl, fg_color="transparent")
            btns.grid(row=r, column=5, padx=2, pady=2, sticky="w")
            ctk.CTkButton(btns, text="Edit", width=55,
                          command=lambda fid=x["id"]: self.farmer_dialog(fid)
                          ).pack(side="left", padx=2)
            lbl = "Hide" if x["active"] else "Show"
            ctk.CTkButton(btns, text=lbl, width=55, fg_color="gray",
                          command=lambda fid=x["id"], a=x["active"]:
                          self.toggle_farmer(fid, a)).pack(side="left", padx=2)

    def toggle_farmer(self, fid, active):
        db.set_farmer_active(fid, not active)
        self._refresh_farmer_table()
        self.say("Farmer hidden." if active else "Farmer restored.")

    def farmer_dialog(self, fid=None):
        x = db.get_farmer(fid) if fid else None
        fields = [("name", "Name*", x["name"] if x else ""),
                  ("village", "Village", x["village"] if x else ""),
                  ("phone", "Phone", x["phone"] if x else ""),
                  ("account_no", "Bank account no.",
                   x["account_no"] if x else ""),
                  ("ifsc", "IFSC", x["ifsc"] if x else "")]

        def on_save(v):
            if not v["name"].strip():
                raise ValueError("Name is required")
            if fid:
                db.update_farmer(fid, v["name"], v["village"], v["phone"],
                                 v["account_no"], v["ifsc"])
            else:
                db.add_farmer(v["name"], v["village"], v["phone"],
                              v["account_no"], v["ifsc"])
            self._refresh_farmer_table()
            self.say("Farmer saved.")

        Dialog(self, "Edit Farmer" if fid else "Add Farmer", fields, on_save)

    # --------------------------------------------------------- rate chart
    def build_rates(self):
        f = ctk.CTkFrame(self.content, fg_color="transparent")
        self._title(f, "Rate Chart")
        ctk.CTkLabel(
            f, text="Rate per litre is picked from the first slab whose fat "
                   "AND SNF ranges contain the reading. Keep slabs "
                   "non-overlapping; readings outside every slab fall back "
                   "to the default rate below.",
            wraplength=900, font=ctk.CTkFont(size=12)).pack(
            anchor="w", pady=(0, 8))
        top = ctk.CTkFrame(f, fg_color="transparent")
        top.pack(fill="x", pady=(0, 8))
        ctk.CTkButton(top, text="+ Add Slab",
                      command=self.slab_dialog).pack(side="left")
        ctk.CTkLabel(top, text="Default rate (Rs/L):").pack(
            side="left", padx=(16, 4))
        self.def_rate = ctk.StringVar(
            value=db.get_setting("default_rate", "28.0"))
        ctk.CTkEntry(top, textvariable=self.def_rate, width=80).pack(
            side="left")
        ctk.CTkButton(top, text="Save", width=70,
                      command=self.save_default_rate).pack(side="left", padx=6)
        self.rate_tbl = ScrollTable(
            f, ["Fat range", "SNF range", "Rate (Rs/L)", "Label", ""],
            widths=[2, 2, 2, 4, 2])
        self.rate_tbl.pack(fill="both", expand=True)
        self._refresh_rate_table()
        return f

    def _refresh_rate_table(self):
        self.rate_tbl.clear()
        for s in db.list_rate_chart():
            r = self.rate_tbl.add_row([
                f"{s['min_fat']:.1f} – {s['max_fat']:.1f}",
                f"{s['min_snf']:.1f} – {s['max_snf']:.1f}",
                f"{s['rate']:.2f}", s["label"], ""])
            btns = ctk.CTkFrame(self.rate_tbl, fg_color="transparent")
            btns.grid(row=r, column=4, padx=2, pady=2, sticky="w")
            ctk.CTkButton(btns, text="Edit", width=55,
                          command=lambda sid=s["id"]: self.slab_dialog(sid)
                          ).pack(side="left", padx=2)
            ctk.CTkButton(btns, text="Delete", width=60, fg_color="#c0392b",
                          command=lambda sid=s["id"]: self.delete_slab(sid)
                          ).pack(side="left", padx=2)

    def slab_dialog(self, sid=None):
        slabs = {s["id"]: s for s in db.list_rate_chart()}
        s = slabs.get(sid)
        g = lambda k: str(s[k]) if s else ""
        fields = [("min_fat", "Min fat", g("min_fat")),
                  ("max_fat", "Max fat", g("max_fat")),
                  ("min_snf", "Min SNF", g("min_snf")),
                  ("max_snf", "Max SNF", g("max_snf")),
                  ("rate", "Rate (Rs/L)*", g("rate")),
                  ("label", "Label", s["label"] if s else "")]

        def on_save(v):
            args = (num(v["min_fat"], "Min fat"), num(v["max_fat"], "Max fat"),
                    num(v["min_snf"], "Min SNF"), num(v["max_snf"], "Max SNF"),
                    num(v["rate"], "Rate"), v["label"].strip())
            if sid:
                db.update_rate_slab(sid, *args)
            else:
                db.add_rate_slab(*args)
            self._refresh_rate_table()
            self.say("Rate chart saved.")

        Dialog(self, "Edit Slab" if sid else "Add Slab", fields, on_save)

    def delete_slab(self, sid):
        if messagebox.askyesno("Delete", "Delete this rate slab?"):
            db.delete_rate_slab(sid)
            self._refresh_rate_table()
            self.say("Slab deleted.")

    def save_default_rate(self):
        try:
            r = num(self.def_rate.get(), "Default rate")
            if r < 0:
                raise ValueError("Default rate cannot be negative")
        except ValueError as exc:
            messagebox.showerror("Error", str(exc))
            return
        db.set_setting("default_rate", str(r))
        self.say(f"Default rate set to Rs {r:.2f}/L.")

    # ------------------------------------------------------------ payments
    def build_payments(self):
        f = ctk.CTkFrame(self.content, fg_color="transparent")
        self._title(f, "Payment Sheets")
        top = ctk.CTkFrame(f, fg_color="transparent")
        top.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(top, text="Period:").pack(side="left", padx=(0, 4))
        self.p_start = ctk.StringVar(value=db.today_iso()[:8] + "01")
        self.p_end = ctk.StringVar(value=db.today_iso())
        ctk.CTkEntry(top, textvariable=self.p_start, width=120).pack(
            side="left", padx=4)
        ctk.CTkLabel(top, text="to").pack(side="left")
        ctk.CTkEntry(top, textvariable=self.p_end, width=120).pack(
            side="left", padx=4)
        ctk.CTkButton(top, text="Generate Sheet", width=140,
                      command=self._refresh_sheet).pack(side="left", padx=8)
        ctk.CTkButton(top, text="Print Sheet (A4)", width=140,
                      command=self.print_sheet).pack(side="left", padx=4)
        self.sheet_tbl = ScrollTable(
            f, ["Farmer", "Village", "Opening", "Litres", "Gross",
                "Paid", "Pending", ""],
            widths=[3, 2, 1, 1, 1, 1, 1, 3])
        self.sheet_tbl.pack(fill="both", expand=True)
        self._sheet_rows = []
        self._refresh_sheet()
        ctk.CTkLabel(f, text="Recent payments",
                     font=ctk.CTkFont(size=15, weight="bold")).pack(
            anchor="w", pady=(10, 4))
        ptbl = ScrollTable(f, ["Date", "Farmer", "Period", "Mode", "Amount",
                               "Note"], widths=[1, 3, 2, 1, 1, 3], height=140)
        ptbl.pack(fill="x")
        for p in db.list_payments()[:50]:
            ptbl.add_row([p["date"], p["farmer_name"],
                          f"{p['period_start']}→{p['period_end']}", p["mode"],
                          f"Rs {p['amount']:.2f}", p["note"] or "-"])
        return f

    def _period(self):
        s, e = self.p_start.get().strip(), self.p_end.get().strip()
        if len(s) != 10 or len(e) != 10 or s > e:
            raise ValueError("Period must be YYYY-MM-DD to YYYY-MM-DD, "
                             "start ≤ end")
        return s, e

    def _refresh_sheet(self):
        try:
            s, e = self._period()
        except ValueError as exc:
            messagebox.showerror("Error", str(exc))
            return
        rows, total = db.payment_sheet(s, e)
        self._sheet_rows = rows
        self._sheet_total = total
        self.sheet_tbl.clear()
        for r in rows:
            row = self.sheet_tbl.add_row([
                r["name"], r["village"], f"{r['opening']:.2f}",
                f"{r['liters']:.2f}", f"{r['gross']:.2f}",
                f"{r['paid']:.2f}", f"{r['pending']:.2f}", ""])
            btns = ctk.CTkFrame(self.sheet_tbl, fg_color="transparent")
            btns.grid(row=row, column=7, padx=2, pady=2, sticky="w")
            ctk.CTkButton(btns, text="Pay", width=55,
                          command=lambda rr=r: self.pay_dialog(rr)).pack(
                side="left", padx=2)
            ctk.CTkButton(btns, text="Statement", width=80,
                          command=lambda rr=r: self.print_statement(rr)).pack(
                side="left", padx=2)
        t = total
        self.sheet_tbl.add_row(
            [f"TOTAL ({t['farmers']})", "", f"{t['opening']:.2f}",
             f"{t['liters']:.2f}", f"{t['gross']:.2f}", f"{t['paid']:.2f}",
             f"{t['pending']:.2f}", ""], bold_last=True)

    def pay_dialog(self, r):
        max_pay = round(r["opening"] + r["gross"] - r["paid"], 2)
        if max_pay <= 0:
            messagebox.showinfo("Nothing due",
                                f"{r['name']} has no pending amount.")
            return
        fields = [("amount", f"Amount* (max Rs {max_pay:.2f})",
                   f"{max_pay:.2f}"),
                  ("date", "Date (YYYY-MM-DD)", db.today_iso()),
                  ("note", "Note", "")]
        dropdowns = {"mode": list(db.PAYMENT_MODES)}
        fields.insert(1, ("mode", "Mode*", "Cash"))

        def on_save(v):
            amt = num(v["amount"], "Amount")
            if amt > max_pay:
                raise ValueError(
                    f"Cannot pay more than the pending Rs {max_pay:.2f}")
            s, e = self._period()
            db.record_payment(r["farmer_id"], s, e, amt, v["mode"],
                              v["date"].strip(), v["note"])
            self._refresh_sheet()
            self.say(f"Paid Rs {amt:.2f} to {r['name']}.")

        Dialog(self, f"Pay — {r['name']}", fields, on_save,
               dropdowns=dropdowns)

    def print_sheet(self):
        try:
            s, e = self._period()
        except ValueError as exc:
            messagebox.showerror("Error", str(exc))
            return
        rows, total = db.payment_sheet(s, e)
        if not rows:
            self.say("No milk supplied in this period — nothing to print.")
            return
        path = printing.payment_sheet_pdf(s, e, rows, total)
        self.say(f"Saved: {path}")
        open_file(path)

    def print_statement(self, r):
        s, e = self._period()
        farmer = db.get_farmer(r["farmer_id"])
        cols = db.list_collections(farmer_id=r["farmer_id"], start=s, end=e)
        pays = [p for p in db.list_payments(farmer_id=r["farmer_id"])
                if p["period_start"] == s and p["period_end"] == e]
        totals = {"gross": r["gross"], "paid": r["paid"],
                  "pending": r["pending"]}
        path = printing.farmer_statement_pdf(farmer, s, e, cols, pays,
                                             r["opening"], totals)
        self.say(f"Saved: {path}")
        open_file(path)

    # -------------------------------------------------------------- backup
    def build_backup(self):
        f = ctk.CTkFrame(self.content, fg_color="transparent")
        self._title(f, "Backup & Settings")
        ctk.CTkButton(f, text="Backup Now (zip)", width=220,
                      command=self.do_backup).pack(anchor="w", pady=6)
        ctk.CTkButton(f, text="Restore from Backup…", width=220,
                      command=self.do_restore).pack(anchor="w", pady=6)
        ctk.CTkButton(f, text="Open Data Folder", width=220,
                      command=lambda: open_file(db.APP_DIR)).pack(
            anchor="w", pady=6)
        ctk.CTkLabel(f, text="Restore keeps a .safety-copy of the current "
                     "database first.", font=ctk.CTkFont(size=12)).pack(
            anchor="w", pady=(0, 16))
        ctk.CTkLabel(f, text="Dairy name",
                     font=ctk.CTkFont(weight="bold")).pack(anchor="w")
        self.dname = ctk.StringVar(value=db.get_setting("dairy_name"))
        ctk.CTkEntry(f, textvariable=self.dname, width=400).pack(
            anchor="w", pady=6)
        ctk.CTkButton(f, text="Save Settings", width=160,
                      command=self.save_settings).pack(anchor="w", pady=6)
        return f

    def do_backup(self):
        path = db.backup_db()
        self.say(f"Backup saved: {path}")
        messagebox.showinfo("Backup", f"Saved:\n{path}")

    def do_restore(self):
        zp = filedialog.askopenfilename(
            title="Choose backup zip",
            filetypes=[("Zip files", "*.zip")])
        if not zp:
            return
        if not messagebox.askyesno(
                "Restore",
                "Restore will replace the current database.\n"
                "A safety copy is kept first. Continue?"):
            return
        try:
            safety = db.restore_db(zp)
        except Exception as exc:
            messagebox.showerror("Restore failed", str(exc))
            return
        self.dairy_lbl.configure(text=db.get_setting("dairy_name"))
        self.say(f"Restored. Safety copy: {safety}")
        self.show("dashboard")

    def save_settings(self):
        db.set_setting("dairy_name", self.dname.get().strip() or "Dairy")
        self.dairy_lbl.configure(text=db.get_setting("dairy_name"))
        self.say("Settings saved.")


def main():
    db.init_db()
    App().mainloop()


if __name__ == "__main__":
    main()
