"""Data model for the roster tool.

All user input is kept as plain dictionaries of strings (so the GUI and the
JSON config file share one format) and parsed into typed objects here.

This file is heavily commented, line by line, so it can be read as a guide to
how the tool represents a month's roster.
"""

# ``from __future__ import annotations`` makes every type hint in this file be
# stored as plain text rather than evaluated at import time. That lets us write
# modern hints such as ``str | None`` even on older Python versions.
from __future__ import annotations

# ``calendar`` gives us the number of days in a month (monthrange).
import calendar
# ``dataclass`` auto-writes __init__/__repr__ for our small record classes;
# ``field`` lets a dataclass field have a mutable default (like an empty list).
from dataclasses import dataclass, field
# ``date`` is a calendar day, ``datetime`` parses date/time text, and
# ``timedelta`` is a length of time (e.g. "one day") used to step between days.
from datetime import date, datetime, timedelta

# ---- Single-letter codes shown in each grid cell ----------------------------
# Keeping them as named constants means the rest of the code never hard-codes
# the letters, so a code can be renamed in one place.
MORNING = "M"        # morning shift
EVENING = "E"        # evening shift
NIGHT = "N"          # night shift
COMP_OFF = "CO"      # compensatory day off, earned after a night shift
LEAVE = "L"          # a normal leave day
LONG_LEAVE = "LL"    # a long leave day (vacation / medical)
WEEK_OFF = "WO"      # ordinary weekend off
HOLIDAY_OFF = "H"    # a public-holiday off

# The three real working shifts, in a fixed order.
SHIFTS = (MORNING, EVENING, NIGHT)
# Map each shift code to its full display name.
SHIFT_NAMES = {MORNING: "Morning", EVENING: "Evening", NIGHT: "Night"}
# The reverse map (lower-cased name -> code), so "morning" can be read back.
SHIFT_BY_NAME = {v.lower(): k for k, v in SHIFT_NAMES.items()}
# Codes that count as "working" (used when checking rest between night shifts).
WORKING_CODES = set(SHIFTS)
# Codes that mean the engineer is unavailable that day.
ABSENT_CODES = {COMP_OFF, LEAVE, LONG_LEAVE}
# Every code, in the order used for legends and summary columns.
ALL_CODES = (MORNING, EVENING, NIGHT, COMP_OFF, LEAVE, LONG_LEAVE, WEEK_OFF, HOLIDAY_OFF)
# A human-readable description of each code, shown in tooltips and legends.
CODE_DESCRIPTIONS = {
    MORNING: "Morning shift",
    EVENING: "Evening shift",
    NIGHT: "Night shift",
    COMP_OFF: "Comp off (after night shift)",
    LEAVE: "Leave",
    LONG_LEAVE: "Long leave",
    WEEK_OFF: "Weekend off",
    HOLIDAY_OFF: "Holiday",
}

# ---- Day categories ---------------------------------------------------------
# Every calendar day is exactly one of these four types.
WORKING = "Working"   # a normal working day
FREEZE = "Freeze"     # inside a release-freeze period (no minimum coverage)
WEEKEND = "Weekend"   # a configured weekend day
HOLIDAY = "Holiday"   # a public holiday
# All four, in the order shown on the Rules page.
DAY_TYPES = (WORKING, FREEZE, WEEKEND, HOLIDAY)

# ---- Shift-request modes ----------------------------------------------------
MUST = "Must"        # the engineer must work this shift
AVOID = "Avoid"      # the engineer must never work this shift
PREFER = "Prefer"    # the engineer would like this shift when the rules allow
# All three modes, used to validate user input.
REQUEST_MODES = (MUST, PREFER, AVOID)

# Short weekday labels, indexed the same way Python's date.weekday() returns
# (Monday = 0 ... Sunday = 6).
WEEKDAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

