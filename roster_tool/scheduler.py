"""Roster generation.

A greedy day-by-day builder fills each day in rule priority order
(leave/comp-off -> fixed requests -> primary on-call -> secondary on-call ->
night -> morning -> evening -> everyone else). Ties are broken by fairness
counters and then randomly; many randomised attempts are generated and the
one with the fewest rule violations and the most even workload wins.
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
    WEEK_OFF,
    Roster,
    RosterConfig,
)
from .validator import ERROR, WARNING, Issue, count, validate

PRIMARY = "P"
SECONDARY = "S"
OFFDAY_PRIMARY = "P_off"


def generate(cfg: RosterConfig) -> tuple[Roster, list[Issue]]:
    """Return the best roster found and its validation issues."""
    if not cfg.engineers:
        raise ValueError("Add at least one engineer before generating a roster")
    master = random.Random(cfg.seed)
    best = None
    for _ in range(cfg.attempts):
        roster = _build(cfg, random.Random(master.random()))
        issues = validate(roster)
        score = _score(roster, issues)
        if best is None or score < best[0]:
            best = (score, roster, issues)
    return best[1], best[2]


def _score(roster: Roster, issues: list[Issue]) -> float:
    cfg = roster.config
    names = cfg.engineer_names
    sme = [e.name for e in cfg.engineers if e.is_sme]
    non_sme = [e.name for e in cfg.engineers if not e.is_sme]
    counts = {n: roster.counts(n) for n in names}

    def spread(group, key):
        values = [counts[n][key] for n in group]
        return statistics.pstdev(values) if len(values) > 1 else 0.0

    fairness = (
        3 * spread(names, NIGHT)
        + spread(names, MORNING)
        + spread(names, EVENING)
        + 2 * spread(non_sme, "Primary")
        + 2 * spread(sme, "Secondary")
    )
    return count(issues, ERROR) * 10_000 + count(issues, WARNING) * 100 + fairness


def _build(cfg: RosterConfig, rng: random.Random) -> Roster:
    days = cfg.days
    month_days = set(days)
    names = cfg.engineer_names
    sme = {e.name for e in cfg.engineers if e.is_sme}

    grid: dict[str, dict[date, str]] = {n: {} for n in names}
    primary: dict[date, str] = {}
    secondary: dict[date, str] = {}
    stats = {n: Counter() for n in names}
    # Engineer -> day of their pending comp off. Until that day they rest
    # (weekend/holiday off, no on-call); on that day they are on CO.
    comp_off_due: dict[str, date] = {}

    def can_take_comp_off(name: str, d: date) -> bool:
        """A night on day d needs the engineer free until their comp off,
        which is the next working day (weekends/holidays are skipped)."""
        co = cfg.comp_off_day(d)
        if co in month_days and (cfg.leave_on(name, co) or cfg.must_shift(name, co)):
            return False
        rest = d + timedelta(days=1)
        while rest <= co and rest in month_days:
            ov = cfg.override_on(rest)
            if ov and name in (ov.primary, ov.secondary):
                return False
            rest += timedelta(days=1)
        return True

    def pick(candidates, key):
        candidates = list(candidates)
        if not candidates:
            return None
        return min(candidates, key=lambda n: (key(n), rng.random()))

    for d in days:
        dtype = cfg.day_type(d)
        off_day = cfg.is_off_day(d)
        mins = cfg.min_coverage.get(dtype, {})

        # 1. Leave and comp off.
        pool = []
        for n in names:
            lv = cfg.leave_on(n, d)
            if lv:
                grid[n][d] = LONG_LEAVE if lv.long_leave else LEAVE
            elif comp_off_due.get(n) == d:
                grid[n][d] = COMP_OFF
                del comp_off_due[n]
            elif n in comp_off_due:
                # Resting after a night, before the comp off (weekend/holiday).
                grid[n][d] = HOLIDAY_OFF if dtype == HOLIDAY else WEEK_OFF
            else:
                pool.append(n)
        rng.shuffle(pool)

        # 2. Fixed shift requests.
        assigned: dict[str, str] = {}
        for n in pool:
            must = cfg.must_shift(n, d)
            if must and (must != NIGHT or can_take_comp_off(n, d)):
                assigned[n] = must

        ov = cfg.override_on(d)

        # 3. Primary on-call: non-SME, not on Morning/Night.
        def primary_ok(n):
            return n in pool and n not in sme and assigned.get(n) not in (MORNING, NIGHT)

        p = ov.primary if ov and ov.primary and primary_ok(ov.primary) else None
        if p is None:
            p = pick(
                (n for n in pool if primary_ok(n)),
                lambda n: (
                    stats[n][OFFDAY_PRIMARY] if off_day else 0,
                    EVENING in cfg.avoided_shifts(n, d) and not off_day,
                    stats[n][PRIMARY],
                ),
            )
        if p:
            primary[d] = p
            stats[p][PRIMARY] += 1
            if off_day:
                stats[p][OFFDAY_PRIMARY] += 1
            elif p not in assigned:
                assigned[p] = EVENING

        # 4. Secondary on-call: SME, not needed on weekends/holidays.
        s = None
        if ov and ov.secondary and ov.secondary in pool and ov.secondary in sme and ov.secondary != p:
            s = ov.secondary
        elif not off_day:
            s = pick(
                (n for n in pool if n in sme and n != p),
                lambda n: (assigned.get(n) == NIGHT, stats[n][SECONDARY]),
            )
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
                    chosen = pick(cand, lambda n: stats[n][shift])
                    if chosen is None:
                        break
                    assigned[chosen] = shift
                    need -= 1

        # 8. Everyone else: on working/freeze days they work Morning or
        # Evening (balancing today's headcount, then their own history);
        # on weekends/holidays they are off.
        for n in pool:
            if n in assigned:
                continue
            if off_day:
                grid[n][d] = HOLIDAY_OFF if dtype == HOLIDAY else WEEK_OFF
                continue
            options = [sh for sh in (MORNING, EVENING) if sh not in cfg.avoided_shifts(n, d)] or [MORNING, EVENING]
            today = Counter(assigned.values())
            assigned[n] = min(options, key=lambda sh: (today[sh], stats[n][sh], rng.random()))

        for n, shift in assigned.items():
            grid[n][d] = shift
            stats[n][shift] += 1

        for n, shift in assigned.items():
            if shift == NIGHT:
                comp_off_due[n] = cfg.comp_off_day(d)

    return Roster(cfg, grid, primary, secondary)
