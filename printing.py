"""DairyManager — PDF reports via reportlab.

All generators save to dairy_data/reports/ and return the file path:
    payment_sheet_pdf(...)   period-wise farmer payment sheet (A4)
    farmer_statement_pdf(...) single farmer's collections + payments (A4)
    daily_report_pdf(...)     one day's collection summary (A4 or 80mm)
"""

import os
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                Paragraph, Spacer)
from reportlab.lib.styles import getSampleStyleSheet

from db import APP_DIR, get_setting

REPORTS_DIR = os.path.join(APP_DIR, "reports")
THERMAL_WIDTH = 80 * mm

TABLE_STYLE = TableStyle([
    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f6feb")),
    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ("FONTSIZE", (0, 0), (-1, -1), 9),
    ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
    ("ALIGN", (0, 0), (0, -1), "LEFT"),
    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
    ("ROWBACKGROUNDS", (0, 1), (-1, -1),
     [colors.white, colors.HexColor("#f2f6ff")]),
    ("TOPPADDING", (0, 0), (-1, -1), 4),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
])


def _doc(path, pagesize=A4, margins=15 * mm):
    os.makedirs(REPORTS_DIR, exist_ok=True)
    return SimpleDocTemplate(
        path, pagesize=pagesize,
        leftMargin=margins, rightMargin=margins,
        topMargin=margins, bottomMargin=margins,
    )


def _header(story, styles, title, subtitle):
    dairy = get_setting("dairy_name", "Dairy")
    story.append(Paragraph(f"<b>{dairy}</b>", styles["Title"]))
    story.append(Paragraph(title, styles["Heading2"]))
    story.append(Paragraph(subtitle, styles["Normal"]))
    story.append(Spacer(1, 10))


def _stamp():
    return "Generated " + datetime.now().strftime("%d %b %Y, %I:%M %p")


def _table(data):
    t = Table(data, repeatRows=1)
    t.setStyle(TABLE_STYLE)
    return t


def payment_sheet_pdf(start, end, rows, total):
    """Printable per-period payment sheet for all farmers (A4)."""
    path = os.path.join(
        REPORTS_DIR, f"payment_sheet_{start}_to_{end}.pdf")
    doc = _doc(path)
    styles = getSampleStyleSheet()
    story = []
    _header(story, styles, "Farmer Payment Sheet",
            f"Period: {start} to {end} &nbsp;|&nbsp; {_stamp()}")
    data = [["Farmer", "Village", "Opening (Rs)", "Litres",
             "Gross (Rs)", "Paid (Rs)", "Pending (Rs)"]]
    for r in rows:
        data.append([r["name"], r["village"],
                     f"{r['opening']:.2f}", f"{r['liters']:.2f}",
                     f"{r['gross']:.2f}", f"{r['paid']:.2f}",
                     f"{r['pending']:.2f}"])
    data.append(["TOTAL", f"{total['farmers']} farmers",
                 f"{total['opening']:.2f}", f"{total['liters']:.2f}",
                 f"{total['gross']:.2f}", f"{total['paid']:.2f}",
                 f"{total['pending']:.2f}"])
    story.append(_table(data))
    story.append(Spacer(1, 24))
    story.append(Paragraph("Signature: ____________________", styles["Normal"]))
    doc.build(story)
    return path


def farmer_statement_pdf(farmer, start, end, collections, payments,
                         opening, totals):
    """One farmer's milk statement for a period (A4)."""
    fname = "".join(c if c.isalnum() else "_" for c in farmer["name"])[:30]
    path = os.path.join(
        REPORTS_DIR, f"statement_{fname}_{start}_to_{end}.pdf")
    doc = _doc(path)
    styles = getSampleStyleSheet()
    story = []
    contact = " ".join(x for x in
                       [farmer.get("village", ""), farmer.get("phone", "")]
                       if x)
    _header(story, styles, f"Milk Statement — {farmer['name']}",
            f"{contact}<br/>Period: {start} to {end}"
            f" &nbsp;|&nbsp; {_stamp()}")
    cdata = [["Date", "Shift", "Litres", "Fat", "SNF", "Rate (Rs/L)",
              "Amount (Rs)"]]
    for c in collections:
        cdata.append([c["date"], c["shift"], f"{c['liters']:.2f}",
                      f"{c['fat']:.1f}", f"{c['snf']:.1f}",
                      f"{c['rate']:.2f}", f"{c['amount']:.2f}"])
    cdata.append(["", "", "", "", "", "Period gross:",
                  f"{totals['gross']:.2f}"])
    story.append(_table(cdata))
    story.append(Spacer(1, 14))
    pdata = [["Payment date", "Mode", "Note", "Amount (Rs)"]]
    for p in payments:
        pdata.append([p["date"], p["mode"], p["note"] or "-",
                      f"{p['amount']:.2f}"])
    pdata.append(["", "", "Period paid:", f"{totals['paid']:.2f}"])
    story.append(_table(pdata))
    story.append(Spacer(1, 14))
    story.append(Paragraph(
        f"Opening pending: <b>Rs {opening:.2f}</b><br/>"
        f"Closing pending: <b>Rs {totals['pending']:.2f}</b>",
        styles["Normal"]))
    doc.build(story)
    return path


def daily_report_pdf(day, collections, summary, paper="A4"):
    """One day's collection summary, A4 or 80mm thermal."""
    wide = paper != "80mm"
    if wide:
        path = os.path.join(REPORTS_DIR, f"daily_collection_{day}.pdf")
        doc = _doc(path)
    else:
        path = os.path.join(REPORTS_DIR, f"daily_collection_{day}_80mm.pdf")
        doc = _doc(path, pagesize=(THERMAL_WIDTH, 297 * mm),
                   margins=5 * mm)
    styles = getSampleStyleSheet()
    story = []
    _header(story, styles, "Daily Collection Report",
            f"Date: {day} &nbsp;|&nbsp; {_stamp()}")
    story.append(Paragraph(
        f"Total milk: <b>{summary['liters']:.2f} L</b> &nbsp;|&nbsp; "
        f"Morning: {summary['morning']:.2f} L &nbsp;|&nbsp; "
        f"Evening: {summary['evening']:.2f} L<br/>"
        f"Farmers: <b>{summary['farmers']}</b> &nbsp;|&nbsp; "
        f"Value: <b>Rs {summary['value']:.2f}</b>", styles["Normal"]))
    story.append(Spacer(1, 10))
    if wide:
        data = [["Farmer", "Village", "Shift", "Litres", "Fat", "SNF",
                 "Rate", "Amount (Rs)"]]
        for c in collections:
            data.append([c["farmer_name"], c["village"], c["shift"],
                         f"{c['liters']:.2f}", f"{c['fat']:.1f}",
                         f"{c['snf']:.1f}", f"{c['rate']:.2f}",
                         f"{c['amount']:.2f}"])
    else:
        small = getSampleStyleSheet()["Normal"]
        small.fontSize = 8
        data = [["Farmer", "Shift", "L", "Fat", "Rs"]]
        for c in collections:
            data.append([c["farmer_name"][:14], c["shift"][:3],
                         f"{c['liters']:.1f}", f"{c['fat']:.1f}",
                         f"{c['amount']:.0f}"])
    story.append(_table(data))
    doc.build(story)
    return path