# Default start/end clock times per shift, used by the calendar (.ics) export.
DEFAULT_SHIFT_TIMES = {MORNING: ("06:00", "14:00"), EVENING: ("14:00", "22:00"), NIGHT: ("22:00", "06:00")}

# The counters carried from one month to the next so the rotation stays fair.
# (These key names match what Roster.counts() produces.)
CARRY_KEYS = (MORNING, EVENING, NIGHT, "Primary", "Secondary", "OffDayPrimary")

# The default minimum number of engineers required per shift, per day type.
# Working days need at least one Morning and one Night; everything else is 0.
DEFAULT_MIN_COVERAGE = {
    WORKING: {MORNING: 1, EVENING: 0, NIGHT: 1},
    FREEZE: {MORNING: 0, EVENING: 0, NIGHT: 0},
    WEEKEND: {MORNING: 0, EVENING: 0, NIGHT: 0},
    HOLIDAY: {MORNING: 0, EVENING: 0, NIGHT: 0},
}


def parse_date(value, year: int | None = None, month: int | None = None) -> date:
    """Parse ``YYYY-MM-DD`` (or ``DD/MM/YYYY``). A bare day number is taken
    as a day of the given year/month."""
    # If it is already a date object, hand it straight back.
    if isinstance(value, date):
        return value
    # Otherwise turn it into text and trim surrounding spaces.
    text = str(value).strip()
    # An empty string is not a valid date.
    if not text:
        raise ValueError("date is empty")
    # A plain number like "14" means "the 14th" of the supplied month/year.
    if text.isdigit() and year and month:
        return date(year, month, int(text))
    # Try each accepted written format in turn.
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            # strptime parses the text; .date() drops the (zero) time part.
            return datetime.strptime(text, fmt).date()
        except ValueError:
            # This format did not match; try the next one.
            pass
    # Nothing matched, so report a clear error.
    raise ValueError(f"invalid date '{text}' (use YYYY-MM-DD)")


def parse_range(start, end, year=None, month=None) -> tuple[date, date]:
    # Parse the start date (required).
    s = parse_date(start, year, month)
    # Parse the end date if one was given; otherwise the range is a single day.
    e = parse_date(end, year, month) if str(end or "").strip() else s
    # A backwards range (end before start) is a mistake.
    if e < s:
        raise ValueError(f"end date {e} is before start date {s}")
    # Return the (start, end) pair.
    return s, e


def parse_time(value) -> str:
    # Turn the value into trimmed text.
    text = str(value).strip()
    try:
        # Parse "HH:MM" and reformat it, which also normalises e.g. "6:00".
        return datetime.strptime(text, "%H:%M").strftime("%H:%M")
    except ValueError:
        # Re-raise with a friendlier message the user can act on.
        raise ValueError(f"invalid time '{text}' (use HH:MM, e.g. 06:00)")


def parse_bool(value) -> bool:
    # A real boolean is returned unchanged.
    if isinstance(value, bool):
        return value
    # Otherwise treat a set of common "true" spellings as True.
    return str(value).strip().lower() in ("1", "true", "yes", "y", "sme")


def parse_shift(value) -> str:
    # Trim the input text.
    text = str(value).strip()
    # Accept a code directly, e.g. "n" or "N".
    if text.upper() in SHIFTS:
        return text.upper()
    # Accept a full name, e.g. "Night".
    if text.lower() in SHIFT_BY_NAME:
        return SHIFT_BY_NAME[text.lower()]
    # Anything else is invalid.
    raise ValueError(f"invalid shift '{value}' (use Morning, Evening or Night)")


def daterange(start: date, end: date):
    """Yield each date from start to end inclusive (a small helper generator)."""
    # Begin at the start date.
    d = start
    # Keep going until we pass the end date.
    while d <= end:
        # Hand this day to the caller.
        yield d
        # Step forward one day.
        d += timedelta(days=1)


@dataclass
class Engineer:
    # One team member.
    name: str                    # their name (also the key used everywhere)
    designation: str = ""        # job title, shown for information only
    is_sme: bool = False         # True for subject-matter experts (secondary on-call)


