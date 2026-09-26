"""Saving and loading roster files, carry-over between months, change
tracking against a published version, and shift swaps.

A roster file (JSON) holds everything needed to reopen a month exactly as it
was left: the inputs, the (hand-edited) roster, its locked cells and the
last published version used for change tracking.

This file is commented line by line.
"""

from __future__ import annotations

# ``calendar`` gives month names; ``json`` reads/writes the roster files.
import calendar
import json
# ``dataclass`` builds the small RosterFile/Change records; dates for keys.
from dataclasses import dataclass
from datetime import date, datetime

# The pieces of the model we serialise and the codes swaps care about.
from .model import CARRY_KEYS, COMP_OFF, NIGHT, Locks, Roster, RosterConfig

# A marker so we can recognise our own files, and a version for future changes.
FORMAT = "roster-creator/roster"
VERSION = 1


# -- serialisation ------------------------------------------------------------
def _assignments_to_dict(roster: Roster) -> dict:
    # Turn a roster's cells and on-call maps into JSON-friendly dicts.
    # Dates become ISO strings ("2026-10-14") because JSON has no date type.
    return {
        # grid: {engineer: {iso date: code}}, skipping empty cells.
        "grid": {n: {d.isoformat(): c for d, c in days.items()} for n, days in roster.grid.items()},
        # on-call maps: {iso date: engineer}, skipping days with nobody.
        "primary": {d.isoformat(): n for d, n in roster.primary.items() if n},
        "secondary": {d.isoformat(): n for d, n in roster.secondary.items() if n},
    }


def _roster_from_dict(cfg: RosterConfig, data: dict, locks: Locks | None = None) -> Roster:
    # Rebuild a Roster object from the serialised dicts.
    days = set(cfg.days)                              # valid days for filtering
    grid = {n: {} for n in cfg.engineer_names}        # start empty
    for name, cells in (data.get("grid") or {}).items():
        # Ignore names not in the current team.
        if name in grid:
            for iso, code in cells.items():
                d = date.fromisoformat(iso)           # parse the ISO date
                if d in days:                          # ignore out-of-month days
                    grid[name][d] = code
    # Parse the on-call maps back into date keys.
    primary = {date.fromisoformat(k): v for k, v in (data.get("primary") or {}).items()}
    secondary = {date.fromisoformat(k): v for k, v in (data.get("secondary") or {}).items()}
    # Assemble the Roster (with locks if supplied, else an empty lock set).
    return Roster(cfg, grid, primary, secondary, locks or Locks())


def locks_to_dict(locks: Locks) -> dict:
    # Serialise the lock sets for saving.
    return {
        # cells become a sorted list of {engineer, date, code} objects.
        "cells": [{"engineer": n, "date": d.isoformat(), "code": c} for (n, d), c in sorted(locks.cells.items())],
        # on-call locks become {iso date: engineer}.
        "primary": {d.isoformat(): n for d, n in locks.primary.items()},
        "secondary": {d.isoformat(): n for d, n in locks.secondary.items()},
    }


def locks_from_dict(data: dict | None) -> Locks:
    # Rebuild a Locks object from its serialised form.
    data = data or {}
    return Locks(
        # cells: list of objects back into a {(engineer, date): code} dict.
        {(c["engineer"], date.fromisoformat(c["date"])): c["code"] for c in data.get("cells", [])},
        # on-call locks back into {date: engineer} dicts.
        {date.fromisoformat(k): v for k, v in (data.get("primary") or {}).items()},
        {date.fromisoformat(k): v for k, v in (data.get("secondary") or {}).items()},
    )


@dataclass
class RosterFile:
    # The in-memory result of opening a saved roster file.
    inputs: dict                       # the raw input dict
    roster: Roster                     # the (hand-edited) roster
    published: Roster | None = None    # the published snapshot, if any
    published_at: str = ""             # when it was published (display text)


def roster_file_dict(inputs: dict, roster: Roster, published: Roster | None = None, published_at: str = "") -> dict:
    """The on-disk roster-file structure, as a plain dict."""
    return {
        "format": FORMAT,                                     # our marker
        "version": VERSION,                                   # schema version
        "saved_at": datetime.now().isoformat(timespec="seconds"),  # timestamp
        "inputs": inputs,                                     # the input dict
        "roster": _assignments_to_dict(roster),              # the current roster
        "locks": locks_to_dict(roster.locks),                # pinned cells
        # The published snapshot, or null if nothing has been published yet.
        "published": _assignments_to_dict(published) if published else None,
        "published_at": published_at,
    }


def save_roster_file(path: str, inputs: dict, roster: Roster, published: Roster | None = None, published_at: str = "") -> None:
    # Write the roster-file dict to disk as pretty-printed JSON.
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(roster_file_dict(inputs, roster, published, published_at), fh, indent=2)


def is_roster_file(data: dict) -> bool:
    # True if a loaded JSON object is one of our roster files.
    return isinstance(data, dict) and data.get("format") == FORMAT


