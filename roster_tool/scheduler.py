"""Roster generation.

A greedy day-by-day builder fills each day in rule priority order
(locked cells -> leave/comp-off -> fixed requests -> primary on-call ->
secondary on-call -> night -> morning -> evening -> everyone else). Ties are
broken by fairness counters (including totals carried over from previous
months) and then randomly; many randomised attempts are generated and the one
with the fewest rule violations and the most even workload wins.

This file is commented line by line to explain the scheduling algorithm.
"""

from __future__ import annotations

# ``random`` drives the many randomised attempts; a seeded generator makes runs
# reproducible.
import random
# ``statistics`` gives us pstdev (population standard deviation) for fairness.
import statistics
# ``Counter`` is a dict that counts things (used for per-engineer tallies).
from collections import Counter
# Dates and day-stepping.
from datetime import date, timedelta

# Import the codes, day types and data classes the algorithm works with.
from .model import (
    COMP_OFF,
    EVENING,
    HOLIDAY,
    HOLIDAY_OFF,
    LEAVE,
    LONG_LEAVE,
    MORNING,
    NIGHT,
    SHIFTS,
    WEEK_OFF,
    Locks,
    Roster,
    RosterConfig,
)
# The validator scores each candidate roster; preference_stats counts honoured
# preferences.
from .validator import ERROR, WARNING, Issue, count, preference_stats, validate

# String keys used in the per-engineer counters (they match Roster.counts()).
PRIMARY = "Primary"
SECONDARY = "Secondary"
OFFDAY_PRIMARY = "OffDayPrimary"


def generate(cfg: RosterConfig, locks: Locks | None = None, baseline: Roster | None = None) -> tuple[Roster, list[Issue]]:
    """Return the best roster found and its validation issues. Locked cells
    and on-call slots are kept exactly as given. With a ``baseline`` (the
    published roster) assignments are kept wherever the rules allow, so a
    regenerate only changes what it has to."""
    # You cannot build a roster with nobody on the team.
    if not cfg.engineers:
        raise ValueError("Add at least one engineer before generating a roster")
    # Drop any locks that point at engineers/days not in this month.
    locks = _valid_locks(cfg, locks or Locks())
    # One master random generator, seeded from the config for reproducibility.
    master = random.Random(cfg.seed)
    # ``best`` will hold the lowest-scoring (score, roster, issues) triple.
    best = None
    # Try many randomised builds and keep the best.
    for _ in range(cfg.attempts):
        # Each attempt gets its own random stream, derived from the master.
        roster = _build(cfg, locks, random.Random(master.random()), baseline)
        # Check it against the rules.
        issues = validate(roster)
        # Score it: lower is better.
        score = _score(roster, issues, baseline)
        # Keep it if it is the first attempt or beats the current best.
        if best is None or score < best[0]:
            best = (score, roster, issues)
    # Return the best roster and its issues.
    return best[1], best[2]


def _valid_locks(cfg: RosterConfig, locks: Locks) -> Locks:
    """Drop locks for engineers or days that are no longer in the roster."""
    # The valid engineer names and days for this month.
    names, days = set(cfg.engineer_names), set(cfg.days)
    # Rebuild the lock sets, keeping only entries that still make sense.
    return Locks(
        # Keep a pinned cell only if its engineer and day both still exist.
        {(n, d): c for (n, d), c in locks.cells.items() if n in names and d in days},
        # Keep a pinned primary only for a valid day and a real (or empty) name.
        {d: n for d, n in locks.primary.items() if d in days and (n in names or not n)},
        # Same for secondary.
        {d: n for d, n in locks.secondary.items() if d in days and (n in names or not n)},
    )


def _changes(roster: Roster, baseline: Roster) -> int:
    # Count how many cells differ between a candidate and the baseline roster.
    n = 0
    for d in roster.days:
        # Differences in engineer shift cells.
        n += sum(1 for name in roster.config.engineer_names if roster.code(name, d) != baseline.code(name, d))
        # A difference in the day's primary on-call (True counts as 1).
        n += roster.primary.get(d) != baseline.primary.get(d)
        # A difference in the day's secondary on-call.
        n += roster.secondary.get(d) != baseline.secondary.get(d)
    return n