@dataclass
class Leave:
    # A block of leave for one engineer.
    engineer: str                # whose leave it is
    start: date                  # first day off
    end: date                    # last day off
    long_leave: bool = False     # True renders it as LL instead of L
    note: str = ""               # optional free-text reason

    def covers(self, d: date) -> bool:
        # True if day ``d`` falls inside this leave block.
        return self.start <= d <= self.end


@dataclass
class ShiftRequirement:
    # A rule tying an engineer to (or away from) a shift over a date range.
    engineer: str                # whose requirement it is
    start: date                  # first day it applies
    end: date                    # last day it applies
    shift: str                   # the shift code it concerns
    mode: str = MUST             # Must, Prefer or Avoid
    note: str = ""               # optional free-text note

    def covers(self, d: date) -> bool:
        # True if day ``d`` falls inside this requirement's date range.
        return self.start <= d <= self.end


@dataclass
class OnCallOverride:
    # A hand-picked on-call assignment for one specific day.
    day: date                    # the day it applies to
    primary: str = ""            # forced primary on-call engineer (or "")
    secondary: str = ""          # forced secondary on-call engineer (or "")


@dataclass
class Holiday:
    # A public holiday.
    day: date                    # the date
    name: str = ""               # its name, e.g. "Diwali"


@dataclass
class FreezePeriod:
    # A range of days exempt from the minimum-coverage rule.
    start: date                  # first frozen day
    end: date                    # last frozen day
    note: str = ""               # optional note

    def covers(self, d: date) -> bool:
        # True if day ``d`` is inside the freeze period.
        return self.start <= d <= self.end


