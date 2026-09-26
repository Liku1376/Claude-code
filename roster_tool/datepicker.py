"""A small calendar date picker for Tkinter (no extra packages).

``DateEntry`` is a text field with a calendar button. The field still accepts
typed dates; the button opens a month view where a click fills the field in
``YYYY-MM-DD`` form.
"""

from __future__ import annotations

import calendar
import tkinter as tk
from datetime import date
from tkinter import ttk

from . import theme as T
from .model import parse_date

WEEKDAYS = ("Mo", "Tu", "We", "Th", "Fr", "Sa", "Su")


class CalendarPopup(tk.Toplevel):
    """Month-view popup. Closes on selection, Escape or a click outside."""

    CELL = 34

    def __init__(self, anchor: tk.Widget, initial: date, selected: date | None, on_pick, is_weekend, holiday_name):
        super().__init__(anchor)
        self.anchor = anchor
        self.on_pick = on_pick
        self.is_weekend = is_weekend
        self.holiday_name = holiday_name
        self.selected = selected
        self.year, self.month = initial.year, initial.month

        self.overrideredirect(True)
        self.configure(bg=T.BORDER)
        self.body = tk.Frame(self, bg=T.SURFACE, padx=10, pady=10)
        self.body.pack(padx=1, pady=1)

        head = tk.Frame(self.body, bg=T.SURFACE)
        head.pack(fill="x", pady=(0, 6))
        self._nav(head, "‹", -1).pack(side="left")
        self.title_lbl = tk.Label(head, bg=T.SURFACE, fg=T.TEXT, font=T.Fonts.get(11, "bold"))
        self.title_lbl.pack(side="left", expand=True)
        self._nav(head, "›", 1).pack(side="right")

        self.grid_frame = tk.Frame(self.body, bg=T.SURFACE)
        self.grid_frame.pack()
        self.hint = tk.Label(self.body, text="", bg=T.SURFACE, fg=T.MUTED, font=T.Fonts.get(8), anchor="w")
        self.hint.pack(fill="x", pady=(6, 0))

        foot = tk.Frame(self.body, bg=T.SURFACE)
        foot.pack(fill="x", pady=(4, 0))
        self._link(foot, "Today", lambda: self._pick(date.today())).pack(side="left")
        self._link(foot, "Clear", lambda: self._pick(None)).pack(side="right")

        self._render()
        self.update_idletasks()
        x = anchor.winfo_rootx()
        y = anchor.winfo_rooty() + anchor.winfo_height() + 2
        # Keep the popup on screen.
        x = min(x, self.winfo_screenwidth() - self.winfo_reqwidth() - 4)
        if y + self.winfo_reqheight() > self.winfo_screenheight():
            y = anchor.winfo_rooty() - self.winfo_reqheight() - 2
        self.geometry(f"+{max(0, x)}+{max(0, y)}")

        self.bind("<Escape>", lambda _e: self.close())
        self.bind("<ButtonPress>", self._maybe_close, add="+")
        self.focus_force()
        try:
            self.grab_set()
        except tk.TclError:
            pass

    # -- widgets -------------------------------------------------------------
    def _nav(self, parent, text, step):
        lbl = tk.Label(parent, text=text, bg=T.SURFACE, fg=T.MUTED, font=T.Fonts.get(14, "bold"), width=2, cursor="hand2")
        lbl.bind("<Button-1>", lambda _e: self._shift(step))
        lbl.bind("<Enter>", lambda _e: lbl.configure(bg=T.SIDEBAR_HOVER))
        lbl.bind("<Leave>", lambda _e: lbl.configure(bg=T.SURFACE))
        return lbl

    def _link(self, parent, text, cmd):
        lbl = tk.Label(parent, text=text, bg=T.SURFACE, fg=T.PRIMARY, font=T.Fonts.get(9, "bold"), cursor="hand2")
        lbl.bind("<Button-1>", lambda _e: cmd())
        return lbl

    def _shift(self, step):
        m = self.month - 1 + step
        self.year, self.month = self.year + m // 12, m % 12 + 1
        self._render()

    def _render(self):
        for w in self.grid_frame.winfo_children():
            w.destroy()
        self.title_lbl.configure(text=f"{calendar.month_name[self.month]} {self.year}")
        for i, wd in enumerate(WEEKDAYS):
            tk.Label(self.grid_frame, text=wd, bg=T.SURFACE, fg=T.MUTED, font=T.Fonts.get(8, "bold"), width=4).grid(row=0, column=i, pady=(0, 4))
        today = date.today()
        weeks = calendar.Calendar(firstweekday=0).monthdatescalendar(self.year, self.month)
        for r, week in enumerate(weeks, 1):
            for c, d in enumerate(week):
                self._day_cell(d, today).grid(row=r, column=c, padx=1, pady=1)

    def _day_cell(self, d: date, today: date):
        in_month = d.month == self.month
        holiday = self.holiday_name(d)
        weekend = self.is_weekend(d)
        bg, fg, weight = T.SURFACE, T.TEXT, "normal"
        if holiday:
            bg, fg = "#EDE9FE", "#5B21B6"
        elif weekend:
            bg, fg = "#F3F4F6", T.MUTED
        if not in_month:
            fg = "#D1D5DB"
        if d == self.selected:
            bg, fg, weight = T.PRIMARY, "white", "bold"
        cell = tk.Label(
            self.grid_frame, text=str(d.day), width=4, pady=5, bg=bg, fg=fg, font=T.Fonts.get(9, weight), cursor="hand2",
            highlightthickness=1, highlightbackground=T.PRIMARY if d == today else bg,
        )
        hover_bg = T.PRIMARY_LIGHT if d != self.selected else bg

        def enter(_e):
            cell.configure(bg=hover_bg)
            label = d.strftime("%A %d %B %Y") + (f"  ·  {holiday}" if holiday else "")
            self.hint.configure(text=label)

        cell.bind("<Enter>", enter)
        cell.bind("<Leave>", lambda _e: (cell.configure(bg=bg), self.hint.configure(text="")))
        cell.bind("<Button-1>", lambda _e: self._pick(d))
        return cell

    # -- behaviour -----------------------------------------------------------
    def _maybe_close(self, event):
        x0, y0 = self.winfo_rootx(), self.winfo_rooty()
        inside = x0 <= event.x_root < x0 + self.winfo_width() and y0 <= event.y_root < y0 + self.winfo_height()
        if not inside:
            self.close()

    def _pick(self, d: date | None):
        self.on_pick(d)
        self.close()

    def close(self):
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()
        try:
            self.anchor.focus_set()
        except tk.TclError:
            pass


