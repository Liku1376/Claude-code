"""Western (tropical) astrology: signs, natal charts, houses and aspects."""

from __future__ import annotations

from . import astronomy as astro

SIGNS = (
    {"name": "Aries", "symbol": "♈", "element": "Fire", "modality": "Cardinal", "ruler": "Mars",
     "dates": "Mar 21 – Apr 19", "keywords": "bold, pioneering, direct",
     "strengths": "courage, initiative, enthusiasm, honesty",
     "challenges": "impatience, impulsiveness, a short temper",
     "lucky": {"number": 9, "color": "Red", "day": "Tuesday", "stone": "Diamond"}},
    {"name": "Taurus", "symbol": "♉", "element": "Earth", "modality": "Fixed", "ruler": "Venus",
     "dates": "Apr 20 – May 20", "keywords": "steady, sensual, patient",
     "strengths": "reliability, patience, devotion, practicality",
     "challenges": "stubbornness, possessiveness, resistance to change",
     "lucky": {"number": 6, "color": "Green", "day": "Friday", "stone": "Emerald"}},
    {"name": "Gemini", "symbol": "♊", "element": "Air", "modality": "Mutable", "ruler": "Mercury",
     "dates": "May 21 – Jun 20", "keywords": "curious, witty, adaptable",
     "strengths": "communication, quick learning, versatility, humour",
     "challenges": "restlessness, inconsistency, scattered focus",
     "lucky": {"number": 5, "color": "Yellow", "day": "Wednesday", "stone": "Agate"}},
    {"name": "Cancer", "symbol": "♋", "element": "Water", "modality": "Cardinal", "ruler": "Moon",
     "dates": "Jun 21 – Jul 22", "keywords": "nurturing, protective, intuitive",
     "strengths": "loyalty, empathy, tenacity, imagination",
     "challenges": "moodiness, over-sensitivity, holding on too long",
     "lucky": {"number": 2, "color": "Silver", "day": "Monday", "stone": "Pearl"}},
    {"name": "Leo", "symbol": "♌", "element": "Fire", "modality": "Fixed", "ruler": "Sun",
     "dates": "Jul 23 – Aug 22", "keywords": "radiant, generous, dramatic",
     "strengths": "creativity, warmth, leadership, confidence",
     "challenges": "pride, need for attention, inflexibility",
     "lucky": {"number": 1, "color": "Gold", "day": "Sunday", "stone": "Ruby"}},
    {"name": "Virgo", "symbol": "♍", "element": "Earth", "modality": "Mutable", "ruler": "Mercury",
     "dates": "Aug 23 – Sep 22", "keywords": "precise, helpful, analytical",
     "strengths": "diligence, discernment, kindness, practicality",
     "challenges": "worry, perfectionism, self-criticism",
     "lucky": {"number": 5, "color": "Navy", "day": "Wednesday", "stone": "Sapphire"}},
    {"name": "Libra", "symbol": "♎", "element": "Air", "modality": "Cardinal", "ruler": "Venus",
     "dates": "Sep 23 – Oct 22", "keywords": "harmonious, diplomatic, graceful",
     "strengths": "fairness, charm, cooperation, aesthetic sense",
     "challenges": "indecision, people-pleasing, avoiding conflict",
     "lucky": {"number": 6, "color": "Pink", "day": "Friday", "stone": "Opal"}},
    {"name": "Scorpio", "symbol": "♏", "element": "Water", "modality": "Fixed", "ruler": "Mars / Pluto",
     "dates": "Oct 23 – Nov 21", "keywords": "intense, perceptive, transformative",
     "strengths": "determination, depth, loyalty, resourcefulness",
     "challenges": "jealousy, secrecy, holding grudges",
     "lucky": {"number": 8, "color": "Maroon", "day": "Tuesday", "stone": "Topaz"}},
    {"name": "Sagittarius", "symbol": "♐", "element": "Fire", "modality": "Mutable", "ruler": "Jupiter",
     "dates": "Nov 22 – Dec 21", "keywords": "adventurous, optimistic, philosophical",
     "strengths": "generosity, idealism, humour, love of freedom",
     "challenges": "tactlessness, overpromising, restlessness",
     "lucky": {"number": 3, "color": "Purple", "day": "Thursday", "stone": "Turquoise"}},
    {"name": "Capricorn", "symbol": "♑", "element": "Earth", "modality": "Cardinal", "ruler": "Saturn",
     "dates": "Dec 22 – Jan 19", "keywords": "ambitious, disciplined, responsible",
     "strengths": "self-control, persistence, strategy, integrity",
     "challenges": "pessimism, rigidity, overwork",
     "lucky": {"number": 8, "color": "Brown", "day": "Saturday", "stone": "Garnet"}},
    {"name": "Aquarius", "symbol": "♒", "element": "Air", "modality": "Fixed", "ruler": "Saturn / Uranus",
     "dates": "Jan 20 – Feb 18", "keywords": "original, humanitarian, independent",
     "strengths": "vision, friendship, inventiveness, open-mindedness",
     "challenges": "detachment, contrariness, unpredictability",
     "lucky": {"number": 4, "color": "Electric blue", "day": "Saturday", "stone": "Amethyst"}},
    {"name": "Pisces", "symbol": "♓", "element": "Water", "modality": "Mutable", "ruler": "Jupiter / Neptune",
     "dates": "Feb 19 – Mar 20", "keywords": "compassionate, imaginative, spiritual",
     "strengths": "intuition, artistry, gentleness, empathy",
     "challenges": "escapism, over-giving, unclear boundaries",
     "lucky": {"number": 7, "color": "Sea green", "day": "Thursday", "stone": "Aquamarine"}},
)
SIGN_NAMES = tuple(s["name"] for s in SIGNS)

