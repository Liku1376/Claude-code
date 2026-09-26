"""Checks a roster against the mandatory rules and the user's requests.

Errors are violations of mandatory rules; warnings are requests that could
not be honoured (leave, shift requirements); info lines are notes.

This file is commented line by line to explain exactly what each rule checks.
"""

from __future__ import annotations

# ``dataclass`` builds the small Issue record; dates/day-stepping for the checks.
from dataclasses import dataclass
from datetime import date, timedelta

# The codes, names and data classes the checks refer to.
from .model import (
    ABSENT_CODES,
    COMP_OFF,
    LEAVE,
    LONG_LEAVE,
    EVENING,
    MORNING,
    NIGHT,
    SHIFT_NAMES,
    SHIFTS,
    WORKING_CODES,
    Locks,
    Roster,
    RosterConfig,
)

# The three severity levels an Issue can have.
ERROR = "Error"      # a mandatory rule is broken
WARNING = "Warning"  # a request could not be honoured
INFO = "Info"        # a note, not a problem


@dataclass
class Issue:
    # One problem or note found while checking a roster.
    severity: str          # ERROR / WARNING / INFO
    day: date | None       # the day it concerns, or None for a whole-month note
    message: str           # the human-readable text

    def __str__(self) -> str:
        # Format like "[Error] 06 Oct (Tue): ..." for the console / logs.
        when = self.day.strftime("%d %b (%a)") if self.day else "Month"
        return f"[{self.severity}] {when}: {self.message}"


def validate(roster: Roster) -> list[Issue]:
    # Shorthands for the config, the growing issue list and the month's days.
    cfg = roster.config
    issues: list[Issue] = []
    days = roster.days
    last_day = days[-1]

    # Comp offs still due for nights worked at the very end of last month.
    for name, co in cfg.carried_comp_offs().items():
        # The carried comp off must actually appear on its day.
        if roster.code(name, co) != COMP_OFF:
            issues.append(Issue(ERROR, co, f"{name} has a comp off due from last month's night shift on this day"))
        # And nothing may be worked before that comp off is taken.
        for rest in days:
            if rest >= co:
                break
            if roster.code(name, rest) in WORKING_CODES:
                issues.append(Issue(ERROR, rest, f"{name} is rostered to work before taking last month's comp off"))

    # Now check every day of the month.
    for d in days:
        # Classify the day.
        dtype = cfg.day_type(d)
        off_day = cfg.is_off_day(d)

        # Rule 1: minimum coverage per shift (Working days by default need
        # at least one Morning and one Night; configurable per day type).
        for shift in SHIFTS:
            need = cfg.min_coverage.get(dtype, {}).get(shift, 0)   # required count
            have = len(roster.on_shift(d, shift))                  # actual count
            if have < need:
                issues.append(Issue(ERROR, d, f"{dtype} day needs {need} on {SHIFT_NAMES[shift]} shift, has {have}"))

        # Rule 2: every night shift earns a comp off on the next working day
        # (weekends and holidays are skipped), with no shifts in between.
        for name in cfg.engineer_names:
            code = roster.code(name, d)
            # A comp off must never land on a weekend or holiday.
            if code == COMP_OFF and off_day:
                issues.append(Issue(ERROR, d, f"{name} has a comp off on a {dtype.lower()} - comp offs must be on working days"))
            # Only nights trigger the comp-off checks below.
            if code != NIGHT:
                continue
            # Where the comp off is due.
            co = cfg.comp_off_day(d)
            if co > last_day:
                # The comp off falls in next month - just a note, not an error.
                issues.append(Issue(INFO, d, f"{name} works night on {d:%d %b} - comp off due on {co:%a %d %b} (next month)"))
            elif roster.code(name, co) != COMP_OFF:
                # The comp off is due this month but is missing.
                issues.append(Issue(ERROR, co, f"{name} worked night on {d:%d %b} - comp off is due on this working day"))
            # Check that nothing is worked between the night and the comp off.
            rest = d + timedelta(days=1)
            while rest < co and rest <= last_day:
                if roster.code(name, rest) in WORKING_CODES:
                    issues.append(Issue(ERROR, rest, f"{name} is rostered to work before taking the comp off for the {d:%d %b} night"))
                rest += timedelta(days=1)

        # Rule 3: primary on-call - every day, non-SME, not in Morning/Night.
        p = roster.primary.get(d, "")
        if not p:
            # Every day must have a primary on-call.
            issues.append(Issue(ERROR, d, "No primary on-call engineer"))
        else:
            eng = cfg.engineer(p)          # the assigned engineer
            code = roster.code(p, d)       # what shift they are on that day
            if eng is None:
                issues.append(Issue(ERROR, d, f"Primary on-call '{p}' is not in the team"))
            elif eng.is_sme:
                # Primary on-call must be a non-SME.
                issues.append(Issue(ERROR, d, f"Primary on-call {p} is an SME (must be non-SME)"))
            if code in (MORNING, NIGHT):
                # They must not also be on a Morning or Night shift.
                issues.append(Issue(ERROR, d, f"Primary on-call {p} is also on {SHIFT_NAMES[code]} shift"))
            if code in ABSENT_CODES:
                # They must actually be available (not on leave/comp off).
                issues.append(Issue(ERROR, d, f"Primary on-call {p} is unavailable ({code})"))

        # Rule 4: secondary on-call - SME, required except weekends/holidays.
        s = roster.secondary.get(d, "")
        if not s:
            # A missing secondary is only a problem on working/freeze days.
            if not off_day:
                issues.append(Issue(ERROR, d, "No secondary on-call (SME) engineer"))
        else:
            eng = cfg.engineer(s)
            if eng is None:
                issues.append(Issue(ERROR, d, f"Secondary on-call '{s}' is not in the team"))
            elif not eng.is_sme:
                # Secondary on-call must be an SME.
                issues.append(Issue(ERROR, d, f"Secondary on-call {s} is not an SME"))
            if roster.code(s, d) in ABSENT_CODES:
                # They must be available.
                issues.append(Issue(ERROR, d, f"Secondary on-call {s} is unavailable ({roster.code(s, d)})"))
            if s == p:
                # One person cannot cover both on-call roles.
                issues.append(Issue(ERROR, d, f"{s} is both primary and secondary on-call"))

        # Requests (warnings, not hard rules): leave, shift requirements, overrides.
        for name in cfg.engineer_names:
            code = roster.code(name, d)
            lv = cfg.leave_on(name, d)
            # Requested leave but rostered to something else.
            if lv and code not in (LEAVE, LONG_LEAVE):
                issues.append(Issue(WARNING, d, f"{name} requested {'long ' if lv.long_leave else ''}leave but has {code}"))
            # A "Must" shift that was not honoured (and not overridden by leave).
            must = cfg.must_shift(name, d)
            if must and code != must and not lv:
                issues.append(Issue(WARNING, d, f"{name} must work {SHIFT_NAMES[must]} but has {code}"))
            # An "Avoid" shift that was assigned anyway.
            if code in cfg.avoided_shifts(name, d):
                issues.append(Issue(WARNING, d, f"{name} asked to avoid {SHIFT_NAMES[code]} but is rostered on it"))

        # On-call overrides that could not be used.
        ov = cfg.override_on(d)
        if ov:
            if ov.primary and ov.primary != p:
                issues.append(Issue(WARNING, d, f"Requested primary on-call {ov.primary} could not be used"))
            if ov.secondary and ov.secondary != s:
                issues.append(Issue(WARNING, d, f"Requested secondary on-call {ov.secondary} could not be used"))

    # A single informational note about how well preferences were met.
    met, requested = preference_stats(roster)
    if requested:
        issues.append(Issue(INFO, None, f"Shift preferences met on {met} of {requested} requested working days"))

    # Sort so errors come first, then warnings, then info, each in date order.
    order = {ERROR: 0, WARNING: 1, INFO: 2}
    issues.sort(key=lambda i: (order[i.severity], i.day or date.min))
    return issues