def roster_file_from_dict(data: dict) -> RosterFile:
    # Turn a loaded JSON object back into a RosterFile.
    if not is_roster_file(data):
        raise ValueError("This is not a Roster Creator roster file")
    # Rebuild the config from the saved inputs.
    cfg = RosterConfig.from_dict(data["inputs"])
    # Rebuild the current roster (with its locks).
    roster = _roster_from_dict(cfg, data.get("roster") or {}, locks_from_dict(data.get("locks")))
    # Rebuild the published snapshot if there is one.
    published = _roster_from_dict(cfg, data["published"]) if data.get("published") else None
    return RosterFile(data["inputs"], roster, published, data.get("published_at", ""))


def load_roster_file(path: str) -> RosterFile:
    # Read a roster file from disk and parse it.
    with open(path, encoding="utf-8") as fh:
        return roster_file_from_dict(json.load(fh))


# -- carry-over ---------------------------------------------------------------
def carry_over_from(prev: Roster) -> dict:
    """Build the ``carry_over`` input block for the month after ``prev``:
    nights whose comp off falls next month, and running fairness totals."""
    cfg = prev.config
    last_day = prev.days[-1]
    # Collect nights near month-end whose comp off spills into next month.
    nights = []
    for name in cfg.engineer_names:
        for d in prev.days:
            if prev.code(name, d) == NIGHT and cfg.comp_off_day(d) > last_day:
                nights.append({"engineer": name, "date": d.isoformat()})
    # Collect each engineer's running totals (this month + any earlier carry).
    totals = {}
    for name in cfg.engineer_names:
        counts = prev.total_counts(name)
        totals[name] = {k: counts.get(k, 0) for k in CARRY_KEYS}
    # Return the block the next month's config will read.
    return {
        "source": f"{calendar.month_name[cfg.month]} {cfg.year}",  # display label
        "source_year": cfg.year,
        "source_month": cfg.month,
        "nights": nights,
        "prior_counts": totals,
    }


def next_month(year: int, month: int) -> tuple[int, int]:
    # The (year, month) that follows the given one, rolling December into January.
    return (year + 1, 1) if month == 12 else (year, month + 1)


# -- change tracking ----------------------------------------------------------
@dataclass
class Change:
    # One difference between the published roster and the current one.
    day: date
    who: str  # engineer name, or "Primary on-call" / "Secondary on-call"
    old: str  # value in the published roster
    new: str  # value now

    def __str__(self) -> str:
        # e.g. "Mon 12 Oct  Chitra: E -> M" for the copyable change list.
        return f"{self.day:%a %d %b}  {self.who}: {self.old or '-'} -> {self.new or '-'}"


def diff(published: Roster, current: Roster) -> list[Change]:
    # Compare two rosters cell by cell and list what changed.
    changes = []
    # Only compare days both rosters share.
    days = [d for d in current.days if d in set(published.days)]
    for d in days:
        # Engineer shift cells.
        for name in current.config.engineer_names:
            old, new = published.code(name, d), current.code(name, d)
            # Only report engineers present in the published roster.
            if name in published.grid and old != new:
                changes.append(Change(d, name, old, new))
        # On-call rows.
        for label, a, b in (("Primary on-call", published.primary, current.primary), ("Secondary on-call", published.secondary, current.secondary)):
            if a.get(d, "") != b.get(d, ""):
                changes.append(Change(d, label, a.get(d, ""), b.get(d, "")))
    return changes


def changed_cells(changes: list[Change]) -> set[tuple[str, date]]:
    # The set of (who, day) pairs that changed, for highlighting in the grid.
    return {(c.who, c.day) for c in changes}


# -- swaps ----------------------------------------------------------------------
def swap(roster: Roster, a: str, b: str, d: date) -> Roster:
    """Return a copy of the roster where engineers a and b swap their shift
    and on-call duties on day d. When a night shift changes hands, its comp
    off moves with it. The swapped cells are locked so a later regenerate
    keeps them."""
    # Work on a copy so the original roster is untouched.
    new = roster.copy()

    def exchange(day):
        """Exchange a's and b's shift and on-call duties on one day."""
        # Swap their shift codes for this day.
        ca, cb = new.code(a, day), new.code(b, day)
        new.grid[a][day], new.grid[b][day] = cb, ca
        # Lock both swapped cells so a later regenerate keeps the swap.
        new.locks.cells[(a, day)] = cb
        new.locks.cells[(b, day)] = ca
        # If either engineer had on-call that day, move it to the other.
        for table, lock_table in ((new.primary, new.locks.primary), (new.secondary, new.locks.secondary)):
            who = table.get(day)
            if who in (a, b):
                table[day] = b if who == a else a
                lock_table[day] = table[day]

    # Remember the two shift codes before swapping.
    ca, cb = new.code(a, d), new.code(b, d)
    # Do the swap for the chosen day.
    exchange(d)
    # If exactly one of them was on a night shift, the comp off must move too.
    if NIGHT in (ca, cb) and ca != cb:
        night_worker = a if ca == NIGHT else b        # who was on the night
        co = new.config.comp_off_day(d)               # where their comp off is
        # If that comp off is in this month and really is a CO, swap that day too.
        if co in set(new.days) and roster.code(night_worker, co) == COMP_OFF:
            exchange(co)
    return new