PLANET_INFO = {
    "Sun": ("☉", "identity, vitality and purpose"),
    "Moon": ("☽", "emotions, instincts and inner needs"),
    "Mercury": ("☿", "thinking, learning and communication"),
    "Venus": ("♀", "love, beauty, money and values"),
    "Mars": ("♂", "drive, courage and desire"),
    "Jupiter": ("♃", "growth, luck, wisdom and opportunity"),
    "Saturn": ("♄", "discipline, limits, responsibility and maturity"),
    "Uranus": ("♅", "change, freedom and sudden breakthroughs"),
    "Neptune": ("♆", "dreams, intuition, spirituality and illusion"),
    "Pluto": ("♇", "power, transformation and rebirth"),
    "North Node": ("☊", "the direction of growth and destiny"),
    "Ascendant": ("AC", "outer personality and first impressions"),
    "Midheaven": ("MC", "career, reputation and public life"),
}

HOUSE_MEANINGS = (
    "self, body and appearance", "money, possessions and self-worth",
    "communication, siblings and short trips", "home, family and roots",
    "creativity, romance, children and pleasure", "work, health and daily routine",
    "partnership and marriage", "shared resources, intimacy and transformation",
    "higher learning, travel and beliefs", "career, status and ambition",
    "friends, networks and hopes", "solitude, the subconscious and endings",
)

ASPECTS = (
    {"name": "Conjunction", "angle": 0, "orb": 8, "symbol": "☌", "nature": "intense",
     "meaning": "merge and amplify each other"},
    {"name": "Sextile", "angle": 60, "orb": 5, "symbol": "⚹", "nature": "harmonious",
     "meaning": "offer easy opportunities when you act on them"},
    {"name": "Square", "angle": 90, "orb": 7, "symbol": "□", "nature": "challenging",
     "meaning": "create friction that pushes you to grow"},
    {"name": "Trine", "angle": 120, "orb": 7, "symbol": "△", "nature": "harmonious",
     "meaning": "flow together naturally and supportively"},
    {"name": "Opposition", "angle": 180, "orb": 8, "symbol": "☍", "nature": "challenging",
     "meaning": "pull in opposite directions and ask for balance"},
)

COMPATIBLE_ELEMENTS = {"Fire": ("Fire", "Air"), "Air": ("Air", "Fire"),
                       "Earth": ("Earth", "Water"), "Water": ("Water", "Earth")}