def preference_stats(roster: Roster) -> tuple[int, int]:
    """(days a preferred shift was given, working days with a preference)."""
    cfg = roster.config
    # ``met`` = preferences honoured; ``requested`` = preferences that applied.
    met = requested = 0
    for e in cfg.engineers:
        for d in roster.days:
            pref = cfg.preferred_shift(e.name, d)   # their preference that day (or None)
            code = roster.code(e.name, d)           # what they actually got
            # Only count days where they had a preference and worked a shift.
            if pref and code in WORKING_CODES:
                requested += 1
                met += code == pref                 # True (1) if it matched
    return met, requested


def precheck(cfg: RosterConfig, locks: Locks | None = None) -> list[Issue]:
    """Quick capacity check before generating: flags days where too few
    engineers are available to meet the rules at all."""
    # No locks means an empty lock set.
    locks = locks or Locks()
    issues: list[Issue] = []
    # Comp offs carried over occupy people on their due day.
    carried = cfg.carried_comp_offs()
    # The SME names, for the on-call availability checks.
    sme = {e.name for e in cfg.engineers if e.is_sme}
    for d in cfg.days:
        off_day = cfg.is_off_day(d)
        mins = cfg.min_coverage.get(cfg.day_type(d), {})
        # Work out who is actually available on this day.
        available = []
        for n in cfg.engineer_names:
            locked = locks.cell(n, d)
            if locked is not None:
                # A pinned real shift counts as available; a pinned off/leave does not.
                if locked in SHIFTS:
                    available.append(n)
                continue
            # Leave or a due comp off makes them unavailable.
            if cfg.leave_on(n, d) or carried.get(n) == d:
                continue
            available.append(n)
        # Split the available people into non-SMEs and SMEs.
        non_sme = [n for n in available if n not in sme]
        smes = [n for n in available if n in sme]
        # No non-SME means primary on-call cannot be filled.
        if not non_sme:
            issues.append(Issue(WARNING, d, "No non-SME engineer available for primary on-call"))
        # No SME on a working day means secondary on-call cannot be filled.
        if not off_day and not smes:
            issues.append(Issue(WARNING, d, "No SME available for secondary on-call"))
        # The minimum Morning/Evening/Night counts for this day.
        m, e, n = mins.get(MORNING, 0), mins.get(EVENING, 0), mins.get(NIGHT, 0)
        # On working days the primary on-call covers an Evening slot; on days
        # off they are on call from home, so they can't fill a shift.
        need = m + n + (max(e, 1) if not off_day else e + 1)
        if len(available) < need:
            # Build a readable "(Morning 1, Night 1, primary on-call)" list.
            parts = [f"{SHIFT_NAMES[sh]} {k}" for sh, k in ((MORNING, m), (EVENING, e), (NIGHT, n)) if k]
            issues.append(Issue(
                WARNING, d,
                f"Only {len(available)} engineer(s) available but at least {need} needed "
                f"({', '.join(parts + ['primary on-call'])})",
            ))
    return issues


def count(issues: list[Issue], severity: str) -> int:
    # How many issues have a given severity (used for the summary tiles).
    return sum(1 for i in issues if i.severity == severity)
