"""Export a roster to CSV or Excel.

This file is commented line by line. CSV is a plain text table any spreadsheet
can open; Excel export (via the optional ``openpyxl`` package) adds colours,
frozen headers and a legend.
"""

from __future__ import annotations

# The standard-library CSV writer.
import csv

# Codes, descriptions and weekday names used to build the table.
from .model import ALL_CODES, CODE_DESCRIPTIONS, WEEKDAY_NAMES, Roster
# Issue is only imported for the type hint on to_excel.
from .validator import Issue

# Cell background colours (hex, no '#') shared by the GUI grid and Excel export.
CODE_COLORS = {
    "M": "FEF3C7",
    "E": "DBEAFE",
    "N": "312E81",
    "CO": "D1FAE5",
    "L": "FEE2E2",
    "LL": "FCA5A5",
    "WO": "F3F4F6",
    "H": "EDE9FE",
}
# Matching text colours so each code stays readable on its background.
CODE_TEXT_COLORS = {
    "M": "92400E",
    "E": "1E40AF",
    "N": "FFFFFF",
    "CO": "065F46",
    "L": "991B1B",
    "LL": "7F1D1D",
    "WO": "9CA3AF",
    "H": "5B21B6",
}
# Header shading per day type.
DAYTYPE_COLORS = {"Working": "FFFFFF", "Freeze": "FFEDD5", "Weekend": "F3F4F6", "Holiday": "EDE9FE"}

# The summary columns appended to the right of the grid.
SUMMARY_KEYS = ("M", "E", "N", "CO", "L", "LL", "Primary", "Secondary")


def table_rows(roster: Roster) -> list[list[str]]:
    """The roster as a plain table: header rows, one row per engineer, then
    the on-call rows."""
    cfg = roster.config
    days = roster.days
    # Row 1: column headers - the fixed columns, each day number, then summaries.
    header = ["Engineer", "Designation", "SME"] + [d.strftime("%d") for d in days] + list(SUMMARY_KEYS)
    # Row 2: the weekday under each day number.
    weekday = ["", "", ""] + [WEEKDAY_NAMES[d.weekday()] for d in days] + [""] * len(SUMMARY_KEYS)
    # Row 3: the day type (Working/Weekend/Holiday/Freeze).
    daytype = ["", "", "Day type"] + [cfg.day_type(d) for d in days] + [""] * len(SUMMARY_KEYS)
    # The first three rows are the header block.
    rows = [header, weekday, daytype]
    # One row per engineer: their details, their codes, then their tallies.
    for e in cfg.engineers:
        counts = roster.counts(e.name)
        rows.append(
            [e.name, e.designation, "Yes" if e.is_sme else "No"]
            + [roster.code(e.name, d) for d in days]
            + [str(counts[k]) for k in SUMMARY_KEYS]
        )
    # Two on-call rows at the bottom.
    rows.append(["Primary on-call", "", ""] + [roster.primary.get(d, "") for d in days] + [""] * len(SUMMARY_KEYS))
    rows.append(["Secondary on-call", "", ""] + [roster.secondary.get(d, "") for d in days] + [""] * len(SUMMARY_KEYS))
    return rows


def to_csv(roster: Roster, path: str) -> None:
    # Write the plain table plus a small legend to a CSV file.
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerows(table_rows(roster))   # the whole grid
        writer.writerow([])                    # a blank separator row
        writer.writerow(["Legend"])            # legend heading
        for code in ALL_CODES:
            writer.writerow([code, CODE_DESCRIPTIONS[code]])   # code + meaning


def to_excel(roster: Roster, path: str, issues: list[Issue] | None = None) -> None:
    # openpyxl is optional; import it here so CSV export still works without it.
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
        from openpyxl.utils import get_column_letter
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise RuntimeError("Excel export needs the 'openpyxl' package (pip install openpyxl)") from exc

    cfg = roster.config
    # Create the workbook and its first sheet.
    wb = Workbook()
    ws = wb.active
    ws.title = f"Roster {cfg.year}-{cfg.month:02d}"
    # A thin grey border applied to every cell.
    thin = Side(style="thin", color="BBBBBB")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    # Centre alignment for the day/summary cells.
    center = Alignment(horizontal="center", vertical="center")

    def fill(hex_color):
        # A solid background fill of the given colour.
        return PatternFill("solid", start_color=hex_color, end_color=hex_color)

    # The same table used for CSV.
    rows = table_rows(roster)
    first_day_col = 4          # columns 1-3 are Engineer/Designation/SME
    n_days = len(roster.days)
    # Write and style every cell (openpyxl rows/cols are 1-based).
    for r, row in enumerate(rows, 1):
        for c, value in enumerate(row, 1):
            # Summary numbers become real numbers; everything else stays text.
            cell = ws.cell(row=r, column=c, value=int(value) if value.isdigit() and r > 3 else value)
            cell.border = border
            if c >= first_day_col:
                cell.alignment = center       # centre the day/summary columns
            if r <= 3:
                cell.font = Font(bold=True)    # bold the three header rows
            # Which day (if any) this column corresponds to.
            day_idx = c - first_day_col
            if 0 <= day_idx < n_days:
                d = roster.days[day_idx]
                if r <= 3:
                    # Header cells get their day-type colour.
                    cell.fill = fill(DAYTYPE_COLORS[cfg.day_type(d)])
                elif value in CODE_COLORS:
                    # Body cells get their code colour and matching text colour.
                    cell.fill = fill(CODE_COLORS[value])
                    cell.font = Font(color=CODE_TEXT_COLORS.get(value, "000000"), bold=value == "N")
    # Keep the header rows and name columns visible while scrolling.
    ws.freeze_panes = ws.cell(row=4, column=first_day_col)
    # Fixed widths for the first three columns.
    ws.column_dimensions["A"].width = 20
    ws.column_dimensions["B"].width = 16
    ws.column_dimensions["C"].width = 9
    # On-call rows hold names, so size each day column to fit them.
    for i, d in enumerate(roster.days):
        width = max(5, len(roster.primary.get(d, "")) + 1, len(roster.secondary.get(d, "")) + 1)
        ws.column_dimensions[get_column_letter(first_day_col + i)].width = width

    # Write the legend a couple of rows below the table.
    legend_row = len(rows) + 2
    ws.cell(row=legend_row, column=1, value="Legend").font = Font(bold=True)
    for i, code in enumerate(ALL_CODES, 1):
        c = ws.cell(row=legend_row + i, column=1, value=code)
        c.fill = fill(CODE_COLORS[code])
        c.font = Font(color=CODE_TEXT_COLORS.get(code, "000000"))
        ws.cell(row=legend_row + i, column=2, value=CODE_DESCRIPTIONS[code])

    # If issues were supplied, add a second "Issues" sheet listing them.
    if issues is not None:
        ws2 = wb.create_sheet("Issues")
        ws2.append(["Severity", "Date", "Message"])
        for i in issues:
            ws2.append([i.severity, i.day.isoformat() if i.day else "", i.message])
        if not issues:
            ws2.append(["OK", "", "All mandatory rules are satisfied"])
        ws2.column_dimensions["C"].width = 90

    # Save the finished workbook.
    wb.save(path)
