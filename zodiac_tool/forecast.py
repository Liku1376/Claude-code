"""Predictions for any date — past, present or future.

* ``horoscope``: sun-sign horoscope (day / week / month / year) from the
  real planetary positions, read through "solar houses".
* ``personal_transits``: today's (or any day's) transits to a natal chart.
* ``life_timeline``: major life cycles (returns, oppositions, squares) across
  a lifetime, each tagged past / current / future.
* ``sky_events``: new and full moons, eclipses, retrograde stations and sign
  changes for a calendar year.

Interpretations are traditional astrological meanings composed from the
computed astronomy; they are for reflection and entertainment.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, tzinfo

from . import astronomy as astro
from .western import (ASPECTS, HOUSE_MEANINGS, PLANET_INFO, SIGN_NAMES, SIGNS, find_aspect, fmt_pos,
                      house_of, sign_of)

TRANSITING = ("Sun", "Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto")
FAST = {"Sun", "Mercury", "Venus", "Mars"}
COLORS = ("Red", "Orange", "Gold", "Yellow", "Green", "Teal", "Sky blue", "Royal blue",
          "Indigo", "Violet", "Pink", "White", "Silver", "Cream", "Maroon")

TRANSIT_THEMES = {
    "Sun": "focus and vitality", "Moon": "mood", "Mercury": "conversations, plans and paperwork",
    "Venus": "love, pleasure and money", "Mars": "energy, drive and friction",
    "Jupiter": "luck, growth and opportunity", "Saturn": "tests, structure and hard-earned progress",
    "Uranus": "surprises, change and liberation", "Neptune": "inspiration, confusion and idealism",
    "Pluto": "deep transformation and power",
}
ASPECT_VERBS = {"Conjunction": "energises", "Sextile": "opens doors for", "Square": "challenges",
                "Trine": "supports", "Opposition": "confronts"}


def _local(jd: float, tz: tzinfo) -> datetime:
    return astro.from_julian_day(jd).astimezone(tz)


def _seed(*parts) -> int:
    return int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest(), 16)


def _solar_house(lon: float, sign: int) -> int:
    return (sign_of(lon) - sign) % 12 + 1


# -- Sun-sign horoscope -------------------------------------------------------
_GOOD_HOUSES = {1, 3, 5, 9, 10, 11}
_HARD_HOUSES = {6, 8, 12}


def _clamp(v: float) -> int:
    return max(1, min(5, int(round(v))))


def horoscope(sign: int, jd: float, period: str, tz: tzinfo) -> dict:
    """A horoscope for a sun sign covering a day, week, month or year from ``jd``."""
    days = {"day": 1, "week": 7, "month": 30, "year": 365}.get(period, 1)
    mid = jd + days / 2
    pos = {p: astro.planet_longitude(p, mid if days > 1 else jd) for p in ("Moon",) + TRANSITING}
    houses = {p: _solar_house(lon, sign) for p, lon in pos.items()}
    sign_point = sign * 30 + 15
    s = SIGNS[sign]

    def asp_to_sign(planet):
        a = find_aspect(pos[planet], sign_point, 2.2)
        return a[0] if a else None

    score = {"love": 3.0, "career": 3.0, "money": 3.0, "health": 3.0}
    lines = {}
    # Love: Venus (and the Moon for short periods).
    vh = houses["Venus"]
    lines["love"] = f"Venus moves through your {_ord(vh)} house of {HOUSE_MEANINGS[vh - 1]}, "
    if vh in (1, 5, 7, 11):
        lines["love"] += "a sweet placement for romance and attraction — reach out, say how you feel."
        score["love"] += 1.2
    elif vh in _HARD_HOUSES:
        lines["love"] += "so affection may feel private or complicated; kindness and patience win."
        score["love"] -= 0.8
    else:
        lines["love"] += "bringing gentle warmth to everyday connections."
        score["love"] += 0.3
    # Career: Sun, Mars, Saturn and Jupiter.
    sh, mh = houses["Sun"], houses["Mars"]
    lines["career"] = (f"The Sun lights up your {_ord(sh)} house ({HOUSE_MEANINGS[sh - 1]}) and Mars drives "
                       f"your {_ord(mh)} house ({HOUSE_MEANINGS[mh - 1]}). ")
    if sh in (10, 1, 6) or mh in (10, 1):
        lines["career"] += "Work and ambition are in the spotlight — take initiative and be visible."
        score["career"] += 1
    elif mh in _HARD_HOUSES:
        lines["career"] += "Energy may be scattered behind the scenes; plan before you push."
        score["career"] -= 0.7
    else:
        lines["career"] += "Steady effort brings quiet progress."
    # Money: Jupiter and Venus in the money houses.
    jh = houses["Jupiter"]
    lines["money"] = f"Jupiter in your {_ord(jh)} house expands {HOUSE_MEANINGS[jh - 1]}. "
    if jh in (2, 8, 10, 11) or vh in (2, 11):
        lines["money"] += "Financial opportunities are favoured; let gains compound."
        score["money"] += 1
    elif houses["Saturn"] in (2, 8):
        lines["money"] += "Saturn asks for budgeting and caution with debts."
        score["money"] -= 0.8
    else:
        lines["money"] += "Keep spending in line with long-term plans."
    # Health: Mars and the 6th house, Moon for the day.
    lines["health"] = "Mars gives a vigorous boost — channel it into exercise." if mh in (1, 3, 6, 10, 11) else (
        "Pace yourself and protect your sleep." if mh in _HARD_HOUSES else "Energy is balanced; keep routines simple.")
    score["health"] += 0.7 if mh in (1, 3, 10, 11) else (-0.7 if mh in _HARD_HOUSES else 0)

    notes = []
    if astro.speed("Mercury", mid) < 0:
        notes.append("Mercury is retrograde — double-check messages, travel and contracts; revisit rather than launch.")
        score["career"] -= 0.4
    for planet in ("Jupiter", "Saturn", "Mars", "Venus"):
        asp = asp_to_sign(planet)
        if asp:
            good = asp["nature"] == "harmonious" or (asp["name"] == "Conjunction" and planet in ("Jupiter", "Venus"))
            article = "an" if asp["name"][0] in "AEIOU" else "a"
            notes.append(f"{planet} forms {article} {asp['name'].lower()} to your sign, which "
                         f"{ASPECT_VERBS[asp['name']]} your {TRANSIT_THEMES[planet]}.")
            for k in score:
                score[k] += 0.4 if good else -0.3

    if period == "day":
        moh = houses["Moon"]
        overall = (f"The Moon is in {SIGN_NAMES[sign_of(pos['Moon'])]}, your {_ord(moh)} solar house, putting "
                   f"{HOUSE_MEANINGS[moh - 1]} on today's agenda. ")
        overall += ("Emotionally this is a supportive day." if moh in _GOOD_HOUSES else
                    "Take things slowly and give yourself space." if moh in _HARD_HOUSES else
                    "Balance your needs with other people's.")
        for k in score:
            score[k] += 0.5 if moh in _GOOD_HOUSES else (-0.5 if moh in _HARD_HOUSES else 0)
    elif period == "year":
        sat = houses["Saturn"]
        overall = (f"This year Jupiter brings growth to your {_ord(jh)} house of {HOUSE_MEANINGS[jh - 1]}, "
                   f"while Saturn asks for maturity in your {_ord(sat)} house of {HOUSE_MEANINGS[sat - 1]}.")
        ev = [e for e in sky_events(jd, jd + 365, tz) if e.get("eclipse")]
        if ev:
            overall += " Eclipses on " + ", ".join(f"{e['date']} ({e['title']})" for e in ev) + " mark turning points."
    else:
        overall = (f"With the Sun in your {_ord(sh)} house, the {period} centres on {HOUSE_MEANINGS[sh - 1]}. "
                   f"Your {s['element'].lower()} nature responds best by being {s['keywords'].split(', ')[0]}.")
        lun = [e for e in sky_events(jd, jd + days, tz) if e["kind"] == "lunation"]
        for e in lun:
            h = _solar_house(e["lon"], sign)
            overall += f" {e['title']} on {e['date']} in your {_ord(h)} house — {'start something new' if 'New' in e['title'] else 'harvest and release'} around {HOUSE_MEANINGS[h - 1].split(',')[0]}."

    rnd = _seed(sign, period, int(jd))
    start = _local(jd, tz).date()
    return {
        "sign": s["name"], "symbol": s["symbol"], "period": period,
        "from": start.isoformat(), "to": (start + timedelta(days=days - 1)).isoformat(),
        "overall": overall, **lines, "notes": notes,
        "scores": {k: _clamp(v) for k, v in score.items()},
        "lucky": {"number": rnd % 9 + 1,
                  "color": COLORS[(rnd >> 8) % len(COLORS)], "time": f"{(rnd >> 16) % 12 + 1}:00"},
        "planets": {p: fmt_pos(lon) for p, lon in pos.items()},
    }


def _ord(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


# -- Personal transits ---------------------------------------------------------
def personal_transits(natal: dict, jd: float) -> dict:
    """Transits on ``jd`` to a natal chart produced by western.natal_chart."""
    natal_pts = {p["name"]: p["lon"] for p in natal["planets"] if p["name"] in TRANSITING or p["name"] == "Moon"}
    natal_pts["Ascendant"] = natal["ascendant"]["lon"]
    natal_pts["Midheaven"] = natal["midheaven"]["lon"]
    cusps = natal["cusps"]
    hits, placements = [], []
    score = {"love": 3.0, "career": 3.0, "money": 3.0, "health": 3.0}
    for t in TRANSITING:
        lon = astro.planet_longitude(t, jd)
        spd = astro.speed(t, jd)
        house = house_of(lon, cusps)
        placements.append({"planet": t, "position": fmt_pos(lon), "house": house, "retro": spd < 0,
                           "text": f"Transiting {t} in your {_ord(house)} house highlights {HOUSE_MEANINGS[house - 1]}."})
        orb_limit = 2.0 if t in FAST else 3.0
        for n, nlon in natal_pts.items():
            for asp in ASPECTS:
                sep = abs(astro.diff(lon, nlon))
                orb = abs(sep - asp["angle"])
                if orb > orb_limit:
                    continue
                later = abs(abs(astro.diff(lon + spd, nlon)) - asp["angle"])
                good = asp["nature"] == "harmonious" or (asp["name"] == "Conjunction" and t in ("Jupiter", "Venus", "Sun"))
                hard = asp["nature"] == "challenging" or (asp["name"] == "Conjunction" and t in ("Saturn", "Pluto", "Mars"))
                weight = (2.0 if t not in FAST else 1.0) * (1 - orb / (orb_limit + 0.01))
                area = {"Venus": "love", "Moon": "love", "Midheaven": "career", "Sun": "career",
                        "Saturn": "career", "Jupiter": "money", "Mars": "health", "Ascendant": "health"}.get(n, "career")
                score[area] += weight * (0.8 if good else -0.8 if hard else 0.2)
                hits.append({
                    "transit": t, "aspect": asp["name"], "symbol": asp["symbol"], "natal": n,
                    "orb": round(orb, 2), "applying": later < orb, "nature": "harmonious" if good else ("challenging" if hard else "neutral"),
                    "weight": round(weight, 2),
                    "text": (f"Transiting {t} ({TRANSIT_THEMES[t]}) {ASPECT_VERBS[asp['name']]} your natal {n} "
                             f"({PLANET_INFO[n][1]}). " + ("Building — " if later < orb else "Fading — ")
                             + ("long-lasting influence." if t not in FAST else "short-lived influence.")),
                })
    hits.sort(key=lambda h: -h["weight"])
    moon = astro.planet_longitude("Moon", jd)
    mh = house_of(moon, cusps)
    good = sum(1 for h in hits if h["nature"] == "harmonious")
    hard = sum(1 for h in hits if h["nature"] == "challenging")
    tone = ("an easy-flowing, opportunity-rich" if good > hard + 1 else
            "a demanding but growth-oriented" if hard > good + 1 else "a balanced")
    headline = (f"This is {tone} period. The Moon passes your {_ord(mh)} house ({HOUSE_MEANINGS[mh - 1]}). "
                + (f"The strongest influence: {hits[0]['text']}" if hits else "No major transits are exact right now — a quieter time."))
    return {"headline": headline, "aspects": hits, "placements": placements,
            "moon": {"position": fmt_pos(moon), "house": mh, "phase": astro.moon_phase(jd)},
            "scores": {k: _clamp(v) for k, v in score.items()}}


# -- Lifetime cycles -------------------------------------------------------------
LIFE_EVENTS = (
    ("Jupiter", "Jupiter", 0, "Jupiter Return", "A new 12-year cycle of growth, learning, luck and opportunity begins."),
    ("Jupiter", "Sun", 0, "Jupiter crosses your Sun", "A confident, expansive year — recognition and good fortune."),
    ("Jupiter", "Midheaven", 0, "Jupiter on your Midheaven", "A career high point: promotion, visibility and reward."),
    ("Saturn", "Saturn", 0, "Saturn Return", "A coming-of-age reckoning: commitments, career foundations and adult responsibility."),
    ("Saturn", "Saturn", 90, "Saturn square Saturn", "A checkpoint in your 7-year cycle — adjust structures that no longer fit."),
    ("Saturn", "Saturn", 180, "Saturn Opposition", "Halfway through the Saturn cycle — results of earlier efforts show; rebalance."),
    ("Saturn", "Sun", 0, "Saturn crosses your Sun", "Hard work and responsibility mature your identity; slow but lasting success."),
    ("Saturn", "Moon", 0, "Saturn crosses your Moon", "An emotionally serious time; family duties and inner resilience."),
    ("Saturn", "Ascendant", 0, "Saturn crosses your Ascendant", "A new 29-year chapter for self-image, body and direction."),
    ("Uranus", "Uranus", 90, "Uranus square Uranus", "A restless urge for freedom and change in direction."),
    ("Uranus", "Uranus", 180, "Uranus Opposition (mid-life)", "The classic mid-life awakening — break free and reinvent yourself."),
    ("Uranus", "Sun", 0, "Uranus crosses your Sun", "Sudden changes, liberation and surprising new paths."),
    ("Neptune", "Neptune", 90, "Neptune square Neptune", "Questioning dreams and beliefs; spiritual searching."),
    ("Pluto", "Pluto", 90, "Pluto square Pluto", "A deep transformation of power, priorities and identity."),
    ("Pluto", "Sun", 0, "Pluto crosses your Sun", "A profound rebirth of purpose."),
    ("Rahu", "North Node", 0, "Nodal Return", "An 18.6-year destiny point — fresh direction and fated meetings."),
)


def _series(body: str, jd0: float, jd1: float, step: float) -> list[tuple[float, float]]:
    out, jd = [], jd0
    while jd <= jd1 + step:
        out.append((jd, astro.planet_longitude(body, jd)))
        jd += step
    return out


def life_timeline(natal: dict, birth_jd: float, ref_jd: float, tz: tzinfo, years: int = 90) -> list[dict]:
    """Major lifetime transits from birth to ``years`` later."""
    pts = {p["name"]: p["lon"] for p in natal["planets"]}
    pts["Ascendant"] = natal["ascendant"]["lon"]
    pts["Midheaven"] = natal["midheaven"]["lon"]
    end = birth_jd + years * 365.25
    cache: dict[str, list] = {}
    events = []
    for body, target, angle, title, text in LIFE_EVENTS:
        if target not in pts:
            continue
        step = 2.0 if body == "Jupiter" else 5.0
        series = cache.setdefault(body, _series(body, birth_jd + 30, end, step))
        natal_lon = pts[target]
        exact = []
        for sign in ((1, -1) if angle not in (0, 180) else (1,)):
            goal = natal_lon + sign * angle
            prev = None
            for jd, lon in series:
                d = astro.diff(lon, goal)
                if prev is not None and (prev[1] < 0) != (d < 0) and abs(d - prev[1]) < 20:
                    hit = astro.find_crossing(lambda x: astro.diff(astro.planet_longitude(body, x), goal), prev[0], jd, 1e-3)
                    exact.append(hit)
                prev = (jd, d)
        exact.sort()
        groups = []
        for hit in exact:
            if groups and hit - groups[-1][-1] < 420:
                groups[-1].append(hit)
            else:
                groups.append([hit])
        for g in groups:
            if g[0] - birth_jd < 365.25:
                continue  # the planet is still near its birth position, not a real cycle event
            s, e = g[0] - 60, g[-1] + 60
            status = "past" if e < ref_jd else ("current" if s <= ref_jd else "future")
            events.append({
                "title": title, "text": text, "kind": "transit", "status": status,
                "date": _local(g[0], tz).date().isoformat(),
                "passes": [_local(x, tz).date().isoformat() for x in g],
                "age": round((g[0] - birth_jd) / 365.25, 1),
                "jd": g[0],
            })
    events.sort(key=lambda e: e["jd"])
    return events


# -- Sky events ----------------------------------------------------------------
def sky_events(jd0: float, jd1: float, tz: tzinfo) -> list[dict]:
    """Lunations, eclipses, retrograde stations and ingresses in a range."""
    out = []
    for l in astro.lunations(jd0, jd1):
        title = l["eclipse"] or l["type"]
        out.append({"jd": l["jd"], "kind": "lunation", "title": title, "eclipse": bool(l["eclipse"]),
                    "lon": l["longitude"], "detail": f"{l['type']} at {fmt_pos(l['longitude'])}"})
    for p in ("Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto"):
        for s in astro.stations(p, jd0, jd1, 1.0 if p in ("Mercury", "Venus", "Mars") else 3.0):
            out.append({"jd": s["jd"], "kind": "station", "title": f"{p} turns {s['type']}",
                        "lon": s["longitude"], "detail": f"at {fmt_pos(s['longitude'])}"})
    for p in ("Sun", "Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto"):
        for ev in astro.ingresses(p, jd0, jd1, 0.5 if p in ("Sun", "Mercury", "Venus", "Mars") else 2.0):
            to = SIGN_NAMES[ev["to"]]
            extra = {"Aries": " — March equinox", "Cancer": " — June solstice",
                     "Libra": " — September equinox", "Capricorn": " — December solstice"}.get(to, "") if p == "Sun" else ""
            out.append({"jd": ev["jd"], "kind": "ingress", "title": f"{p} enters {to}{extra}",
                        "lon": ev["to"] * 30, "detail": f"{p} leaves {SIGN_NAMES[ev['from']]}"})
    out.sort(key=lambda e: e["jd"])
    for e in out:
        dt = _local(e["jd"], tz)
        e["date"] = dt.date().isoformat()
        e["time"] = dt.strftime("%H:%M")
    return out
