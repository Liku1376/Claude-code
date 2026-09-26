"""Data model for the roster tool.

All user input is kept as plain dictionaries of strings (so the GUI and the
JSON config file share one format) and parsed into typed objects here.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

# Shift / status codes used in the roster grid.
MORNING = "M"
EVENING = "E"
NIGHT = "N"
COMP_OFF = "CO"
LEAVE = "L"
LONG_LEAVE = "LL"
WEEK_OFF = "WO"
HOLIDAY_OFF = "H"

SHIFTS = (MORNING, EVENING, NIGHT)
SHIFT_NAMES = {MORNING: "Morning", EVENING: "Evening", NIGHT: "Night"}
SHIFT_BY_NAME = {v.lower(): k for k, v in SHIFT_NAMES.items()}
WORKING_CODES = set(SHIFTS)
ABSENT_CODES = {COMP_OFF, LEAVE, LONG_LEAVE}
ALL_CODES = (MORNING, EVENING, NIGHT, COMP_OFF, LEAVE, LONG_LEAVE, WEEK_OFF, HOLIDAY_OFF)
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

# Day categories.
WORKING = "Working"
FREEZE = "Freeze"
WEEKEND = "Weekend"
HOLIDAY = "Holiday"
DAY_TYPES = (WORKING, FREEZE, WEEKEND, HOLIDAY)

MUST = "Must"
AVOID = "Avoid"
PREFER = "Prefer"
REQUEST_MODES = (MUST, PREFER, AVOID)

WEEKDAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

DEFAULT_SHIFT_TIMES = {MORNING: ("06:00", "14:00"), EVENING: ("14:00", "22:00"), NIGHT: ("22:00", "06:00")}

# Counters carried from month to month for fairness (see Roster.counts).
CARRY_KEYS = (MORNING, EVENING, NIGHT, "Primary", "Secondary", "OffDayPrimary")

DEFAULT_MIN_COVERAGE = {
    WORKING: {MORNING: 1, EVENING: 0, NIGHT: 1},
    FREEZE: {MORNING: 0, EVENING: 0, NIGHT: 0},
    WEEKEND: {MORNING: 0, EVENING: 0, NIGHT: 0},
    HOLIDAY: {MORNING: 0, EVENING: 0, NIGHT: 0},
}


def parse_date(value, year: int | None = None, month: int | None = None) -> date:
    """Parse ``YYYY-MM-DD`` (or ``DD/MM/YYYY``). A bare day number is taken
    as a day of the given year/month."""
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        raise ValueError("date is empty")
    if text.isdigit() and year and month:
        return date(year, month, int(text))
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"invalid date '{text}' (use YYYY-MM-DD)")


def parse_range(start, end, year=None, month=None) -> tuple[date, date]:
    s = parse_date(start, year, month)
    e = parse_date(end, year, month) if str(end or "").strip() else s
    if e < s:
        raise ValueError(f"end date {e} is before start date {s}")
    return s, e


def parse_time(value) -> str:
    text = str(value).strip()
    try:
        return datetime.strptime(text, "%H:%M").strftime("%H:%M")
    except ValueError:
        raise ValueError(f"invalid time '{text}' (use HH:MM, e.g. 06:00)")


def parse_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "y", "sme")


def parse_shift(value) -> str:
    text = str(value).strip()
    if text.upper() in SHIFTS:
        return text.upper()
    if text.lower() in SHIFT_BY_NAME:
        return SHIFT_BY_NAME[text.lower()]
    raise ValueError(f"invalid shift '{value}' (use Morning, Evening or Night)")


def daterange(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


@dataclass
class Engineer:
    name: str
    designation: str = ""
    is_sme: bool = False


@dataclass
class Leave:
    engineer: str
    start: date
    end: date
    long_leave: bool = False
    note: str = ""

    def covers(self, d: date) -> bool:
        return self.start <= d <= self.end


@dataclass
class ShiftRequirement:
    engineer: str
    start: date
    end: date
    shift: str
    mode: str = MUST  # MUST or AVOID
    note: str = ""

    def covers(self, d: date) -> bool:
        return self.start <= d <= self.end


@dataclass
class OnCallOverride:
    day: date
    primary: str = ""
    secondary: str = ""


@dataclass
class Holiday:
    day: date
    name: str = ""


@dataclass
class FreezePeriod:
    start: date
    end: date
    note: str = ""

    def covers(self, d: date) -> bool:
        return self.start <= d <= self.end


@dataclass
class RosterConfig:
    year: int
    month: int
    engineers: list[Engineer] = field(default_factory=list)
    leaves: list[Leave] = field(default_factory=list)
    requirements: list[ShiftRequirement] = field(default_factory=list)
    oncall_overrides: list[OnCallOverride] = field(default_factory=list)
    holidays: list[Holiday] = field(default_factory=list)
    freeze_periods: list[FreezePeriod] = field(default_factory=list)
    weekend_days: set[int] = field(default_factory=lambda: {5, 6})
    min_coverage: dict[str, dict[str, int]] = field(
        default_factory=lambda: {k: dict(v) for k, v in DEFAULT_MIN_COVERAGE.items()}
    )
    attempts: int = 300
    seed: int | None = None
    shift_times: dict[str, tuple[str, str]] = field(default_factory=lambda: dict(DEFAULT_SHIFT_TIMES))
    # Carry-over from the previous month's roster.
    carry_source: str = ""
    carry_nights: list[tuple[str, date]] = field(default_factory=list)  # nights whose comp off is still due
    prior_counts: dict[str, dict[str, int]] = field(default_factory=dict)  # running totals for fairness

    # ---- calendar helpers -------------------------------------------------
    @property
    def days(self) -> list[date]:
        n = calendar.monthrange(self.year, self.month)[1]
        return [date(self.year, self.month, i) for i in range(1, n + 1)]

    def day_type(self, d: date) -> str:
        if any(h.day == d for h in self.holidays):
            return HOLIDAY
        if d.weekday() in self.weekend_days:
            return WEEKEND
        if any(f.covers(d) for f in self.freeze_periods):
            return FREEZE
        return WORKING

    def is_off_day(self, d: date) -> bool:
        return self.day_type(d) in (WEEKEND, HOLIDAY)

    def comp_off_day(self, night: date) -> date:
        """The comp off for a night shift on ``night``: the next working
        (or freeze) day, skipping weekends and holidays. May fall in the
        next month."""
        d = night + timedelta(days=1)
        while self.is_off_day(d):
            d += timedelta(days=1)
        return d

    def holiday_name(self, d: date) -> str:
        for h in self.holidays:
            if h.day == d:
                return h.name
        return ""

    # ---- lookup helpers ---------------------------------------------------
    @property
    def engineer_names(self) -> list[str]:
        return [e.name for e in self.engineers]

    def engineer(self, name: str) -> Engineer | None:
        for e in self.engineers:
            if e.name == name:
                return e
        return None

    def leave_on(self, name: str, d: date) -> Leave | None:
        for lv in self.leaves:
            if lv.engineer == name and lv.covers(d):
                return lv
        return None

    def must_shift(self, name: str, d: date) -> str | None:
        """Shift the engineer must work on d. Requirements only apply on
        working/freeze days - weekends and holidays stay off."""
        if self.is_off_day(d):
            return None
        for r in self.requirements:
            if r.engineer == name and r.mode == MUST and r.covers(d):
                return r.shift
        return None

    def preferred_shift(self, name: str, d: date) -> str | None:
        """Soft preference - honoured when the rules allow (working days only)."""
        if self.is_off_day(d):
            return None
        for r in self.requirements:
            if r.engineer == name and r.mode == PREFER and r.covers(d):
                return r.shift
        return None

    def carried_comp_offs(self) -> dict[str, date]:
        """Comp offs from last month's nights that fall in this month."""
        days = set(self.days)
        out = {}
        for name, night in self.carry_nights:
            co = self.comp_off_day(night)
            if co in days and self.engineer(name):
                out[name] = co
        return out

    def avoided_shifts(self, name: str, d: date) -> set[str]:
        return {
            r.shift
            for r in self.requirements
            if r.engineer == name and r.mode == AVOID and r.covers(d)
        }

    def override_on(self, d: date) -> OnCallOverride | None:
        for o in self.oncall_overrides:
            if o.day == d:
                return o
        return None

    # ---- (de)serialisation -----------------------------------------------
    @classmethod
    def from_dict(cls, data: dict) -> "RosterConfig":
        """Build a config from the plain-dict format used by the GUI and the
        JSON file. Raises ValueError with a readable message on bad input."""
        errors: list[str] = []
        try:
            year = int(data.get("year"))
            month = int(data.get("month"))
            date(year, month, 1)
        except (TypeError, ValueError):
            raise ValueError("Year/month is invalid")

        cfg = cls(year=year, month=month)

        seen = set()
        for i, row in enumerate(data.get("engineers", []), 1):
            name = str(row.get("name", "")).strip()
            if not name:
                errors.append(f"Engineer #{i}: name is empty")
                continue
            if name in seen:
                errors.append(f"Engineer '{name}' is listed twice")
                continue
            seen.add(name)
            cfg.engineers.append(
                Engineer(name, str(row.get("designation", "")).strip(), parse_bool(row.get("sme", False)))
            )

        def check_engineer(name, where):
            if name not in seen:
                errors.append(f"{where}: unknown engineer '{name}'")
                return False
            return True

        for key, long_leave, label in (("leaves", False, "Leave"), ("long_leaves", True, "Long leave")):
            for i, row in enumerate(data.get(key, []), 1):
                name = str(row.get("engineer", "")).strip()
                try:
                    s, e = parse_range(row.get("start"), row.get("end"), year, month)
                except ValueError as exc:
                    errors.append(f"{label} #{i} ({name}): {exc}")
                    continue
                if check_engineer(name, f"{label} #{i}"):
                    cfg.leaves.append(Leave(name, s, e, long_leave, str(row.get("note", ""))))

        for i, row in enumerate(data.get("requirements", []), 1):
            name = str(row.get("engineer", "")).strip()
            try:
                s, e = parse_range(row.get("start"), row.get("end"), year, month)
                shift = parse_shift(row.get("shift"))
                mode = str(row.get("mode", MUST)).strip().capitalize() or MUST
                if mode not in REQUEST_MODES:
                    raise ValueError(f"invalid type '{mode}' (use Must, Prefer or Avoid)")
            except ValueError as exc:
                errors.append(f"Shift requirement #{i} ({name}): {exc}")
                continue
            if check_engineer(name, f"Shift requirement #{i}"):
                cfg.requirements.append(ShiftRequirement(name, s, e, shift, mode, str(row.get("note", ""))))

        for i, row in enumerate(data.get("oncall", []), 1):
            try:
                d = parse_date(row.get("date"), year, month)
            except ValueError as exc:
                errors.append(f"On-call #{i}: {exc}")
                continue
            p = str(row.get("primary", "")).strip()
            s = str(row.get("secondary", "")).strip()
            ok = True
            if p:
                ok &= check_engineer(p, f"On-call #{i} primary")
            if s:
                ok &= check_engineer(s, f"On-call #{i} secondary")
            if ok:
                cfg.oncall_overrides.append(OnCallOverride(d, p, s))

        for i, row in enumerate(data.get("holidays", []), 1):
            try:
                cfg.holidays.append(Holiday(parse_date(row.get("date"), year, month), str(row.get("name", ""))))
            except ValueError as exc:
                errors.append(f"Holiday #{i}: {exc}")

        for i, row in enumerate(data.get("freeze_periods", []), 1):
            try:
                s, e = parse_range(row.get("start"), row.get("end"), year, month)
                cfg.freeze_periods.append(FreezePeriod(s, e, str(row.get("note", ""))))
            except ValueError as exc:
                errors.append(f"Freeze period #{i}: {exc}")

        if "weekend_days" in data:
            cfg.weekend_days = {int(x) for x in data["weekend_days"]}

        for dtype, mins in (data.get("min_coverage") or {}).items():
            if dtype not in cfg.min_coverage:
                continue
            for shift, value in mins.items():
                try:
                    shift = parse_shift(shift)
                    cfg.min_coverage[dtype][shift] = max(0, int(value))
                except ValueError:
                    errors.append(f"Minimum coverage {dtype}/{shift}: invalid number '{value}'")

        for shift_name, times in (data.get("shift_times") or {}).items():
            try:
                shift = parse_shift(shift_name)
                cfg.shift_times[shift] = (parse_time(times.get("start")), parse_time(times.get("end")))
            except (ValueError, AttributeError) as exc:
                errors.append(f"Shift timing {shift_name}: {exc}")

        carry = data.get("carry_over") or {}
        cfg.carry_source = str(carry.get("source", ""))
        for row in carry.get("nights", []):
            try:
                cfg.carry_nights.append((str(row["engineer"]), parse_date(row["date"])))
            except (KeyError, ValueError):
                errors.append(f"Carry-over night {row}: invalid")
        for name, counts in (carry.get("prior_counts") or {}).items():
            cfg.prior_counts[name] = {k: int(v) for k, v in counts.items() if k in CARRY_KEYS}

        try:
            cfg.attempts = max(1, int(data.get("attempts", cfg.attempts)))
        except (TypeError, ValueError):
            errors.append("Attempts must be a number")
        seed = str(data.get("seed", "") or "").strip()
        if seed:
            try:
                cfg.seed = int(seed)
            except ValueError:
                errors.append("Random seed must be a whole number")

        if errors:
            raise ValueError("\n".join(errors))
        return cfg


