"""Roster generation.

A greedy day-by-day builder fills each day in rule priority order
(locked cells -> leave/comp-off -> fixed requests -> primary on-call ->
secondary on-call -> night -> morning -> evening -> everyone else). Ties are
broken by fairness counters (including totals carried over from previous
months) and then randomly; many randomised attempts are generated and the one
with the fewest rule violations and the most even workload wins.
"""

from __future__ import annotations

import random
import statistics
from collections import Counter
from datetime import date, timedelta

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
from .validator import ERROR, WARNING, Issue, count, preference_stats, validate

PRIMARY = "Primary"
SECONDARY = "Secondary"
OFFDAY_PRIMARY = "OffDayPrimary"


def generate(cfg: RosterConfig, locks: Locks | None = None, baseline: Roster | None = None) -> tuple[Roster, list[Issue]]:
    """Return the best roster found and its validation issues. Locked cells
    and on-call slots are kept exactly as given. With a ``baseline`` (the
    published roster) assignments are kept wherever the rules allow, so a
    regenerate only changes what it has to."""
    if not cfg.engineers:
        raise ValueError("Add at least one engineer before generating a roster")
    locks = _valid_locks(cfg, locks or Locks())
    master = random.Random(cfg.seed)
    best = None
    for _ in range(cfg.attempts):
        roster = _build(cfg, locks, random.Random(master.random()), baseline)
        issues = validate(roster)
        score = _score(roster, issues, baseline)
        if best is None or score < best[0]:
            best = (score, roster, issues)
    return best[1], best[2]


def _valid_locks(cfg: RosterConfig, locks: Locks) -> Locks:
    """Drop locks for engineers or days that are no longer in the roster."""
    names, days = set(cfg.engineer_names), set(cfg.days)
    return Locks(
        {(n, d): c for (n, d), c in locks.cells.items() if n in names and d in days},
        {d: n for d, n in locks.primary.items() if d in days and (n in names or not n)},
        {d: n for d, n in locks.secondary.items() if d in days and (n in names or not n)},
    )


def _changes(roster: Roster, baseline: Roster) -> int:
    n = 0
    for d in roster.days:
        n += sum(1 for name in roster.config.engineer_names if roster.code(name, d) != baseline.code(name, d))
        n += roster.primary.get(d) != baseline.primary.get(d)
        n += roster.secondary.get(d) != baseline.secondary.get(d)
    return n


def _score(roster: Roster, issues: list[Issue], baseline: Roster | None = None) -> float:
    cfg = roster.config
    names = cfg.engineer_names
    sme = [e.name for e in cfg.engineers if e.is_sme]
    non_sme = [e.name for e in cfg.engineers if not e.is_sme]
    counts = {n: roster.total_counts(n) for n in names}

    def spread(group, key):
        values = [counts[n].get(key, 0) for n in group]
        return statistics.pstdev(values) if len(values) > 1 else 0.0

    fairness = (
        3 * spread(names, NIGHT)
        + spread(names, MORNING)
        + spread(names, EVENING)
        + 2 * spread(non_sme, PRIMARY)
        + spread(non_sme, OFFDAY_PRIMARY)
        + 2 * spread(sme, SECONDARY)
    )
    met, requested = preference_stats(roster)
    stability = 5 * _changes(roster, baseline) if baseline else 0
    return count(issues, ERROR) * 10_000 + count(issues, WARNING) * 100 + stability + fairness + 0.5 * (requested - met)


