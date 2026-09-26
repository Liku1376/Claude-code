"""Saving and loading roster files, carry-over between months, change
tracking against a published version, and shift swaps.

A roster file (JSON) holds everything needed to reopen a month exactly as it
was left: the inputs, the (hand-edited) roster, its locked cells and the
last published version used for change tracking.
"""

from __future__ import annotations

import calendar
import json
from dataclasses import dataclass
from datetime import date, datetime

from .model import CARRY_KEYS, COMP_OFF, NIGHT, Locks, Roster, RosterConfig

FORMAT = "roster-creator/roster"
VERSION = 1


# -- serialisation ------------------------------------------------------------
def _assignments_to_dict(roster: Roster) -> dict:
    return {
        "grid": {n: {d.isoformat(): c for d, c in days.items()} for n, days in roster.grid.items()},
        "primary": {d.isoformat(): n for d, n in roster.primary.items() if n},
        "secondary": {d.isoformat(): n for d, n in roster.secondary.items() if n},
    }


def _roster_from_dict(cfg: RosterConfig, data: dict, locks: Locks | None = None) -> Roster:
    days = set(cfg.days)
    grid = {n: {} for n in cfg.engineer_names}
    for name, cells in (data.get("grid") or {}).items():
        if name in grid:
            for iso, code in cells.items():
                d = date.fromisoformat(iso)
                if d in days:
                    grid[name][d] = code
    primary = {date.fromisoformat(k): v for k, v in (data.get("primary") or {}).items()}
    secondary = {date.fromisoformat(k): v for k, v in (data.get("secondary") or {}).items()}
    return Roster(cfg, grid, primary, secondary, locks or Locks())


def locks_to_dict(locks: Locks) -> dict:
    return {
        "cells": [{"engineer": n, "date": d.isoformat(), "code": c} for (n, d), c in sorted(locks.cells.items())],
        "primary": {d.isoformat(): n for d, n in locks.primary.items()},
        "secondary": {d.isoformat(): n for d, n in locks.secondary.items()},
    }


def locks_from_dict(data: dict | None) -> Locks:
    data = data or {}
    return Locks(
        {(c["engineer"], date.fromisoformat(c["date"])): c["code"] for c in data.get("cells", [])},
        {date.fromisoformat(k): v for k, v in (data.get("primary") or {}).items()},
        {date.fromisoformat(k): v for k, v in (data.get("secondary") or {}).items()},
    )


@dataclass
class RosterFile:
    inputs: dict
    roster: Roster
    published: Roster | None = None
    published_at: str = ""


def save_roster_file(path: str, inputs: dict, roster: Roster, published: Roster | None = None, published_at: str = "") -> None:
    data = {
        "format": FORMAT,
        "version": VERSION,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "inputs": inputs,
        "roster": _assignments_to_dict(roster),
        "locks": locks_to_dict(roster.locks),
        "published": _assignments_to_dict(published) if published else None,
        "published_at": published_at,
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


def is_roster_file(data: dict) -> bool:
    return isinstance(data, dict) and data.get("format") == FORMAT


def roster_file_from_dict(data: dict) -> RosterFile:
    if not is_roster_file(data):
        raise ValueError("This is not a Roster Creator roster file")
    cfg = RosterConfig.from_dict(data["inputs"])
    roster = _roster_from_dict(cfg, data.get("roster") or {}, locks_from_dict(data.get("locks")))
    published = _roster_from_dict(cfg, data["published"]) if data.get("published") else None
    return RosterFile(data["inputs"], roster, published, data.get("published_at", ""))


def load_roster_file(path: str) -> RosterFile:
    with open(path, encoding="utf-8") as fh:
        return roster_file_from_dict(json.load(fh))


# -- carry-over ---------------------------------------------------------------
def carry_over_from(prev: Roster) -> dict:
    """Build the ``carry_over`` input block for the month after ``prev``:
    nights whose comp off falls next month, and running fairness totals."""
    cfg = prev.config
    last_day = prev.days[-1]
    nights = []
    for name in cfg.engineer_names:
        for d in prev.days:
            if prev.code(name, d) == NIGHT and cfg.comp_off_day(d) > last_day:
                nights.append({"engineer": name, "date": d.isoformat()})
    totals = {}
    for name in cfg.engineer_names:
        counts = prev.total_counts(name)
        totals[name] = {k: counts.get(k, 0) for k in CARRY_KEYS}
    return {
        "source": f"{calendar.month_name[cfg.month]} {cfg.year}",
        "source_year": cfg.year,
        "source_month": cfg.month,
        "nights": nights,
        "prior_counts": totals,
    }


def next_month(year: int, month: int) -> tuple[int, int]:
    return (year + 1, 1) if month == 12 else (year, month + 1)


# -- change tracking ----------------------------------------------------------
@dataclass
class Change:
    day: date
    who: str  # engineer name, or "Primary on-call" / "Secondary on-call"
    old: str
    new: str

    def __str__(self) -> str:
        return f"{self.day:%a %d %b}  {self.who}: {self.old or '-'} -> {self.new or '-'}"


def diff(published: Roster, current: Roster) -> list[Change]:
    changes = []
    days = [d for d in current.days if d in set(published.days)]
    for d in days:
        for name in current.config.engineer_names:
            old, new = published.code(name, d), current.code(name, d)
            if name in published.grid and old != new:
                changes.append(Change(d, name, old, new))
        for label, a, b in (("Primary on-call", published.primary, current.primary), ("Secondary on-call", published.secondary, current.secondary)):
            if a.get(d, "") != b.get(d, ""):
                changes.append(Change(d, label, a.get(d, ""), b.get(d, "")))
    return changes


def changed_cells(changes: list[Change]) -> set[tuple[str, date]]:
    return {(c.who, c.day) for c in changes}


# -- swaps ----------------------------------------------------------------------
def swap(roster: Roster, a: str, b: str, d: date) -> Roster:
    """Return a copy of the roster where engineers a and b swap their shift
    and on-call duties on day d. When a night shift changes hands, its comp
    off moves with it. The swapped cells are locked so a later regenerate
    keeps them."""
    new = roster.copy()

    def exchange(day):
        """Exchange a's and b's shift and on-call duties on one day."""
        ca, cb = new.code(a, day), new.code(b, day)
        new.grid[a][day], new.grid[b][day] = cb, ca
        new.locks.cells[(a, day)] = cb
        new.locks.cells[(b, day)] = ca
        for table, lock_table in ((new.primary, new.locks.primary), (new.secondary, new.locks.secondary)):
            who = table.get(day)
            if who in (a, b):
                table[day] = b if who == a else a
                lock_table[day] = table[day]

    ca, cb = new.code(a, d), new.code(b, d)
    exchange(d)
    if NIGHT in (ca, cb) and ca != cb:
        night_worker = a if ca == NIGHT else b
        co = new.config.comp_off_day(d)
        if co in set(new.days) and roster.code(night_worker, co) == COMP_OFF:
            exchange(co)
    return new
