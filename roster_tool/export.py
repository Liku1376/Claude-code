"""Export a roster to CSV or Excel."""

from __future__ import annotations

import csv

from .model import ALL_CODES, CODE_DESCRIPTIONS, WEEKDAY_NAMES, Roster
from .validator import Issue

# Cell colours (background hex) shared by the GUI and the Excel export.
CODE_COLORS = {
    "M": "FFF4B3",
    "E": "B8DDF7",
    "N": "4A4E8C",
    "CO": "C9E7C1",
    "L": "F7B7B7",
    "LL": "E58A8A",
    "WO": "E2E2E2",
    "H": "D9C8F0",
}
CODE_TEXT_COLORS = {"N": "FFFFFF"}
DAYTYPE_COLORS = {"Working": "FFFFFF", "Freeze": "FFE0B2", "Weekend": "E2E2E2", "Holiday": "D9C8F0"}

SUMMARY_KEYS = ("M", "E", "N", "CO", "L", "LL", "Primary", "Secondary")


def table_rows(roster: Roster) -> list[list[str]]:
    """The roster as a plain table: header rows, one row per engineer, then
    the on-call rows."""
    cfg = roster.config
    days = roster.days
    header = ["Engineer", "Designation", "SME"] + [d.strftime("%d") for d in days] + list(SUMMARY_KEYS)
    weekday = ["", "", ""] + [WEEKDAY_NAMES[d.weekday()] for d in days] + [""] * len(SUMMARY_KEYS)
    daytype = ["", "", "Day type"] + [cfg.day_type(d) for d in days] + [""] * len(SUMMARY_KEYS)
    rows = [header, weekday, daytype]
    for e in cfg.engineers:
        counts = roster.counts(e.name)
        rows.append(
            [e.name, e.designation, "Yes" if e.is_sme else "No"]
            + [roster.code(e.name, d) for d in days]
            + [str(counts[k]) for k in SUMMARY_KEYS]
        )
    rows.append(["Primary on-call", "", ""] + [roster.primary.get(d, "") for d in days] + [""] * len(SUMMARY_KEYS))
    rows.append(["Secondary on-call", "", ""] + [roster.secondary.get(d, "") for d in days] + [""] * len(SUMMARY_KEYS))
    return rows


def to_csv(roster: Roster, path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerows(table_rows(roster))
        writer.writerow([])
        writer.writerow(["Legend"])
        for code in ALL_CODES:
            writer.writerow([code, CODE_DESCRIPTIONS[code]])


def to_excel(roster: Roster, path: str, issues: list[Issue] | None = None) -> None:
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
        from openpyxl.utils import get_column_letter
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise RuntimeError("Excel export needs the 'openpyxl' package (pip install openpyxl)") from exc

    cfg = roster.config
    wb = Workbook()
    ws = wb.active
    ws.title = f"Roster {cfg.year}-{cfg.month:02d}"
    thin = Side(style="thin", color="BBBBBB")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    center = Alignment(horizontal="center", vertical="center")

    def fill(hex_color):
        return PatternFill("solid", start_color=hex_color, end_color=hex_color)

    rows = table_rows(roster)
    first_day_col = 4
    n_days = len(roster.days)
    for r, row in enumerate(rows, 1):
        for c, value in enumerate(row, 1):
            cell = ws.cell(row=r, column=c, value=int(value) if value.isdigit() and r > 3 else value)
            cell.border = border
            if c >= first_day_col:
                cell.alignment = center
            if r <= 3:
                cell.font = Font(bold=True)
            day_idx = c - first_day_col
            if 0 <= day_idx < n_days:
                d = roster.days[day_idx]
                if r <= 3:
                    cell.fill = fill(DAYTYPE_COLORS[cfg.day_type(d)])
                elif value in CODE_COLORS:
                    cell.fill = fill(CODE_COLORS[value])
                    cell.font = Font(color=CODE_TEXT_COLORS.get(value, "000000"), bold=value == "N")
    ws.freeze_panes = ws.cell(row=4, column=first_day_col)
    ws.column_dimensions["A"].width = 20
    ws.column_dimensions["B"].width = 16
    ws.column_dimensions["C"].width = 9
    # On-call rows hold names, so size each day column to fit them.
    for i, d in enumerate(roster.days):
        width = max(5, len(roster.primary.get(d, "")) + 1, len(roster.secondary.get(d, "")) + 1)
        ws.column_dimensions[get_column_letter(first_day_col + i)].width = width

    legend_row = len(rows) + 2
    ws.cell(row=legend_row, column=1, value="Legend").font = Font(bold=True)
    for i, code in enumerate(ALL_CODES, 1):
        c = ws.cell(row=legend_row + i, column=1, value=code)
        c.fill = fill(CODE_COLORS[code])
        c.font = Font(color=CODE_TEXT_COLORS.get(code, "000000"))
        ws.cell(row=legend_row + i, column=2, value=CODE_DESCRIPTIONS[code])

    if issues is not None:
        ws2 = wb.create_sheet("Issues")
        ws2.append(["Severity", "Date", "Message"])
        for i in issues:
            ws2.append([i.severity, i.day.isoformat() if i.day else "", i.message])
        if not issues:
            ws2.append(["OK", "", "All mandatory rules are satisfied"])
        ws2.column_dimensions["C"].width = 90

    wb.save(path)
