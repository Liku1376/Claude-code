"""Pythagorean numerology: core numbers from a birth date and a name, and
personal year / month / day cycles for any date."""

from __future__ import annotations

from datetime import date

MASTER = {11, 22, 33}
MEANINGS = {
    1: ("The Leader", "independence, initiative and new beginnings"),
    2: ("The Peacemaker", "cooperation, sensitivity and partnership"),
    3: ("The Communicator", "creativity, self-expression and joy"),
    4: ("The Builder", "structure, hard work and stability"),
    5: ("The Adventurer", "freedom, change and experience"),
    6: ("The Nurturer", "responsibility, love, family and service"),
    7: ("The Seeker", "analysis, introspection and spiritual wisdom"),
    8: ("The Powerhouse", "ambition, authority and material success"),
    9: ("The Humanitarian", "compassion, completion and letting go"),
    11: ("The Intuitive (Master)", "inspiration, insight and spiritual leadership"),
    22: ("The Master Builder", "turning big visions into lasting reality"),
    33: ("The Master Teacher", "selfless guidance, healing and compassion"),
}
PERSONAL_YEAR = {
    1: "a fresh start — plant seeds, begin projects and take the lead",
    2: "patience and partnership — slow growth, cooperation and diplomacy",
    3: "expression and social life — creativity, fun and visibility",
    4: "foundations — steady work, organisation and building security",
    5: "change and freedom — travel, movement and unexpected turns",
    6: "home and responsibility — family, love, commitment and service",
    7: "reflection — study, rest, inner work and spiritual growth",
    8: "power and results — career moves, money and recognition",
    9: "completion — endings, release and making room for what's next",
    11: "heightened intuition — inspiration and spiritual awakening",
    22: "mastery — large-scale building and practical vision",
}
LETTERS = {c: (i % 9) + 1 for i, c in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ")}
VOWELS = set("AEIOU")


def reduce(n: int, keep_master: bool = True) -> int:
    while n > 9 and not (keep_master and n in MASTER):
        n = sum(int(c) for c in str(n))
    return n


def life_path(d: date) -> int:
    # Reduce month, day and year separately, then the total (the common method).
    return reduce(reduce(d.month) + reduce(d.day) + reduce(sum(int(c) for c in str(d.year))))


def _name_number(name: str, pick) -> int | None:
    letters = [c for c in name.upper() if c in LETTERS and pick(c)]
    return reduce(sum(LETTERS[c] for c in letters)) if letters else None


def personal_year(birth: date, year: int) -> int:
    return reduce(reduce(birth.month) + reduce(birth.day) + reduce(sum(int(c) for c in str(year))), keep_master=False)


def describe(n: int | None) -> dict | None:
    if n is None:
        return None
    title, text = MEANINGS[n]
    return {"number": n, "title": title, "text": text}


def profile(birth: date, name: str = "") -> dict:
    return {
        "life_path": describe(life_path(birth)),
        "birthday": describe(reduce(birth.day)),
        "expression": describe(_name_number(name, lambda c: True)),
        "soul_urge": describe(_name_number(name, lambda c: c in VOWELS)),
        "personality": describe(_name_number(name, lambda c: c not in VOWELS)),
    }


def cycles(birth: date, on: date) -> dict:
    py = personal_year(birth, on.year)
    pm = reduce(py + on.month, keep_master=False)
    pd = reduce(pm + on.day, keep_master=False)
    return {
        "personal_year": {"number": py, "text": PERSONAL_YEAR[py]},
        "personal_month": {"number": pm, "text": PERSONAL_YEAR[pm]},
        "personal_day": {"number": pd, "text": PERSONAL_YEAR[pd]},
        "universal_year": reduce(sum(int(c) for c in str(on.year)), keep_master=False),
    }


def compatibility(a: int, b: int) -> tuple[int, str]:
    """A simple life-path harmony score (0-100)."""
    a, b = reduce(a, False), reduce(b, False)
    groups = ({1, 5, 7}, {2, 4, 8}, {3, 6, 9})
    if a == b:
        return 80, "You share the same life lesson — easy understanding, similar blind spots."
    if any(a in g and b in g for g in groups):
        return 90, "Your numbers belong to the same family — natural harmony."
    if {a, b} in ({1, 8}, {3, 5}, {2, 6}, {4, 7}, {6, 9}):
        return 75, "Complementary numbers that balance each other."
    return 55, "Different rhythms — rewarding when you respect each other's pace."