def _score(roster: Roster, issues: list[Issue], baseline: Roster | None = None) -> float:
    # Shorthands for the config and the various name groups.
    cfg = roster.config
    names = cfg.engineer_names
    sme = [e.name for e in cfg.engineers if e.is_sme]
    non_sme = [e.name for e in cfg.engineers if not e.is_sme]
    # Per-engineer totals, including carry-over, used to measure fairness.
    counts = {n: roster.total_counts(n) for n in names}

    def spread(group, key):
        # How unevenly a duty (``key``) is spread across ``group``: the standard
        # deviation. 0 means perfectly even; higher is worse.
        values = [counts[n].get(key, 0) for n in group]
        return statistics.pstdev(values) if len(values) > 1 else 0.0

    # Weighted sum of unevenness across the duties we care about (nights weigh
    # most, then on-call, then day shifts).
    fairness = (
        3 * spread(names, NIGHT)
        + spread(names, MORNING)
        + spread(names, EVENING)
        + 2 * spread(non_sme, PRIMARY)
        + spread(non_sme, OFFDAY_PRIMARY)
        + 2 * spread(sme, SECONDARY)
    )
    # How many preferences were met vs requested.
    met, requested = preference_stats(roster)
    # When regenerating against a published roster, penalise every change so the
    # result stays as close to what people already saw as the rules allow.
    stability = 5 * _changes(roster, baseline) if baseline else 0
    # Final score: rule errors dominate (x10,000), then warnings (x100), then
    # stability, fairness, and unmet preferences. Lower is better.
    return count(issues, ERROR) * 10_000 + count(issues, WARNING) * 100 + stability + fairness + 0.5 * (requested - met)


