"""Tkinter GUI for the roster tool."""

from __future__ import annotations

import calendar
import json
import os
import statistics
import sys
import tkinter as tk
from datetime import date
from tkinter import filedialog, messagebox, ttk

from . import export
from . import theme as T
from .model import (
    ALL_CODES,
    CODE_DESCRIPTIONS,
    DAY_TYPES,
    SHIFT_NAMES,
    SHIFTS,
    WEEKDAY_NAMES,
    Roster,
    RosterConfig,
    empty_config_dict,
)
from .scheduler import generate
from .validator import ERROR, INFO, WARNING, count, validate

# Bundled files live next to the package when run from source, or in the
# PyInstaller extraction folder (sys._MEIPASS) when run as a packaged app.
BASE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SAMPLE_CONFIG = os.path.join(BASE_DIR, "examples", "sample_config.json")
ICON_PNG = os.path.join(BASE_DIR, "assets", "icon.png")
DATE_HINT = "Dates: YYYY-MM-DD, DD/MM/YYYY or just the day number of the roster month."
LEGEND_NAMES = {"M": "Morning", "E": "Evening", "N": "Night", "CO": "Comp off", "L": "Leave", "LL": "Long leave", "WO": "Weekend", "H": "Holiday"}
DESIGNATIONS = ("Engineer", "Senior Engineer", "Lead Engineer", "SME", "Manager")


def card(parent, title=None, subtitle=None, padding=16):
    """A white, bordered panel. Returns (outer, body)."""
    outer = ttk.Frame(parent, style="Card.TFrame", padding=padding)
    if title:
        ttk.Label(outer, text=title, style="CardTitle.TLabel").pack(anchor="w")
    if subtitle:
        ttk.Label(outer, text=subtitle, style="Hint.TLabel", justify="left").pack(anchor="w", pady=(2, 0))
    body = ttk.Frame(outer, style="Surface.TFrame")
    body.pack(fill="both", expand=True, pady=(12 if title or subtitle else 0, 0))
    return outer, body


def page(parent, title, subtitle):
    frame = ttk.Frame(parent, padding=(24, 20, 24, 16))
    ttk.Label(frame, text=title, style="PageTitle.TLabel").pack(anchor="w")
    ttk.Label(frame, text=subtitle, style="PageSub.TLabel").pack(anchor="w", pady=(2, 16))
    return frame


