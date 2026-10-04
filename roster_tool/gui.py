"""Tkinter GUI for the roster tool.

This file is heavily commented to explain what each part of the desktop
interface does. Tkinter is Python's built-in windowing toolkit; ``ttk`` is its
themed-widget set. The window is organised as a left sidebar of numbered
"steps" (pages) plus a main area that shows one page at a time. The last page
shows the generated roster grid.
"""

from __future__ import annotations

# ``calendar`` for month names; ``json`` to read/write inputs; ``os`` for paths;
# ``statistics`` for the averages on the summary tiles; ``sys`` to find bundled
# files; ``tkinter`` (as tk) is the GUI toolkit.
import calendar
import json
import os
import statistics
import sys
import tkinter as tk
from datetime import date, datetime
# filedialog = open/save dialogs; messagebox = pop-up alerts; ttk = themed widgets.
from tkinter import filedialog, messagebox, ttk

# Reuse the engine, exports, storage, theme, date picker and rules.
from . import export, ics, storage
from . import theme as T
from .datepicker import DateEntry
from .model import (
    ALL_CODES,
    CODE_DESCRIPTIONS,
    DAY_TYPES,
    SHIFT_NAMES,
    SHIFTS,
    WEEKDAY_NAMES,
    Roster,
    RosterConfig,
    Locks,
    empty_config_dict,
    parse_date,
    parse_time,
)
from .scheduler import generate
from .validator import ERROR, INFO, WARNING, count, precheck, preference_stats, validate

# Bundled files live next to the package when run from source, or in the
# PyInstaller extraction folder (sys._MEIPASS) when run as a packaged app.
BASE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# The sample inputs and the app icon.
SAMPLE_CONFIG = os.path.join(BASE_DIR, "examples", "sample_config.json")
ICON_PNG = os.path.join(BASE_DIR, "assets", "icon.png")
# Hint text shown under every date field.
DATE_HINT = "Use the calendar button or type a date (e.g. 2026-10-14 or 14)."
# Short code -> word, used for the roster legend.
LEGEND_NAMES = {"M": "Morning", "E": "Evening", "N": "Night", "CO": "Comp off", "L": "Leave", "LL": "Long leave", "WO": "Weekend", "H": "Holiday"}
# The colour used to outline cells that changed since publishing.
CHANGED_COLOR = "#F59E0B"
# Row labels for the two on-call rows.
ONCALL_LABELS = {"primary": "Primary on-call", "secondary": "Secondary on-call"}
# Designation suggestions in the Team form.
DESIGNATIONS = ("Engineer", "Senior Engineer", "Lead Engineer", "SME", "Manager")


def card(parent, title=None, subtitle=None, padding=16):
    """A white, bordered panel. Returns (outer, body)."""
    # The bordered outer frame.
    outer = ttk.Frame(parent, style="Card.TFrame", padding=padding)
    # An optional bold title and a muted subtitle.
    if title:
        ttk.Label(outer, text=title, style="CardTitle.TLabel").pack(anchor="w")
    if subtitle:
        ttk.Label(outer, text=subtitle, style="Hint.TLabel", justify="left").pack(anchor="w", pady=(2, 0))
    # The inner content area callers fill in.
    body = ttk.Frame(outer, style="Surface.TFrame")
    body.pack(fill="both", expand=True, pady=(12 if title or subtitle else 0, 0))
    return outer, body


def page(parent, title, subtitle):
    # A page: a padded frame with a big title and a muted subtitle.
    frame = ttk.Frame(parent, padding=(24, 20, 24, 16))
    ttk.Label(frame, text=title, style="PageTitle.TLabel").pack(anchor="w")
    ttk.Label(frame, text=subtitle, style="PageSub.TLabel").pack(anchor="w", pady=(2, 16))
    return frame


