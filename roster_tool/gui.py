"""Tkinter GUI for the roster tool."""

from __future__ import annotations

import calendar
import json
import os
import tkinter as tk
from datetime import date
from tkinter import filedialog, messagebox, ttk

from . import export
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

SAMPLE_CONFIG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples", "sample_config.json")
DATE_HINT = "YYYY-MM-DD or day number"
DESIGNATIONS = ("Engineer", "Senior Engineer", "Lead Engineer", "SME", "Manager")


class RecordEditor(ttk.Frame):
    """A small form + table for editing a list of records.

    ``fields`` is a list of (key, label, kind, extra) where kind is one of
    "entry", "combo" (editable), "choice" (read-only combo) or "check".
    For combos, ``extra`` is a list of values or a callable returning one.
    """

    def __init__(self, master, title, fields, on_change=None, hint=""):
        super().__init__(master, padding=6)
        self.fields = fields
        self.on_change = on_change
        self.rows: list[dict] = []
        self.vars: dict[str, tk.Variable] = {}
        self.widgets: dict[str, ttk.Widget] = {}

        box = ttk.LabelFrame(self, text=title, padding=8)
        box.pack(fill="x")
        for i, (key, label, kind, extra) in enumerate(fields):
            ttk.Label(box, text=label).grid(row=i, column=0, sticky="w", padx=(0, 8), pady=2)
            if kind == "check":
                var = tk.BooleanVar(value=False)
                w = ttk.Checkbutton(box, variable=var)
            else:
                var = tk.StringVar()
                if kind in ("combo", "choice"):
                    w = ttk.Combobox(box, textvariable=var, state="readonly" if kind == "choice" else "normal", width=28)
                else:
                    w = ttk.Entry(box, textvariable=var, width=30)
            w.grid(row=i, column=1, sticky="w", pady=2)
            self.vars[key] = var
            self.widgets[key] = w
        if hint:
            ttk.Label(box, text=hint, foreground="#666").grid(row=len(fields), column=0, columnspan=2, sticky="w", pady=(4, 0))

        btns = ttk.Frame(box)
        btns.grid(row=0, column=2, rowspan=max(3, len(fields)), sticky="n", padx=(16, 0))
        ttk.Button(btns, text="Add", command=self.add).pack(fill="x", pady=1)
        ttk.Button(btns, text="Update selected", command=self.update_selected).pack(fill="x", pady=1)
        ttk.Button(btns, text="Delete selected", command=self.delete_selected).pack(fill="x", pady=1)
        ttk.Button(btns, text="Clear form", command=self.clear_form).pack(fill="x", pady=1)

        table = ttk.Frame(self)
        table.pack(fill="both", expand=True, pady=(6, 0))
        cols = [f[0] for f in fields]
        self.tree = ttk.Treeview(table, columns=cols, show="headings", selectmode="extended", height=8)
        for key, label, _kind, _extra in fields:
            self.tree.heading(key, text=label)
            self.tree.column(key, width=140, anchor="w")
        sb = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.refresh_options()

    # -- form helpers --------------------------------------------------------
    def refresh_options(self):
        for key, _label, kind, extra in self.fields:
            if kind in ("combo", "choice") and extra is not None:
                self.widgets[key]["values"] = list(extra() if callable(extra) else extra)

    def _form_values(self) -> dict | None:
        row = {}
        for key, label, kind, _extra in self.fields:
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

    def _display(self, row):
        out = []
        for key, _label, kind, _extra in self.fields:
            v = row.get(key, "")
            out.append(("Yes" if v else "No") if kind == "check" else v)
        return out

    def _redraw(self):
        self.tree.delete(*self.tree.get_children())
        for i, row in enumerate(self.rows):
            self.tree.insert("", "end", iid=str(i), values=self._display(row))

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

    NAME_W = 170
    CELL_W = 46
    CELL_H = 24
    HEAD_H = 40
    SUMMARY = ("M", "E", "N", "CO", "L", "LL", "Primary", "Secondary")
    SUMMARY_W = 44

    def __init__(self, master, on_edit, on_hover):
        super().__init__(master)
        self.on_edit = on_edit
        self.on_hover = on_hover
        self.roster: Roster | None = None
        self.error_days: set[date] = set()
        self.canvas = tk.Canvas(self, background="white", highlightthickness=0)
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
        self.canvas.create_text(20, 20, anchor="nw", text="Fill in the inputs, then press 'Generate roster'.", fill="#666")

    def show(self, roster: Roster, error_days: set[date]):
        self.roster = roster
        self.error_days = error_days
        self.draw()

    def _rows(self):
        cfg = self.roster.config
        return [("eng", e.name) for e in cfg.engineers] + [("primary", None), ("secondary", None)]

    def _cell_at(self, event):
        if not self.roster:
            return None
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)
        if x < self.NAME_W or y < self.HEAD_H:
            return None
        col = int((x - self.NAME_W) // self.CELL_W)
        row = int((y - self.HEAD_H) // self.CELL_H)
        days = self.roster.days
        rows = self._rows()
        if 0 <= col < len(days) and 0 <= row < len(rows):
            return rows[row], days[col]
        return None

    def draw(self):
        c = self.canvas
        c.delete("all")
        r = self.roster
        cfg = r.config
        days = r.days
        rows = self._rows()
        x0 = self.NAME_W

        # Header: day number + weekday, coloured by day type.
        c.create_rectangle(0, 0, x0, self.HEAD_H, fill="#F4F4F4", outline="#BBBBBB")
        c.create_text(8, self.HEAD_H / 2, anchor="w", text=f"{calendar.month_name[cfg.month]} {cfg.year}", font=("TkDefaultFont", 10, "bold"))
        for i, d in enumerate(days):
            x = x0 + i * self.CELL_W
            dtype = cfg.day_type(d)
            outline = "#D32F2F" if d in self.error_days else "#BBBBBB"
            c.create_rectangle(x, 0, x + self.CELL_W, self.HEAD_H, fill="#" + export.DAYTYPE_COLORS[dtype], outline=outline, width=2 if d in self.error_days else 1)
            c.create_text(x + self.CELL_W / 2, 12, text=d.strftime("%d"), font=("TkDefaultFont", 9, "bold"))
            c.create_text(x + self.CELL_W / 2, 28, text=WEEKDAY_NAMES[d.weekday()] + ("*" if dtype == "Freeze" else ""), font=("TkDefaultFont", 8))
        sx = x0 + len(days) * self.CELL_W
        for j, key in enumerate(self.SUMMARY):
            x = sx + j * self.SUMMARY_W
            c.create_rectangle(x, 0, x + self.SUMMARY_W, self.HEAD_H, fill="#F4F4F4", outline="#BBBBBB")
            c.create_text(x + self.SUMMARY_W / 2, self.HEAD_H / 2, text={"Primary": "Pri", "Secondary": "Sec"}.get(key, key), font=("TkDefaultFont", 8, "bold"))

        for ri, (kind, name) in enumerate(rows):
            y = self.HEAD_H + ri * self.CELL_H
            if kind == "eng":
                eng = cfg.engineer(name)
                label = f"{name}{'  (SME)' if eng.is_sme else ''}"
                bg = "#FFFFFF"
            else:
                label = "Primary on-call" if kind == "primary" else "Secondary on-call"
                bg = "#EEF3FF"
            c.create_rectangle(0, y, x0, y + self.CELL_H, fill=bg, outline="#BBBBBB")
            c.create_text(8, y + self.CELL_H / 2, anchor="w", text=label, font=("TkDefaultFont", 9, "bold" if kind != "eng" else "normal"))
            for i, d in enumerate(days):
                x = x0 + i * self.CELL_W
                if kind == "eng":
                    code = r.code(name, d)
                    fill = "#" + export.CODE_COLORS.get(code, "FFFFFF")
                    fg = "#" + export.CODE_TEXT_COLORS.get(code, "000000")
                    text = code
                    if r.primary.get(d) == name:
                        text += "ᴾ"
                    if r.secondary.get(d) == name:
                        text += "ˢ"
                else:
                    who = (r.primary if kind == "primary" else r.secondary).get(d, "")
                    fill, fg, text = bg, "#000000", who[:6]
                c.create_rectangle(x, y, x + self.CELL_W, y + self.CELL_H, fill=fill, outline="#CCCCCC")
                c.create_text(x + self.CELL_W / 2, y + self.CELL_H / 2, text=text, fill=fg, font=("TkDefaultFont", 9))
            if kind == "eng":
                counts = r.counts(name)
                for j, key in enumerate(self.SUMMARY):
                    x = sx + j * self.SUMMARY_W
                    c.create_rectangle(x, y, x + self.SUMMARY_W, y + self.CELL_H, fill="#FAFAFA", outline="#CCCCCC")
                    c.create_text(x + self.SUMMARY_W / 2, y + self.CELL_H / 2, text=str(counts[key]), font=("TkDefaultFont", 9))

        total_w = sx + len(self.SUMMARY) * self.SUMMARY_W
        total_h = self.HEAD_H + len(rows) * self.CELL_H
        c.configure(scrollregion=(0, 0, total_w + 4, total_h + 4))

    def _motion(self, event):
        hit = self._cell_at(event)
        if not hit:
            self.on_hover("")
            return
        (kind, name), d = hit
        r = self.roster
        cfg = r.config
        head = f"{d:%a %d %b} ({cfg.day_type(d)}{': ' + cfg.holiday_name(d) if cfg.holiday_name(d) else ''})"
        if kind == "eng":
            code = r.code(name, d)
            desc = f"{name}: {CODE_DESCRIPTIONS.get(code, code)}"
        else:
            desc = f"{'Primary' if kind == 'primary' else 'Secondary'} on-call: {(r.primary if kind == 'primary' else r.secondary).get(d, '') or '(none)'}"
        m = ", ".join(r.on_shift(d, "M")) or "-"
        n = ", ".join(r.on_shift(d, "N")) or "-"
        self.on_hover(f"{head}  |  {desc}  |  Morning: {m}  |  Night: {n}")

    def _click(self, event):
        hit = self._cell_at(event)
        if not hit:
            return
        (kind, name), d = hit
        cfg = self.roster.config
        menu = tk.Menu(self, tearoff=0)
        if kind == "eng":
            for code in ALL_CODES:
                menu.add_command(label=f"{code} - {CODE_DESCRIPTIONS[code]}", command=lambda code=code: self.on_edit("code", name, d, code))
        else:
            want_sme = kind == "secondary"
            menu.add_command(label="(none)", command=lambda: self.on_edit(kind, None, d, ""))
            for e in cfg.engineers:
                if e.is_sme == want_sme:
                    menu.add_command(label=e.name, command=lambda n=e.name: self.on_edit(kind, None, d, n))
        menu.tk_popup(event.x_root, event.y_root)


class RosterApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Roster Creator")
        self.geometry("1280x800")
        self.minsize(900, 600)
        self.roster: Roster | None = None
        self.issues = []
        self.config_path: str | None = None

        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")

        self._build_menu()
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=6, pady=6)
        self._build_team_tab()
        self._build_calendar_tab()
        self._build_leave_tabs()
        self._build_requirements_tab()
        self._build_oncall_tab()
        self._build_rules_tab()
        self._build_roster_tab()

        self.status = tk.StringVar(value="Ready")
        ttk.Label(self, textvariable=self.status, anchor="w", relief="sunken", padding=(6, 2)).pack(fill="x", side="bottom")
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

    def _tab(self, title):
        frame = ttk.Frame(self.nb, padding=4)
        self.nb.add(frame, text=title)
        return frame

    def _build_team_tab(self):
        tab = self._tab("1. Team")
        self.team = RecordEditor(
            tab,
            "Engineer",
            [
                ("name", "Name", "entry", None),
                ("designation", "Designation", "combo", DESIGNATIONS),
                ("sme", "SME (subject matter expert)", "check", None),
            ],
            on_change=self._team_changed,
            hint="SMEs are eligible for secondary on-call; non-SMEs for primary on-call.",
        )
        self.team.pack(fill="both", expand=True)

    def _build_calendar_tab(self):
        tab = self._tab("2. Month & Calendar")
        top = ttk.LabelFrame(tab, text="Roster month", padding=8)
        top.pack(fill="x", padx=6, pady=6)
        ttk.Label(top, text="Year").pack(side="left")
        self.year_var = tk.StringVar()
        ttk.Spinbox(top, from_=2000, to=2100, textvariable=self.year_var, width=6).pack(side="left", padx=(4, 16))
        ttk.Label(top, text="Month").pack(side="left")
        self.month_var = tk.StringVar()
        ttk.Combobox(top, textvariable=self.month_var, values=list(calendar.month_name)[1:], state="readonly", width=12).pack(side="left", padx=(4, 24))
        ttk.Label(top, text="Weekend days").pack(side="left")
        self.weekend_vars = []
        for i, day in enumerate(WEEKDAY_NAMES):
            v = tk.BooleanVar(value=i in (5, 6))
            ttk.Checkbutton(top, text=day, variable=v).pack(side="left")
            self.weekend_vars.append(v)

        body = ttk.Frame(tab)
        body.pack(fill="both", expand=True)
        self.holidays = RecordEditor(
            body, "Holiday", [("date", "Date", "entry", None), ("name", "Name", "entry", None)], hint=f"Date: {DATE_HINT}"
        )
        self.holidays.pack(side="left", fill="both", expand=True)
        self.freeze = RecordEditor(
            body,
            "Freeze period",
            [("start", "Start date", "entry", None), ("end", "End date", "entry", None), ("note", "Note", "entry", None)],
            hint="Freeze days are exempt from the minimum Morning/Night rule\n(configurable on the Rules tab).",
        )
        self.freeze.pack(side="left", fill="both", expand=True)

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
        self.leaves = RecordEditor(self._tab("3. Leave"), "Leave request", fields, hint=f"Dates: {DATE_HINT}. Leave the end date empty for a single day.")
        self.leaves.pack(fill="both", expand=True)
        self.long_leaves = RecordEditor(self._tab("4. Long Leave"), "Long leave", fields, hint=f"Dates: {DATE_HINT}. Shown as LL in the roster.")
        self.long_leaves.pack(fill="both", expand=True)

    def _build_requirements_tab(self):
        tab = self._tab("5. Shift Requirements")
        self.requirements = RecordEditor(
            tab,
            "Specific shift requirement",
            [
                ("engineer", "Engineer", "choice", lambda: self._names()),
                ("start", "Start date", "entry", None),
                ("end", "End date (optional)", "entry", None),
                ("shift", "Shift", "choice", [SHIFT_NAMES[s] for s in SHIFTS]),
                ("mode", "Type", "choice", ["Must", "Avoid"]),
                ("note", "Note", "entry", None),
            ],
            hint="Must = engineer works this shift on those working days.\nAvoid = engineer is not rostered on this shift (e.g. no nights).",
        )
        self.requirements.pack(fill="both", expand=True)

    def _build_oncall_tab(self):
        tab = self._tab("6. On-Call")
        self.oncall = RecordEditor(
            tab,
            "On-call engineer for a day (optional override)",
            [
                ("date", "Date", "entry", None),
                ("primary", "Primary (non-SME)", "choice", lambda: [""] + self._names(sme=False)),
                ("secondary", "Secondary (SME)", "choice", lambda: [""] + self._names(sme=True)),
            ],
            hint="Days without an entry get an on-call engineer automatically, rotated fairly.\n"
            "Secondary on-call is not required on weekends and holidays.",
        )
        self.oncall.pack(fill="both", expand=True)

    def _build_rules_tab(self):
        tab = self._tab("7. Rules")
        box = ttk.LabelFrame(tab, text="Minimum engineers per shift", padding=10)
        box.pack(fill="x", padx=6, pady=6)
        ttk.Label(box, text="Day type").grid(row=0, column=0, sticky="w")
        for j, s in enumerate(SHIFTS, 1):
            ttk.Label(box, text=SHIFT_NAMES[s]).grid(row=0, column=j, padx=8)
        self.min_vars: dict[str, dict[str, tk.StringVar]] = {}
        for i, dtype in enumerate(DAY_TYPES, 1):
            ttk.Label(box, text=dtype).grid(row=i, column=0, sticky="w", pady=2)
            self.min_vars[dtype] = {}
            for j, s in enumerate(SHIFTS, 1):
                v = tk.StringVar(value="0")
                ttk.Spinbox(box, from_=0, to=20, textvariable=v, width=5).grid(row=i, column=j, padx=8)
                self.min_vars[dtype][s] = v

        adv = ttk.LabelFrame(tab, text="Generator", padding=10)
        adv.pack(fill="x", padx=6, pady=6)
        ttk.Label(adv, text="Attempts (more = fairer, slower)").grid(row=0, column=0, sticky="w")
        self.attempts_var = tk.StringVar()
        ttk.Spinbox(adv, from_=1, to=5000, textvariable=self.attempts_var, width=7).grid(row=0, column=1, sticky="w", padx=8)
        ttk.Label(adv, text="Random seed (optional, for repeatable output)").grid(row=1, column=0, sticky="w")
        self.seed_var = tk.StringVar()
        ttk.Entry(adv, textvariable=self.seed_var, width=9).grid(row=1, column=1, sticky="w", padx=8)

        rules = ttk.LabelFrame(tab, text="Mandatory rules applied", padding=10)
        rules.pack(fill="x", padx=6, pady=6)
        text = (
            "1. At least 1 engineer on Morning and Night shift on working days "
            "(freeze periods, weekends and holidays excluded - see the table above).\n"
            "2. The day after every night shift is a comp off (CO).\n"
            "3. Primary on-call every day: a non-SME engineer who is not on Morning or Night shift that day.\n"
            "4. Secondary on-call: an SME engineer; not required on weekends and holidays.\n"
            "Leave, long leave and shift requirements are honoured; anything that cannot be met is reported."
        )
        ttk.Label(rules, text=text, justify="left", wraplength=900).pack(anchor="w")

    def _build_roster_tab(self):
        tab = self._tab("8. Roster")
        bar = ttk.Frame(tab)
        bar.pack(fill="x", pady=(0, 4))
        ttk.Button(bar, text="Generate roster", command=self.generate).pack(side="left")
        ttk.Button(bar, text="Re-validate", command=self.revalidate).pack(side="left", padx=4)
        ttk.Button(bar, text="Export Excel…", command=self.export_excel).pack(side="left", padx=4)
        ttk.Button(bar, text="Export CSV…", command=self.export_csv).pack(side="left")
        self.summary_var = tk.StringVar(value="")
        ttk.Label(bar, textvariable=self.summary_var, font=("TkDefaultFont", 10, "bold")).pack(side="left", padx=16)

        legend = ttk.Frame(tab)
        legend.pack(fill="x", pady=(0, 4))
        for code in ALL_CODES:
            tk.Label(
                legend,
                text=f" {code} ",
                bg="#" + export.CODE_COLORS[code],
                fg="#" + export.CODE_TEXT_COLORS.get(code, "000000"),
                relief="solid",
                bd=1,
            ).pack(side="left", padx=(6, 2))
            ttk.Label(legend, text=CODE_DESCRIPTIONS[code]).pack(side="left")
        ttk.Label(legend, text="   ᴾ/ˢ = primary/secondary on-call, * = freeze day. Click a cell to edit.").pack(side="left")

        pane = ttk.PanedWindow(tab, orient="vertical")
        pane.pack(fill="both", expand=True)
        self.grid_view = RosterGrid(pane, self._on_grid_edit, lambda s: self.status.set(s or "Ready"))
        pane.add(self.grid_view, weight=4)

        issues_frame = ttk.Frame(pane)
        self.issue_tree = ttk.Treeview(issues_frame, columns=("sev", "date", "msg"), show="headings", height=7)
        for col, label, w in (("sev", "Severity", 80), ("date", "Date", 110), ("msg", "Message", 900)):
            self.issue_tree.heading(col, text=label)
            self.issue_tree.column(col, width=w, anchor="w", stretch=col == "msg")
        self.issue_tree.tag_configure(ERROR, foreground="#B71C1C")
        self.issue_tree.tag_configure(WARNING, foreground="#E65100")
        self.issue_tree.tag_configure(INFO, foreground="#555555")
        self.issue_tree.tag_configure("ok", foreground="#1B5E20")
        sb = ttk.Scrollbar(issues_frame, orient="vertical", command=self.issue_tree.yview)
        self.issue_tree.configure(yscrollcommand=sb.set)
        self.issue_tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        pane.add(issues_frame, weight=1)

    # -- data in/out -----------------------------------------------------------
    def _team_changed(self):
        for editor in (self.leaves, self.long_leaves, self.requirements, self.oncall):
            editor.refresh_options()

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
        self._team_changed()

    def new_config(self):
        if messagebox.askyesno("New", "Clear all inputs?", parent=self):
            self.config_path = None
            self.load_dict(empty_config_dict())

    def open_config(self):
        path = filedialog.askopenfilename(parent=self, filetypes=[("Roster inputs", "*.json"), ("All files", "*")])
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
        self.status.set(f"Loaded {path}")

    def load_sample(self):
        self._open_path(SAMPLE_CONFIG)
        self.config_path = None

    def save_config(self, ask=False):
        path = self.config_path
        if ask or not path:
            path = filedialog.asksaveasfilename(parent=self, defaultextension=".json", filetypes=[("Roster inputs", "*.json")])
            if not path:
                return
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.collect_dict(), fh, indent=2)
        self.config_path = path
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
        self.nb.select(len(self.nb.tabs()) - 1)

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
            self.issue_tree.insert("", "end", values=("OK", "", "All mandatory rules are satisfied"), tags=("ok",))
        for i in self.issues:
            self.issue_tree.insert("", "end", values=(i.severity, i.day.strftime("%a %d %b") if i.day else "", i.message), tags=(i.severity,))
        verdict = "All mandatory rules met" if errors == 0 else f"{errors} rule violation(s)"
        self.summary_var.set(f"{verdict}  •  {warnings} warning(s)")
        self.status.set("Roster ready - hover over a cell for details, click to edit")

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
        path = filedialog.asksaveasfilename(parent=self, defaultextension=".xlsx", initialfile=self._default_name("xlsx"), filetypes=[("Excel", "*.xlsx")])
        if path:
            try:
                export.to_excel(self.roster, path, self.issues)
                self.status.set(f"Exported {path}")
            except (OSError, RuntimeError) as exc:
                messagebox.showerror("Export failed", str(exc), parent=self)

    def export_csv(self):
        if not self._require_roster():
            return
        path = filedialog.asksaveasfilename(parent=self, defaultextension=".csv", initialfile=self._default_name("csv"), filetypes=[("CSV", "*.csv")])
        if path:
            try:
                export.to_csv(self.roster, path)
                self.status.set(f"Exported {path}")
            except OSError as exc:
                messagebox.showerror("Export failed", str(exc), parent=self)


def main():
    RosterApp().mainloop()


if __name__ == "__main__":
    main()