class DateEntry(ttk.Frame):
    """Entry + calendar button bound to a StringVar."""

    def __init__(self, master, textvariable: tk.StringVar, default_date=None, is_weekend=None, holiday_name=None, width=18):
        super().__init__(master, style="Surface.TFrame")
        self.var = textvariable
        self.default_date = default_date or date.today
        self.is_weekend = is_weekend or (lambda d: d.weekday() >= 5)
        self.holiday_name = holiday_name or (lambda d: "")
        self.entry = ttk.Entry(self, textvariable=textvariable, width=width)
        self.entry.pack(side="left", fill="x", expand=True)
        self.button = tk.Canvas(self, width=34, height=30, bg=T.SURFACE, highlightthickness=1, highlightbackground=T.BORDER, cursor="hand2")
        self.button.pack(side="left", padx=(4, 0))
        self._draw_icon(T.MUTED)
        self.button.bind("<Button-1>", lambda _e: self.open())
        self.button.bind("<Enter>", lambda _e: self._draw_icon(T.PRIMARY))
        self.button.bind("<Leave>", lambda _e: self._draw_icon(T.MUTED))
        self.entry.bind("<Alt-Down>", lambda _e: self.open())

    def _draw_icon(self, color):
        c = self.button
        c.delete("all")
        c.create_rectangle(10, 9, 25, 23, outline=color, width=2)
        c.create_line(10, 13, 25, 13, fill=color, width=2)
        c.create_line(14, 6, 14, 10, fill=color, width=2)
        c.create_line(21, 6, 21, 10, fill=color, width=2)
        for x in (14, 18, 22):
            c.create_rectangle(x - 1, 17, x, 18, fill=color, outline=color)

    def _current(self) -> date | None:
        try:
            return parse_date(self.var.get(), *self._default_ym())
        except ValueError:
            return None

    def _default_ym(self):
        d = self.default_date()
        return d.year, d.month

    def open(self):
        current = self._current()
        CalendarPopup(
            self.entry, current or self.default_date(), current,
            on_pick=lambda d: self.var.set(d.isoformat() if d else ""),
            is_weekend=self.is_weekend, holiday_name=self.holiday_name,
        )