def _build(cfg: RosterConfig, locks: Locks, rng: random.Random, baseline: Roster | None = None) -> Roster:
    days = cfg.days
    month_days = set(days)
    names = cfg.engineer_names
    sme = {e.name for e in cfg.engineers if e.is_sme}

    grid: dict[str, dict[date, str]] = {n: {} for n in names}
    primary: dict[date, str] = {}
    secondary: dict[date, str] = {}
    # Fairness counters start from the totals carried over from last month.
    stats = {n: Counter(cfg.prior_counts.get(n, {})) for n in names}
    # Engineer -> day of their pending comp off. Until that day they rest
    # (weekend/holiday off, no on-call); on that day they are on CO.
    comp_off_due: dict[str, date] = dict(cfg.carried_comp_offs())

    def locked_oncall(name: str, d: date) -> bool:
        return name in (locks.primary.get(d), locks.secondary.get(d))

    def can_take_comp_off(name: str, d: date) -> bool:
        """A night on day d needs the engineer free until their comp off,
        which is the next working day (weekends/holidays are skipped)."""
        co = cfg.comp_off_day(d)
        if co in month_days:
            if cfg.leave_on(name, co) or cfg.must_shift(name, co):
                return False
            if locks.cell(name, co) not in (None, COMP_OFF):
                return False
        rest = d + timedelta(days=1)
        while rest <= co and rest in month_days:
            ov = cfg.override_on(rest)
            if (ov and name in (ov.primary, ov.secondary)) or locked_oncall(name, rest):
                return False
            if rest < co and locks.cell(name, rest) in SHIFTS:
                return False
            rest += timedelta(days=1)
        return True

    def pick(candidates, key):
        candidates = list(candidates)
        if not candidates:
            return None
        return min(candidates, key=lambda n: (key(n), rng.random()))

    def was(n: str, d: date, shift: str) -> int:
        """0 if the baseline had this assignment, else 1 (0 without a baseline)."""
        return int(bool(baseline) and baseline.code(n, d) != shift)

    def pref_bias(n: str, d: date, shift: str) -> int:
        pref = cfg.preferred_shift(n, d)
        if pref is None:
            return 0
        return -2 if pref == shift else 1

    for d in days:
        dtype = cfg.day_type(d)
        off_day = cfg.is_off_day(d)
        off_code = HOLIDAY_OFF if dtype == HOLIDAY else WEEK_OFF
        mins = cfg.min_coverage.get(dtype, {})

        # 0-1. Locked cells, then leave and comp off.
        pool = []
        assigned: dict[str, str] = {}
        for n in names:
            locked = locks.cell(n, d)
            lv = cfg.leave_on(n, d)
            if comp_off_due.get(n) == d:
                del comp_off_due[n]
                if locked is None or locked == COMP_OFF:
                    grid[n][d] = COMP_OFF
                    continue
            if locked is not None:
                if locked in SHIFTS:
                    assigned[n] = locked
                    pool.append(n)
                else:
                    grid[n][d] = locked
                continue
            if lv:
                grid[n][d] = LONG_LEAVE if lv.long_leave else LEAVE
            elif n in comp_off_due:
                # Resting after a night, before the comp off (weekend/holiday).
                grid[n][d] = off_code
            else:
                pool.append(n)
        rng.shuffle(pool)

        # 2. Fixed shift requests.
        for n in pool:
            if n in assigned:
                continue
            must = cfg.must_shift(n, d)
            if must and (must != NIGHT or can_take_comp_off(n, d)):
                assigned[n] = must

        ov = cfg.override_on(d)

        # 3. Primary on-call: non-SME, not on Morning/Night.
        def primary_ok(n):
            return n in pool and n not in sme and assigned.get(n) not in (MORNING, NIGHT)

        if d in locks.primary:
            p = locks.primary[d] or None
        else:
            p = ov.primary if ov and ov.primary and primary_ok(ov.primary) else None
            if p is None:
                p = pick(
                    (n for n in pool if primary_ok(n)),
                    lambda n: (
                        bool(baseline) and baseline.primary.get(d) != n,
                        stats[n][OFFDAY_PRIMARY] if off_day else 0,
                        EVENING in cfg.avoided_shifts(n, d) and not off_day,
                        cfg.preferred_shift(n, d) in (MORNING, NIGHT),
                        stats[n][PRIMARY],
                    ),
                )
        if p:
            primary[d] = p
            stats[p][PRIMARY] += 1
            if off_day:
                stats[p][OFFDAY_PRIMARY] += 1
            elif p in pool and p not in assigned:
                assigned[p] = EVENING

        # 4. Secondary on-call: SME, not needed on weekends/holidays.
        if d in locks.secondary:
            s = locks.secondary[d] or None
        elif ov and ov.secondary and ov.secondary in pool and ov.secondary in sme and ov.secondary != p:
            s = ov.secondary
        elif not off_day:
            s = pick(
                (n for n in pool if n in sme and n != p),
                lambda n: (bool(baseline) and baseline.secondary.get(d) != n, assigned.get(n) == NIGHT, stats[n][SECONDARY]),
            )
        else:
            s = None
        if s:
            secondary[d] = s
            stats[s][SECONDARY] += 1

        # 5-7. Minimum coverage: Night first (it is the most constrained),
        # then Morning, then Evening.
        for shift in (NIGHT, MORNING, EVENING):
            need = mins.get(shift, 0) - sum(1 for v in assigned.values() if v == shift)
            for relax_avoid in (False, True):
                while need > 0:
                    cand = [
                        n
                        for n in pool
                        if n not in assigned
                        and n != p
                        and (shift != NIGHT or (n != s and can_take_comp_off(n, d)))
                        and (relax_avoid or shift not in cfg.avoided_shifts(n, d))
                    ]
                    chosen = pick(cand, lambda n: (was(n, d, shift), stats[n][shift] + pref_bias(n, d, shift)))
                    if chosen is None:
                        break
                    assigned[chosen] = shift
                    need -= 1

        # 8. Everyone else: on working/freeze days they work Morning or
        # Evening (their preference if they have one, otherwise balancing
        # today's headcount and their own history); weekends/holidays are off.
        for n in pool:
            if n in assigned:
                continue
            if off_day:
                grid[n][d] = off_code
                continue
            options = [sh for sh in (MORNING, EVENING) if sh not in cfg.avoided_shifts(n, d)] or [MORNING, EVENING]
            if baseline and baseline.code(n, d) in options:
                assigned[n] = baseline.code(n, d)
                continue
            pref = cfg.preferred_shift(n, d)
            if pref in options:
                assigned[n] = pref
                continue
            today = Counter(assigned.values())
            assigned[n] = min(options, key=lambda sh: (today[sh], stats[n][sh], rng.random()))

        for n, shift in assigned.items():
            grid[n][d] = shift
            stats[n][shift] += 1
            if shift == NIGHT:
                comp_off_due[n] = cfg.comp_off_day(d)

    return Roster(cfg, grid, primary, secondary, locks.copy())