@dataclass
class RosterConfig:
    # Everything needed to build one month's roster.
    year: int                    # the roster year
    month: int                   # the roster month (1-12)
    # ``field(default_factory=...)`` gives each new config its own fresh list,
    # instead of all configs sharing one list.
    engineers: list[Engineer] = field(default_factory=list)
    leaves: list[Leave] = field(default_factory=list)
    requirements: list[ShiftRequirement] = field(default_factory=list)
    oncall_overrides: list[OnCallOverride] = field(default_factory=list)
    holidays: list[Holiday] = field(default_factory=list)
    freeze_periods: list[FreezePeriod] = field(default_factory=list)
    # Which weekday numbers count as the weekend (default Saturday=5, Sunday=6).
    weekend_days: set[int] = field(default_factory=lambda: {5, 6})
    # A per-day-type, per-shift copy of the default minimums (a deep-ish copy so
    # editing one config's minimums does not change the defaults).
    min_coverage: dict[str, dict[str, int]] = field(
        default_factory=lambda: {k: dict(v) for k, v in DEFAULT_MIN_COVERAGE.items()}
    )
    attempts: int = 300          # how many randomised attempts the generator makes
    seed: int | None = None      # optional random seed for reproducible output
    # Start/end clock times per shift, used by the calendar export.
    shift_times: dict[str, tuple[str, str]] = field(default_factory=lambda: dict(DEFAULT_SHIFT_TIMES))
    # ---- Carry-over from the previous month's roster ----
    carry_source: str = ""       # a label like "October 2026" for display
    carry_nights: list[tuple[str, date]] = field(default_factory=list)  # nights whose comp off is still due
    prior_counts: dict[str, dict[str, int]] = field(default_factory=dict)  # running totals for fairness

    # ---- calendar helpers -------------------------------------------------
    @property
    def days(self) -> list[date]:
        # monthrange returns (weekday_of_first, number_of_days); we want [1].
        n = calendar.monthrange(self.year, self.month)[1]
        # Build a list of every date in the month, day 1 to day n.
        return [date(self.year, self.month, i) for i in range(1, n + 1)]

    def day_type(self, d: date) -> str:
        # A holiday takes priority over everything else.
        if any(h.day == d for h in self.holidays):
            return HOLIDAY
        # Then weekends (d.weekday() is 0-6; check it against the weekend set).
        if d.weekday() in self.weekend_days:
            return WEEKEND
        # Then any freeze period covering this day.
        if any(f.covers(d) for f in self.freeze_periods):
            return FREEZE
        # Otherwise it is an ordinary working day.
        return WORKING

    def is_off_day(self, d: date) -> bool:
        # "Off" means weekend or holiday (freeze days are still worked).
        return self.day_type(d) in (WEEKEND, HOLIDAY)

    def comp_off_day(self, night: date) -> date:
        """The comp off for a night shift on ``night``: the next working
        (or freeze) day, skipping weekends and holidays. May fall in the
        next month."""
        # Start with the day after the night shift.
        d = night + timedelta(days=1)
        # Skip forward over any weekend/holiday days.
        while self.is_off_day(d):
            d += timedelta(days=1)
        # The first non-off day is where the comp off lands.
        return d

    def holiday_name(self, d: date) -> str:
        # Look for a holiday on this day and return its name.
        for h in self.holidays:
            if h.day == d:
                return h.name
        # No holiday on this day.
        return ""

    # ---- lookup helpers ---------------------------------------------------
    @property
    def engineer_names(self) -> list[str]:
        # Just the list of names, in team order.
        return [e.name for e in self.engineers]

    def engineer(self, name: str) -> Engineer | None:
        # Find the Engineer object with this name.
        for e in self.engineers:
            if e.name == name:
                return e
        # Not found.
        return None

    def leave_on(self, name: str, d: date) -> Leave | None:
        # Return the leave block covering (name, d), if any.
        for lv in self.leaves:
            if lv.engineer == name and lv.covers(d):
                return lv
        # No leave for this engineer on this day.
        return None

    def must_shift(self, name: str, d: date) -> str | None:
        """Shift the engineer must work on d. Requirements only apply on
        working/freeze days - weekends and holidays stay off."""
        # Nobody is forced to work on a weekend or holiday.
        if self.is_off_day(d):
            return None
        # Find a matching "Must" requirement and return its shift.
        for r in self.requirements:
            if r.engineer == name and r.mode == MUST and r.covers(d):
                return r.shift
        # No forced shift for this engineer today.
        return None

    def preferred_shift(self, name: str, d: date) -> str | None:
        """Soft preference - honoured when the rules allow (working days only)."""
        # Preferences do not apply on days off.
        if self.is_off_day(d):
            return None
        # Find a matching "Prefer" requirement and return its shift.
        for r in self.requirements:
            if r.engineer == name and r.mode == PREFER and r.covers(d):
                return r.shift
        # No preference for this engineer today.
        return None

    def carried_comp_offs(self) -> dict[str, date]:
        """Comp offs from last month's nights that fall in this month."""
        # The set of days in this month, for fast membership tests.
        days = set(self.days)
        # Build a mapping of engineer -> the day their carried comp off lands.
        out = {}
        for name, night in self.carry_nights:
            # Work out where each carried night's comp off would fall.
            co = self.comp_off_day(night)
            # Only keep it if it lands in this month and the engineer is present.
            if co in days and self.engineer(name):
                out[name] = co
        return out

    def avoided_shifts(self, name: str, d: date) -> set[str]:
        # The set of shifts this engineer asked to avoid on day ``d``.
        return {
            r.shift
            for r in self.requirements
            if r.engineer == name and r.mode == AVOID and r.covers(d)
        }

    def override_on(self, d: date) -> OnCallOverride | None:
        # Return the hand-picked on-call override for this day, if any.
        for o in self.oncall_overrides:
            if o.day == d:
                return o
        # No override for this day.
        return None

    # ---- (de)serialisation -----------------------------------------------
    @classmethod
    def from_dict(cls, data: dict) -> "RosterConfig":
        """Build a config from the plain-dict format used by the GUI and the
        JSON file. Raises ValueError with a readable message on bad input."""
        # Collect every problem so we can report them all at once at the end.
        errors: list[str] = []
        try:
            # Read and validate the year and month.
            year = int(data.get("year"))
            month = int(data.get("month"))
            # Constructing a date proves the month number is valid (1-12).
            date(year, month, 1)
        except (TypeError, ValueError):
            # A bad year/month is fatal - we cannot build any calendar without it.
            raise ValueError("Year/month is invalid")

        # Start with an empty config for this month.
        cfg = cls(year=year, month=month)

        # Track engineer names we have already added, to catch duplicates and
        # to validate references from leave/requirements/on-call.
        seen = set()
        # ``enumerate(..., 1)`` numbers the rows from 1 for friendly messages.
        for i, row in enumerate(data.get("engineers", []), 1):
            # Read and trim the name.
            name = str(row.get("name", "")).strip()
            if not name:
                # A nameless engineer is skipped with a note.
                errors.append(f"Engineer #{i}: name is empty")
                continue
            if name in seen:
                # Two engineers with the same name would be ambiguous.
                errors.append(f"Engineer '{name}' is listed twice")
                continue
            # Remember this name and add the Engineer object.
            seen.add(name)
            cfg.engineers.append(
                Engineer(name, str(row.get("designation", "")).strip(), parse_bool(row.get("sme", False)))
            )

        def check_engineer(name, where):
            # Helper: verify a referenced name is a real engineer.
            if name not in seen:
                errors.append(f"{where}: unknown engineer '{name}'")
                return False
            return True

        # Parse the two leave lists with one loop (leaves and long_leaves).
        for key, long_leave, label in (("leaves", False, "Leave"), ("long_leaves", True, "Long leave")):
            for i, row in enumerate(data.get(key, []), 1):
                # Whose leave this is.
                name = str(row.get("engineer", "")).strip()
                try:
                    # Parse the (start, end) date range.
                    s, e = parse_range(row.get("start"), row.get("end"), year, month)
                except ValueError as exc:
                    # A bad date range is recorded and skipped.
                    errors.append(f"{label} #{i} ({name}): {exc}")
                    continue
                # Only add the leave if the engineer name is valid.
                if check_engineer(name, f"{label} #{i}"):
                    cfg.leaves.append(Leave(name, s, e, long_leave, str(row.get("note", ""))))

        # Parse shift requirements (Must / Prefer / Avoid).
        for i, row in enumerate(data.get("requirements", []), 1):
            name = str(row.get("engineer", "")).strip()
            try:
                # Date range, the shift, and the mode all have to be valid.
                s, e = parse_range(row.get("start"), row.get("end"), year, month)
                shift = parse_shift(row.get("shift"))
                # Normalise the mode text ("must" -> "Must"), defaulting to Must.
                mode = str(row.get("mode", MUST)).strip().capitalize() or MUST
                if mode not in REQUEST_MODES:
                    raise ValueError(f"invalid type '{mode}' (use Must, Prefer or Avoid)")
            except ValueError as exc:
                errors.append(f"Shift requirement #{i} ({name}): {exc}")
                continue
            if check_engineer(name, f"Shift requirement #{i}"):
                cfg.requirements.append(ShiftRequirement(name, s, e, shift, mode, str(row.get("note", ""))))

        # Parse on-call overrides.
        for i, row in enumerate(data.get("oncall", []), 1):
            try:
                # The day the override applies to.
                d = parse_date(row.get("date"), year, month)
            except ValueError as exc:
                errors.append(f"On-call #{i}: {exc}")
                continue
            # Read the (optional) forced primary and secondary names.
            p = str(row.get("primary", "")).strip()
            s = str(row.get("secondary", "")).strip()
            ok = True
            # Validate whichever names are present.
            if p:
                ok &= check_engineer(p, f"On-call #{i} primary")
            if s:
                ok &= check_engineer(s, f"On-call #{i} secondary")
            # Only add the override if all named engineers are valid.
            if ok:
                cfg.oncall_overrides.append(OnCallOverride(d, p, s))

        # Parse holidays.
        for i, row in enumerate(data.get("holidays", []), 1):
            try:
                cfg.holidays.append(Holiday(parse_date(row.get("date"), year, month), str(row.get("name", ""))))
            except ValueError as exc:
                errors.append(f"Holiday #{i}: {exc}")

        # Parse freeze periods.
        for i, row in enumerate(data.get("freeze_periods", []), 1):
            try:
                s, e = parse_range(row.get("start"), row.get("end"), year, month)
                cfg.freeze_periods.append(FreezePeriod(s, e, str(row.get("note", ""))))
            except ValueError as exc:
                errors.append(f"Freeze period #{i}: {exc}")

        # Which weekdays are the weekend (only override if the key is present).
        if "weekend_days" in data:
            cfg.weekend_days = {int(x) for x in data["weekend_days"]}

        # Minimum coverage: a nested {day type: {shift name: number}} mapping.
        for dtype, mins in (data.get("min_coverage") or {}).items():
            # Ignore day-type keys we do not recognise.
            if dtype not in cfg.min_coverage:
                continue
            for shift, value in mins.items():
                try:
                    # Convert the shift name to a code and store a non-negative int.
                    shift = parse_shift(shift)
                    cfg.min_coverage[dtype][shift] = max(0, int(value))
                except ValueError:
                    errors.append(f"Minimum coverage {dtype}/{shift}: invalid number '{value}'")

        # Shift timings for the calendar export.
        for shift_name, times in (data.get("shift_times") or {}).items():
            try:
                shift = parse_shift(shift_name)
                # Store the (start, end) pair as validated "HH:MM" strings.
                cfg.shift_times[shift] = (parse_time(times.get("start")), parse_time(times.get("end")))
            except (ValueError, AttributeError) as exc:
                errors.append(f"Shift timing {shift_name}: {exc}")

        # Carry-over block from the previous month (may be absent -> {}).
        carry = data.get("carry_over") or {}
        # A display label such as "October 2026".
        cfg.carry_source = str(carry.get("source", ""))
        # Each pending night becomes an (engineer, date) pair.
        for row in carry.get("nights", []):
            try:
                cfg.carry_nights.append((str(row["engineer"]), parse_date(row["date"])))
            except (KeyError, ValueError):
                errors.append(f"Carry-over night {row}: invalid")
        # Running fairness totals per engineer (only the keys we track).
        for name, counts in (carry.get("prior_counts") or {}).items():
            cfg.prior_counts[name] = {k: int(v) for k, v in counts.items() if k in CARRY_KEYS}

        try:
            # Number of generation attempts, at least 1.
            cfg.attempts = max(1, int(data.get("attempts", cfg.attempts)))
        except (TypeError, ValueError):
            errors.append("Attempts must be a number")
        # An optional random seed; blank means "no seed".
        seed = str(data.get("seed", "") or "").strip()
        if seed:
            try:
                cfg.seed = int(seed)
            except ValueError:
                errors.append("Random seed must be a whole number")

        # If anything went wrong, raise them all together, one per line.
        if errors:
            raise ValueError("\n".join(errors))
        # Otherwise hand back the finished, validated config.
        return cfg