class RecordEditor(ttk.Frame):
    """A form card + table card for editing a list of records.

    ``fields`` is a list of (key, label, kind, extra) where kind is one of
    "entry", "date" (entry + calendar picker), "combo" (editable), "choice"
    (read-only combo) or "check". For combos, ``extra`` is a list of values
    or a callable returning one.
    """

    # Set by the app: supplies the roster month, weekends and holidays so the
    # calendar popups open on the right month and highlight days off.
    date_context = None

    def __init__(self, master, title, fields, on_change=None, hint="", noun="entry", columns=2):
        super().__init__(master)
        # Remember the field spec, change callback and singular noun for messages.
        self.fields = fields
        self.on_change = on_change
        self.noun = noun
        # The rows of data, and the input widgets/variables by field key.
        self.rows: list[dict] = []
        self.vars: dict[str, tk.Variable] = {}
        self.widgets: dict[str, ttk.Widget] = {}

        # Build the form card and lay the fields out in a grid.
        form_card, form = card(self, title, hint)
        form_card.pack(fill="x")
        for i, (key, label, kind, extra) in enumerate(fields):
            # Each field sits in its own little cell within the grid.
            cell = ttk.Frame(form, style="Surface.TFrame")
            cell.grid(row=i // columns, column=i % columns, sticky="ew", padx=(0, 20), pady=4)
            if kind == "check":
                # A checkbox field (its label is on the checkbox itself).
                var = tk.BooleanVar(value=False)
                w = ttk.Checkbutton(cell, text=label, variable=var)
                ttk.Label(cell, text=" ", style="Card.TLabel").pack(anchor="w")  # spacer to align rows
                w.pack(anchor="w", pady=(2, 0))
            else:
                # A labelled text/date/combo field.
                ttk.Label(cell, text=label, style="Card.TLabel", foreground=T.MUTED, font=T.Fonts.get(9, "bold")).pack(anchor="w")
                var = tk.StringVar()
                if kind in ("combo", "choice"):
                    # A dropdown; "choice" is read-only, "combo" is editable.
                    w = ttk.Combobox(cell, textvariable=var, state="readonly" if kind == "choice" else "normal", width=20)
                elif kind == "date":
                    # A date field with a calendar popup (see datepicker.py).
                    ctx = self.date_context
                    w = DateEntry(
                        cell, var,
                        default_date=lambda key=key: self._default_date(key),
                        is_weekend=ctx.is_weekend if ctx else None,
                        holiday_name=ctx.holiday_name if ctx else None,
                    )
                else:
                    # A plain text entry.
                    w = ttk.Entry(cell, textvariable=var, width=22)
                w.pack(anchor="w", fill="x", pady=(3, 0))
            # Store the variable and widget for this field.
            self.vars[key] = var
            self.widgets[key] = w
        # Let all columns share width evenly.
        for c in range(columns):
            form.columnconfigure(c, weight=1)

        # The Add / Update / Delete / Clear buttons under the form.
        btns = ttk.Frame(form, style="Surface.TFrame")
        btns.grid(row=(len(fields) + columns - 1) // columns, column=0, columnspan=columns, sticky="w", pady=(12, 0))
        ttk.Button(btns, text="＋  Add", style="Accent.TButton", command=self.add).pack(side="left")
        ttk.Button(btns, text="Update", command=self.update_selected).pack(side="left", padx=(8, 0))
        ttk.Button(btns, text="Delete", style="Danger.TButton", command=self.delete_selected).pack(side="left", padx=(8, 0))
        ttk.Button(btns, text="Clear", command=self.clear_form).pack(side="left", padx=(8, 0))

        # The table card below the form.
        table_card = ttk.Frame(self, style="Card.TFrame", padding=1)
        table_card.pack(fill="both", expand=True, pady=(14, 0))
        # A header row above the table showing the count.
        head = ttk.Frame(table_card, style="Surface.TFrame", padding=(14, 10))
        head.pack(fill="x")
        self.count_var = tk.StringVar()
        ttk.Label(head, textvariable=self.count_var, style="Card.TLabel", font=T.Fonts.get(10, "bold")).pack(side="left")
        ttk.Label(head, text="Select a row to edit it", style="Hint.TLabel").pack(side="right")

        # The table itself (a Treeview with one column per field).
        table = ttk.Frame(table_card, style="Surface.TFrame")
        table.pack(fill="both", expand=True)
        cols = [f[0] for f in fields]
        self.tree = ttk.Treeview(table, columns=cols, show="headings", selectmode="extended", height=8)
        for key, label, _kind, _extra in fields:
            self.tree.heading(key, text=label.upper(), anchor="w")
            self.tree.column(key, width=150, anchor="w")
        # A tag used to zebra-stripe alternate rows.
        self.tree.tag_configure("odd", background=T.STRIPE)
        # A vertical scrollbar wired to the table.
        sb = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        # Clicking a row loads it back into the form.
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        # An "empty" message shown when there are no rows.
        self.empty = tk.Label(table, text=f"No {noun}s yet - fill in the form above and press Add.", bg=T.SURFACE, fg=T.MUTED, font=T.Fonts.get(10))
        # Populate dropdown options and draw the (empty) table.
        self.refresh_options()
        self._redraw()

    # -- form helpers --------------------------------------------------------
    def _default_date(self, key):
        """Month a calendar opens on: an end date follows the start date,
        otherwise the roster month."""
        ctx = self.date_context
        # Default to the roster month (or today if no context).
        fallback = ctx.roster_month_start() if ctx else date.today()
        # For an "end" field, open on the same month as the "start" value.
        if key == "end" and "start" in self.vars:
            try:
                return parse_date(self.vars["start"].get(), fallback.year, fallback.month)
            except ValueError:
                pass
        return fallback

    def refresh_options(self):
        # Refresh the values of any dropdowns whose options come from a function
        # (e.g. the engineer list, which changes as the team changes).
        for key, _label, kind, extra in self.fields:
            if kind in ("combo", "choice") and extra is not None:
                self.widgets[key]["values"] = list(extra() if callable(extra) else extra)

    def _form_values(self) -> dict | None:
        # Read the current form into a row dict.
        row = {}
        for key, _label, kind, _extra in self.fields:
            value = self.vars[key].get()
            row[key] = value if kind == "check" else str(value).strip()
        # The first field is required; warn and return None if it is blank.
        first_key, first_label = self.fields[0][0], self.fields[0][1]
        if not row[first_key]:
            messagebox.showwarning("Missing value", f"'{first_label}' is required", parent=self)
            return None
        return row

    def clear_form(self):
        # Reset every field to blank/unchecked and clear the table selection.
        for key, _label, kind, _extra in self.fields:
            self.vars[key].set(False if kind == "check" else "")
        self.tree.selection_remove(*self.tree.selection())

    def _display(self, row):
        # Turn a row dict into the list of cell strings shown in the table.
        out = []
        for key, _label, kind, _extra in self.fields:
            v = row.get(key, "")
            out.append(("✓ Yes" if v else "—") if kind == "check" else v)
        return out

    def _redraw(self):
        # Clear and rebuild the table from self.rows.
        self.tree.delete(*self.tree.get_children())
        for i, row in enumerate(self.rows):
            # Odd rows get the "odd" stripe tag.
            self.tree.insert("", "end", iid=str(i), values=self._display(row), tags=("odd",) if i % 2 else ())
        # Update the count label ("3 engineers").
        n = len(self.rows)
        self.count_var.set(f"{n} {self.noun}{'' if n == 1 else 's'}")
        # Show or hide the empty-state message.
        if n:
            self.empty.place_forget()
        else:
            self.empty.place(relx=0.5, rely=0.55, anchor="center")

    def _changed(self):
        # Redraw the table and notify the app that inputs changed.
        self._redraw()
        if self.on_change:
            self.on_change()

    # -- actions -------------------------------------------------------------
    def add(self):
        # Add the form's values as a new row.
        row = self._form_values()
        if row is not None:
            self.rows.append(row)
            self._changed()
            self.clear_form()

    def update_selected(self):
        # Overwrite the one selected row with the form's values.
        sel = self.tree.selection()
        if len(sel) != 1:
            messagebox.showinfo("Update", "Select exactly one row to update", parent=self)
            return
        row = self._form_values()
        if row is not None:
            self.rows[int(sel[0])] = row
            self._changed()

    def delete_selected(self):
        # Delete every selected row (highest index first so positions stay valid).
        idx = sorted((int(i) for i in self.tree.selection()), reverse=True)
        for i in idx:
            del self.rows[i]
        if idx:
            self._changed()

    def _on_select(self, _event=None):
        # When exactly one row is selected, copy it into the form for editing.
        sel = self.tree.selection()
        if len(sel) == 1:
            row = self.rows[int(sel[0])]
            for key, _label, kind, _extra in self.fields:
                self.vars[key].set(bool(row.get(key)) if kind == "check" else row.get(key, ""))

    def get_rows(self) -> list[dict]:
        # A copy of the rows (so callers cannot mutate our list).
        return [dict(r) for r in self.rows]

    def set_rows(self, rows):
        # Replace all rows (used when loading a file), normalising each value.
        self.rows = []
        for r in rows or []:
            row = {}
            for key, _label, kind, _extra in self.fields:
                v = r.get(key, False if kind == "check" else "")
                row[key] = bool(v) if kind == "check" else str(v)
            self.rows.append(row)
        self._redraw()


class RosterGrid(ttk.Frame):
    """Scrollable, colour-coded roster grid drawn on a canvas.

    Click an engineer cell to change its code, or an on-call cell to change
    the on-call engineer; the roster is re-validated after every edit.
    """

    # Sizes (in pixels) of the grid layout.
    NAME_W = 190   # width of the left name column
    CELL_W = 44    # width of a day cell
    CELL_H = 30    # height of a row
    HEAD_H = 48    # height of the header
    GAP = 2        # gap around each coloured pill
    # The summary columns on the right, and short labels for the on-call ones.
    SUMMARY = ("M", "E", "N", "CO", "L", "LL", "Primary", "Secondary")
    SUMMARY_LABELS = {"Primary": "PRI", "Secondary": "SEC"}
    SUMMARY_W = 42

    def __init__(self, master, on_edit, on_hover):
        super().__init__(master, style="Surface.TFrame")
        # Callbacks: on_edit(action, target, day, value); on_hover(text).
        self.on_edit = on_edit
        self.on_hover = on_hover
        # State the grid draws from.
        self.roster: Roster | None = None
        self.error_days: set[date] = set()
        self.changes: dict = {}
        # A canvas we draw the whole grid onto, with two scrollbars.
        self.canvas = tk.Canvas(self, background=T.SURFACE, highlightthickness=0)
        xs = ttk.Scrollbar(self, orient="horizontal", command=self.canvas.xview)
        ys = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=xs.set, yscrollcommand=ys.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        ys.grid(row=0, column=1, sticky="ns")
        xs.grid(row=1, column=0, sticky="ew")
        # Let the canvas expand to fill the frame.
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        # Mouse handlers: click to edit, motion to hover-highlight, leave to clear.
        self.canvas.bind("<Button-1>", self._click)
        self.canvas.bind("<Motion>", self._motion)
        self.canvas.bind("<Leave>", lambda _e: (self.canvas.delete("hover"), self.on_hover("")))
        # Show the empty placeholder until a roster is set.
        self._empty_state()

    def _empty_state(self):
        # Draw the "no roster yet" placeholder text.
        c = self.canvas
        c.create_text(32, 40, anchor="nw", text="No roster yet", font=T.Fonts.get(14, "bold"), fill=T.TEXT)
        c.create_text(
            32, 70, anchor="nw", fill=T.MUTED, font=T.Fonts.get(10),
            text="Fill in the team and requests using the steps on the left,\nthen press  “Generate roster”.",
        )

    def show(self, roster: Roster, error_days: set[date], changes: dict | None = None):
        # Update the grid's state and redraw.
        self.roster = roster
        self.error_days = error_days
        # (engineer name or on-call row label, day) -> previous value
        self.changes = changes or {}
        self.draw()

    def _lock_icon(self, x, y):
        """Tiny padlock at (x, y) = top-left corner."""
        c = self.canvas
        # A small arc (the shackle) over a filled rectangle (the body).
        c.create_arc(x + 1.5, y, x + 7.5, y + 7, start=0, extent=180, style="arc", outline=T.TEXT, width=1.5)
        c.create_rectangle(x, y + 3.5, x + 9, y + 10, fill=T.TEXT, outline="")

    def _changed_mark(self, x, y):
        # An orange outline around a changed cell.
        self.canvas.create_rectangle(x + 1, y + 1, x + self.CELL_W - 1, y + self.CELL_H - 1, outline=CHANGED_COLOR, width=2)

    def _rows(self):
        # The rows to draw: one per engineer, then the two on-call rows.
        cfg = self.roster.config
        return [("eng", e.name) for e in cfg.engineers] + [("primary", None), ("secondary", None)]

    def _row_y(self, ri):
        # The y pixel of row index ``ri``. A small gap separates engineers from
        # the on-call rows.
        n_eng = len(self.roster.config.engineers)
        return self.HEAD_H + ri * self.CELL_H + (10 if ri >= n_eng else 0)

    def _cell_at(self, event):
        # Work out which (row, column) a mouse event landed on, or None.
        if not self.roster:
            return None
        # Convert screen coords to canvas coords (accounts for scrolling).
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)
        # Ignore the name column and the header.
        if x < self.NAME_W or y < self.HEAD_H:
            return None
        # Which day column.
        col = int((x - self.NAME_W) // self.CELL_W)
        rows = self._rows()
        days = self.roster.days
        # Find the row whose vertical band contains y.
        for ri in range(len(rows)):
            y0 = self._row_y(ri)
            if y0 <= y < y0 + self.CELL_H and 0 <= col < len(days):
                return ri, col
        return None

    def _pill(self, x0, y0, x1, y1, fill, r=6):
        """Rounded rectangle."""
        c = self.canvas
        # A smoothed polygon approximates a rounded rectangle for the cell fill.
        pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1, x1 - r, y1, x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
        return c.create_polygon(pts, smooth=True, fill=fill, outline="")

    def draw(self):
        # Redraw the entire grid from scratch.
        c = self.canvas
        c.delete("all")
        r = self.roster
        cfg = r.config
        days = r.days
        rows = self._rows()
        # Left edge of the day columns, the gap size, a font shorthand, counts.
        x0 = self.NAME_W
        g = self.GAP
        f = T.Fonts.get
        n_eng = len(cfg.engineers)
        # x of the summary block, and the y of the grid's bottom.
        sx = x0 + len(days) * self.CELL_W
        bottom = self._row_y(len(rows) - 1) + self.CELL_H

        # Column shading for weekends / holidays / freeze days.
        for i, d in enumerate(days):
            dtype = cfg.day_type(d)
            if dtype != "Working":
                x = x0 + i * self.CELL_W
                c.create_rectangle(x, 0, x + self.CELL_W, bottom, fill="#" + export.DAYTYPE_COLORS[dtype], outline="")

        # Header: the month/year on the left.
        c.create_text(12, self.HEAD_H / 2 - 7, anchor="w", text=calendar.month_name[cfg.month], font=f(13, "bold"), fill=T.TEXT)
        c.create_text(12, self.HEAD_H / 2 + 11, anchor="w", text=f"{cfg.year}  ·  {n_eng} engineers", font=f(9), fill=T.MUTED)
        # Header: each day's weekday and number, coloured by day type.
        for i, d in enumerate(days):
            x = x0 + i * self.CELL_W
            dtype = cfg.day_type(d)
            color = {"Holiday": "#6D28D9", "Freeze": "#C2410C"}.get(dtype, T.MUTED if dtype == "Weekend" else T.TEXT)
            c.create_text(x + self.CELL_W / 2, 15, text=WEEKDAY_NAMES[d.weekday()][:2].upper(), font=f(8, "bold"), fill=T.MUTED if dtype == "Working" else color)
            c.create_text(x + self.CELL_W / 2, 32, text=str(d.day), font=f(11, "bold"), fill=color)
            # A red dot under days that break a rule.
            if d in self.error_days:
                c.create_oval(x + self.CELL_W / 2 - 3, self.HEAD_H - 7, x + self.CELL_W / 2 + 3, self.HEAD_H - 1, fill=T.DANGER, outline="")
        # Header: the summary column labels.
        for j, key in enumerate(self.SUMMARY):
            x = sx + 8 + j * self.SUMMARY_W
            c.create_text(x + self.SUMMARY_W / 2, self.HEAD_H / 2, text=self.SUMMARY_LABELS.get(key, key), font=f(8, "bold"), fill=T.MUTED)
        # A line under the header.
        c.create_line(0, self.HEAD_H - 0.5, sx + 8 + len(self.SUMMARY) * self.SUMMARY_W, self.HEAD_H - 0.5, fill=T.BORDER)

        # Draw every row.
        for ri, (kind, name) in enumerate(rows):
            y = self._row_y(ri)
            cy = y + self.CELL_H / 2   # vertical centre of the row
            if kind == "eng":
                # Engineer name, an "SME" tag, and their designation.
                eng = cfg.engineer(name)
                tid = c.create_text(12, cy, anchor="w", text=name, font=f(10, "bold"), fill=T.TEXT)
                bx = c.bbox(tid)[2] + 8   # x just past the name
                if eng.is_sme:
                    self._pill(bx, cy - 8, bx + 34, cy + 8, T.PRIMARY_LIGHT, r=8)
                    c.create_text(bx + 17, cy, text="SME", font=f(7, "bold"), fill=T.PRIMARY)
                    bx += 40
                if eng.designation:
                    c.create_text(bx, cy, anchor="w", text=eng.designation[:18], font=f(8), fill=T.MUTED)
                # A faint separator under all but the last engineer.
                if ri < n_eng - 1:
                    c.create_line(0, y + self.CELL_H, x0, y + self.CELL_H, fill=T.GRID_LINE)
            else:
                # An on-call row label.
                label = "Primary on-call" if kind == "primary" else "Secondary on-call"
                c.create_text(12, cy, anchor="w", text=label, font=f(10, "bold"), fill=T.PRIMARY_DARK)

            # Draw each day cell in this row.
            for i, d in enumerate(days):
                x = x0 + i * self.CELL_W
                if kind == "eng":
                    # A coloured pill with the code letter.
                    code = r.code(name, d)
                    fill = "#" + export.CODE_COLORS.get(code, "FFFFFF")
                    fg = "#" + export.CODE_TEXT_COLORS.get(code, "111827")
                    self._pill(x + g, y + g, x + self.CELL_W - g, y + self.CELL_H - g, fill, r=5)
                    c.create_text(x + self.CELL_W / 2, cy, text=code, fill=fg, font=f(9, "bold"))
                    # Orange outline if the cell changed since publishing.
                    if (name, d) in self.changes:
                        self._changed_mark(x, y)
                    # A padlock if the cell is locked.
                    if (name, d) in r.locks.cells:
                        self._lock_icon(x + 4, y + 4)
                    # Small dots mark on-call duty (primary = indigo, secondary = teal).
                    if r.primary.get(d) == name:
                        c.create_oval(x + self.CELL_W - 10, y + 5, x + self.CELL_W - 5, y + 10, fill=T.PRIMARY, outline="white")
                    if r.secondary.get(d) == name:
                        c.create_oval(x + self.CELL_W - 10, y + self.CELL_H - 10, x + self.CELL_W - 5, y + self.CELL_H - 5, fill="#0D9488", outline="white")
                else:
                    # An on-call cell showing the assigned name (or a dot).
                    who = (r.primary if kind == "primary" else r.secondary).get(d, "")
                    if who:
                        self._pill(x + g, y + g, x + self.CELL_W - g, y + self.CELL_H - g, T.PRIMARY_LIGHT if kind == "primary" else "#CCFBF1", r=5)
                        c.create_text(x + self.CELL_W / 2, cy, text=who[:5], fill=T.PRIMARY_DARK if kind == "primary" else "#115E59", font=f(8, "bold"))
                    else:
                        c.create_text(x + self.CELL_W / 2, cy, text="·", fill="#D1D5DB", font=f(10))
                    # Changed / locked marks for on-call cells too.
                    if (ONCALL_LABELS[kind], d) in self.changes:
                        self._changed_mark(x, y)
                    if d in (r.locks.primary if kind == "primary" else r.locks.secondary):
                        self._lock_icon(x + 4, y + 4)
            # The summary counts for engineer rows.
            if kind == "eng":
                counts = r.counts(name)
                for j, key in enumerate(self.SUMMARY):
                    x = sx + 8 + j * self.SUMMARY_W
                    v = counts[key]
                    c.create_text(x + self.SUMMARY_W / 2, cy, text=str(v), font=f(9, "bold" if v else "normal"), fill=T.TEXT if v else "#D1D5DB")

        # Set the scrollable region and cap the visible height.
        total_w = sx + 8 + len(self.SUMMARY) * self.SUMMARY_W
        c.configure(scrollregion=(0, 0, total_w + 8, bottom + 12), height=min(bottom + 12, 560))

    def _motion(self, event):
        # On mouse move, highlight the hovered cell and show details below.
        c = self.canvas
        c.delete("hover")
        hit = self._cell_at(event)
        if not hit:
            self.on_hover("")
            return
        ri, col = hit
        kind, name = self._rows()[ri]
        d = self.roster.days[col]
        # Draw an accent outline around the hovered cell.
        x = self.NAME_W + col * self.CELL_W
        y = self._row_y(ri)
        c.create_rectangle(x + 1, y + 1, x + self.CELL_W - 1, y + self.CELL_H - 1, outline=T.PRIMARY, width=2, tags="hover")
        c.configure(cursor="hand2")

        # Build the status-bar description of this cell.
        r = self.roster
        cfg = r.config
        head = f"{d:%A %d %b} · {cfg.day_type(d)}{' (' + cfg.holiday_name(d) + ')' if cfg.holiday_name(d) else ''}"
        if kind == "eng":
            desc = f"{name}: {CODE_DESCRIPTIONS.get(r.code(name, d), r.code(name, d))}"
            key, locked = (name, d), (name, d) in r.locks.cells
        else:
            desc = f"{'Primary' if kind == 'primary' else 'Secondary'} on-call: {(r.primary if kind == 'primary' else r.secondary).get(d, '') or '(none)'}"
            key, locked = (ONCALL_LABELS[kind], d), d in (r.locks.primary if kind == "primary" else r.locks.secondary)
        # Note if the cell is locked or has changed since publishing.
        if locked:
            desc += "  (locked)"
        if key in self.changes:
            desc += f"  (was {self.changes[key] or 'empty'} when published)"
        # Also show who is on Morning and Night that day.
        m = ", ".join(r.on_shift(d, "M")) or "-"
        n = ", ".join(r.on_shift(d, "N")) or "-"
        self.on_hover(f"{head}   |   {desc}   |   Morning: {m}   |   Night: {n}")

    def _click(self, event):
        # On click, open a context menu for the cell.
        hit = self._cell_at(event)
        if not hit:
            return
        ri, col = hit
        kind, name = self._rows()[ri]
        d = self.roster.days[col]
        cfg = self.roster.config
        r = self.roster
        # Shared menu styling.
        opts = dict(tearoff=0, font=T.Fonts.get(10), bg=T.SURFACE, activebackground=T.PRIMARY_LIGHT, activeforeground=T.PRIMARY_DARK, bd=0)
        menu = tk.Menu(self, **opts)
        # ``target`` tells the edit callback which cell/row this is.
        target = ("eng", name) if kind == "eng" else (kind, None)
        if kind == "eng":
            # A disabled header line, then a code choice for each code.
            menu.add_command(label=f"{name} · {d:%a %d %b}", state="disabled")
            for code in ALL_CODES:
                menu.add_command(label=f"{code:<3}  {CODE_DESCRIPTIONS[code]}", command=lambda code=code: self.on_edit("set", target, d, code))
            menu.add_separator()
            # A "Swap with…" submenu listing the other engineers.
            swap_menu = tk.Menu(menu, **opts)
            for other in cfg.engineer_names:
                if other != name:
                    swap_menu.add_command(label=f"{other}  ({r.code(other, d)})", command=lambda o=other: self.on_edit("swap", target, d, o))
            menu.add_cascade(label="Swap with…", menu=swap_menu)
            locked = (name, d) in r.locks.cells
        else:
            # An on-call cell: choose the engineer (filtered by SME status).
            want_sme = kind == "secondary"
            menu.add_command(label=f"{ONCALL_LABELS[kind]} · {d:%a %d %b}", state="disabled")
            menu.add_command(label="(none)", command=lambda: self.on_edit("set", target, d, ""))
            for e in cfg.engineers:
                if e.is_sme == want_sme:
                    menu.add_command(label=e.name, command=lambda n=e.name: self.on_edit("set", target, d, n))
            menu.add_separator()
            locked = d in (r.locks.primary if kind == "primary" else r.locks.secondary)
        # A Lock or Unlock entry depending on the current state.
        if locked:
            menu.add_command(label="Unlock (let Generate change it)", command=lambda: self.on_edit("unlock", target, d, None))
        else:
            menu.add_command(label="Lock (keep it when regenerating)", command=lambda: self.on_edit("lock", target, d, None))
        # Show the menu at the mouse position.
        menu.tk_popup(event.x_root, event.y_root)


class SwapDialog(tk.Toplevel):
    """Swap two engineers' duties on one day, previewing any rule problems
    the swap would cause before it is applied."""

    def __init__(self, app, a="", b="", day=None):
        super().__init__(app)
        self.app = app
        self.title("Swap shifts")
        self.configure(bg=T.SURFACE, padx=20, pady=18)
        self.transient(app)          # stay on top of the main window
        self.resizable(False, False)
        names = app.roster.config.engineer_names
        f = T.Fonts.get
        # Title and explanatory subtitle.
        tk.Label(self, text="Swap shifts", bg=T.SURFACE, fg=T.TEXT, font=f(14, "bold")).grid(row=0, column=0, columnspan=3, sticky="w")
        tk.Label(
            self, text="The two engineers exchange their shift and on-call duty for the day.\nSwapped cells are locked so regenerating keeps them.",
            bg=T.SURFACE, fg=T.MUTED, font=f(9), justify="left",
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(2, 12))
        # The two engineer pickers and the date, as bound variables.
        self.a, self.b, self.day = tk.StringVar(value=a), tk.StringVar(value=b), tk.StringVar(value=day.isoformat() if day else "")
        for col, (label, var) in enumerate((("Engineer", self.a), ("Swaps with", self.b))):
            tk.Label(self, text=label, bg=T.SURFACE, fg=T.MUTED, font=f(9, "bold")).grid(row=2, column=col, sticky="w", padx=(0, 12))
            ttk.Combobox(self, textvariable=var, values=names, state="readonly", width=18).grid(row=3, column=col, sticky="w", padx=(0, 12))
        tk.Label(self, text="Date", bg=T.SURFACE, fg=T.MUTED, font=f(9, "bold")).grid(row=2, column=2, sticky="w")
        DateEntry(self, self.day, default_date=app.roster_month_start, is_weekend=app.is_weekend, holiday_name=app.holiday_name, width=12).grid(row=3, column=2, sticky="w")

        # The preview box and the rule-check line.
        self.preview = tk.Label(self, text="", bg=T.STRIPE, fg=T.TEXT, font=f(10), justify="left", anchor="w", padx=12, pady=10, width=62)
        self.preview.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(16, 8))
        self.check = tk.Label(self, text="", bg=T.SURFACE, fg=T.MUTED, font=f(9), justify="left", anchor="w", wraplength=520)
        self.check.grid(row=5, column=0, columnspan=3, sticky="ew")

        # Cancel and Swap buttons.
        btns = tk.Frame(self, bg=T.SURFACE)
        btns.grid(row=6, column=0, columnspan=3, sticky="e", pady=(16, 0))
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(side="right")
        self.ok = ttk.Button(btns, text="Swap", style="Accent.TButton", command=self.apply)
        self.ok.pack(side="right", padx=(0, 8))
        # Re-preview whenever a field changes.
        for v in (self.a, self.b, self.day):
            v.trace_add("write", lambda *_: self.refresh())
        self.bind("<Escape>", lambda _e: self.destroy())
        self.result = None
        # Draw the initial preview.
        self.refresh()
        # Centre the dialog over the main window.
        self.update_idletasks()
        x = app.winfo_rootx() + (app.winfo_width() - self.winfo_reqwidth()) // 2
        y = app.winfo_rooty() + (app.winfo_height() - self.winfo_reqheight()) // 3
        self.geometry(f"+{max(0, x)}+{max(0, y)}")
        self.grab_set()   # make it modal

    def _parse(self):
        # Read and validate the two names and the date; None if incomplete.
        roster = self.app.roster
        a, b = self.a.get(), self.b.get()
        try:
            d = parse_date(self.day.get(), roster.config.year, roster.config.month)
        except ValueError:
            return None
        if not a or not b or a == b or d not in set(roster.days):
            return None
        return a, b, d

    def refresh(self):
        # Recompute the preview and the rule check for the current selection.
        parsed = self._parse()
        self.result = None
        if not parsed:
            # Not enough chosen yet.
            self.preview.configure(text="Pick two different engineers and a day in the roster month.")
            self.check.configure(text="", fg=T.MUTED)
            self.ok.state(["disabled"])
            return
        a, b, d = parsed
        roster = self.app.roster
        # Compute the swapped roster and describe what changes.
        new = storage.swap(roster, a, b, d)
        lines, last_day = [], None
        for c in storage.diff(roster, new):
            if c.day != last_day:
                lines.append(f"{c.day:%A %d %B}" + ("   (comp off moves with the night)" if last_day else ""))
                last_day = c.day
            lines.append(f"   {c.who}:  {c.old or '-'}  →  {c.new or '-'}")
        self.preview.configure(text="\n".join(lines) or "Nothing changes - both have the same duty that day.")
        # Show any NEW rule errors the swap would introduce.
        before = {i.message for i in validate(roster) if i.severity == ERROR}
        added = [i for i in validate(new) if i.severity == ERROR and i.message not in before]
        if added:
            text = "This swap would break these rules:\n" + "\n".join(f"  • {i.day:%d %b}: {i.message}" if i.day else f"  • {i.message}" for i in added[:6])
            self.check.configure(text=text, fg=T.DANGER)
            self.ok.configure(text="Swap anyway")
        else:
            self.check.configure(text="✓ No new rule problems.", fg=T.SUCCESS)
            self.ok.configure(text="Swap")
        self.ok.state(["!disabled"])
        self.result = new

    def apply(self):
        # Apply the previewed swap to the app and close.
        if self.result is not None:
            a, b, d = self._parse()
            self.app.apply_roster(self.result, f"Swapped {a} and {b} on {d:%d %b}")
        self.destroy()


class StatTile(tk.Frame):
    """A small summary tile: caption above a big value."""

    def __init__(self, master, caption):
        super().__init__(master, bg=T.SURFACE, highlightbackground=T.BORDER, highlightthickness=1, padx=14, pady=7)
        # A small uppercase caption, a big value, and a muted subtext.
        self.caption = tk.Label(self, text=caption.upper(), bg=T.SURFACE, fg=T.MUTED, font=T.Fonts.get(8, "bold"))
        self.caption.pack(anchor="w")
        self.value = tk.Label(self, text="—", bg=T.SURFACE, fg=T.TEXT, font=T.Fonts.get(15, "bold"))
        self.value.pack(anchor="w")
        self.sub = tk.Label(self, text="", bg=T.SURFACE, fg=T.MUTED, font=T.Fonts.get(8))
        self.sub.pack(anchor="w")

    def set(self, value, sub="", fg=T.TEXT, bg=T.SURFACE):
        # Update the tile's value/subtext and optional colours.
        for w in (self, self.caption, self.value, self.sub):
            w.configure(bg=bg)
        self.value.configure(text=value, fg=fg)
        self.sub.configure(text=sub)


class Sidebar(tk.Frame):
    """Vertical step navigation replacing notebook tabs."""

    def __init__(self, master, on_select):
        super().__init__(master, bg=T.SIDEBAR_BG, width=230, highlightbackground=T.BORDER, highlightthickness=1)
        self.pack_propagate(False)   # keep the fixed width
        self.on_select = on_select   # callback(index) when a step is clicked
        self.items = []              # per-step widget bundles
        self.selected = 0
        # A small "STEPS" heading.
        tk.Label(self, text="STEPS", bg=T.SIDEBAR_BG, fg=T.MUTED, font=T.Fonts.get(8, "bold"), anchor="w").pack(fill="x", padx=20, pady=(18, 6))

    def add(self, number, title):
        # Add one navigation step.
        idx = len(self.items)
        row = tk.Frame(self, bg=T.SIDEBAR_BG, cursor="hand2")
        row.pack(fill="x", padx=10, pady=1)
        # A left accent bar (shown when selected).
        bar = tk.Frame(row, bg=T.SIDEBAR_BG, width=4)
        bar.pack(side="left", fill="y")
        # The number chip, the title, and a right-aligned count badge.
        num = tk.Label(row, text=str(number), width=2, bg="#F3F4F6", fg=T.MUTED, font=T.Fonts.get(9, "bold"))
        num.pack(side="left", padx=(10, 10), pady=9)
        text = tk.Label(row, text=title, bg=T.SIDEBAR_BG, fg=T.TEXT, font=T.Fonts.get(10), anchor="w")
        text.pack(side="left", fill="x", expand=True)
        badge = tk.Label(row, text="", bg=T.SIDEBAR_BG, fg=T.MUTED, font=T.Fonts.get(9))
        badge.pack(side="right", padx=(0, 10))
        item = {"row": row, "bar": bar, "num": num, "text": text, "badge": badge}
        self.items.append(item)
        # Bind click and hover to every part of the row.
        for w in (row, num, text, badge, bar):
            w.bind("<Button-1>", lambda _e, i=idx: self.on_select(i))
            w.bind("<Enter>", lambda _e, i=idx: self._hover(i, True))
            w.bind("<Leave>", lambda _e, i=idx: self._hover(i, False))
        self._paint(idx)

    def set_badge(self, idx, text):
        # Set the count badge on a step.
        self.items[idx]["badge"].configure(text=text)

    def select(self, idx):
        # Change which step is highlighted.
        old, self.selected = self.selected, idx
        self._paint(old)
        self._paint(idx)

    def _hover(self, idx, on):
        # Tint a non-selected step on hover.
        if idx != self.selected:
            self._paint(idx, T.SIDEBAR_HOVER if on else None)

    def _paint(self, idx, bg=None):
        # Recolour one step based on selected/hover state.
        it = self.items[idx]
        sel = idx == self.selected
        bg = bg or (T.PRIMARY_LIGHT if sel else T.SIDEBAR_BG)
        for k in ("row", "text", "badge"):
            it[k].configure(bg=bg)
        it["bar"].configure(bg=T.PRIMARY if sel else bg)
        it["text"].configure(fg=T.PRIMARY_DARK if sel else T.TEXT, font=T.Fonts.get(10, "bold" if sel else "normal"))
        it["num"].configure(bg=T.PRIMARY if sel else "#F3F4F6", fg="white" if sel else T.MUTED)


class RosterApp(tk.Tk):
    # The main application window (subclasses Tk, the root window).
    def __init__(self):
        super().__init__()
        self.title("Roster Creator")
        # Size the window sensibly for the screen.
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{max(1000, min(1440, sw - 60))}x{max(640, min(960, sh - 90))}")
        self.minsize(1000, 640)
        # Apply the colour/font theme.
        T.apply_theme(self)
        # Set the window icon (ignore if the image is unavailable).
        try:
            self._icon = tk.PhotoImage(file=ICON_PNG)
            self.iconphoto(True, self._icon)
        except tk.TclError:
            pass
        # ---- Application state ----
        self.last_dir = os.path.expanduser("~")   # folder file dialogs open in
        self.roster: Roster | None = None          # the current roster
        self.issues = []                           # its validation issues
        self.config_path: str | None = None  # inputs-only file
        self.roster_path: str | None = None  # full roster file
        self.published: Roster | None = None  # last published version, for change tracking
        self.published_at = ""
        self.carry_over: dict = {}

        # Give every RecordEditor access to this app (for calendar context).
        RecordEditor.date_context = self
        # Build the menu bar and the header.
        self._build_menu()
        self._build_header()
        # The body holds the sidebar and the (tab-less) notebook of pages.
        body = ttk.Frame(self)
        body.pack(fill="both", expand=True)
        self.sidebar = Sidebar(body, self.show_page)
        self.sidebar.pack(side="left", fill="y")
        self.nb = ttk.Notebook(body, style="Pages.TNotebook")
        self.nb.pack(side="left", fill="both", expand=True)

        # A status bar at the bottom.
        self.status = tk.StringVar(value="Ready")
        ttk.Label(self, textvariable=self.status, style="Status.TLabel", anchor="w").pack(fill="x", side="bottom", before=body)

        # Build each page in order.
        self._build_team_tab()
        self._build_calendar_tab()
        self._build_leave_tabs()
        self._build_requirements_tab()
        self._build_oncall_tab()
        self._build_rules_tab()
        self._build_roster_tab()
        # Start on the first page with blank inputs.
        self.show_page(0)
        self.load_dict(empty_config_dict())

    # -- layout --------------------------------------------------------------
    def _build_menu(self):
        # The menu bar: File and Roster menus.
        menubar = tk.Menu(self)
        fm = tk.Menu(menubar, tearoff=0)
        fm.add_command(label="New", command=self.new_config)
        fm.add_command(label="Open roster or inputs…", accelerator="Ctrl+O", command=self.open_file)
        fm.add_command(label="Save roster", accelerator="Ctrl+S", command=self.save_roster)
        fm.add_command(label="Save roster as…", command=lambda: self.save_roster(ask=True))
        fm.add_command(label="Save inputs only…", command=lambda: self.save_config(ask=True))
        fm.add_command(label="Load sample data", command=self.load_sample)
        fm.add_separator()
        fm.add_command(label="Import previous month's roster…", command=self.import_previous)
        fm.add_separator()
        fm.add_command(label="Export roster to Excel…", command=self.export_excel)
        fm.add_command(label="Export roster to CSV…", command=self.export_csv)
        fm.add_command(label="Export calendar invites (.ics)…", command=self.export_ics)
        fm.add_separator()
        fm.add_command(label="Exit", command=self.destroy)
        menubar.add_cascade(label="File", menu=fm)
        # The Roster menu.
        rm = tk.Menu(menubar, tearoff=0)
        rm.add_command(label="Generate roster", accelerator="Ctrl+G", command=self.generate)
        rm.add_command(label="Swap shifts…", command=self.open_swap)
        rm.add_command(label="Mark as published", command=self.mark_published)
        rm.add_command(label="Clear all locks", command=self.clear_locks)
        menubar.add_cascade(label="Roster", menu=rm)
        self.config(menu=menubar)
        # Keyboard shortcuts.
        self.bind_all("<Control-s>", lambda _e: self.save_roster())
        self.bind_all("<Control-o>", lambda _e: self.open_file())
        self.bind_all("<Control-g>", lambda _e: self.generate())

    def _build_header(self):
        # The dark header bar with the logo, title and a Generate button.
        bar = tk.Frame(self, bg=T.HEADER_BG, height=64)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        # A little calendar logo drawn on a canvas.
        logo = tk.Canvas(bar, width=36, height=36, bg=T.HEADER_BG, highlightthickness=0)
        logo.pack(side="left", padx=(20, 12))
        # A tiny calendar icon.
        logo.create_rectangle(4, 7, 32, 32, fill=T.PRIMARY, outline="")
        logo.create_rectangle(4, 7, 32, 14, fill="#818CF8", outline="")
        for cx in (10, 18, 26):
            for cy in (19, 26):
                logo.create_rectangle(cx - 2, cy - 2, cx + 2, cy + 2, fill="white", outline="")
        # The title and subtitle.
        titles = tk.Frame(bar, bg=T.HEADER_BG)
        titles.pack(side="left")
        tk.Label(titles, text="Roster Creator", bg=T.HEADER_BG, fg=T.HEADER_FG, font=T.Fonts.get(15, "bold")).pack(anchor="w")
        tk.Label(titles, text="Shift & on-call planner", bg=T.HEADER_BG, fg=T.HEADER_MUTED, font=T.Fonts.get(9)).pack(anchor="w")

        # On the right: a context line and the Generate button.
        right = tk.Frame(bar, bg=T.HEADER_BG)
        right.pack(side="right", padx=20)
        self.header_context = tk.Label(right, text="", bg=T.HEADER_BG, fg=T.HEADER_MUTED, font=T.Fonts.get(10))
        self.header_context.pack(side="left", padx=(0, 16))
        tk.Button(
            right, text="Generate roster  ▶", command=self.generate, bg=T.PRIMARY, fg="white", activebackground="#6366F1",
            activeforeground="white", relief="flat", bd=0, highlightthickness=0, padx=16, pady=7, font=T.Fonts.get(10, "bold"), cursor="hand2",
        ).pack(side="left")

    def _add_page(self, title, subtitle, nav_title):
        # Create a page frame, add it to the notebook, and add a sidebar step.
        frame = page(self.nb, title, subtitle)
        self.nb.add(frame)
        self.sidebar.add(len(self.sidebar.items) + 1, nav_title)
        return frame

    def show_page(self, idx):
        # Switch to a page and highlight its sidebar step.
        self.nb.select(idx)
        self.sidebar.select(idx)

    def _build_team_tab(self):
        # The Team page: a RecordEditor over the engineers list.
        tab = self._add_page("Team", "Who is on the roster. SMEs cover secondary on-call; everyone else covers primary on-call.", "Team")
        self.team = RecordEditor(
            tab,
            "Add an engineer",
            [
                ("name", "Name", "entry", None),
                ("designation", "Designation", "combo", DESIGNATIONS),
                ("sme", "Subject matter expert (SME)", "check", None),
            ],
            on_change=self._inputs_changed,
            noun="engineer",
            columns=3,
        )
        self.team.pack(fill="both", expand=True)

    def _build_calendar_tab(self):
        # The Month & Calendar page.
        tab = self._add_page("Month & Calendar", "Pick the roster month and mark weekends, holidays and freeze periods.", "Calendar")
        # A card for the month, year and weekend-day choices.
        top, body = card(tab, "Roster month")
        top.pack(fill="x")
        ttk.Label(body, text="Month", style="Card.TLabel", foreground=T.MUTED, font=T.Fonts.get(9, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(body, text="Year", style="Card.TLabel", foreground=T.MUTED, font=T.Fonts.get(9, "bold")).grid(row=0, column=1, sticky="w", padx=(12, 0))
        ttk.Label(body, text="Weekend days", style="Card.TLabel", foreground=T.MUTED, font=T.Fonts.get(9, "bold")).grid(row=0, column=2, sticky="w", padx=(32, 0))
        self.month_var = tk.StringVar()
        self.year_var = tk.StringVar()
        ttk.Combobox(body, textvariable=self.month_var, values=list(calendar.month_name)[1:], state="readonly", width=14).grid(row=1, column=0, sticky="w", pady=(3, 0))
        ttk.Spinbox(body, from_=2000, to=2100, textvariable=self.year_var, width=7).grid(row=1, column=1, sticky="w", padx=(12, 0), pady=(3, 0))
        # A checkbox per weekday for the weekend selection.
        days = ttk.Frame(body, style="Surface.TFrame")
        days.grid(row=1, column=2, sticky="w", padx=(32, 0), pady=(3, 0))
        self.weekend_vars = []
        for i, day in enumerate(WEEKDAY_NAMES):
            v = tk.BooleanVar(value=i in (5, 6))
            ttk.Checkbutton(days, text=day, variable=v).pack(side="left", padx=(0, 8))
            self.weekend_vars.append(v)
        # Update the header when month/year change.
        for v in (self.month_var, self.year_var):
            v.trace_add("write", lambda *_: self._update_header())

        # Two side-by-side editors: holidays and freeze periods.
        row = ttk.Frame(tab)
        row.pack(fill="both", expand=True, pady=(14, 0))
        self.holidays = RecordEditor(
            row, "Holiday", [("date", "Date", "date", None), ("name", "Name", "entry", None)],
            hint=DATE_HINT, noun="holiday", on_change=self._inputs_changed,
        )
        self.holidays.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        self.freeze = RecordEditor(
            row,
            "Freeze period",
            [("start", "Start date", "date", None), ("end", "End date", "date", None), ("note", "Note", "entry", None)],
            hint="Freeze days are exempt from the minimum Morning/Night rule (see Rules).",
            noun="freeze period", on_change=self._inputs_changed,
        )
        self.freeze.grid(row=0, column=1, sticky="nsew", padx=(7, 0))
        row.columnconfigure((0, 1), weight=1, uniform="cal")
        row.rowconfigure(0, weight=1)

    # -- date context for calendar pickers --------------------------------------
    def roster_month_start(self) -> date:
        # The 1st of the currently-selected roster month (today's month on error).
        try:
            return date(int(self.year_var.get()), list(calendar.month_name).index(self.month_var.get()), 1)
        except (ValueError, AttributeError):
            return date.today().replace(day=1)

    def is_weekend(self, d: date) -> bool:
        # Whether day ``d`` is a weekend per the checkboxes.
        return self.weekend_vars[d.weekday()].get()

    def holiday_name(self, d: date) -> str:
        # The holiday name on day ``d`` (empty if none), read from the editor rows.
        start = self.roster_month_start()
        for row in self.holidays.get_rows() if hasattr(self, "holidays") else []:
            try:
                if parse_date(row.get("date"), start.year, start.month) == d:
                    return row.get("name") or "Holiday"
            except ValueError:
                continue
        return ""

    def _names(self, sme=None):
        # The engineer names, optionally filtered to SMEs / non-SMEs.
        rows = self.team.get_rows() if hasattr(self, "team") else []
        return [r["name"] for r in rows if sme is None or bool(r.get("sme")) == sme]

    def _build_leave_tabs(self):
        # The Leave and Long Leave pages share the same field layout.
        fields = [
            ("engineer", "Engineer", "choice", lambda: self._names()),
            ("start", "Start date", "date", None),
            ("end", "End date (optional)", "date", None),
            ("note", "Note", "entry", None),
        ]
        tab = self._add_page("Leave", "Planned days off. Leave the end date empty for a single day. Shown as L.", "Leave")
        self.leaves = RecordEditor(tab, "Add leave", fields, hint=DATE_HINT, noun="leave request", on_change=self._inputs_changed)
        self.leaves.pack(fill="both", expand=True)
        tab = self._add_page("Long Leave", "Extended absences such as vacations or medical leave. Shown as LL.", "Long Leave")
        self.long_leaves = RecordEditor(tab, "Add long leave", fields, hint=DATE_HINT, noun="long leave", on_change=self._inputs_changed)
        self.long_leaves.pack(fill="both", expand=True)

    def _build_requirements_tab(self):
        # The Shift Requirements page (Must / Prefer / Avoid).
        tab = self._add_page("Shift Requirements", "Pin an engineer to a shift, give them a preferred shift, or keep them off one (e.g. no nights).", "Shift Requirements")
        self.requirements = RecordEditor(
            tab,
            "Add a shift requirement",
            [
                ("engineer", "Engineer", "choice", lambda: self._names()),
                ("shift", "Shift", "choice", [SHIFT_NAMES[s] for s in SHIFTS]),
                ("start", "Start date", "date", None),
                ("end", "End date (optional)", "date", None),
                ("mode", "Type", "choice", ["Must", "Prefer", "Avoid"]),
                ("note", "Note", "entry", None),
            ],
            hint="Must = always this shift.   Prefer = this shift when the rules allow.   Avoid = never this shift.",
            noun="requirement", on_change=self._inputs_changed,
        )
        self.requirements.pack(fill="both", expand=True)

    def _build_oncall_tab(self):
        # The On-Call overrides page.
        tab = self._add_page("On-Call", "Optionally fix who is on call for specific days. Other days are rotated automatically.", "On-Call")
        self.oncall = RecordEditor(
            tab,
            "Set on-call for a day",
            [
                ("date", "Date", "date", None),
                ("primary", "Primary (non-SME)", "choice", lambda: [""] + self._names(sme=False)),
                ("secondary", "Secondary (SME)", "choice", lambda: [""] + self._names(sme=True)),
            ],
            hint="Secondary on-call is not required on weekends and holidays.",
            noun="on-call override", on_change=self._inputs_changed, columns=3,
        )
        self.oncall.pack(fill="both", expand=True)

    def _build_rules_tab(self):
        # The Rules page: minimums, generator settings, timings and carry-over.
        tab = self._add_page("Rules", "Coverage minimums and generator settings.", "Rules")
        cols = ttk.Frame(tab)
        cols.pack(fill="x")
        # --- Minimum engineers per shift, per day type ---
        outer, box = card(cols, "Minimum engineers per shift", "Default: at least 1 on Morning and Night on working days only.")
        outer.pack(side="left", fill="both", expand=True, padx=(0, 7))
        hdr = dict(style="Card.TLabel", foreground=T.MUTED, font=T.Fonts.get(9, "bold"))
        ttk.Label(box, text="DAY TYPE", **hdr).grid(row=0, column=0, sticky="w")
        for j, s in enumerate(SHIFTS, 1):
            ttk.Label(box, text=SHIFT_NAMES[s].upper(), **hdr).grid(row=0, column=j, padx=10, sticky="w")
        # One spinbox per (day type, shift), stored by day type then shift.
        self.min_vars: dict[str, dict[str, tk.StringVar]] = {}
        for i, dtype in enumerate(DAY_TYPES, 1):
            ttk.Label(box, text=dtype, style="Card.TLabel").grid(row=i, column=0, sticky="w", pady=4)
            self.min_vars[dtype] = {}
            for j, s in enumerate(SHIFTS, 1):
                v = tk.StringVar(value="0")
                ttk.Spinbox(box, from_=0, to=20, textvariable=v, width=5).grid(row=i, column=j, padx=10, sticky="w")
                self.min_vars[dtype][s] = v

        # --- Generator settings (attempts and seed) ---
        outer, adv = card(cols, "Generator", "More attempts give a fairer roster but take longer.")
        outer.pack(side="left", fill="both", expand=True, padx=(7, 0))
        ttk.Label(adv, text="ATTEMPTS", **hdr).grid(row=0, column=0, sticky="w")
        self.attempts_var = tk.StringVar()
        ttk.Spinbox(adv, from_=1, to=5000, textvariable=self.attempts_var, width=8).grid(row=1, column=0, sticky="w", pady=(3, 12))
        ttk.Label(adv, text="RANDOM SEED (OPTIONAL)", **hdr).grid(row=2, column=0, sticky="w")
        self.seed_var = tk.StringVar()
        ttk.Entry(adv, textvariable=self.seed_var, width=10).grid(row=3, column=0, sticky="w", pady=(3, 0))
        ttk.Label(adv, text="Set a seed to get the same roster every time.", style="Hint.TLabel").grid(row=4, column=0, sticky="w", pady=(4, 0))

        # --- Shift timings and carry-over, side by side ---
        cols2 = ttk.Frame(tab)
        cols2.pack(fill="x", pady=(14, 0))
        outer, times = card(cols2, "Shift timings", "Used for the calendar invites (.ics). A night ending earlier than it starts ends next morning.")
        outer.pack(side="left", fill="both", expand=True, padx=(0, 7))
        ttk.Label(times, text="SHIFT", **hdr).grid(row=0, column=0, sticky="w")
        ttk.Label(times, text="START", **hdr).grid(row=0, column=1, sticky="w", padx=10)
        ttk.Label(times, text="END", **hdr).grid(row=0, column=2, sticky="w", padx=10)
        # A (start, end) pair of entries per shift.
        self.time_vars: dict[str, tuple[tk.StringVar, tk.StringVar]] = {}
        for i, sh in enumerate(SHIFTS, 1):
            ttk.Label(times, text=SHIFT_NAMES[sh], style="Card.TLabel").grid(row=i, column=0, sticky="w", pady=3)
            a, b = tk.StringVar(), tk.StringVar()
            ttk.Entry(times, textvariable=a, width=7).grid(row=i, column=1, sticky="w", padx=10)
            ttk.Entry(times, textvariable=b, width=7).grid(row=i, column=2, sticky="w", padx=10)
            self.time_vars[sh] = (a, b)

        # The carry-over card with a description and import/clear buttons.
        outer, carry = card(cols2, "Carry-over from previous month", "Keeps comp offs and fairness going from one month to the next.")
        outer.pack(side="left", fill="both", expand=True, padx=(7, 0))
        self.carry_var = tk.StringVar()
        ttk.Label(carry, textvariable=self.carry_var, style="Card.TLabel", justify="left", wraplength=460).pack(anchor="w")
        cbtn = ttk.Frame(carry, style="Surface.TFrame")
        cbtn.pack(anchor="w", pady=(10, 0))
        ttk.Button(cbtn, text="Import previous month's roster…", style="Accent.TButton", command=self.import_previous).pack(side="left")
        ttk.Button(cbtn, text="Clear", command=self.clear_carry_over).pack(side="left", padx=(8, 0))

        # A reference card listing the mandatory rules.
        outer, rules = card(tab, "Mandatory rules applied")
        outer.pack(fill="x", pady=(14, 0))
        items = (
            ("Coverage", "At least 1 engineer on Morning and Night on working days (freeze, weekends and holidays excluded)."),
            ("Comp off", "Every night shift earns a comp off (CO) on the next working day - never on a weekend or holiday."),
            ("Primary on-call", "Every day - a non-SME engineer who is not on Morning or Night that day."),
            ("Secondary on-call", "An SME engineer - not required on weekends and holidays."),
            ("Requests", "Leave, long leave and shift requirements are honoured; anything that can't be met is reported."),
        )
        for i, (head, text) in enumerate(items):
            tk.Label(rules, text="✓", bg=T.SUCCESS_LIGHT, fg=T.SUCCESS, font=T.Fonts.get(9, "bold"), width=2).grid(row=i, column=0, sticky="w", pady=4)
            ttk.Label(rules, text=head, style="Card.TLabel", font=T.Fonts.get(10, "bold")).grid(row=i, column=1, sticky="w", padx=(10, 14))
            ttk.Label(rules, text=text, style="Card.TLabel", foreground=T.MUTED).grid(row=i, column=2, sticky="w")

    def _build_roster_tab(self):
        # The Roster page: toolbar, summary tiles, legend, the grid and the
        # Checks/Changes tabs.
        tab = self._add_page(
            "Roster",
            "Click a cell to change, lock or swap it. Locked cells stay put when you regenerate.",
            "Roster",
        )
        # Toolbar of actions.
        bar = ttk.Frame(tab)
        bar.pack(fill="x", pady=(0, 10))
        ttk.Button(bar, text="Generate roster  ▶", style="Big.Accent.TButton", command=self.generate).pack(side="left")
        ttk.Button(bar, text="⇄  Swap shifts…", command=self.open_swap).pack(side="left", padx=(8, 0))
        ttk.Button(bar, text="✓  Mark as published", command=self.mark_published).pack(side="left", padx=(8, 0))
        ttk.Button(bar, text="Clear locks", command=self.clear_locks).pack(side="left", padx=(8, 0))
        ttk.Button(bar, text="Calendar (.ics)", command=self.export_ics).pack(side="right")
        ttk.Button(bar, text="CSV", command=self.export_csv).pack(side="right", padx=(0, 8))
        ttk.Button(bar, text="Excel", command=self.export_excel).pack(side="right", padx=(0, 8))
        ttk.Button(bar, text="Save roster", command=self.save_roster).pack(side="right", padx=(0, 8))

        # The six summary tiles.
        tiles = ttk.Frame(tab)
        tiles.pack(fill="x", pady=(0, 10))
        self.tiles = {}
        for i, key in enumerate(("Status", "Rule violations", "Warnings", "Nights / person", "Preferences met", "Changes")):
            t = StatTile(tiles, key)
            t.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 10, 0))
            tiles.columnconfigure(i, weight=1, uniform="tiles")
            self.tiles[key] = t

        # The colour legend (one chip per code).
        legend = tk.Frame(tab, bg=T.BG)
        legend.pack(fill="x", pady=(0, 8))
        for code in ALL_CODES:
            tk.Label(
                legend, text=code, width=3, bg="#" + export.CODE_COLORS[code], fg="#" + export.CODE_TEXT_COLORS.get(code, "111827"),
                font=T.Fonts.get(8, "bold"), pady=2,
            ).pack(side="left", padx=(0, 4))
            tk.Label(legend, text=LEGEND_NAMES[code], bg=T.BG, fg=T.MUTED, font=T.Fonts.get(9)).pack(side="left", padx=(0, 10))
        legend.pack_configure(pady=(0, 4))
        # A second legend row for the dots and markers.
        markers = tk.Frame(tab, bg=T.BG)
        markers.pack(fill="x", pady=(0, 8))
        for color, text in ((T.PRIMARY, "Primary on-call"), ("#0D9488", "Secondary on-call"), (T.DANGER, "Rule broken that day")):
            dot = tk.Canvas(markers, width=10, height=10, bg=T.BG, highlightthickness=0)
            dot.create_oval(1, 1, 9, 9, fill=color, outline="")
            dot.pack(side="left", padx=(0, 4))
            tk.Label(markers, text=text, bg=T.BG, fg=T.MUTED, font=T.Fonts.get(9)).pack(side="left", padx=(0, 14))
        # The "changed" outline marker.
        mark = tk.Canvas(markers, width=14, height=12, bg=T.BG, highlightthickness=0)
        mark.create_rectangle(1, 1, 13, 11, outline=CHANGED_COLOR, width=2)
        mark.pack(side="left", padx=(0, 4))
        tk.Label(markers, text="Changed since published", bg=T.BG, fg=T.MUTED, font=T.Fonts.get(9)).pack(side="left", padx=(0, 14))
        # The "locked" padlock marker.
        lock = tk.Canvas(markers, width=12, height=12, bg=T.BG, highlightthickness=0)
        lock.create_arc(2.5, 1, 8.5, 8, start=0, extent=180, style="arc", outline=T.TEXT, width=1.5)
        lock.create_rectangle(1, 4.5, 10, 11, fill=T.TEXT, outline="")
        lock.pack(side="left", padx=(0, 4))
        tk.Label(markers, text="Locked - kept when regenerating", bg=T.BG, fg=T.MUTED, font=T.Fonts.get(9)).pack(side="left")

        # A vertical split: the grid on top, the Checks/Changes tabs below.
        pane = ttk.PanedWindow(tab, orient="vertical")
        pane.pack(fill="both", expand=True)
        grid_card = ttk.Frame(pane, style="Card.TFrame", padding=8)
        self.grid_view = RosterGrid(grid_card, self._on_grid_edit, lambda s: self.status.set(s or "Ready"))
        self.grid_view.pack(fill="both", expand=True)
        pane.add(grid_card, weight=4)

        # A small notebook holding the Checks and Changes tables.
        bottom = ttk.Notebook(pane)
        pane.add(bottom, weight=1)
        self.bottom_nb = bottom

        # The Checks tab (validation issues).
        issues_card = ttk.Frame(bottom, style="Surface.TFrame")
        bottom.add(issues_card, text="  Checks  ")
        self.issue_tree = self._table(
            issues_card, (("sev", "SEVERITY", 110, False), ("date", "DATE", 120, False), ("msg", "MESSAGE", 900, True))
        )
        # Colour rows by severity.
        self.issue_tree.tag_configure(ERROR, foreground=T.DANGER, background=T.DANGER_LIGHT)
        self.issue_tree.tag_configure(WARNING, foreground="#B45309", background=T.WARNING_LIGHT)
        self.issue_tree.tag_configure(INFO, foreground=T.MUTED)
        self.issue_tree.tag_configure("ok", foreground=T.SUCCESS, background=T.SUCCESS_LIGHT)

        # The Changes tab (differences since publishing).
        changes_card = ttk.Frame(bottom, style="Surface.TFrame")
        bottom.add(changes_card, text="  Changes since published  ")
        head = ttk.Frame(changes_card, style="Surface.TFrame", padding=(10, 6))
        head.pack(fill="x")
        self.published_var = tk.StringVar(value="Not published yet.")
        ttk.Label(head, textvariable=self.published_var, style="Hint.TLabel").pack(side="left")
        ttk.Button(head, text="Copy list", command=self.copy_changes).pack(side="right")
        self.change_tree = self._table(
            changes_card, (("date", "DATE", 120, False), ("who", "WHO", 180, False), ("old", "BEFORE", 140, False), ("new", "AFTER", 140, False))
        )
        self.change_tree.tag_configure("chg", background=T.WARNING_LIGHT)
        # Remember the roster page's index so we can switch to it after generating.
        self.roster_page = len(self.nb.tabs()) - 1

    def _table(self, parent, columns):
        # Build a scrollable Treeview table from a column spec.
        inner = ttk.Frame(parent, style="Surface.TFrame")
        inner.pack(fill="both", expand=True)
        tree = ttk.Treeview(inner, columns=[c[0] for c in columns], show="headings", height=3)
        for key, label, width, stretch in columns:
            tree.heading(key, text=label, anchor="w")
            tree.column(key, width=width, anchor="w", stretch=stretch)
        sb = ttk.Scrollbar(inner, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        return tree

    # -- data in/out -----------------------------------------------------------
    def _inputs_changed(self):
        # Called whenever any input list changes: refresh dropdowns and badges.
        for editor in (self.leaves, self.long_leaves, self.requirements, self.oncall):
            editor.refresh_options()
        # Update each sidebar step's count badge (calendar is a special case).
        for idx, editor in enumerate((self.team, None, self.leaves, self.long_leaves, self.requirements, self.oncall)):
            if editor is not None:
                n = len(editor.rows)
                self.sidebar.set_badge(idx, str(n) if n else "")
        self.sidebar.set_badge(1, str(len(self.holidays.rows) + len(self.freeze.rows)) if hasattr(self, "freeze") and (self.holidays.rows or self.freeze.rows) else "")
        self._update_header()

    def _update_header(self):
        # Update the header context line with the month and team size.
        if not hasattr(self, "team"):
            return
        n = len(self.team.rows)
        sme = sum(1 for r in self.team.rows if r.get("sme"))
        self.header_context.configure(text=f"{self.month_var.get()} {self.year_var.get()}   ·   {n} engineers ({sme} SME)")

    def collect_dict(self) -> dict:
        # Gather every input widget's value into the plain-dict format.
        month_names = list(calendar.month_name)
        return {
            "year": self.year_var.get(),
            "month": month_names.index(self.month_var.get()) if self.month_var.get() in month_names else "",
            "engineers": self.team.get_rows(),
            "leaves": self.leaves.get_rows(),
            "long_leaves": self.long_leaves.get_rows(),
            "requirements": self.requirements.get_rows(),
            "oncall": self.oncall.get_rows(),
            "holidays": self.holidays.get_rows(),
            "freeze_periods": self.freeze.get_rows(),
            "weekend_days": [i for i, v in enumerate(self.weekend_vars) if v.get()],
            "min_coverage": {dt: {SHIFT_NAMES[s]: v.get() for s, v in d.items()} for dt, d in self.min_vars.items()},
            "attempts": self.attempts_var.get(),
            "seed": self.seed_var.get(),
            "shift_times": {SHIFT_NAMES[sh]: {"start": a.get(), "end": b.get()} for sh, (a, b) in self.time_vars.items()},
            "carry_over": self.carry_over,
        }

    def load_dict(self, data: dict):
        # Fill every input widget from a plain-dict (merged over blank defaults).
        base = empty_config_dict()
        base.update(data)
        self.year_var.set(str(base["year"]))
        self.month_var.set(calendar.month_name[int(base["month"])])
        self.team.set_rows(base["engineers"])
        self.leaves.set_rows(base["leaves"])
        self.long_leaves.set_rows(base["long_leaves"])
        self.requirements.set_rows(base["requirements"])
        self.oncall.set_rows(base["oncall"])
        self.holidays.set_rows(base["holidays"])
        self.freeze.set_rows(base["freeze_periods"])
        # Tick the weekend-day checkboxes.
        for i, v in enumerate(self.weekend_vars):
            v.set(i in [int(x) for x in base["weekend_days"]])
        # Fill the minimum-coverage spinboxes (falling back to defaults).
        defaults = empty_config_dict()
        for dt, d in self.min_vars.items():
            for s, v in d.items():
                v.set(str(base["min_coverage"].get(dt, {}).get(SHIFT_NAMES[s], defaults["min_coverage"][dt][SHIFT_NAMES[s]])))
        # Fill the shift-timing entries.
        for sh, (a, b) in self.time_vars.items():
            t = (base.get("shift_times") or {}).get(SHIFT_NAMES[sh]) or defaults["shift_times"][SHIFT_NAMES[sh]]
            a.set(t.get("start", "")), b.set(t.get("end", ""))
        # Attempts, seed and carry-over.
        self.attempts_var.set(str(base["attempts"]))
        self.seed_var.set(str(base.get("seed") or ""))
        self.carry_over = dict(base.get("carry_over") or {})
        self._update_carry_label()
        self._inputs_changed()

    def _reset_roster(self):
        # Clear the current roster and reset the roster page to empty.
        self.roster, self.issues = None, []
        self.roster_path = None
        self.published, self.published_at = None, ""
        self.grid_view.roster = None
        self.grid_view.canvas.delete("all")
        self.grid_view._empty_state()
        for tree in (self.issue_tree, self.change_tree):
            tree.delete(*tree.get_children())
        for t in self.tiles.values():
            t.set("—")
        self.published_var.set("Not published yet.")

    def new_config(self):
        # Start over after confirmation.
        if messagebox.askyesno("New", "Clear all inputs and the current roster?", parent=self):
            self.config_path = None
            self._reset_roster()
            self.load_dict(empty_config_dict())

    def open_file(self):
        # Ask for a file, then open it.
        path = filedialog.askopenfilename(
            parent=self, initialdir=self.last_dir, filetypes=[("Roster or inputs", "*.json"), ("All files", "*")]
        )
        if path:
            self._open_path(path)

    def _open_path(self, path):
        # Open a JSON file: a full roster file, or a plain inputs file.
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            if storage.is_roster_file(data):
                rf = storage.roster_file_from_dict(data)
            else:
                rf = None
        except (OSError, ValueError, KeyError) as exc:
            messagebox.showerror("Open failed", str(exc), parent=self)
            return
        self._reset_roster()
        if rf:
            # A full roster file: load inputs, roster and published snapshot.
            self.load_dict(rf.inputs)
            self.roster = rf.roster
            self.published, self.published_at = rf.published, rf.published_at
            self.roster_path, self.config_path = path, None
            self.issues = validate(self.roster)
            self._show_roster()
            self.show_page(self.roster_page)
        else:
            # A plain inputs file: just load the inputs.
            self.load_dict(data)
            self.config_path = path
        self._remember_dir(path)
        self.status.set(f"Opened {path}")

    def load_sample(self):
        # Load the bundled sample without pointing "Save" at it.
        last_dir = self.last_dir
        self._open_path(SAMPLE_CONFIG)
        # Don't point file dialogs or "Save" at the bundled sample.
        self.config_path = None
        self.last_dir = last_dir

    def save_config(self, ask=False):
        # Save just the inputs (no roster) to a JSON file.
        path = self.config_path
        if ask or not path:
            path = filedialog.asksaveasfilename(parent=self, initialdir=self.last_dir, defaultextension=".json", filetypes=[("Roster inputs", "*.json")])
            if not path:
                return
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.collect_dict(), fh, indent=2)
        self.config_path = path
        self._remember_dir(path)
        self.status.set(f"Saved inputs to {path}")

    def save_roster(self, ask=False):
        # Save the full roster file (inputs + roster + locks + published).
        if not self.roster:
            # Nothing generated yet - saving the inputs is all we can do.
            self.save_config(ask=True)
            return
        path = self.roster_path
        if ask or not path:
            path = filedialog.asksaveasfilename(
                parent=self, initialdir=self.last_dir, defaultextension=".json",
                initialfile=self._default_name("json"), filetypes=[("Roster file", "*.json")],
            )
            if not path:
                return
        try:
            storage.save_roster_file(path, self.collect_dict(), self.roster, self.published, self.published_at)
        except OSError as exc:
            messagebox.showerror("Save failed", str(exc), parent=self)
            return
        self.roster_path = path
        self._remember_dir(path)
        self.status.set(f"Saved roster to {path}")

    # -- carry-over ------------------------------------------------------------
    def _update_carry_label(self):
        # Refresh the carry-over description on the Rules page.
        co = self.carry_over
        if not co:
            self.carry_var.set(
                "Nothing imported. Import last month's saved roster so nights worked at the end of last month "
                "get their comp off here, and nights / on-call stay fair across months."
            )
            return
        nights = ", ".join(f"{n['engineer']} ({date.fromisoformat(n['date']):%d %b})" for n in co.get("nights", [])) or "none"
        self.carry_var.set(f"Imported from {co.get('source', 'previous month')}.\nPending comp offs for nights: {nights}.\nRunning totals for fairness are included.")

    def clear_carry_over(self):
        # Drop the carry-over block.
        self.carry_over = {}
        self._update_carry_label()

    def import_previous(self):
        # Import last month's roster file to seed carry-over.
        path = filedialog.askopenfilename(parent=self, initialdir=self.last_dir, title="Previous month's roster", filetypes=[("Roster file", "*.json")])
        if not path:
            return
        try:
            prev = storage.load_roster_file(path)
        except (OSError, ValueError, KeyError) as exc:
            messagebox.showerror("Import failed", f"{exc}\n\nPick a roster saved with 'Save roster'.", parent=self)
            return
        # Offer to advance the roster month to the month after the imported one.
        pcfg = prev.roster.config
        ny, nm = storage.next_month(pcfg.year, pcfg.month)
        cur = self.roster_month_start()
        if (cur.year, cur.month) != (ny, nm):
            if messagebox.askyesno(
                "Roster month",
                f"That roster is for {calendar.month_name[pcfg.month]} {pcfg.year}.\n"
                f"Set this roster's month to {calendar.month_name[nm]} {ny}?",
                parent=self,
            ):
                self.year_var.set(str(ny))
                self.month_var.set(calendar.month_name[nm])
        # If the team is empty, offer to copy team/rules from the imported file.
        if not self.team.rows and messagebox.askyesno(
            "Copy team", "Your team list is empty. Copy the team, weekend days, rules and shift timings from that roster?", parent=self
        ):
            src = prev.inputs
            self.team.set_rows(src.get("engineers", []))
            keep = self.collect_dict()
            for key in ("weekend_days", "min_coverage", "shift_times", "attempts"):
                if key in src:
                    keep[key] = src[key]
            self.load_dict(keep)
        # Build and store the carry-over block, then jump to the Rules page.
        self.carry_over = storage.carry_over_from(prev.roster)
        self._update_carry_label()
        self._remember_dir(path)
        self.show_page(6)
        self.status.set(f"Imported carry-over from {self.carry_over['source']}")

    # -- roster ----------------------------------------------------------------
    def _current_locks(self, cfg: RosterConfig) -> Locks:
        # The current roster's locks, but only if it is for the same month.
        r = self.roster
        if r and (r.config.year, r.config.month) == (cfg.year, cfg.month):
            return r.locks
        return Locks()

    def generate(self):
        # Validate inputs, warn about understaffed days, then build the roster.
        try:
            cfg = RosterConfig.from_dict(self.collect_dict())
        except ValueError as exc:
            messagebox.showerror("Please fix the inputs", str(exc), parent=self)
            return
        if not cfg.engineers:
            messagebox.showinfo("No team", "Add at least one engineer on the Team page first.", parent=self)
            return
        locks = self._current_locks(cfg)
        # Run the capacity pre-check; if it flags days, confirm before continuing.
        problems = precheck(cfg, locks)
        if problems:
            lines = "\n".join(f"• {i.day:%a %d %b}: {i.message}" for i in problems[:8])
            more = f"\n…and {len(problems) - 8} more" if len(problems) > 8 else ""
            if not messagebox.askyesno(
                "Not enough people on some days",
                f"The team can't meet the rules on these days:\n\n{lines}{more}\n\n"
                "Adjust leave or the minimums on the Rules page, or generate anyway and fix by hand.\n\nGenerate anyway?",
                icon="warning", parent=self,
            ):
                return
        # Show a busy cursor while generating.
        self.status.set("Generating…")
        self.config(cursor="watch")
        self.update_idletasks()
        try:
            # Use the published roster as a baseline only if it is this month.
            baseline = self.published if self.published and (self.published.config.year, self.published.config.month) == (cfg.year, cfg.month) else None
            roster, issues = generate(cfg, locks, baseline)
        except ValueError as exc:
            messagebox.showerror("Cannot generate", str(exc), parent=self)
            return
        finally:
            self.config(cursor="")
        # Drop a published snapshot from a different month.
        if self.published and (self.published.config.year, self.published.config.month) != (cfg.year, cfg.month):
            self.published, self.published_at = None, ""
        # Store and show the new roster.
        self.roster, self.issues = roster, issues
        self._show_roster()
        self.show_page(self.roster_page)
        # A status message summarising what was kept / changed.
        n = len(locks.cells) + len(locks.primary) + len(locks.secondary)
        notes = []
        if n:
            notes.append(f"kept {n} locked cell(s)")
        if baseline:
            notes.append(f"{len(self._changes())} change(s) from the published roster")
        if notes:
            self.status.set("Roster regenerated - " + ", ".join(notes))

    def apply_roster(self, roster: Roster, message: str = ""):
        # Replace the current roster (e.g. after a swap) and re-validate.
        self.roster = roster
        self.revalidate()
        if message:
            self.status.set(message)

    def revalidate(self):
        # Re-run the rule checks and refresh the display.
        if self.roster:
            self.issues = validate(self.roster)
            self._show_roster()

    def _on_grid_edit(self, action, target, d, value):
        # Handle an edit from the grid's context menu.
        r = self.roster
        kind, name = target
        if action == "swap":
            # Open the swap dialog pre-filled with the two engineers and day.
            self.open_swap(name, value, d)
            return
        if kind == "eng":
            if action == "set":
                # Change the cell and lock it (hand edits are kept on regenerate).
                r.grid[name][d] = value
                r.locks.cells[(name, d)] = value  # hand edits are kept on regenerate
            elif action == "lock":
                r.locks.cells[(name, d)] = r.code(name, d)
            elif action == "unlock":
                r.locks.cells.pop((name, d), None)
        else:
            # An on-call cell.
            table = r.primary if kind == "primary" else r.secondary
            locks = r.locks.primary if kind == "primary" else r.locks.secondary
            if action == "set":
                if value:
                    table[d] = value
                else:
                    table.pop(d, None)
                locks[d] = value
            elif action == "lock":
                locks[d] = table.get(d, "")
            elif action == "unlock":
                locks.pop(d, None)
        # Re-check after any edit.
        self.revalidate()

    def open_swap(self, a="", b="", d=None):
        # Open the swap dialog if a roster exists.
        if self._require_roster():
            SwapDialog(self, a, b, d)

    def clear_locks(self):
        # Remove all locks after confirmation.
        if not self._require_roster():
            return
        n = len(self.roster.locks.cells) + len(self.roster.locks.primary) + len(self.roster.locks.secondary)
        if n and messagebox.askyesno("Clear locks", f"Unlock all {n} locked cell(s)? The roster itself is not changed.", parent=self):
            self.roster.locks = Locks()
            self._show_roster()

    def mark_published(self):
        # Snapshot the current roster as "published" to start change tracking.
        if not self._require_roster():
            return
        self.published = self.roster.copy()
        self.published_at = datetime.now().strftime("%d %b %Y %H:%M")
        self._show_roster()
        self.status.set("Marked as published - later changes will be highlighted")

    def _changes(self):
        # The list of changes since publishing (empty if not published).
        if not (self.roster and self.published):
            return []
        return storage.diff(self.published, self.roster)

    def copy_changes(self):
        # Copy the change list to the clipboard as text.
        changes = self._changes()
        if not changes:
            messagebox.showinfo("Changes", "No changes since the roster was published.", parent=self)
            return
        text = "Roster changes since " + (self.published_at or "publishing") + ":\n" + "\n".join(f"- {c}" for c in changes)
        self.clipboard_clear()
        self.clipboard_append(text)
        self.status.set(f"Copied {len(changes)} change(s) to the clipboard")

    def _show_roster(self):
        # Update the grid, the Checks/Changes tables and the summary tiles.
        errors = count(self.issues, ERROR)
        warnings = count(self.issues, WARNING)
        changes = self._changes()
        # Redraw the grid with error days and changed cells.
        self.grid_view.show(
            self.roster,
            {i.day for i in self.issues if i.severity == ERROR and i.day},
            {(c.who, c.day): c.old for c in changes},
        )
        # Fill the Checks table.
        self.issue_tree.delete(*self.issue_tree.get_children())
        if errors == 0:
            self.issue_tree.insert("", "end", values=("✓ OK", "", "All mandatory rules are satisfied"), tags=("ok",))
        icons = {ERROR: "✗ Error", WARNING: "! Warning", INFO: "i Info"}
        for i in self.issues:
            self.issue_tree.insert("", "end", values=(icons[i.severity], i.day.strftime("%a %d %b") if i.day else "", i.message), tags=(i.severity,))

        # Fill the Changes table.
        self.change_tree.delete(*self.change_tree.get_children())
        for c in changes:
            self.change_tree.insert("", "end", values=(f"{c.day:%a %d %b}", c.who, c.old or "-", c.new or "-"), tags=("chg",))
        # Update the "published" status line and the Changes tab label.
        if self.published:
            self.published_var.set(f"Published {self.published_at}. {len(changes)} change(s) since then." if changes else f"Published {self.published_at}. No changes since then.")
        else:
            self.published_var.set("Not published yet. Click 'Mark as published' when you share the roster to start tracking changes.")
        self.bottom_nb.tab(1, text=f"  Changes since published ({len(changes)})  " if changes else "  Changes since published  ")

        # Status tile: rules met vs needs fixing.
        if errors == 0:
            self.tiles["Status"].set("✓ Rules met", "Ready to share", fg=T.SUCCESS, bg=T.SUCCESS_LIGHT)
        else:
            self.tiles["Status"].set("✗ Fix rules", "See checks below", fg=T.DANGER, bg=T.DANGER_LIGHT)
        # Violations and warnings tiles.
        self.tiles["Rule violations"].set(str(errors), "mandatory rules", fg=T.DANGER if errors else T.TEXT)
        self.tiles["Warnings"].set(str(warnings), "requests not met", fg="#B45309" if warnings else T.TEXT)
        # Nights-per-person tile (range, plus average or carry-over range).
        cfg = self.roster.config
        nights = [self.roster.counts(n)["N"] for n in cfg.engineer_names]
        sub = f"average {statistics.mean(nights):.1f}"
        if cfg.prior_counts:
            totals = [self.roster.total_counts(n)["N"] for n in cfg.engineer_names]
            sub = f"incl. previous months: {min(totals)}–{max(totals)}"
        self.tiles["Nights / person"].set(f"{min(nights)}–{max(nights)}", sub)
        # Preferences-met tile.
        met, requested = preference_stats(self.roster)
        self.tiles["Preferences met"].set(f"{met}/{requested}" if requested else "—", "preferred shifts given" if requested else "no preferences set")
        # Changes / locks tile.
        locks = self.roster.locks
        n_locks = len(locks.cells) + len(locks.primary) + len(locks.secondary)
        if self.published:
            self.tiles["Changes"].set(
                str(len(changes)), f"since published · {n_locks} locked", fg=CHANGED_COLOR if changes else T.TEXT
            )
        else:
            self.tiles["Changes"].set("—", f"not published · {n_locks} locked")
        self.status.set("Roster ready - hover over a cell for details, click to edit, lock or swap")

    def _remember_dir(self, path):
        # Remember the folder a file was in, so dialogs reopen there.
        self.last_dir = os.path.dirname(os.path.abspath(path))

    def _require_roster(self):
        # Guard: many actions need a roster to exist first.
        if not self.roster:
            messagebox.showinfo("No roster", "Generate a roster first", parent=self)
            return False
        return True

    def _default_name(self, ext):
        # A default export filename like "roster_2026_10.xlsx".
        cfg = self.roster.config
        return f"roster_{cfg.year}_{cfg.month:02d}.{ext}"

    def export_excel(self):
        # Save the roster as an Excel file.
        if not self._require_roster():
            return
        path = filedialog.asksaveasfilename(parent=self, initialdir=self.last_dir, defaultextension=".xlsx", initialfile=self._default_name("xlsx"), filetypes=[("Excel", "*.xlsx")])
        if path:
            try:
                export.to_excel(self.roster, path, self.issues)
                self._remember_dir(path)
                self.status.set(f"Exported {path}")
            except Exception as exc:
                # Catch everything (e.g. openpyxl errors) so a failed export
                # always tells the user why instead of silently doing nothing.
                messagebox.showerror("Excel export failed", f"{exc}", parent=self)

    def export_csv(self):
        # Save the roster as a CSV file.
        if not self._require_roster():
            return
        path = filedialog.asksaveasfilename(parent=self, initialdir=self.last_dir, defaultextension=".csv", initialfile=self._default_name("csv"), filetypes=[("CSV", "*.csv")])
        if path:
            try:
                export.to_csv(self.roster, path)
                self._remember_dir(path)
                self.status.set(f"Exported {path}")
            except Exception as exc:
                messagebox.showerror("CSV export failed", f"{exc}", parent=self)

    def export_ics(self):
        # Save one .ics calendar per engineer plus a team calendar into a folder.
        if not self._require_roster():
            return
        # Use the timings currently on the Rules page.
        try:
            times = {sh: (parse_time(a.get()), parse_time(b.get())) for sh, (a, b) in self.time_vars.items()}
        except ValueError as exc:
            messagebox.showerror("Shift timings", f"{exc}\n\nFix the shift timings on the Rules page.", parent=self)
            return
        folder = filedialog.askdirectory(parent=self, initialdir=self.last_dir, title="Folder for the calendar files")
        if not folder:
            return
        # Apply the timings and write the files.
        self.roster.config.shift_times.update(times)
        try:
            paths = ics.export_all(self.roster, folder)
        except Exception as exc:
            messagebox.showerror("Calendar export failed", f"{exc}", parent=self)
            return
        self.last_dir = folder
        messagebox.showinfo(
            "Calendar invites created",
            f"Created {len(paths)} calendar files in:\n{folder}\n\n"
            "Send each engineer their own file. Opening it (or importing it in Outlook / Google Calendar) "
            "adds their shifts, on-call days, comp offs and leave. 'Team - roster ….ics' has everyone.",
            parent=self,
        )
        self.status.set(f"Exported {len(paths)} calendar files to {folder}")


def main():
    # Create the window and enter Tkinter's event loop.
    RosterApp().mainloop()


# When run directly, start the GUI.
if __name__ == "__main__":
    main()
