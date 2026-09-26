"""Visual theme for the GUI: colours, fonts and ttk styles.

Everything is plain Tkinter/ttk (the "clam" theme restyled), so no extra
packages are needed. This file is commented line by line; ``ttk`` is Tkinter's
themed-widget set, and a "style" is a named bundle of appearance settings.
"""

from __future__ import annotations

# Tkinter is Python's built-in GUI toolkit. ``tkfont`` handles fonts; ``ttk``
# provides the themed widgets we restyle here.
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

# ---- Colour palette (hex strings) -------------------------------------------
PRIMARY = "#4F46E5"        # main indigo accent
PRIMARY_DARK = "#3730A3"   # darker accent (pressed / selected text)
PRIMARY_LIGHT = "#EEF2FF"  # pale accent (selected rows, SME tag)
HEADER_BG = "#1E1B4B"      # dark header bar background
HEADER_FG = "#FFFFFF"      # header text
HEADER_MUTED = "#A5B4FC"   # header secondary text
SIDEBAR_BG = "#FFFFFF"     # sidebar background
SIDEBAR_HOVER = "#F3F4F6"  # sidebar hover highlight
BG = "#F4F6FB"             # page background
SURFACE = "#FFFFFF"        # card / panel background
BORDER = "#E5E7EB"         # borders
GRID_LINE = "#EEF0F4"      # faint row separators
TEXT = "#111827"           # primary text
MUTED = "#6B7280"          # secondary text
SUCCESS = "#059669"        # green (rules met)
SUCCESS_LIGHT = "#ECFDF5"  # pale green background
WARNING_COLOR = "#D97706"  # amber (warnings)
WARNING_LIGHT = "#FFFBEB"  # pale amber background
DANGER = "#DC2626"         # red (errors)
DANGER_LIGHT = "#FEF2F2"   # pale red background
STRIPE = "#F9FAFB"         # zebra-stripe row colour

# Fonts to try, in order of preference; the first one installed is used.
_FONT_CANDIDATES = ("Segoe UI", "SF Pro Text", "Helvetica Neue", "Inter", "Ubuntu", "Noto Sans", "DejaVu Sans")


class Fonts:
    # The chosen font family (updated by apply_theme once we know what exists).
    family = "TkDefaultFont"

    @classmethod
    def get(cls, size=10, weight="normal"):
        # Build a Tkinter font tuple, e.g. ("Segoe UI", 12, "bold").
        return (cls.family, size, weight)


def apply_theme(root: tk.Tk) -> None:
    # The set of font families actually available on this machine.
    available = set(tkfont.families(root))
    # Pick the first preferred font that is installed.
    for name in _FONT_CANDIDATES:
        if name in available:
            Fonts.family = name
            break
    # Point Tkinter's named default fonts at our chosen family and size.
    for named in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
        try:
            tkfont.nametofont(named).configure(family=Fonts.family, size=10)
        except tk.TclError:
            # Some named fonts may not exist on every platform; ignore those.
            pass

    # Set the window background and start from the "clam" base theme.
    root.configure(background=BG)
    style = ttk.Style(root)
    style.theme_use("clam")
    f = Fonts.get   # short alias for building font tuples below

    # "." is the root style all widgets inherit from.
    style.configure(".", background=BG, foreground=TEXT, font=f(10), bordercolor=BORDER, focuscolor=PRIMARY)
    # Frames: plain page frames, bordered cards, and borderless white surfaces.
    style.configure("TFrame", background=BG)
    style.configure("Card.TFrame", background=SURFACE, relief="solid", borderwidth=1, bordercolor=BORDER)
    style.configure("Surface.TFrame", background=SURFACE)
    # Labels: on the page, on a card, card titles, hints, page titles/subtitles.
    style.configure("TLabel", background=BG, foreground=TEXT)
    style.configure("Card.TLabel", background=SURFACE)
    style.configure("CardTitle.TLabel", background=SURFACE, font=f(12, "bold"))
    style.configure("Hint.TLabel", background=SURFACE, foreground=MUTED, font=f(9))
    style.configure("PageTitle.TLabel", background=BG, font=f(16, "bold"))
    style.configure("PageSub.TLabel", background=BG, foreground=MUTED, font=f(10))
    # Checkboxes on a white card, with an accent tick when selected.
    style.configure("TCheckbutton", background=SURFACE)
    style.map("TCheckbutton", background=[("active", SURFACE)], indicatorcolor=[("selected", PRIMARY), ("!selected", SURFACE)])

    # Inputs: entries, dropdowns and spinboxes, with an accent border on focus.
    for widget in ("TEntry", "TCombobox", "TSpinbox"):
        style.configure(widget, fieldbackground=SURFACE, bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER, padding=5, arrowcolor=MUTED)
        style.map(widget, bordercolor=[("focus", PRIMARY)], lightcolor=[("focus", PRIMARY)])
    # Read-only comboboxes keep a white field instead of the default grey.
    style.map("TCombobox", fieldbackground=[("readonly", SURFACE)], selectbackground=[("readonly", SURFACE)], selectforeground=[("readonly", TEXT)])

    # Buttons: shared padding/font, then plain / accent / danger / big variants.
    base = dict(padding=(14, 7), borderwidth=0, font=f(10, "bold"), focusthickness=0)
    style.configure("TButton", background=SURFACE, foreground=TEXT, bordercolor=BORDER, lightcolor=SURFACE, darkcolor=SURFACE, **{**base, "borderwidth": 1})
    style.map("TButton", background=[("pressed", "#E5E7EB"), ("active", "#F3F4F6")])
    style.configure("Accent.TButton", background=PRIMARY, foreground="white", lightcolor=PRIMARY, darkcolor=PRIMARY, bordercolor=PRIMARY, **base)
    style.map("Accent.TButton", background=[("pressed", PRIMARY_DARK), ("active", "#6366F1")])
    style.configure("Danger.TButton", background=SURFACE, foreground=DANGER, bordercolor="#FECACA", lightcolor=SURFACE, darkcolor=SURFACE, **{**base, "borderwidth": 1})
    style.map("Danger.TButton", background=[("pressed", "#FEE2E2"), ("active", DANGER_LIGHT)])
    style.configure("Big.Accent.TButton", padding=(20, 10), font=f(11, "bold"))

    # Tables (Treeview): white rows, accent selection, muted bold headings.
    style.configure("Treeview", background=SURFACE, fieldbackground=SURFACE, foreground=TEXT, rowheight=28, borderwidth=0, font=f(10))
    style.map("Treeview", background=[("selected", PRIMARY_LIGHT)], foreground=[("selected", PRIMARY_DARK)])
    style.configure("Treeview.Heading", background="#F9FAFB", foreground=MUTED, font=f(9, "bold"), relief="flat", padding=(8, 6), bordercolor=BORDER)
    style.map("Treeview.Heading", background=[("active", "#F3F4F6")])

    # A notebook whose tabs are hidden - pages are switched from the sidebar
    # instead (an empty tab layout hides the row of tabs).
    style.layout("Pages.TNotebook.Tab", [])
    style.configure("Pages.TNotebook", background=BG, borderwidth=0, tabmargins=0)

    # Scrollbars, paned dividers and the status-bar label.
    style.configure("TScrollbar", background="#E5E7EB", troughcolor=BG, bordercolor=BG, arrowcolor=MUTED, lightcolor="#E5E7EB", darkcolor="#E5E7EB")
    style.configure("TPanedwindow", background=BG)
    style.configure("Status.TLabel", background=SURFACE, foreground=MUTED, padding=(12, 5), font=f(9))
