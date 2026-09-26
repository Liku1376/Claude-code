"""iCalendar (.ics) export - one calendar per engineer, plus a team calendar.

Shifts become timed events (using the shift timings from the Rules page);
on-call, comp offs and leave become all-day events. Event UIDs are stable, so
importing an updated file replaces events in calendars that support updates.
"""

from __future__ import annotations

import calendar
import os
import re
from datetime import date, datetime, timedelta, timezone

from .model import COMP_OFF, LEAVE, LONG_LEAVE, SHIFT_NAMES, SHIFTS, Roster

ALL_DAY = {COMP_OFF: "Comp off", LEAVE: "Leave", LONG_LEAVE: "Long leave"}


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line: str) -> str:
    """Fold lines longer than 75 octets (RFC 5545)."""
    out, cur = [], ""
    for ch in line:
        if len((cur + ch).encode("utf-8")) > 75:
            out.append(cur)
            cur = " " + ch
        else:
            cur += ch
    out.append(cur)
    return "\r\n".join(out)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "x"


def _event(uid: str, summary: str, start: str, end: str, all_day: bool, description: str = "") -> list[str]:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    kind = ";VALUE=DATE" if all_day else ""
    lines = [
        "BEGIN:VEVENT",
        f"UID:{uid}@roster-creator",
        f"DTSTAMP:{stamp}",
        f"DTSTART{kind}:{start}",
        f"DTEND{kind}:{end}",
        f"SUMMARY:{_escape(summary)}",
    ]
    if description:
        lines.append(f"DESCRIPTION:{_escape(description)}")
    lines += ["TRANSP:OPAQUE" if not all_day else "TRANSP:TRANSPARENT", "END:VEVENT"]
    return lines


def _events_for(roster: Roster, name: str, prefix: str = "") -> list[str]:
    cfg = roster.config
    lines: list[str] = []
    for d in roster.days:
        code = roster.code(name, d)
        ymd = d.strftime("%Y%m%d")
        nxt = (d + timedelta(days=1)).strftime("%Y%m%d")
        if code in SHIFTS:
            start_s, end_s = cfg.shift_times[code]
            start = datetime.combine(d, datetime.strptime(start_s, "%H:%M").time())
            end = datetime.combine(d, datetime.strptime(end_s, "%H:%M").time())
            if end <= start:  # e.g. night 22:00-06:00 ends next morning
                end += timedelta(days=1)
            lines += _event(
                f"{_slug(name)}-{ymd}-shift", f"{prefix}{SHIFT_NAMES[code]} shift",
                start.strftime("%Y%m%dT%H%M%S"), end.strftime("%Y%m%dT%H%M%S"), False,
                f"{SHIFT_NAMES[code]} shift {start_s}-{end_s}",
            )
        elif code in ALL_DAY:
            lines += _event(f"{_slug(name)}-{ymd}-absence", f"{prefix}{ALL_DAY[code]}", ymd, nxt, True)
        for role, table in (("Primary", roster.primary), ("Secondary", roster.secondary)):
            if table.get(d) == name:
                lines += _event(f"{_slug(name)}-{ymd}-{role.lower()}", f"{prefix}{role} on-call", ymd, nxt, True)
    return lines


def build_calendar(roster: Roster, name: str | None = None) -> str:
    """The .ics text for one engineer, or for the whole team when name is None."""
    cfg = roster.config
    month = f"{calendar.month_name[cfg.month]} {cfg.year}"
    title = f"Roster {month} - {name}" if name else f"Team roster {month}"
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Roster Creator//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_escape(title)}",
    ]
    names = [name] if name else cfg.engineer_names
    for n in names:
        lines += _events_for(roster, n, prefix="" if name else f"{n}: ")
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"


def export_all(roster: Roster, folder: str) -> list[str]:
    """Write one .ics per engineer plus a team calendar; returns the paths."""
    cfg = roster.config
    tag = date(cfg.year, cfg.month, 1).strftime("%Y-%m")
    os.makedirs(folder, exist_ok=True)
    paths = []
    for name in cfg.engineer_names + [None]:
        safe = re.sub(r'[\\/:*?"<>|]+', "_", name) if name else "Team"
        path = os.path.join(folder, f"{safe} - roster {tag}.ics")
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(build_calendar(roster, name))
        paths.append(path)
    return paths