BODIES = ("Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn",
          "Uranus", "Neptune", "Pluto", "North Node")


def sign_of(lon: float) -> int:
    return int(astro.norm(lon) // 30)


def fmt_pos(lon: float) -> str:
    """Format a longitude as e.g. 12°34' Leo."""
    lon = astro.norm(lon)
    deg = lon % 30
    d = int(deg)
    m = int(round((deg - d) * 60))
    if m == 60:
        d, m = d + 1, 0
    return f"{d}°{m:02d}' {SIGN_NAMES[int(lon // 30)]}"


def sun_sign_for_date(month: int, day: int) -> int:
    """Sun sign from a calendar date alone (traditional boundaries)."""
    # (month, day) each sign starts, in calendar order, with its sign index.
    starts = ((1, 20, 10), (2, 19, 11), (3, 21, 0), (4, 20, 1), (5, 21, 2), (6, 21, 3),
              (7, 23, 4), (8, 23, 5), (9, 23, 6), (10, 23, 7), (11, 22, 8), (12, 22, 9))
    sign = 9  # Jan 1 - 19: Capricorn
    for m, d, idx in starts:
        if (month, day) >= (m, d):
            sign = idx
    return sign


def positions(jd: float, sidereal: bool = False) -> dict[str, dict]:
    """Longitude, speed and retrograde flag for every chart body."""
    ayan = astro.lahiri_ayanamsa(jd) if sidereal else 0.0
    out = {}
    for name in BODIES:
        key = "Rahu" if name == "North Node" else name
        lon = astro.norm(astro.planet_longitude(key, jd) - ayan)
        spd = astro.speed(key, jd)
        out[name] = {"lon": lon, "speed": spd, "retro": spd < 0 and name not in ("Sun", "Moon", "North Node")}
    return out


def house_cusps(asc: float, mc: float, system: str) -> list[float]:
    """House cusps for the Whole Sign, Equal or Porphyry systems."""
    if system == "whole":
        start = sign_of(asc) * 30
        return [astro.norm(start + 30 * i) for i in range(12)]
    if system == "porphyry":
        ic, dsc = astro.norm(mc + 180), astro.norm(asc + 180)
        cusps = [0.0] * 12
        quads = ((asc, ic, 0), (ic, dsc, 3), (dsc, mc, 6), (mc, asc, 9))
        for start, end, idx in quads:
            span = astro.norm(end - start)
            for k in range(3):
                cusps[idx + k] = astro.norm(start + span * k / 3)
        return cusps
    return [astro.norm(asc + 30 * i) for i in range(12)]


def house_of(lon: float, cusps: list[float]) -> int:
    """1-based house number containing a longitude."""
    for i in range(12):
        start, end = cusps[i], cusps[(i + 1) % 12]
        if astro.norm(lon - start) < astro.norm(end - start) or astro.norm(end - start) == 0:
            return i + 1
    return 1


def find_aspect(a: float, b: float, orb_scale: float = 1.0):
    """The tightest aspect between two longitudes, or None."""
    sep = abs(astro.diff(a, b))
    best = None
    for asp in ASPECTS:
        orb = abs(sep - asp["angle"])
        if orb <= asp["orb"] * orb_scale and (best is None or orb < best[1]):
            best = (asp, orb)
    return best


def aspects_between(points_a: dict, points_b: dict | None = None, orb_scale: float = 1.0) -> list[dict]:
    """Aspects within one chart (points_b None) or between two charts."""
    out = []
    names_a = list(points_a)
    for i, na in enumerate(names_a):
        others = names_a[i + 1:] if points_b is None else list(points_b)
        for nb in others:
            lb = (points_a if points_b is None else points_b)[nb]
            hit = find_aspect(points_a[na], lb, orb_scale)
            if hit:
                asp, orb = hit
                out.append({"a": na, "b": nb, "aspect": asp["name"], "symbol": asp["symbol"],
                            "nature": asp["nature"], "orb": round(orb, 2),
                            "text": f"{na} ({PLANET_INFO.get(na, ('', na))[1]}) and {nb} "
                                    f"({PLANET_INFO.get(nb, ('', nb))[1]}) {asp['meaning']}."})
    out.sort(key=lambda x: x["orb"])
    return out


def planet_in_sign_text(planet: str, sign_idx: int) -> str:
    sign = SIGNS[sign_idx]
    return (f"Your {planet} — {PLANET_INFO[planet][1]} — expresses itself through {sign['name']}: "
            f"{sign['keywords']}. At best this shows as {sign['strengths'].split(', ')[0]} and "
            f"{sign['strengths'].split(', ')[1]}; watch for {sign['challenges'].split(', ')[0]}.")


def natal_chart(jd: float, lat: float, lon: float, house_system: str = "porphyry", sidereal: bool = False) -> dict:
    """A complete natal chart as plain JSON-friendly data."""
    ayan = astro.lahiri_ayanamsa(jd) if sidereal else 0.0
    ang = astro.angles(jd, lat, lon)
    asc, mc = astro.norm(ang["asc"] - ayan), astro.norm(ang["mc"] - ayan)
    system = house_system if house_system in ("whole", "equal", "porphyry") else "porphyry"
    cusps = house_cusps(asc, mc, system)
    pos = positions(jd, sidereal)
    planets = []
    for name, p in pos.items():
        s = sign_of(p["lon"])
        house = house_of(p["lon"], cusps)
        planets.append({
            "name": name, "glyph": PLANET_INFO[name][0], "lon": round(p["lon"], 4),
            "sign": SIGN_NAMES[s], "sign_symbol": SIGNS[s]["symbol"], "position": fmt_pos(p["lon"]),
            "house": house, "retro": p["retro"], "speed": round(p["speed"], 4),
            "text": (planet_in_sign_text(name, s) if name in PLANET_INFO and name != "North Node"
                     else f"Your North Node in {SIGN_NAMES[s]} points your growth towards {SIGNS[s]['keywords']} qualities.")
                    + f" It falls in house {house}: {HOUSE_MEANINGS[house - 1]}.",
        })
    points = {p["name"]: p["lon"] for p in planets if p["name"] != "North Node"}
    points["Ascendant"], points["Midheaven"] = asc, mc
    elements = {"Fire": 0, "Earth": 0, "Air": 0, "Water": 0}
    modalities = {"Cardinal": 0, "Fixed": 0, "Mutable": 0}
    for name in ("Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Ascendant"):
        sign = SIGNS[sign_of(points[name])]
        weight = 2 if name in ("Sun", "Moon", "Ascendant") else 1
        elements[sign["element"]] += weight
        modalities[sign["modality"]] += weight
    sun_s, moon_s, asc_s = (SIGNS[sign_of(points[k])] for k in ("Sun", "Moon", "Ascendant"))
    summary = (f"Sun in {sun_s['name']}: at your core you are {sun_s['keywords']}. "
               f"Moon in {moon_s['name']}: emotionally you need to feel {moon_s['keywords'].split(', ')[0]} "
               f"and respond in a {moon_s['keywords'].split(', ')[-1]} way. "
               f"{asc_s['name']} rising: others first meet someone {asc_s['keywords']}. "
               f"Your dominant element is {max(elements, key=elements.get)} and your dominant mode is "
               f"{max(modalities, key=modalities.get)}.")
    return {
        "zodiac": "sidereal (Lahiri)" if sidereal else "tropical",
        "ayanamsa": round(ayan, 4),
        "house_system": system,
        "ascendant": {"lon": round(asc, 4), "position": fmt_pos(asc), "sign": SIGN_NAMES[sign_of(asc)]},
        "midheaven": {"lon": round(mc, 4), "position": fmt_pos(mc), "sign": SIGN_NAMES[sign_of(mc)]},
        "cusps": [round(c, 4) for c in cusps],
        "planets": planets,
        "aspects": aspects_between(points),
        "elements": elements,
        "modalities": modalities,
        "summary": summary,
    }