def empty_config_dict(year: int | None = None, month: int | None = None) -> dict:
    # Today's date, used to default the roster month.
    today = date.today()
    if year is None or month is None:
        # Rosters are usually planned ahead, so default to *next* month:
        # jump to the 1st, add 32 days (guaranteed into next month), snap to 1st.
        nxt = (today.replace(day=1) + timedelta(days=32)).replace(day=1)
        year, month = nxt.year, nxt.month
    # Return the blank input structure the GUI and web app start from.
    return {
        "year": year,
        "month": month,
        "engineers": [],
        "leaves": [],
        "long_leaves": [],
        "requirements": [],
        "oncall": [],
        "holidays": [],
        "freeze_periods": [],
        "weekend_days": [5, 6],
        # Minimums keyed by full shift *name* (that is the on-disk format).
        "min_coverage": {k: {SHIFT_NAMES[s]: n for s, n in v.items()} for k, v in DEFAULT_MIN_COVERAGE.items()},
        "attempts": 300,
        "seed": "",
        # Shift timings keyed by full shift name, as {start, end} objects.
        "shift_times": {SHIFT_NAMES[s]: {"start": a, "end": b} for s, (a, b) in DEFAULT_SHIFT_TIMES.items()},
        "carry_over": {},
    }


@dataclass
class Locks:
    """Cells the user has pinned. Generation keeps them and fills the rest."""

    # Pinned engineer cells: (engineer name, day) -> the code to keep.
    cells: dict[tuple[str, date], str] = field(default_factory=dict)
    # Pinned primary on-call per day: day -> engineer name.
    primary: dict[date, str] = field(default_factory=dict)
    # Pinned secondary on-call per day: day -> engineer name.
    secondary: dict[date, str] = field(default_factory=dict)

    def __bool__(self) -> bool:
        # ``if locks:`` is True when anything at all is pinned.
        return bool(self.cells or self.primary or self.secondary)

    def cell(self, name: str, d: date) -> str | None:
        # The pinned code for (name, d), or None if that cell is not locked.
        return self.cells.get((name, d))

    def copy(self) -> "Locks":
        # A shallow copy so edits to the copy do not touch the original dicts.
        return Locks(dict(self.cells), dict(self.primary), dict(self.secondary))