def _build(cfg: RosterConfig, locks: Locks, rng: random.Random, baseline: Roster | None = None) -> Roster:
    # The month's days, plus a set for fast "is this day in the month" checks.
    days = cfg.days
    month_days = set(days)
    # All engineer names, and the subset who are SMEs.
    names = cfg.engineer_names
    sme = {e.name for e in cfg.engineers if e.is_sme}

    # The empty roster we will fill in: grid[name][day] = code.
    grid: dict[str, dict[date, str]] = {n: {} for n in names}
    # Per-day on-call maps.
    primary: dict[date, str] = {}
    secondary: dict[date, str] = {}
    # Fairness counters start from last month's carried-over totals.
    stats = {n: Counter(cfg.prior_counts.get(n, {})) for n in names}
    # Engineer -> the day their pending comp off is due. Until that day they
    # rest (weekend/holiday off, no on-call); on that day they are marked CO.
    # Seed it with comp offs carried over from last month's end-of-month nights.
    comp_off_due: dict[str, date] = dict(cfg.carried_comp_offs())

    def locked_oncall(name: str, d: date) -> bool:
        # True if this engineer is pinned to either on-call slot on day ``d``.
        return name in (locks.primary.get(d), locks.secondary.get(d))

    def can_take_comp_off(name: str, d: date) -> bool:
        """A night on day d needs the engineer free until their comp off,
        which is the next working day (weekends/holidays are skipped)."""
        # Where the comp off would land.
        co = cfg.comp_off_day(d)
        # If the comp-off day is in this month, it must actually be free.
        if co in month_days:
            # Blocked if they have leave or a forced shift that day.
            if cfg.leave_on(name, co) or cfg.must_shift(name, co):
                return False
            # Blocked if that cell is pinned to something other than CO.
            if locks.cell(name, co) not in (None, COMP_OFF):
                return False
        # Every day between the night and the comp off must be free of duty.
        rest = d + timedelta(days=1)
        while rest <= co and rest in month_days:
            ov = cfg.override_on(rest)
            # Blocked if they are forced (by override or lock) onto on-call.
            if (ov and name in (ov.primary, ov.secondary)) or locked_oncall(name, rest):
                return False
            # Blocked if a day *before* the comp off is pinned to a real shift.
            if rest < co and locks.cell(name, rest) in SHIFTS:
                return False
            rest += timedelta(days=1)
        # Otherwise this engineer can take the night and its comp off.
        return True

    def pick(candidates, key):
        # Choose the best candidate by ``key`` (lowest wins), breaking ties
        # randomly so the roster varies between attempts.
        candidates = list(candidates)
        if not candidates:
            return None
        return min(candidates, key=lambda n: (key(n), rng.random()))

    def was(n: str, d: date, shift: str) -> int:
        """0 if the baseline had this assignment, else 1 (0 without a baseline)."""
        # Used as the first sort key so, when regenerating, engineers who
        # already had this shift in the published roster are preferred.
        return int(bool(baseline) and baseline.code(n, d) != shift)

    def pref_bias(n: str, d: date, shift: str) -> int:
        # Nudge the fairness score: -2 if this is the engineer's preferred shift
        # (make it more likely), +1 if they prefer a different one, 0 if none.
        pref = cfg.preferred_shift(n, d)
        if pref is None:
            return 0
        return -2 if pref == shift else 1

    # Build the month one day at a time.
    for d in days:
        # Classify the day and pick the "off" code to use for it.
        dtype = cfg.day_type(d)
        off_day = cfg.is_off_day(d)
        off_code = HOLIDAY_OFF if dtype == HOLIDAY else WEEK_OFF
        # The minimum coverage required for this day type.
        mins = cfg.min_coverage.get(dtype, {})

        # 0-1. Place locked cells, leave and comp offs; collect who is still free.
        pool = []                       # engineers still available to schedule today
        assigned: dict[str, str] = {}   # today's decisions so far: name -> shift
        for n in names:
            # Is this cell pinned? Is this engineer on leave today?
            locked = locks.cell(n, d)
            lv = cfg.leave_on(n, d)
            # If a comp off is due today, place it (unless a lock overrides it).
            if comp_off_due.get(n) == d:
                del comp_off_due[n]
                if locked is None or locked == COMP_OFF:
                    grid[n][d] = COMP_OFF
                    continue
            # A pinned cell is honoured exactly.
            if locked is not None:
                if locked in SHIFTS:
                    # A pinned real shift: record it but keep them in the pool so
                    # the on-call logic can still see them.
                    assigned[n] = locked
                    pool.append(n)
                else:
                    # A pinned non-shift code (leave, off, CO...) is just placed.
                    grid[n][d] = locked
                continue
            # Not pinned: leave wins next.
            if lv:
                grid[n][d] = LONG_LEAVE if lv.long_leave else LEAVE
            elif n in comp_off_due:
                # Resting after a night, before the comp off (weekend/holiday).
                grid[n][d] = off_code
            else:
                # Free to be scheduled.
                pool.append(n)
        # Shuffle so ties among equally-good candidates do not always favour the
        # same person.
        rng.shuffle(pool)

        # 2. Honour fixed ("Must") shift requests.
        for n in pool:
            if n in assigned:
                continue
            must = cfg.must_shift(n, d)
            # Take a forced non-night shift always; a forced night only if the
            # engineer can also take the resulting comp off.
            if must and (must != NIGHT or can_take_comp_off(n, d)):
                assigned[n] = must

        # Any hand-picked on-call override for today.
        ov = cfg.override_on(d)

        # 3. Primary on-call: a non-SME who is not on Morning or Night.
        def primary_ok(n):
            return n in pool and n not in sme and assigned.get(n) not in (MORNING, NIGHT)

        if d in locks.primary:
            # A pinned primary (may be "" meaning "explicitly none").
            p = locks.primary[d] or None
        else:
            # Use the override if it is valid, otherwise pick the fairest option.
            p = ov.primary if ov and ov.primary and primary_ok(ov.primary) else None
            if p is None:
                p = pick(
                    (n for n in pool if primary_ok(n)),
                    lambda n: (
                        # Prefer whoever had it in the published roster,
                        bool(baseline) and baseline.primary.get(d) != n,
                        # then spread weekend/holiday primary duty evenly,
                        stats[n][OFFDAY_PRIMARY] if off_day else 0,
                        # avoid people who asked to avoid Evening on working days,
                        EVENING in cfg.avoided_shifts(n, d) and not off_day,
                        # avoid people who prefer a Morning/Night shift,
                        cfg.preferred_shift(n, d) in (MORNING, NIGHT),
                        # then even out total primary duty.
                        stats[n][PRIMARY],
                    ),
                )
        if p:
            # Record the primary and bump their counters.
            primary[d] = p
            stats[p][PRIMARY] += 1
            if off_day:
                stats[p][OFFDAY_PRIMARY] += 1
            elif p in pool and p not in assigned:
                # On a working day the primary also covers the Evening shift.
                assigned[p] = EVENING

        # 4. Secondary on-call: an SME (not needed on weekends/holidays).
        if d in locks.secondary:
            # A pinned secondary.
            s = locks.secondary[d] or None
        elif ov and ov.secondary and ov.secondary in pool and ov.secondary in sme and ov.secondary != p:
            # A valid override.
            s = ov.secondary
        elif not off_day:
            # Otherwise pick the fairest available SME (not the primary).
            s = pick(
                (n for n in pool if n in sme and n != p),
                lambda n: (bool(baseline) and baseline.secondary.get(d) != n, assigned.get(n) == NIGHT, stats[n][SECONDARY]),
            )
        else:
            # No secondary is required on a day off.
            s = None
        if s:
            # Record the secondary and bump their counter.
            secondary[d] = s
            stats[s][SECONDARY] += 1

        # 5-7. Meet the minimum coverage. Do Night first (most constrained),
        # then Morning, then Evening.
        for shift in (NIGHT, MORNING, EVENING):
            # How many more of this shift we still need after existing decisions.
            need = mins.get(shift, 0) - sum(1 for v in assigned.values() if v == shift)
            # First try without breaking any "Avoid" request; if that is not
            # enough, relax that on a second pass.
            for relax_avoid in (False, True):
                while need > 0:
                    # Everyone who could take this shift right now.
                    cand = [
                        n
                        for n in pool
                        if n not in assigned                                      # not already busy today
                        and n != p                                               # the primary is spoken for
                        and (shift != NIGHT or (n != s and can_take_comp_off(n, d)))  # nights need a free comp off
                        and (relax_avoid or shift not in cfg.avoided_shifts(n, d))    # respect Avoid until relaxed
                    ]
                    # Pick the fairest candidate (baseline first, then history + preference).
                    chosen = pick(cand, lambda n: (was(n, d, shift), stats[n][shift] + pref_bias(n, d, shift)))
                    if chosen is None:
                        # Nobody left who can take it; stop trying this shift.
                        break
                    assigned[chosen] = shift
                    need -= 1

        # 8. Everyone still free works a day shift (Morning/Evening) on working
        # days, or is off on weekends/holidays.
        for n in pool:
            if n in assigned:
                continue
            if off_day:
                grid[n][d] = off_code
                continue
            # Their allowed day-shift options (respecting Avoid, else both).
            options = [sh for sh in (MORNING, EVENING) if sh not in cfg.avoided_shifts(n, d)] or [MORNING, EVENING]
            # Keep the published assignment if it is still a valid option.
            if baseline and baseline.code(n, d) in options:
                assigned[n] = baseline.code(n, d)
                continue
            # Otherwise honour a preference if it fits.
            pref = cfg.preferred_shift(n, d)
            if pref in options:
                assigned[n] = pref
                continue
            # Otherwise balance today's headcount, then their own history.
            today = Counter(assigned.values())
            assigned[n] = min(options, key=lambda sh: (today[sh], stats[n][sh], rng.random()))

        # Commit today's decisions into the grid and update the counters.
        for n, shift in assigned.items():
            grid[n][d] = shift
            stats[n][shift] += 1
            # A night worked today schedules a comp off on its next working day.
            if shift == NIGHT:
                comp_off_due[n] = cfg.comp_off_day(d)

    # Wrap the filled grid and on-call maps into a Roster (with a copy of the
    # locks so the caller's locks are not mutated).
    return Roster(cfg, grid, primary, secondary, locks.copy())
