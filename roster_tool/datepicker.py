"""A small calendar date picker for Tkinter (no extra packages).

``DateEntry`` is a text field with a calendar button. The field still accepts
typed dates; the button opens a month view where a click fills the field in
``YYYY-MM-DD`` form.

This file is commented line by line. (The web app uses the browser's own date
picker instead; this one is only for the desktop GUI.)
"""

from __future__ import annotations

# ``calendar`` builds the month grid; Tkinter provides the widgets.
import calendar
import tkinter as tk
from datetime import date
from tkinter import ttk

# Our colour/font theme, and the shared date parser.
from . import theme as T
from .model import parse_date

# Two-letter weekday headers, Monday first.
WEEKDAYS = ("Mo", "Tu", "We", "Th", "Fr", "Sa", "Su")


class CalendarPopup(tk.Toplevel):
    """Month-view popup. Closes on selection, Escape or a click outside."""

    CELL = 34   # (reserved) nominal day-cell size

    def __init__(self, anchor: tk.Widget, initial: date, selected: date | None, on_pick, is_weekend, holiday_name):
        # A Toplevel is a separate little window; ``anchor`` is the field it opens under.
        super().__init__(anchor)
        self.anchor = anchor              # the field we return focus to
        self.on_pick = on_pick            # callback(date | None) when a day is chosen
        self.is_weekend = is_weekend      # function(date) -> bool, for shading
        self.holiday_name = holiday_name  # function(date) -> str, for shading/tooltip
        self.selected = selected          # currently selected date (highlighted)
        self.year, self.month = initial.year, initial.month  # month on show

        # Remove the OS window frame so it looks like a dropdown; a 1px border
        # is faked by colouring the outer window and insetting the body.
        self.overrideredirect(True)
        self.configure(bg=T.BORDER)
        self.body = tk.Frame(self, bg=T.SURFACE, padx=10, pady=10)
        self.body.pack(padx=1, pady=1)

        # Header: previous-month arrow, month/year title, next-month arrow.
        head = tk.Frame(self.body, bg=T.SURFACE)
        head.pack(fill="x", pady=(0, 6))
        self._nav(head, "‹", -1).pack(side="left")
        self.title_lbl = tk.Label(head, bg=T.SURFACE, fg=T.TEXT, font=T.Fonts.get(11, "bold"))
        self.title_lbl.pack(side="left", expand=True)
        self._nav(head, "›", 1).pack(side="right")

        # The grid of day cells, and a hint line under it.
        self.grid_frame = tk.Frame(self.body, bg=T.SURFACE)
        self.grid_frame.pack()
        self.hint = tk.Label(self.body, text="", bg=T.SURFACE, fg=T.MUTED, font=T.Fonts.get(8), anchor="w")
        self.hint.pack(fill="x", pady=(6, 0))

        # Footer: "Today" and "Clear" shortcuts.
        foot = tk.Frame(self.body, bg=T.SURFACE)
        foot.pack(fill="x", pady=(4, 0))
        self._link(foot, "Today", lambda: self._pick(date.today())).pack(side="left")
        self._link(foot, "Clear", lambda: self._pick(None)).pack(side="right")

        # Draw the current month.
        self._render()
        # Make sure sizes are known before positioning.
        self.update_idletasks()
        # Position just under the anchor field.
        x = anchor.winfo_rootx()
        y = anchor.winfo_rooty() + anchor.winfo_height() + 2
        # Keep the popup on screen (shift left / flip above if it would overflow).
        x = min(x, self.winfo_screenwidth() - self.winfo_reqwidth() - 4)
        if y + self.winfo_reqheight() > self.winfo_screenheight():
            y = anchor.winfo_rooty() - self.winfo_reqheight() - 2
        self.geometry(f"+{max(0, x)}+{max(0, y)}")

        # Close on Escape or a click outside; grab input so it behaves like a menu.
        self.bind("<Escape>", lambda _e: self.close())
        self.bind("<ButtonPress>", self._maybe_close, add="+")
        self.focus_force()
        try:
            self.grab_set()
        except tk.TclError:
            # grab_set can fail in odd states (e.g. during teardown); ignore.
            pass

    # -- widgets -------------------------------------------------------------
    def _nav(self, parent, text, step):
        # A clickable arrow that moves the shown month by ``step`` (-1 or +1).
        lbl = tk.Label(parent, text=text, bg=T.SURFACE, fg=T.MUTED, font=T.Fonts.get(14, "bold"), width=2, cursor="hand2")
        lbl.bind("<Button-1>", lambda _e: self._shift(step))
        lbl.bind("<Enter>", lambda _e: lbl.configure(bg=T.SIDEBAR_HOVER))   # hover in
        lbl.bind("<Leave>", lambda _e: lbl.configure(bg=T.SURFACE))          # hover out
        return lbl

    def _link(self, parent, text, cmd):
        # A small accent-coloured text link ("Today" / "Clear").
        lbl = tk.Label(parent, text=text, bg=T.SURFACE, fg=T.PRIMARY, font=T.Fonts.get(9, "bold"), cursor="hand2")
        lbl.bind("<Button-1>", lambda _e: cmd())
        return lbl

    def _shift(self, step):
        # Move the shown month by ``step``, rolling over year boundaries.
        m = self.month - 1 + step                       # 0-based month plus step
        self.year, self.month = self.year + m // 12, m % 12 + 1
        self._render()

    def _render(self):
        # Clear and redraw the day grid for the current month.
        for w in self.grid_frame.winfo_children():
            w.destroy()
        # Update the "October 2026" title.
        self.title_lbl.configure(text=f"{calendar.month_name[self.month]} {self.year}")
        # Weekday header row.
        for i, wd in enumerate(WEEKDAYS):
            tk.Label(self.grid_frame, text=wd, bg=T.SURFACE, fg=T.MUTED, font=T.Fonts.get(8, "bold"), width=4).grid(row=0, column=i, pady=(0, 4))
        today = date.today()
        # ``monthdatescalendar`` returns whole weeks (including spill-over days).
        weeks = calendar.Calendar(firstweekday=0).monthdatescalendar(self.year, self.month)
        for r, week in enumerate(weeks, 1):
            for c, d in enumerate(week):
                self._day_cell(d, today).grid(row=r, column=c, padx=1, pady=1)

    def _day_cell(self, d: date, today: date):
        # Build one clickable day cell, coloured by its role.
        in_month = d.month == self.month           # spill-over days are greyed
        holiday = self.holiday_name(d)             # non-empty if a holiday
        weekend = self.is_weekend(d)
        bg, fg, weight = T.SURFACE, T.TEXT, "normal"
        if holiday:
            bg, fg = "#EDE9FE", "#5B21B6"          # purple for holidays
        elif weekend:
            bg, fg = "#F3F4F6", T.MUTED            # grey for weekends
        if not in_month:
            fg = "#D1D5DB"                          # faint for other months
        if d == self.selected:
            bg, fg, weight = T.PRIMARY, "white", "bold"   # highlight the selection
        # The cell label; a coloured outline marks "today".
        cell = tk.Label(
            self.grid_frame, text=str(d.day), width=4, pady=5, bg=bg, fg=fg, font=T.Fonts.get(9, weight), cursor="hand2",
            highlightthickness=1, highlightbackground=T.PRIMARY if d == today else bg,
        )
        # The hover background (do not override the selected cell's colour).
        hover_bg = T.PRIMARY_LIGHT if d != self.selected else bg

        def enter(_e):
            # On hover, tint the cell and show the full date (and holiday) below.
            cell.configure(bg=hover_bg)
            label = d.strftime("%A %d %B %Y") + (f"  ·  {holiday}" if holiday else "")
            self.hint.configure(text=label)

        cell.bind("<Enter>", enter)
        # On leave, restore the colour and clear the hint.
        cell.bind("<Leave>", lambda _e: (cell.configure(bg=bg), self.hint.configure(text="")))
        # A click selects this day.
        cell.bind("<Button-1>", lambda _e: self._pick(d))
        return cell

    # -- behaviour -----------------------------------------------------------
    def _maybe_close(self, event):
        # Close if the click landed outside the popup's own rectangle.
        x0, y0 = self.winfo_rootx(), self.winfo_rooty()
        inside = x0 <= event.x_root < x0 + self.winfo_width() and y0 <= event.y_root < y0 + self.winfo_height()
        if not inside:
            self.close()

    def _pick(self, d: date | None):
        # Report the chosen date (or None for "clear") and close.
        self.on_pick(d)
        self.close()

    def close(self):
        # Release the input grab and destroy the popup, returning focus to the field.
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
        # A frame holding a text entry plus a small calendar-icon button.
        super().__init__(master, style="Surface.TFrame")
        self.var = textvariable                                   # the bound text variable
        self.default_date = default_date or date.today           # which month to open on
        self.is_weekend = is_weekend or (lambda d: d.weekday() >= 5)  # default weekend test
        self.holiday_name = holiday_name or (lambda d: "")        # default: no holidays
        # The typable entry.
        self.entry = ttk.Entry(self, textvariable=textvariable, width=width)
        self.entry.pack(side="left", fill="x", expand=True)
        # A small canvas used as the calendar button (we draw the icon on it).
        self.button = tk.Canvas(self, width=34, height=30, bg=T.SURFACE, highlightthickness=1, highlightbackground=T.BORDER, cursor="hand2")
        self.button.pack(side="left", padx=(4, 0))
        self._draw_icon(T.MUTED)
        # Open the popup on click; recolour the icon on hover.
        self.button.bind("<Button-1>", lambda _e: self.open())
        self.button.bind("<Enter>", lambda _e: self._draw_icon(T.PRIMARY))
        self.button.bind("<Leave>", lambda _e: self._draw_icon(T.MUTED))
        # Alt+Down also opens the picker from the keyboard.
        self.entry.bind("<Alt-Down>", lambda _e: self.open())

    def _draw_icon(self, color):
        # Draw a tiny calendar glyph on the button canvas in the given colour.
        c = self.button
        c.delete("all")
        c.create_rectangle(10, 9, 25, 23, outline=color, width=2)   # the body
        c.create_line(10, 13, 25, 13, fill=color, width=2)          # header line
        c.create_line(14, 6, 14, 10, fill=color, width=2)           # left ring
        c.create_line(21, 6, 21, 10, fill=color, width=2)           # right ring
        for x in (14, 18, 22):
            c.create_rectangle(x - 1, 17, x, 18, fill=color, outline=color)  # date dots

    def _current(self) -> date | None:
        # The date currently typed in the field, or None if it is blank/invalid.
        try:
            return parse_date(self.var.get(), *self._default_ym())
        except ValueError:
            return None

    def _default_ym(self):
        # The (year, month) the popup should default to.
        d = self.default_date()
        return d.year, d.month

    def open(self):
        # Open the calendar popup, seeded with the current value if there is one.
        current = self._current()
        CalendarPopup(
            self.entry, current or self.default_date(), current,
            # When a day is picked, write it back as an ISO date (or clear it).
            on_pick=lambda d: self.var.set(d.isoformat() if d else ""),
            is_weekend=self.is_weekend, holiday_name=self.holiday_name,
        )
