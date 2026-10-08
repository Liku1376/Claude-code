"""Chinese zodiac: animal, element and polarity, with the Lunar New Year
computed astronomically (second new moon after the winter solstice, Beijing
time)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from . import astronomy as astro

ANIMALS = (
    ("Rat", "quick-witted, resourceful, charming"), ("Ox", "diligent, dependable, determined"),
    ("Tiger", "brave, confident, competitive"), ("Rabbit", "gentle, elegant, responsible"),
    ("Dragon", "ambitious, energetic, charismatic"), ("Snake", "wise, intuitive, enigmatic"),
    ("Horse", "free-spirited, active, warm-hearted"), ("Goat", "calm, creative, kind"),
    ("Monkey", "clever, curious, playful"), ("Rooster", "observant, hardworking, courageous"),
    ("Dog", "loyal, honest, protective"), ("Pig", "generous, sincere, easy-going"),
)
ELEMENTS = ("Wood", "Fire", "Earth", "Metal", "Water")
STEMS = ("Jia", "Yi", "Bing", "Ding", "Wu", "Ji", "Geng", "Xin", "Ren", "Gui")
BRANCHES = ("Zi", "Chou", "Yin", "Mao", "Chen", "Si", "Wu", "Wei", "Shen", "You", "Xu", "Hai")
ELEMENT_TEXT = {
    "Wood": "growth, generosity and cooperation", "Fire": "passion, leadership and dynamism",
    "Earth": "stability, patience and practicality", "Metal": "determination, focus and integrity",
    "Water": "intuition, flexibility and diplomacy",
}
SIX_HARMONY = {frozenset(p) for p in ((0, 1), (2, 11), (3, 10), (4, 9), (5, 8), (6, 7))}
BEIJING = timezone(timedelta(hours=8))


def _new_moons_after(jd: float, count: int) -> list[float]:
    out = [l["jd"] for l in astro.lunations(jd, jd + 31 * count + 2) if l["type"] == "New Moon"]
    return out[:count]


def _solstice(year: int) -> float:
    jd0 = astro.julian_day(datetime(year, 12, 18, tzinfo=timezone.utc))
    return astro.find_crossing(lambda x: astro.diff(astro.sun_longitude(x), 270), jd0, jd0 + 7)


def lunar_new_year(year: int) -> date:
    """Gregorian date of the Chinese New Year falling in ``year``."""
    sol = _solstice(year - 1)
    nm = _new_moons_after(sol, 3)
    # The new moon starting month 11 contains the solstice; count in Beijing days.
    sol_day = astro.from_julian_day(sol).astimezone(BEIJING).date()
    days = [astro.from_julian_day(j).astimezone(BEIJING).date() for j in nm]
    if days[0] == sol_day:
        days = days[1:]
    return days[1]


def year_info(cyear: int) -> dict:
    animal = (cyear - 4) % 12
    stem = (cyear - 4) % 10
    element = ELEMENTS[stem // 2]
    name, traits = ANIMALS[animal]
    return {"year": cyear, "animal": name, "animal_index": animal, "traits": traits,
            "element": element, "element_text": ELEMENT_TEXT[element],
            "polarity": "Yang" if stem % 2 == 0 else "Yin",
            "stem_branch": f"{STEMS[stem]}-{BRANCHES[animal]}",
            "label": f"{element} {name}"}


def chinese_year_for(d: date) -> int:
    lny = lunar_new_year(d.year)
    return d.year if d >= lny else d.year - 1


def relation(a: int, b: int) -> tuple[str, int, str]:
    """Traditional relationship between two animal signs: label, score 0-100, note."""
    if a == b:
        return "Same sign", 70, "You understand each other instinctively but can mirror each other's flaws."
    if frozenset((a, b)) in SIX_HARMONY:
        return "Secret friends (Six Harmony)", 90, "A deeply supportive, complementary bond."
    if (a - b) % 4 == 0:
        return "Trine allies (San He)", 95, "You share values and pace — one of the best pairings."
    if (a - b) % 12 == 6:
        return "Clash (Liu Chong)", 30, "Opposite natures — exciting but demanding; patience is needed."
    if (a - b) % 3 == 0:
        return "Challenging", 50, "Differences in temperament take conscious effort."
    return "Neutral", 65, "A workable match that grows with shared goals."


def profile(birth: date) -> dict:
    cy = chinese_year_for(birth)
    info = year_info(cy)
    animal = info["animal_index"]
    best = [ANIMALS[i][0] for i in range(12) if i != animal and ((i - animal) % 4 == 0 or frozenset((i, animal)) in SIX_HARMONY)]
    clash = ANIMALS[(animal + 6) % 12][0]
    info.update({
        "lunar_new_year": lunar_new_year(cy).isoformat(),
        "best_matches": best, "clash": clash,
        "text": (f"Born in the year of the {info['label']} ({info['polarity']}), you are seen as "
                 f"{info['traits']}. The {info['element']} element adds {info['element_text']}. "
                 f"Your best allies are the {', '.join(best)}; the {clash} is your opposite sign."),
    })
    return info


def year_forecast(birth: date, year: int) -> dict:
    """How a given Chinese year treats your sign (past, present or future)."""
    mine = year_info(chinese_year_for(birth))["animal_index"]
    target = year_info(year)
    label, score, _ = relation(mine, target["animal_index"])
    if target["animal_index"] == mine:
        text = (f"{year} is your Ben Ming Nian (zodiac year). Tradition says to tread carefully, "
                "wear red for protection, and use the year to reset rather than gamble.")
    elif (target["animal_index"] - mine) % 12 == 6:
        text = (f"{year} clashes with your sign (Tai Sui clash): expect changes, moves or shake-ups. "
                "Stay flexible, avoid unnecessary risks and look after your health.")
    elif score >= 90:
        text = f"{year} is a supportive year for you ({label}): good for new ventures, relationships and growth."
    else:
        text = f"{year} is a {label.lower()} year for you: steady effort pays off more than shortcuts."
    return {"year": year, "year_sign": target["label"], "relation": label, "score": score, "text": text}