def empty_config_dict(year: int | None = None, month: int | None = None) -> dict:
    today = date.today()
    if year is None or month is None:
        # Default to next month - rosters are usually planned ahead.
        nxt = (today.replace(day=1) + timedelta(days=32)).replace(day=1)
        year, month = nxt.year, nxt.month
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
        "min_coverage": {k: {SHIFT_NAMES[s]: n for s, n in v.items()} for k, v in DEFAULT_MIN_COVERAGE.items()},
        "attempts": 300,
        "seed": "",
        "shift_times": {SHIFT_NAMES[s]: {"start": a, "end": b} for s, (a, b) in DEFAULT_SHIFT_TIMES.items()},
        "carry_over": {},
    }


@dataclass
class Locks:
    """Cells the user has pinned. Generation keeps them and fills the rest."""

    cells: dict[tuple[str, date], str] = field(default_factory=dict)  # (engineer, day) -> code
    primary: dict[date, str] = field(default_factory=dict)
    secondary: dict[date, str] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return bool(self.cells or self.primary or self.secondary)

    def cell(self, name: str, d: date) -> str | None:
        return self.cells.get((name, d))

    def copy(self) -> "Locks":
        return Locks(dict(self.cells), dict(self.primary), dict(self.secondary))


@dataclass
class Roster:
    """A generated (and possibly hand-edited) roster for one month."""

    config: RosterConfig
    grid: dict[str, dict[date, str]]  # engineer -> day -> code
    primary: dict[date, str]  # day -> engineer ("" if none)
    secondary: dict[date, str]
    locks: Locks = field(default_factory=Locks)

    @property
    def days(self) -> list[date]:
        return self.config.days

    def code(self, name: str, d: date) -> str:
        return self.grid.get(name, {}).get(d, "")

    def on_shift(self, d: date, shift: str) -> list[str]:
        return [n for n in self.config.engineer_names if self.code(n, d) == shift]

    def counts(self, name: str) -> dict[str, int]:
        result = {c: 0 for c in ALL_CODES}
        for d in self.days:
            c = self.code(name, d)
            if c in result:
                result[c] += 1
        result["Primary"] = sum(1 for d in self.days if self.primary.get(d) == name)
        result["Secondary"] = sum(1 for d in self.days if self.secondary.get(d) == name)
        result["OffDayPrimary"] = sum(1 for d in self.days if self.primary.get(d) == name and self.config.is_off_day(d))
        return result

    def total_counts(self, name: str) -> dict[str, int]:
        """This month's counts plus the carried-over running totals."""
        result = self.counts(name)
        for k, v in self.config.prior_counts.get(name, {}).items():
            result[k] = result.get(k, 0) + v
        return result

    def copy(self) -> "Roster":
        return Roster(
            self.config,
            {n: dict(days) for n, days in self.grid.items()},
            dict(self.primary),
            dict(self.secondary),
            self.locks.copy(),
        )
