"""Checks a roster against the mandatory rules and the user's requests.

Errors are violations of mandatory rules; warnings are requests that could
not be honoured (leave, shift requirements) or informational notes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from .model import (
    ABSENT_CODES,
    COMP_OFF,
    LEAVE,
    LONG_LEAVE,
    MORNING,
    NIGHT,
    SHIFT_NAMES,
    SHIFTS,
    WORKING_CODES,
    Roster,
)

ERROR = "Error"
WARNING = "Warning"
INFO = "Info"


@dataclass
class Issue:
    severity: str
    day: date | None
    message: str

    def __str__(self) -> str:
        when = self.day.strftime("%d %b (%a)") if self.day else "Month"
        return f"[{self.severity}] {when}: {self.message}"


def validate(roster: Roster) -> list[Issue]:
    cfg = roster.config
    issues: list[Issue] = []
    days = roster.days
    last_day = days[-1]

    for d in days:
        dtype = cfg.day_type(d)
        off_day = cfg.is_off_day(d)

        # Rule 1: minimum coverage per shift (Working days by default need
        # at least one Morning and one Night; configurable per day type).
        for shift in SHIFTS:
            need = cfg.min_coverage.get(dtype, {}).get(shift, 0)
            have = len(roster.on_shift(d, shift))
            if have < need:
                issues.append(Issue(ERROR, d, f"{dtype} day needs {need} on {SHIFT_NAMES[shift]} shift, has {have}"))

        # Rule 2: every night shift earns a comp off on the next working day
        # (weekends and holidays are skipped), with no shifts in between.
        for name in cfg.engineer_names:
            code = roster.code(name, d)
            if code == COMP_OFF and off_day:
                issues.append(Issue(ERROR, d, f"{name} has a comp off on a {dtype.lower()} - comp offs must be on working days"))
            if code != NIGHT:
                continue
            co = cfg.comp_off_day(d)
            if co > last_day:
                issues.append(Issue(INFO, d, f"{name} works night on {d:%d %b} - comp off due on {co:%a %d %b} (next month)"))
            elif roster.code(name, co) != COMP_OFF:
                issues.append(Issue(ERROR, co, f"{name} worked night on {d:%d %b} - comp off is due on this working day"))
            rest = d + timedelta(days=1)
            while rest < co and rest <= last_day:
                if roster.code(name, rest) in WORKING_CODES:
                    issues.append(Issue(ERROR, rest, f"{name} is rostered to work before taking the comp off for the {d:%d %b} night"))
                rest += timedelta(days=1)

        # Rule 3: primary on-call - every day, non-SME, not in Morning/Night.
        p = roster.primary.get(d, "")
        if not p:
            issues.append(Issue(ERROR, d, "No primary on-call engineer"))
        else:
            eng = cfg.engineer(p)
            code = roster.code(p, d)
            if eng is None:
                issues.append(Issue(ERROR, d, f"Primary on-call '{p}' is not in the team"))
            elif eng.is_sme:
                issues.append(Issue(ERROR, d, f"Primary on-call {p} is an SME (must be non-SME)"))
            if code in (MORNING, NIGHT):
                issues.append(Issue(ERROR, d, f"Primary on-call {p} is also on {SHIFT_NAMES[code]} shift"))
            if code in ABSENT_CODES:
                issues.append(Issue(ERROR, d, f"Primary on-call {p} is unavailable ({code})"))

        # Rule 4: secondary on-call - SME, required except weekends/holidays.
        s = roster.secondary.get(d, "")
        if not s:
            if not off_day:
                issues.append(Issue(ERROR, d, "No secondary on-call (SME) engineer"))
        else:
            eng = cfg.engineer(s)
            if eng is None:
                issues.append(Issue(ERROR, d, f"Secondary on-call '{s}' is not in the team"))
            elif not eng.is_sme:
                issues.append(Issue(ERROR, d, f"Secondary on-call {s} is not an SME"))
            if roster.code(s, d) in ABSENT_CODES:
                issues.append(Issue(ERROR, d, f"Secondary on-call {s} is unavailable ({roster.code(s, d)})"))
            if s == p:
                issues.append(Issue(ERROR, d, f"{s} is both primary and secondary on-call"))

        # Requests: leave, shift requirements, on-call overrides.
        for name in cfg.engineer_names:
            code = roster.code(name, d)
            lv = cfg.leave_on(name, d)
            if lv and code not in (LEAVE, LONG_LEAVE):
                issues.append(Issue(WARNING, d, f"{name} requested {'long ' if lv.long_leave else ''}leave but has {code}"))
            must = cfg.must_shift(name, d)
            if must and code != must and not lv:
                issues.append(Issue(WARNING, d, f"{name} must work {SHIFT_NAMES[must]} but has {code}"))
            if code in cfg.avoided_shifts(name, d):
                issues.append(Issue(WARNING, d, f"{name} asked to avoid {SHIFT_NAMES[code]} but is rostered on it"))

        ov = cfg.override_on(d)
        if ov:
            if ov.primary and ov.primary != p:
                issues.append(Issue(WARNING, d, f"Requested primary on-call {ov.primary} could not be used"))
            if ov.secondary and ov.secondary != s:
                issues.append(Issue(WARNING, d, f"Requested secondary on-call {ov.secondary} could not be used"))

    order = {ERROR: 0, WARNING: 1, INFO: 2}
    issues.sort(key=lambda i: (order[i.severity], i.day or date.min))
    return issues


def count(issues: list[Issue], severity: str) -> int:
    return sum(1 for i in issues if i.severity == severity)