class RecordEditor(ttk.Frame):
    """A form card + table card for editing a list of records.

    ``fields`` is a list of (key, label, kind, extra) where kind is one of
    "entry", "combo" (editable), "choice" (read-only combo) or "check".
    For combos, ``extra`` is a list of values or a callable returning one.
    """

    def __init__(self, master, title, fields, on_change=None, hint="", noun="entry", columns=2):
        super().__init__(master)
        self.fields = fields
        self.on_change = on_change
        self.noun = noun
        self.rows: list[dict] = []
        self.vars: dict[str, tk.Variable] = {}
        self.widgets: dict[str, ttk.Widget] = {}

        form_card, form = card(self, title, hint)
        form_card.pack(fill="x")
        for i, (key, label, kind, extra) in enumerate(fields):
            cell = ttk.Frame(form, style="Surface.TFrame")
            cell.grid(row=i // columns, column=i % columns, sticky="ew", padx=(0, 20), pady=4)
            if kind == "check":
                var = tk.BooleanVar(value=False)
                w = ttk.Checkbutton(cell, text=label, variable=var)
                ttk.Label(cell, text=" ", style="Card.TLabel").pack(anchor="w")
                w.pack(anchor="w", pady=(2, 0))
            else:
                ttk.Label(cell, text=label, style="Card.TLabel", foreground=T.MUTED, font=T.Fonts.get(9, "bold")).pack(anchor="w")
                var = tk.StringVar()
                if kind in ("combo", "choice"):
                    w = ttk.Combobox(cell, textvariable=var, state="readonly" if kind == "choice" else "normal", width=20)
                else:
                    w = ttk.Entry(cell, textvariable=var, width=22)
                w.pack(anchor="w", fill="x", pady=(3, 0))
            self.vars[key] = var
            self.widgets[key] = w
        for c in range(columns):
            form.columnconfigure(c, weight=1)

        btns = ttk.Frame(form, style="Surface.TFrame")
        btns.grid(row=(len(fields) + columns - 1) // columns, column=0, columnspan=columns, sticky="w", pady=(12, 0))
        ttk.Button(btns, text="＋  Add", style="Accent.TButton", command=self.add).pack(side="left")
        ttk.Button(btns, text="Update", command=self.update_selected).pack(side="left", padx=(8, 0))
        ttk.Button(btns, text="Delete", style="Danger.TButton", command=self.delete_selected).pack(side="left", padx=(8, 0))
        ttk.Button(btns, text="Clear", command=self.clear_form).pack(side="left", padx=(8, 0))

        table_card = ttk.Frame(self, style="Card.TFrame", padding=1)
        table_card.pack(fill="both", expand=True, pady=(14, 0))
        head = ttk.Frame(table_card, style="Surface.TFrame", padding=(14, 10))
        head.pack(fill="x")
        self.count_var = tk.StringVar()
        ttk.Label(head, textvariable=self.count_var, style="Card.TLabel", font=T.Fonts.get(10, "bold")).pack(side="left")
        ttk.Label(head, text="Select a row to edit it", style="Hint.TLabel").pack(side="right")

        table = ttk.Frame(table_card, style="Surface.TFrame")
        table.pack(fill="both", expand=True)
        cols = [f[0] for f in fields]
        self.tree = ttk.Treeview(table, columns=cols, show="headings", selectmode="extended", height=8)
        for key, label, _kind, _extra in fields:
            self.tree.heading(key, text=label.upper(), anchor="w")
            self.tree.column(key, width=150, anchor="w")
        self.tree.tag_configure("odd", background=T.STRIPE)
        sb = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.empty = tk.Label(table, text=f"No {noun}s yet - fill in the form above and press Add.", bg=T.SURFACE, fg=T.MUTED, font=T.Fonts.get(10))
        self.refresh_options()
        self._redraw()

    # -- form helpers --------------------------------------------------------
    def refresh_options(self):
        for key, _label, kind, extra in self.fields:
            if kind in ("combo", "choice") and extra is not None:
                self.widgets[key]["values"] = list(extra() if callable(extra) else extra)

    def _form_values(self) -> dict | None:
        row = {}
        for key, _label, kind, _extra in self.fields:
            value = self.vars[key].get()
            row[key] = value if kind == "check" else str(value).strip()
        first_key, first_label = self.fields[0][0], self.fields[0][1]
        if not row[first_key]:
            messagebox.showwarning("Missing value", f"'{first_label}' is required", parent=self)
            return None
        return row

    def clear_form(self):
        for key, _label, kind, _extra in self.fields:
            self.vars[key].set(False if kind == "check" else "")
        self.tree.selection_remove(*self.tree.selection())

    def _display(self, row):
        out = []
        for key, _label, kind, _extra in self.fields:
            v = row.get(key, "")
            out.append(("✓ Yes" if v else "—") if kind == "check" else v)
        return out

    def _redraw(self):
        self.tree.delete(*self.tree.get_children())
        for i, row in enumerate(self.rows):
            self.tree.insert("", "end", iid=str(i), values=self._display(row), tags=("odd",) if i % 2 else ())
        n = len(self.rows)
        self.count_var.set(f"{n} {self.noun}{'' if n == 1 else 's'}")
        if n:
            self.empty.place_forget()
        else:
            self.empty.place(relx=0.5, rely=0.55, anchor="center")

    def _changed(self):
        self._redraw()
        if self.on_change:
            self.on_change()

    # -- actions -------------------------------------------------------------
    def add(self):
        row = self._form_values()
        if row is not None:
            self.rows.append(row)
            self._changed()
            self.clear_form()

    def update_selected(self):
        sel = self.tree.selection()
        if len(sel) != 1:
            messagebox.showinfo("Update", "Select exactly one row to update", parent=self)
            return
        row = self._form_values()
        if row is not None:
            self.rows[int(sel[0])] = row
            self._changed()

    def delete_selected(self):
        idx = sorted((int(i) for i in self.tree.selection()), reverse=True)
        for i in idx:
            del self.rows[i]
        if idx:
            self._changed()

    def _on_select(self, _event=None):
        sel = self.tree.selection()
        if len(sel) == 1:
            row = self.rows[int(sel[0])]
            for key, _label, kind, _extra in self.fields:
                self.vars[key].set(bool(row.get(key)) if kind == "check" else row.get(key, ""))

    def get_rows(self) -> list[dict]:
        return [dict(r) for r in self.rows]

    def set_rows(self, rows):
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

    NAME_W = 190
    CELL_W = 44
    CELL_H = 30
    HEAD_H = 48
    GAP = 2
    SUMMARY = ("M", "E", "N", "CO", "L", "LL", "Primary", "Secondary")
    SUMMARY_LABELS = {"Primary": "PRI", "Secondary": "SEC"}
    SUMMARY_W = 42

    def __init__(self, master, on_edit, on_hover):
        super().__init__(master, style="Surface.TFrame")
        self.on_edit = on_edit
        self.on_hover = on_hover
        self.roster: Roster | None = None
        self.error_days: set[date] = set()
        self.canvas = tk.Canvas(self, background=T.SURFACE, highlightthickness=0)
        xs = ttk.Scrollbar(self, orient="horizontal", command=self.canvas.xview)
        ys = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=xs.set, yscrollcommand=ys.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        ys.grid(row=0, column=1, sticky="ns")
        xs.grid(row=1, column=0, sticky="ew")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.canvas.bind("<Button-1>", self._click)
        self.canvas.bind("<Motion>", self._motion)
        self.canvas.bind("<Leave>", lambda _e: (self.canvas.delete("hover"), self.on_hover("")))
        self._empty_state()

    def _empty_state(self):
        c = self.canvas
        c.create_text(32, 40, anchor="nw", text="No roster yet", font=T.Fonts.get(14, "bold"), fill=T.TEXT)
        c.create_text(
            32, 70, anchor="nw", fill=T.MUTED, font=T.Fonts.get(10),
            text="Fill in the team and requests using the steps on the left,\nthen press  “Generate roster”.",
        )

    def show(self, roster: Roster, error_days: set[date]):
        self.roster = roster
        self.error_days = error_days
        self.draw()

    def _rows(self):
        cfg = self.roster.config
        return [("eng", e.name) for e in cfg.engineers] + [("primary", None), ("secondary", None)]

    def _row_y(self, ri):
        # A small gap separates engineers from the on-call rows.
        n_eng = len(self.roster.config.engineers)
        return self.HEAD_H + ri * self.CELL_H + (10 if ri >= n_eng else 0)

    def _cell_at(self, event):
        if not self.roster:
            return None
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)
        if x < self.NAME_W or y < self.HEAD_H:
            return None
        col = int((x - self.NAME_W) // self.CELL_W)
        rows = self._rows()
        days = self.roster.days
        for ri in range(len(rows)):
            y0 = self._row_y(ri)
            if y0 <= y < y0 + self.CELL_H and 0 <= col < len(days):
                return ri, col
        return None

    def _pill(self, x0, y0, x1, y1, fill, r=6):
        """Rounded rectangle."""
        c = self.canvas
        pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1, x1 - r, y1, x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
        return c.create_polygon(pts, smooth=True, fill=fill, outline="")

    def draw(self):
        c = self.canvas
        c.delete("all")
        r = self.roster
        cfg = r.config
        days = r.days
        rows = self._rows()
        x0 = self.NAME_W
        g = self.GAP
        f = T.Fonts.get
        n_eng = len(cfg.engineers)
        sx = x0 + len(days) * self.CELL_W
        bottom = self._row_y(len(rows) - 1) + self.CELL_H

        # Column shading for weekends / holidays / freeze days.
        for i, d in enumerate(days):
            dtype = cfg.day_type(d)
            if dtype != "Working":
                x = x0 + i * self.CELL_W
                c.create_rectangle(x, 0, x + self.CELL_W, bottom, fill="#" + export.DAYTYPE_COLORS[dtype], outline="")

        # Header
        c.create_text(12, self.HEAD_H / 2 - 7, anchor="w", text=calendar.month_name[cfg.month], font=f(13, "bold"), fill=T.TEXT)
        c.create_text(12, self.HEAD_H / 2 + 11, anchor="w", text=f"{cfg.year}  ·  {n_eng} engineers", font=f(9), fill=T.MUTED)
        for i, d in enumerate(days):
            x = x0 + i * self.CELL_W
            dtype = cfg.day_type(d)
            color = {"Holiday": "#6D28D9", "Freeze": "#C2410C"}.get(dtype, T.MUTED if dtype == "Weekend" else T.TEXT)
            c.create_text(x + self.CELL_W / 2, 15, text=WEEKDAY_NAMES[d.weekday()][:2].upper(), font=f(8, "bold"), fill=T.MUTED if dtype == "Working" else color)
            c.create_text(x + self.CELL_W / 2, 32, text=str(d.day), font=f(11, "bold"), fill=color)
            if d in self.error_days:
                c.create_oval(x + self.CELL_W / 2 - 3, self.HEAD_H - 7, x + self.CELL_W / 2 + 3, self.HEAD_H - 1, fill=T.DANGER, outline="")
        for j, key in enumerate(self.SUMMARY):
            x = sx + 8 + j * self.SUMMARY_W
            c.create_text(x + self.SUMMARY_W / 2, self.HEAD_H / 2, text=self.SUMMARY_LABELS.get(key, key), font=f(8, "bold"), fill=T.MUTED)
        c.create_line(0, self.HEAD_H - 0.5, sx + 8 + len(self.SUMMARY) * self.SUMMARY_W, self.HEAD_H - 0.5, fill=T.BORDER)

        for ri, (kind, name) in enumerate(rows):
            y = self._row_y(ri)
            cy = y + self.CELL_H / 2
            if kind == "eng":
                eng = cfg.engineer(name)
                tid = c.create_text(12, cy, anchor="w", text=name, font=f(10, "bold"), fill=T.TEXT)
                bx = c.bbox(tid)[2] + 8
                if eng.is_sme:
                    self._pill(bx, cy - 8, bx + 34, cy + 8, T.PRIMARY_LIGHT, r=8)
                    c.create_text(bx + 17, cy, text="SME", font=f(7, "bold"), fill=T.PRIMARY)
                    bx += 40
                if eng.designation:
                    c.create_text(bx, cy, anchor="w", text=eng.designation[:18], font=f(8), fill=T.MUTED)
                if ri < n_eng - 1:
                    c.create_line(0, y + self.CELL_H, x0, y + self.CELL_H, fill=T.GRID_LINE)
            else:
                label = "Primary on-call" if kind == "primary" else "Secondary on-call"
                c.create_text(12, cy, anchor="w", text=label, font=f(10, "bold"), fill=T.PRIMARY_DARK)

            for i, d in enumerate(days):
                x = x0 + i * self.CELL_W
                if kind == "eng":
                    code = r.code(name, d)
                    fill = "#" + export.CODE_COLORS.get(code, "FFFFFF")
                    fg = "#" + export.CODE_TEXT_COLORS.get(code, "111827")
                    self._pill(x + g, y + g, x + self.CELL_W - g, y + self.CELL_H - g, fill, r=5)
                    c.create_text(x + self.CELL_W / 2, cy, text=code, fill=fg, font=f(9, "bold"))
                    # Small dots mark on-call duty (primary = indigo, secondary = teal).
                    if r.primary.get(d) == name:
                        c.create_oval(x + self.CELL_W - 10, y + 5, x + self.CELL_W - 5, y + 10, fill=T.PRIMARY, outline="white")
                    if r.secondary.get(d) == name:
                        c.create_oval(x + self.CELL_W - 10, y + self.CELL_H - 10, x + self.CELL_W - 5, y + self.CELL_H - 5, fill="#0D9488", outline="white")
                else:
                    who = (r.primary if kind == "primary" else r.secondary).get(d, "")
                    if who:
                        self._pill(x + g, y + g, x + self.CELL_W - g, y + self.CELL_H - g, T.PRIMARY_LIGHT if kind == "primary" else "#CCFBF1", r=5)
                        c.create_text(x + self.CELL_W / 2, cy, text=who[:5], fill=T.PRIMARY_DARK if kind == "primary" else "#115E59", font=f(8, "bold"))
                    else:
                        c.create_text(x + self.CELL_W / 2, cy, text="·", fill="#D1D5DB", font=f(10))
            if kind == "eng":
                counts = r.counts(name)
                for j, key in enumerate(self.SUMMARY):
                    x = sx + 8 + j * self.SUMMARY_W
                    v = counts[key]
                    c.create_text(x + self.SUMMARY_W / 2, cy, text=str(v), font=f(9, "bold" if v else "normal"), fill=T.TEXT if v else "#D1D5DB")

        total_w = sx + 8 + len(self.SUMMARY) * self.SUMMARY_W
        c.configure(scrollregion=(0, 0, total_w + 8, bottom + 12), height=min(bottom + 12, 560))

    def _motion(self, event):
        c = self.canvas
        c.delete("hover")
        hit = self._cell_at(event)
        if not hit:
            self.on_hover("")
            return
        ri, col = hit
        kind, name = self._rows()[ri]
        d = self.roster.days[col]
        x = self.NAME_W + col * self.CELL_W
        y = self._row_y(ri)
        c.create_rectangle(x + 1, y + 1, x + self.CELL_W - 1, y + self.CELL_H - 1, outline=T.PRIMARY, width=2, tags="hover")
        c.configure(cursor="hand2")

        r = self.roster
        cfg = r.config
        head = f"{d:%A %d %b} · {cfg.day_type(d)}{' (' + cfg.holiday_name(d) + ')' if cfg.holiday_name(d) else ''}"
        if kind == "eng":
            desc = f"{name}: {CODE_DESCRIPTIONS.get(r.code(name, d), r.code(name, d))}"
        else:
            desc = f"{'Primary' if kind == 'primary' else 'Secondary'} on-call: {(r.primary if kind == 'primary' else r.secondary).get(d, '') or '(none)'}"
        m = ", ".join(r.on_shift(d, "M")) or "-"
        n = ", ".join(r.on_shift(d, "N")) or "-"
        self.on_hover(f"{head}   |   {desc}   |   Morning: {m}   |   Night: {n}")

    def _click(self, event):
        hit = self._cell_at(event)
        if not hit:
            return
        ri, col = hit
        kind, name = self._rows()[ri]
        d = self.roster.days[col]
        cfg = self.roster.config
        menu = tk.Menu(self, tearoff=0, font=T.Fonts.get(10), bg=T.SURFACE, activebackground=T.PRIMARY_LIGHT, activeforeground=T.PRIMARY_DARK, bd=0)
        if kind == "eng":
            for code in ALL_CODES:
                menu.add_command(label=f"{code:<3}  {CODE_DESCRIPTIONS[code]}", command=lambda code=code: self.on_edit("code", name, d, code))
        else:
            want_sme = kind == "secondary"
            menu.add_command(label="(none)", command=lambda: self.on_edit(kind, None, d, ""))
            for e in cfg.engineers:
                if e.is_sme == want_sme:
                    menu.add_command(label=e.name, command=lambda n=e.name: self.on_edit(kind, None, d, n))
        menu.tk_popup(event.x_root, event.y_root)


class StatTile(tk.Frame):
    """A small summary tile: caption above a big value."""

    def __init__(self, master, caption):
        super().__init__(master, bg=T.SURFACE, highlightbackground=T.BORDER, highlightthickness=1, padx=16, pady=10)
        self.caption = tk.Label(self, text=caption.upper(), bg=T.SURFACE, fg=T.MUTED, font=T.Fonts.get(8, "bold"))
        self.caption.pack(anchor="w")
        self.value = tk.Label(self, text="—", bg=T.SURFACE, fg=T.TEXT, font=T.Fonts.get(16, "bold"))
        self.value.pack(anchor="w")
        self.sub = tk.Label(self, text="", bg=T.SURFACE, fg=T.MUTED, font=T.Fonts.get(8))
        self.sub.pack(anchor="w")

    def set(self, value, sub="", fg=T.TEXT, bg=T.SURFACE):
        for w in (self, self.caption, self.value, self.sub):
            w.configure(bg=bg)
        self.value.configure(text=value, fg=fg)
        self.sub.configure(text=sub)


class Sidebar(tk.Frame):
    """Vertical step navigation replacing notebook tabs."""

    def __init__(self, master, on_select):
        super().__init__(master, bg=T.SIDEBAR_BG, width=230, highlightbackground=T.BORDER, highlightthickness=1)
        self.pack_propagate(False)
        self.on_select = on_select
        self.items = []
        self.selected = 0
        tk.Label(self, text="STEPS", bg=T.SIDEBAR_BG, fg=T.MUTED, font=T.Fonts.get(8, "bold"), anchor="w").pack(fill="x", padx=20, pady=(18, 6))

    def add(self, number, title):
        idx = len(self.items)
        row = tk.Frame(self, bg=T.SIDEBAR_BG, cursor="hand2")
        row.pack(fill="x", padx=10, pady=1)
        bar = tk.Frame(row, bg=T.SIDEBAR_BG, width=4)
        bar.pack(side="left", fill="y")
        num = tk.Label(row, text=str(number), width=2, bg="#F3F4F6", fg=T.MUTED, font=T.Fonts.get(9, "bold"))
        num.pack(side="left", padx=(10, 10), pady=9)
        text = tk.Label(row, text=title, bg=T.SIDEBAR_BG, fg=T.TEXT, font=T.Fonts.get(10), anchor="w")
        text.pack(side="left", fill="x", expand=True)
        badge = tk.Label(row, text="", bg=T.SIDEBAR_BG, fg=T.MUTED, font=T.Fonts.get(9))
        badge.pack(side="right", padx=(0, 10))
        item = {"row": row, "bar": bar, "num": num, "text": text, "badge": badge}
        self.items.append(item)
        for w in (row, num, text, badge, bar):
            w.bind("<Button-1>", lambda _e, i=idx: self.on_select(i))
            w.bind("<Enter>", lambda _e, i=idx: self._hover(i, True))
            w.bind("<Leave>", lambda _e, i=idx: self._hover(i, False))
        self._paint(idx)

    def set_badge(self, idx, text):
        self.items[idx]["badge"].configure(text=text)

    def select(self, idx):
        old, self.selected = self.selected, idx
        self._paint(old)
        self._paint(idx)

    def _hover(self, idx, on):
        if idx != self.selected:
            self._paint(idx, T.SIDEBAR_HOVER if on else None)

    def _paint(self, idx, bg=None):
        it = self.items[idx]
        sel = idx == self.selected
        bg = bg or (T.PRIMARY_LIGHT if sel else T.SIDEBAR_BG)
        for k in ("row", "text", "badge"):
            it[k].configure(bg=bg)
        it["bar"].configure(bg=T.PRIMARY if sel else bg)
        it["text"].configure(fg=T.PRIMARY_DARK if sel else T.TEXT, font=T.Fonts.get(10, "bold" if sel else "normal"))
        it["num"].configure(bg=T.PRIMARY if sel else "#F3F4F6", fg="white" if sel else T.MUTED)


class RosterApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Roster Creator")
        self.geometry("1360x840")
        self.minsize(1000, 640)
        T.apply_theme(self)
        try:
            self._icon = tk.PhotoImage(file=ICON_PNG)
            self.iconphoto(True, self._icon)
        except tk.TclError:
            pass
        self.last_dir = os.path.expanduser("~")
        self.roster: Roster | None = None
        self.issues = []
        self.config_path: str | None = None

        self._build_menu()
        self._build_header()
        body = ttk.Frame(self)
        body.pack(fill="both", expand=True)
        self.sidebar = Sidebar(body, self.show_page)
        self.sidebar.pack(side="left", fill="y")
        self.nb = ttk.Notebook(body, style="Pages.TNotebook")
        self.nb.pack(side="left", fill="both", expand=True)

        self.status = tk.StringVar(value="Ready")
        ttk.Label(self, textvariable=self.status, style="Status.TLabel", anchor="w").pack(fill="x", side="bottom", before=body)

        self._build_team_tab()
        self._build_calendar_tab()
        self._build_leave_tabs()
        self._build_requirements_tab()
        self._build_oncall_tab()
        self._build_rules_tab()
        self._build_roster_tab()
        self.show_page(0)
        self.load_dict(empty_config_dict())

    # -- layout --------------------------------------------------------------
    def _build_menu(self):
        menubar = tk.Menu(self)
        fm = tk.Menu(menubar, tearoff=0)
        fm.add_command(label="New", command=self.new_config)
        fm.add_command(label="Open inputs…", command=self.open_config)
        fm.add_command(label="Save inputs", command=self.save_config)
        fm.add_command(label="Save inputs as…", command=lambda: self.save_config(ask=True))
        fm.add_command(label="Load sample data", command=self.load_sample)
        fm.add_separator()
        fm.add_command(label="Export roster to Excel…", command=self.export_excel)
        fm.add_command(label="Export roster to CSV…", command=self.export_csv)
        fm.add_separator()
        fm.add_command(label="Exit", command=self.destroy)
        menubar.add_cascade(label="File", menu=fm)
        self.config(menu=menubar)

    def _build_header(self):
        bar = tk.Frame(self, bg=T.HEADER_BG, height=64)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        logo = tk.Canvas(bar, width=36, height=36, bg=T.HEADER_BG, highlightthickness=0)
        logo.pack(side="left", padx=(20, 12))
        # A tiny calendar icon.
        logo.create_rectangle(4, 7, 32, 32, fill=T.PRIMARY, outline="")
        logo.create_rectangle(4, 7, 32, 14, fill="#818CF8", outline="")
        for cx in (10, 18, 26):
            for cy in (19, 26):
                logo.create_rectangle(cx - 2, cy - 2, cx + 2, cy + 2, fill="white", outline="")
        titles = tk.Frame(bar, bg=T.HEADER_BG)
        titles.pack(side="left")
        tk.Label(titles, text="Roster Creator", bg=T.HEADER_BG, fg=T.HEADER_FG, font=T.Fonts.get(15, "bold")).pack(anchor="w")
        tk.Label(titles, text="Shift & on-call planner", bg=T.HEADER_BG, fg=T.HEADER_MUTED, font=T.Fonts.get(9)).pack(anchor="w")

        right = tk.Frame(bar, bg=T.HEADER_BG)
        right.pack(side="right", padx=20)
        self.header_context = tk.Label(right, text="", bg=T.HEADER_BG, fg=T.HEADER_MUTED, font=T.Fonts.get(10))
        self.header_context.pack(side="left", padx=(0, 16))
        tk.Button(
            right, text="Generate roster  ▶", command=self.generate, bg=T.PRIMARY, fg="white", activebackground="#6366F1",
            activeforeground="white", relief="flat", bd=0, highlightthickness=0, padx=16, pady=7, font=T.Fonts.get(10, "bold"), cursor="hand2",
        ).pack(side="left")

    def _add_page(self, title, subtitle, nav_title):
        frame = page(self.nb, title, subtitle)
        self.nb.add(frame)
        self.sidebar.add(len(self.sidebar.items) + 1, nav_title)
        return frame

    def show_page(self, idx):
        self.nb.select(idx)
        self.sidebar.select(idx)

    def _build_team_tab(self):
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
        tab = self._add_page("Month & Calendar", "Pick the roster month and mark weekends, holidays and freeze periods.", "Calendar")
        top, body = card(tab, "Roster month")
        top.pack(fill="x")
        ttk.Label(body, text="Month", style="Card.TLabel", foreground=T.MUTED, font=T.Fonts.get(9, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(body, text="Year", style="Card.TLabel", foreground=T.MUTED, font=T.Fonts.get(9, "bold")).grid(row=0, column=1, sticky="w", padx=(12, 0))
        ttk.Label(body, text="Weekend days", style="Card.TLabel", foreground=T.MUTED, font=T.Fonts.get(9, "bold")).grid(row=0, column=2, sticky="w", padx=(32, 0))
        self.month_var = tk.StringVar()
        self.year_var = tk.StringVar()
        ttk.Combobox(body, textvariable=self.month_var, values=list(calendar.month_name)[1:], state="readonly", width=14).grid(row=1, column=0, sticky="w", pady=(3, 0))
        ttk.Spinbox(body, from_=2000, to=2100, textvariable=self.year_var, width=7).grid(row=1, column=1, sticky="w", padx=(12, 0), pady=(3, 0))
        days = ttk.Frame(body, style="Surface.TFrame")
        days.grid(row=1, column=2, sticky="w", padx=(32, 0), pady=(3, 0))
        self.weekend_vars = []
        for i, day in enumerate(WEEKDAY_NAMES):
            v = tk.BooleanVar(value=i in (5, 6))
            ttk.Checkbutton(days, text=day, variable=v).pack(side="left", padx=(0, 8))
            self.weekend_vars.append(v)
        for v in (self.month_var, self.year_var):
            v.trace_add("write", lambda *_: self._update_header())

        row = ttk.Frame(tab)
        row.pack(fill="both", expand=True, pady=(14, 0))
        self.holidays = RecordEditor(
            row, "Holiday", [("date", "Date", "entry", None), ("name", "Name", "entry", None)],
            hint=DATE_HINT, noun="holiday", on_change=self._inputs_changed,
        )
        self.holidays.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        self.freeze = RecordEditor(
            row,
            "Freeze period",
            [("start", "Start date", "entry", None), ("end", "End date", "entry", None), ("note", "Note", "entry", None)],
            hint="Freeze days are exempt from the minimum Morning/Night rule (see Rules).",
            noun="freeze period", on_change=self._inputs_changed,
        )
        self.freeze.grid(row=0, column=1, sticky="nsew", padx=(7, 0))
        row.columnconfigure((0, 1), weight=1, uniform="cal")
        row.rowconfigure(0, weight=1)

    def _names(self, sme=None):
        rows = self.team.get_rows() if hasattr(self, "team") else []
        return [r["name"] for r in rows if sme is None or bool(r.get("sme")) == sme]

    def _build_leave_tabs(self):
        fields = [
            ("engineer", "Engineer", "choice", lambda: self._names()),
            ("start", "Start date", "entry", None),
            ("end", "End date (optional)", "entry", None),
            ("note", "Note", "entry", None),
        ]
        tab = self._add_page("Leave", "Planned days off. Leave the end date empty for a single day. Shown as L.", "Leave")
        self.leaves = RecordEditor(tab, "Add leave", fields, hint=DATE_HINT, noun="leave request", on_change=self._inputs_changed)
        self.leaves.pack(fill="both", expand=True)
        tab = self._add_page("Long Leave", "Extended absences such as vacations or medical leave. Shown as LL.", "Long Leave")
        self.long_leaves = RecordEditor(tab, "Add long leave", fields, hint=DATE_HINT, noun="long leave", on_change=self._inputs_changed)
        self.long_leaves.pack(fill="both", expand=True)

    def _build_requirements_tab(self):
        tab = self._add_page("Shift Requirements", "Pin an engineer to a shift, or keep them off one (e.g. no nights).", "Shift Requirements")
        self.requirements = RecordEditor(
            tab,
            "Add a shift requirement",
            [
                ("engineer", "Engineer", "choice", lambda: self._names()),
                ("shift", "Shift", "choice", [SHIFT_NAMES[s] for s in SHIFTS]),
                ("start", "Start date", "entry", None),
                ("end", "End date (optional)", "entry", None),
                ("mode", "Type", "choice", ["Must", "Avoid"]),
                ("note", "Note", "entry", None),
            ],
            hint="Must = works this shift on those working days.   Avoid = never rostered on this shift.",
            noun="requirement", on_change=self._inputs_changed,
        )
        self.requirements.pack(fill="both", expand=True)

    def _build_oncall_tab(self):
        tab = self._add_page("On-Call", "Optionally fix who is on call for specific days. Other days are rotated automatically.", "On-Call")
        self.oncall = RecordEditor(
            tab,
            "Set on-call for a day",
            [
                ("date", "Date", "entry", None),
                ("primary", "Primary (non-SME)", "choice", lambda: [""] + self._names(sme=False)),
                ("secondary", "Secondary (SME)", "choice", lambda: [""] + self._names(sme=True)),
            ],
            hint="Secondary on-call is not required on weekends and holidays.",
            noun="on-call override", on_change=self._inputs_changed, columns=3,
        )
        self.oncall.pack(fill="both", expand=True)

    def _build_rules_tab(self):
        tab = self._add_page("Rules", "Coverage minimums and generator settings.", "Rules")
        cols = ttk.Frame(tab)
        cols.pack(fill="x")
        outer, box = card(cols, "Minimum engineers per shift", "Default: at least 1 on Morning and Night on working days only.")
        outer.pack(side="left", fill="both", expand=True, padx=(0, 7))
        hdr = dict(style="Card.TLabel", foreground=T.MUTED, font=T.Fonts.get(9, "bold"))
        ttk.Label(box, text="DAY TYPE", **hdr).grid(row=0, column=0, sticky="w")
        for j, s in enumerate(SHIFTS, 1):
            ttk.Label(box, text=SHIFT_NAMES[s].upper(), **hdr).grid(row=0, column=j, padx=10, sticky="w")
        self.min_vars: dict[str, dict[str, tk.StringVar]] = {}
        for i, dtype in enumerate(DAY_TYPES, 1):
            ttk.Label(box, text=dtype, style="Card.TLabel").grid(row=i, column=0, sticky="w", pady=4)
            self.min_vars[dtype] = {}
            for j, s in enumerate(SHIFTS, 1):
                v = tk.StringVar(value="0")
                ttk.Spinbox(box, from_=0, to=20, textvariable=v, width=5).grid(row=i, column=j, padx=10, sticky="w")
                self.min_vars[dtype][s] = v

        outer, adv = card(cols, "Generator", "More attempts give a fairer roster but take longer.")
        outer.pack(side="left", fill="both", expand=True, padx=(7, 0))
        ttk.Label(adv, text="ATTEMPTS", **hdr).grid(row=0, column=0, sticky="w")
        self.attempts_var = tk.StringVar()
        ttk.Spinbox(adv, from_=1, to=5000, textvariable=self.attempts_var, width=8).grid(row=1, column=0, sticky="w", pady=(3, 12))
        ttk.Label(adv, text="RANDOM SEED (OPTIONAL)", **hdr).grid(row=2, column=0, sticky="w")
        self.seed_var = tk.StringVar()
        ttk.Entry(adv, textvariable=self.seed_var, width=10).grid(row=3, column=0, sticky="w", pady=(3, 0))
        ttk.Label(adv, text="Set a seed to get the same roster every time.", style="Hint.TLabel").grid(row=4, column=0, sticky="w", pady=(4, 0))

        outer, rules = card(tab, "Mandatory rules applied")
        outer.pack(fill="x", pady=(14, 0))
        items = (
            ("Coverage", "At least 1 engineer on Morning and Night on working days (freeze, weekends and holidays excluded)."),
            ("Comp off", "The day after every night shift is a comp off (CO)."),
            ("Primary on-call", "Every day - a non-SME engineer who is not on Morning or Night that day."),
            ("Secondary on-call", "An SME engineer - not required on weekends and holidays."),
            ("Requests", "Leave, long leave and shift requirements are honoured; anything that can't be met is reported."),
        )
        for i, (head, text) in enumerate(items):
            tk.Label(rules, text="✓", bg=T.SUCCESS_LIGHT, fg=T.SUCCESS, font=T.Fonts.get(9, "bold"), width=2).grid(row=i, column=0, sticky="w", pady=4)
            ttk.Label(rules, text=head, style="Card.TLabel", font=T.Fonts.get(10, "bold")).grid(row=i, column=1, sticky="w", padx=(10, 14))
            ttk.Label(rules, text=text, style="Card.TLabel", foreground=T.MUTED).grid(row=i, column=2, sticky="w")

    def _build_roster_tab(self):
        tab = self._add_page("Roster", "Hover a cell for details. Click a cell to change it - the roster is re-checked instantly.", "Roster")
        bar = ttk.Frame(tab)
        bar.pack(fill="x", pady=(0, 12))
        ttk.Button(bar, text="Generate roster  ▶", style="Big.Accent.TButton", command=self.generate).pack(side="left")
        ttk.Button(bar, text="Re-validate", command=self.revalidate).pack(side="left", padx=(8, 0))
        ttk.Button(bar, text="Export CSV", command=self.export_csv).pack(side="right")
        ttk.Button(bar, text="Export Excel", command=self.export_excel).pack(side="right", padx=(0, 8))

        tiles = ttk.Frame(tab)
        tiles.pack(fill="x", pady=(0, 12))
        self.tiles = {}
        for i, key in enumerate(("Status", "Rule violations", "Warnings", "Nights per person", "Primary on-call per person")):
            t = StatTile(tiles, key)
            t.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 10, 0))
            tiles.columnconfigure(i, weight=1)
            self.tiles[key] = t

        legend = tk.Frame(tab, bg=T.BG)
        legend.pack(fill="x", pady=(0, 8))
        for code in ALL_CODES:
            tk.Label(
                legend, text=code, width=3, bg="#" + export.CODE_COLORS[code], fg="#" + export.CODE_TEXT_COLORS.get(code, "111827"),
                font=T.Fonts.get(8, "bold"), pady=2,
            ).pack(side="left", padx=(0, 5))
            tk.Label(legend, text=LEGEND_NAMES[code], bg=T.BG, fg=T.MUTED, font=T.Fonts.get(9)).pack(side="left", padx=(0, 14))
        for color, text in ((T.PRIMARY, "Primary"), ("#0D9488", "Secondary"), (T.DANGER, "Rule broken")):
            dot = tk.Canvas(legend, width=10, height=10, bg=T.BG, highlightthickness=0)
            dot.create_oval(1, 1, 9, 9, fill=color, outline="")
            dot.pack(side="left", padx=(0, 5))
            tk.Label(legend, text=text, bg=T.BG, fg=T.MUTED, font=T.Fonts.get(9)).pack(side="left", padx=(0, 14))

        pane = ttk.PanedWindow(tab, orient="vertical")
        pane.pack(fill="both", expand=True)
        grid_card = ttk.Frame(pane, style="Card.TFrame", padding=8)
        self.grid_view = RosterGrid(grid_card, self._on_grid_edit, lambda s: self.status.set(s or "Ready"))
        self.grid_view.pack(fill="both", expand=True)
        pane.add(grid_card, weight=4)

        issues_card = ttk.Frame(pane, style="Card.TFrame", padding=1)
        ttk.Label(issues_card, text="Checks", style="CardTitle.TLabel", padding=(14, 10)).pack(anchor="w")
        inner = ttk.Frame(issues_card, style="Surface.TFrame")
        inner.pack(fill="both", expand=True)
        self.issue_tree = ttk.Treeview(inner, columns=("sev", "date", "msg"), show="headings", height=4)
        for col, label, w in (("sev", "SEVERITY", 110), ("date", "DATE", 120), ("msg", "MESSAGE", 900)):
            self.issue_tree.heading(col, text=label, anchor="w")
            self.issue_tree.column(col, width=w, anchor="w", stretch=col == "msg")
        self.issue_tree.tag_configure(ERROR, foreground=T.DANGER, background=T.DANGER_LIGHT)
        self.issue_tree.tag_configure(WARNING, foreground="#B45309", background=T.WARNING_LIGHT)
        self.issue_tree.tag_configure(INFO, foreground=T.MUTED)
        self.issue_tree.tag_configure("ok", foreground=T.SUCCESS, background=T.SUCCESS_LIGHT)
        sb = ttk.Scrollbar(inner, orient="vertical", command=self.issue_tree.yview)
        self.issue_tree.configure(yscrollcommand=sb.set)
        self.issue_tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        pane.add(issues_card, weight=1)
        self.roster_page = len(self.nb.tabs()) - 1

    # -- data in/out -----------------------------------------------------------
    def _inputs_changed(self):
        for editor in (self.leaves, self.long_leaves, self.requirements, self.oncall):
            editor.refresh_options()
        for idx, editor in enumerate((self.team, None, self.leaves, self.long_leaves, self.requirements, self.oncall)):
            if editor is not None:
                n = len(editor.rows)
                self.sidebar.set_badge(idx, str(n) if n else "")
        self.sidebar.set_badge(1, str(len(self.holidays.rows) + len(self.freeze.rows)) if hasattr(self, "freeze") and (self.holidays.rows or self.freeze.rows) else "")
        self._update_header()

    def _update_header(self):
        if not hasattr(self, "team"):
            return
        n = len(self.team.rows)
        sme = sum(1 for r in self.team.rows if r.get("sme"))
        self.header_context.configure(text=f"{self.month_var.get()} {self.year_var.get()}   ·   {n} engineers ({sme} SME)")

    def collect_dict(self) -> dict:
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
        }

    def load_dict(self, data: dict):
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
        for i, v in enumerate(self.weekend_vars):
            v.set(i in [int(x) for x in base["weekend_days"]])
        defaults = empty_config_dict()["min_coverage"]
        for dt, d in self.min_vars.items():
            for s, v in d.items():
                v.set(str(base["min_coverage"].get(dt, {}).get(SHIFT_NAMES[s], defaults[dt][SHIFT_NAMES[s]])))
        self.attempts_var.set(str(base["attempts"]))
        self.seed_var.set(str(base.get("seed") or ""))
        self._inputs_changed()

    def new_config(self):
        if messagebox.askyesno("New", "Clear all inputs?", parent=self):
            self.config_path = None
            self.load_dict(empty_config_dict())

    def open_config(self):
        path = filedialog.askopenfilename(parent=self, initialdir=self.last_dir, filetypes=[("Roster inputs", "*.json"), ("All files", "*")])
        if path:
            self._open_path(path)

    def _open_path(self, path):
        try:
            with open(path, encoding="utf-8") as fh:
                self.load_dict(json.load(fh))
        except (OSError, ValueError, KeyError) as exc:
            messagebox.showerror("Open failed", str(exc), parent=self)
            return
        self.config_path = path
        self._remember_dir(path)
        self.status.set(f"Loaded {path}")

    def load_sample(self):
        last_dir = self.last_dir
        self._open_path(SAMPLE_CONFIG)
        # Don't point file dialogs or "Save" at the bundled sample.
        self.config_path = None
        self.last_dir = last_dir

    def save_config(self, ask=False):
        path = self.config_path
        if ask or not path:
            path = filedialog.asksaveasfilename(parent=self, initialdir=self.last_dir, defaultextension=".json", filetypes=[("Roster inputs", "*.json")])
            if not path:
                return
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.collect_dict(), fh, indent=2)
        self.config_path = path
        self._remember_dir(path)
        self.status.set(f"Saved {path}")

    # -- roster ----------------------------------------------------------------
    def generate(self):
        try:
            cfg = RosterConfig.from_dict(self.collect_dict())
        except ValueError as exc:
            messagebox.showerror("Please fix the inputs", str(exc), parent=self)
            return
        self.status.set("Generating…")
        self.config(cursor="watch")
        self.update_idletasks()
        try:
            self.roster, self.issues = generate(cfg)
        except ValueError as exc:
            messagebox.showerror("Cannot generate", str(exc), parent=self)
            return
        finally:
            self.config(cursor="")
        self._show_roster()
        self.show_page(self.roster_page)

    def revalidate(self):
        if self.roster:
            self.issues = validate(self.roster)
            self._show_roster()

    def _on_grid_edit(self, kind, name, d, value):
        if kind == "code":
            self.roster.grid[name][d] = value
        else:
            target = self.roster.primary if kind == "primary" else self.roster.secondary
            if value:
                target[d] = value
            else:
                target.pop(d, None)
        self.revalidate()

    def _show_roster(self):
        errors = count(self.issues, ERROR)
        warnings = count(self.issues, WARNING)
        self.grid_view.show(self.roster, {i.day for i in self.issues if i.severity == ERROR and i.day})
        self.issue_tree.delete(*self.issue_tree.get_children())
        if errors == 0:
            self.issue_tree.insert("", "end", values=("✓ OK", "", "All mandatory rules are satisfied"), tags=("ok",))
        icons = {ERROR: "✗ Error", WARNING: "! Warning", INFO: "i Info"}
        for i in self.issues:
            self.issue_tree.insert("", "end", values=(icons[i.severity], i.day.strftime("%a %d %b") if i.day else "", i.message), tags=(i.severity,))

        if errors == 0:
            self.tiles["Status"].set("✓ Rules met", "Ready to export", fg=T.SUCCESS, bg=T.SUCCESS_LIGHT)
        else:
            self.tiles["Status"].set("✗ Needs fixes", "See checks below", fg=T.DANGER, bg=T.DANGER_LIGHT)
        self.tiles["Rule violations"].set(str(errors), "mandatory rules", fg=T.DANGER if errors else T.TEXT)
        self.tiles["Warnings"].set(str(warnings), "requests not met", fg="#B45309" if warnings else T.TEXT)
        cfg = self.roster.config
        nights = [self.roster.counts(n)["N"] for n in cfg.engineer_names]
        prim = [self.roster.counts(e.name)["Primary"] for e in cfg.engineers if not e.is_sme]
        self.tiles["Nights per person"].set(f"{min(nights)}–{max(nights)}", f"average {statistics.mean(nights):.1f}")
        if prim:
            self.tiles["Primary on-call per person"].set(f"{min(prim)}–{max(prim)}", f"across {len(prim)} non-SME engineers")
        self.status.set("Roster ready - hover over a cell for details, click to edit")

    def _remember_dir(self, path):
        self.last_dir = os.path.dirname(os.path.abspath(path))

    def _require_roster(self):
        if not self.roster:
            messagebox.showinfo("No roster", "Generate a roster first", parent=self)
            return False
        return True

    def _default_name(self, ext):
        cfg = self.roster.config
        return f"roster_{cfg.year}_{cfg.month:02d}.{ext}"

    def export_excel(self):
        if not self._require_roster():
            return
        path = filedialog.asksaveasfilename(parent=self, initialdir=self.last_dir, defaultextension=".xlsx", initialfile=self._default_name("xlsx"), filetypes=[("Excel", "*.xlsx")])
        if path:
            try:
                export.to_excel(self.roster, path, self.issues)
                self._remember_dir(path)
                self.status.set(f"Exported {path}")
            except (OSError, RuntimeError) as exc:
                messagebox.showerror("Export failed", str(exc), parent=self)

    def export_csv(self):
        if not self._require_roster():
            return
        path = filedialog.asksaveasfilename(parent=self, initialdir=self.last_dir, defaultextension=".csv", initialfile=self._default_name("csv"), filetypes=[("CSV", "*.csv")])
        if path:
            try:
                export.to_csv(self.roster, path)
                self._remember_dir(path)
                self.status.set(f"Exported {path}")
            except OSError as exc:
                messagebox.showerror("Export failed", str(exc), parent=self)


def main():
    RosterApp().mainloop()


if __name__ == "__main__":
    main()