@dataclass
class Roster:
    """A generated (and possibly hand-edited) roster for one month."""

    config: RosterConfig                 # the inputs this roster was built from
    grid: dict[str, dict[date, str]]     # engineer -> day -> code
    primary: dict[date, str]             # day -> primary on-call engineer ("" if none)
    secondary: dict[date, str]           # day -> secondary on-call engineer
    locks: Locks = field(default_factory=Locks)  # any pinned cells

    @property
    def days(self) -> list[date]:
        # Convenience: the month's days come straight from the config.
        return self.config.days

    def code(self, name: str, d: date) -> str:
        # The code in one cell, or "" if nothing has been assigned there.
        return self.grid.get(name, {}).get(d, "")

    def on_shift(self, d: date, shift: str) -> list[str]:
        # Everyone working ``shift`` on day ``d``.
        return [n for n in self.config.engineer_names if self.code(n, d) == shift]

    def counts(self, name: str) -> dict[str, int]:
        # Start every code count at zero.
        result = {c: 0 for c in ALL_CODES}
        # Tally how many of each code this engineer has this month.
        for d in self.days:
            c = self.code(name, d)
            if c in result:
                result[c] += 1
        # Count on-call duties too.
        result["Primary"] = sum(1 for d in self.days if self.primary.get(d) == name)
        result["Secondary"] = sum(1 for d in self.days if self.secondary.get(d) == name)
        # Primary on-call specifically on days off (weekend/holiday), for fairness.
        result["OffDayPrimary"] = sum(1 for d in self.days if self.primary.get(d) == name and self.config.is_off_day(d))
        return result

    def total_counts(self, name: str) -> dict[str, int]:
        """This month's counts plus the carried-over running totals."""
        # Start from this month's counts.
        result = self.counts(name)
        # Add the totals carried over from previous months, key by key.
        for k, v in self.config.prior_counts.get(name, {}).items():
            result[k] = result.get(k, 0) + v
        return result

    def copy(self) -> "Roster":
        # A deep-enough copy: the config is shared, but the grid, on-call maps
        # and locks are duplicated so edits to the copy do not affect this one.
        return Roster(
            self.config,
            {n: dict(days) for n, days in self.grid.items()},
            dict(self.primary),
            dict(self.secondary),
            self.locks.copy(),
        )
