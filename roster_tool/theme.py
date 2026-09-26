"""Visual theme for the GUI: colours, fonts and ttk styles.

Everything is plain Tkinter/ttk (the "clam" theme restyled), so no extra
packages are needed.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

# Palette
PRIMARY = "#4F46E5"
PRIMARY_DARK = "#3730A3"
PRIMARY_LIGHT = "#EEF2FF"
HEADER_BG = "#1E1B4B"
HEADER_FG = "#FFFFFF"
HEADER_MUTED = "#A5B4FC"
SIDEBAR_BG = "#FFFFFF"
SIDEBAR_HOVER = "#F3F4F6"
BG = "#F4F6FB"
SURFACE = "#FFFFFF"
BORDER = "#E5E7EB"
GRID_LINE = "#EEF0F4"
TEXT = "#111827"
MUTED = "#6B7280"
SUCCESS = "#059669"
SUCCESS_LIGHT = "#ECFDF5"
WARNING_COLOR = "#D97706"
WARNING_LIGHT = "#FFFBEB"
DANGER = "#DC2626"
DANGER_LIGHT = "#FEF2F2"
STRIPE = "#F9FAFB"

_FONT_CANDIDATES = ("Segoe UI", "SF Pro Text", "Helvetica Neue", "Inter", "Ubuntu", "Noto Sans", "DejaVu Sans")


class Fonts:
    family = "TkDefaultFont"

    @classmethod
    def get(cls, size=10, weight="normal"):
        return (cls.family, size, weight)


def apply_theme(root: tk.Tk) -> None:
    available = set(tkfont.families(root))
    for name in _FONT_CANDIDATES:
        if name in available:
            Fonts.family = name
            break
    for named in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
        try:
            tkfont.nametofont(named).configure(family=Fonts.family, size=10)
        except tk.TclError:
            pass

    root.configure(background=BG)
    style = ttk.Style(root)
    style.theme_use("clam")
    f = Fonts.get

    style.configure(".", background=BG, foreground=TEXT, font=f(10), bordercolor=BORDER, focuscolor=PRIMARY)
    style.configure("TFrame", background=BG)
    style.configure("Card.TFrame", background=SURFACE, relief="solid", borderwidth=1, bordercolor=BORDER)
    style.configure("Surface.TFrame", background=SURFACE)
    style.configure("TLabel", background=BG, foreground=TEXT)
    style.configure("Card.TLabel", background=SURFACE)
    style.configure("CardTitle.TLabel", background=SURFACE, font=f(12, "bold"))
    style.configure("Hint.TLabel", background=SURFACE, foreground=MUTED, font=f(9))
    style.configure("PageTitle.TLabel", background=BG, font=f(16, "bold"))
    style.configure("PageSub.TLabel", background=BG, foreground=MUTED, font=f(10))
    style.configure("TCheckbutton", background=SURFACE)
    style.map("TCheckbutton", background=[("active", SURFACE)], indicatorcolor=[("selected", PRIMARY), ("!selected", SURFACE)])

    # Inputs
    for widget in ("TEntry", "TCombobox", "TSpinbox"):
        style.configure(widget, fieldbackground=SURFACE, bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER, padding=5, arrowcolor=MUTED)
        style.map(widget, bordercolor=[("focus", PRIMARY)], lightcolor=[("focus", PRIMARY)])
    style.map("TCombobox", fieldbackground=[("readonly", SURFACE)], selectbackground=[("readonly", SURFACE)], selectforeground=[("readonly", TEXT)])

    # Buttons
    base = dict(padding=(14, 7), borderwidth=0, font=f(10, "bold"), focusthickness=0)
    style.configure("TButton", background=SURFACE, foreground=TEXT, bordercolor=BORDER, lightcolor=SURFACE, darkcolor=SURFACE, **{**base, "borderwidth": 1})
    style.map("TButton", background=[("pressed", "#E5E7EB"), ("active", "#F3F4F6")])
    style.configure("Accent.TButton", background=PRIMARY, foreground="white", lightcolor=PRIMARY, darkcolor=PRIMARY, bordercolor=PRIMARY, **base)
    style.map("Accent.TButton", background=[("pressed", PRIMARY_DARK), ("active", "#6366F1")])
    style.configure("Danger.TButton", background=SURFACE, foreground=DANGER, bordercolor="#FECACA", lightcolor=SURFACE, darkcolor=SURFACE, **{**base, "borderwidth": 1})
    style.map("Danger.TButton", background=[("pressed", "#FEE2E2"), ("active", DANGER_LIGHT)])
    style.configure("Big.Accent.TButton", padding=(20, 10), font=f(11, "bold"))

    # Tables
    style.configure("Treeview", background=SURFACE, fieldbackground=SURFACE, foreground=TEXT, rowheight=28, borderwidth=0, font=f(10))
    style.map("Treeview", background=[("selected", PRIMARY_LIGHT)], foreground=[("selected", PRIMARY_DARK)])
    style.configure("Treeview.Heading", background="#F9FAFB", foreground=MUTED, font=f(9, "bold"), relief="flat", padding=(8, 6), bordercolor=BORDER)
    style.map("Treeview.Heading", background=[("active", "#F3F4F6")])

    # Hidden-tab notebook: pages are switched from the sidebar.
    style.layout("Pages.TNotebook.Tab", [])
    style.configure("Pages.TNotebook", background=BG, borderwidth=0, tabmargins=0)

    style.configure("TScrollbar", background="#E5E7EB", troughcolor=BG, bordercolor=BG, arrowcolor=MUTED, lightcolor="#E5E7EB", darkcolor="#E5E7EB")
    style.configure("TPanedwindow", background=BG)
    style.configure("Status.TLabel", background=SURFACE, foreground=MUTED, padding=(12, 5), font=f(9))
