"""iCalendar (.ics) export - one calendar per engineer, plus a team calendar.

Shifts become timed events (using the shift timings from the Rules page);
on-call, comp offs and leave become all-day events. Event UIDs are stable, so
importing an updated file replaces events in calendars that support updates.

This file is commented line by line. ".ics" is the standard calendar file
format understood by Outlook, Google Calendar and Apple Calendar.
"""

from __future__ import annotations

# ``calendar`` for month names; ``os``/``re`` for writing safely-named files;
# date/time helpers for building event timestamps.
import calendar
import os
import re
from datetime import date, datetime, timedelta, timezone

# The codes and names the events describe.
from .model import COMP_OFF, LEAVE, LONG_LEAVE, SHIFT_NAMES, SHIFTS, Roster

# Codes that become all-day events, mapped to their calendar title.
ALL_DAY = {COMP_OFF: "Comp off", LEAVE: "Leave", LONG_LEAVE: "Long leave"}


def _escape(text: str) -> str:
    # The .ics format needs backslashes, semicolons, commas and newlines escaped.
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line: str) -> str:
    """Fold lines longer than 75 octets (RFC 5545)."""
    # The spec requires long lines to be wrapped, continuing with a leading space.
    out, cur = [], ""
    for ch in line:
        # If adding this character would exceed 75 bytes, start a new folded line.
        if len((cur + ch).encode("utf-8")) > 75:
            out.append(cur)
            cur = " " + ch    # continuation lines begin with a space
        else:
            cur += ch
    out.append(cur)
    # Join with CRLF, as the calendar format requires.
    return "\r\n".join(out)


def _slug(text: str) -> str:
    # Make a safe id fragment: lowercase, non-alphanumerics to dashes.
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "x"


def _event(uid: str, summary: str, start: str, end: str, all_day: bool, description: str = "") -> list[str]:
    # Build the lines of one VEVENT (a single calendar entry).
    # A UTC timestamp of when this file was produced.
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    # All-day events use DATE values rather than DATE-TIME.
    kind = ";VALUE=DATE" if all_day else ""
    lines = [
        "BEGIN:VEVENT",
        f"UID:{uid}@roster-creator",   # stable id so re-imports update, not duplicate
        f"DTSTAMP:{stamp}",
        f"DTSTART{kind}:{start}",       # when it starts
        f"DTEND{kind}:{end}",           # when it ends
        f"SUMMARY:{_escape(summary)}",  # the title shown in the calendar
    ]
    if description:
        lines.append(f"DESCRIPTION:{_escape(description)}")
    # Timed events are "busy" (OPAQUE); all-day markers are "free" (TRANSPARENT).
    lines += ["TRANSP:OPAQUE" if not all_day else "TRANSP:TRANSPARENT", "END:VEVENT"]
    return lines


def _events_for(roster: Roster, name: str, prefix: str = "") -> list[str]:
    # Build every calendar event for one engineer.
    cfg = roster.config
    lines: list[str] = []
    for d in roster.days:
        code = roster.code(name, d)                    # their code that day
        ymd = d.strftime("%Y%m%d")                     # this day, as YYYYMMDD
        nxt = (d + timedelta(days=1)).strftime("%Y%m%d")  # next day (all-day end)
        if code in SHIFTS:
            # A real shift becomes a timed event using the configured times.
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
            # Comp off / leave become all-day events.
            lines += _event(f"{_slug(name)}-{ymd}-absence", f"{prefix}{ALL_DAY[code]}", ymd, nxt, True)
        # On-call duty becomes an all-day marker on its day.
        for role, table in (("Primary", roster.primary), ("Secondary", roster.secondary)):
            if table.get(d) == name:
                lines += _event(f"{_slug(name)}-{ymd}-{role.lower()}", f"{prefix}{role} on-call", ymd, nxt, True)
    return lines


def build_calendar(roster: Roster, name: str | None = None) -> str:
    """The .ics text for one engineer, or for the whole team when name is None."""
    cfg = roster.config
    # A label like "October 2026".
    month = f"{calendar.month_name[cfg.month]} {cfg.year}"
    # The calendar's display name.
    title = f"Roster {month} - {name}" if name else f"Team roster {month}"
    # The required calendar header lines.
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Roster Creator//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_escape(title)}",
    ]
    # One engineer, or everyone (team calendar prefixes each event with a name).
    names = [name] if name else cfg.engineer_names
    for n in names:
        lines += _events_for(roster, n, prefix="" if name else f"{n}: ")
    lines.append("END:VCALENDAR")
    # Fold every line and join with CRLF, ending with a trailing CRLF.
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"


def export_all(roster: Roster, folder: str) -> list[str]:
    """Write one .ics per engineer plus a team calendar; returns the paths."""
    cfg = roster.config
    # A "YYYY-MM" tag for the filenames.
    tag = date(cfg.year, cfg.month, 1).strftime("%Y-%m")
    # Make sure the destination folder exists.
    os.makedirs(folder, exist_ok=True)
    paths = []
    # ``+ [None]`` adds the whole-team calendar at the end.
    for name in cfg.engineer_names + [None]:
        # A filesystem-safe file name (strip characters Windows dislikes).
        safe = re.sub(r'[\\/:*?"<>|]+', "_", name) if name else "Team"
        path = os.path.join(folder, f"{safe} - roster {tag}.ics")
        # Write with newline="" so our explicit CRLFs are not altered.
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(build_calendar(roster, name))
        paths.append(path)
    return paths
