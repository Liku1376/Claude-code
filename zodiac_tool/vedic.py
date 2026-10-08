"""Vedic (Jyotish) astrology: sidereal positions, nakshatras, Vimshottari
dasha, Panchang, Manglik and Sade Sati checks, and Ashtakoota (Guna Milan)
matching. Uses the Lahiri ayanamsa and whole-sign houses."""

from __future__ import annotations

from datetime import datetime, timedelta

from . import astronomy as astro

RASHIS = ("Mesha (Aries)", "Vrishabha (Taurus)", "Mithuna (Gemini)", "Karka (Cancer)",
          "Simha (Leo)", "Kanya (Virgo)", "Tula (Libra)", "Vrishchika (Scorpio)",
          "Dhanu (Sagittarius)", "Makara (Capricorn)", "Kumbha (Aquarius)", "Meena (Pisces)")
RASHI_LORDS = ("Mars", "Venus", "Mercury", "Moon", "Sun", "Mercury",
               "Venus", "Mars", "Jupiter", "Saturn", "Saturn", "Jupiter")

NAKSHATRAS = (
    ("Ashwini", "Ketu", "Ashwini Kumaras", "Horse's head"), ("Bharani", "Venus", "Yama", "Yoni"),
    ("Krittika", "Sun", "Agni", "Razor / flame"), ("Rohini", "Moon", "Brahma", "Chariot"),
    ("Mrigashira", "Mars", "Soma", "Deer's head"), ("Ardra", "Rahu", "Rudra", "Teardrop"),
    ("Punarvasu", "Jupiter", "Aditi", "Quiver of arrows"), ("Pushya", "Saturn", "Brihaspati", "Cow's udder"),
    ("Ashlesha", "Mercury", "Nagas", "Coiled serpent"), ("Magha", "Ketu", "Pitris", "Royal throne"),
    ("Purva Phalguni", "Venus", "Bhaga", "Front legs of a bed"),
    ("Uttara Phalguni", "Sun", "Aryaman", "Back legs of a bed"), ("Hasta", "Moon", "Savitar", "Hand"),
    ("Chitra", "Mars", "Vishvakarma", "Bright jewel"), ("Swati", "Rahu", "Vayu", "Young sprout"),
    ("Vishakha", "Jupiter", "Indra-Agni", "Triumphal arch"), ("Anuradha", "Saturn", "Mitra", "Lotus"),
    ("Jyeshtha", "Mercury", "Indra", "Earring / umbrella"), ("Mula", "Ketu", "Nirriti", "Bundle of roots"),
    ("Purva Ashadha", "Venus", "Apas", "Winnowing basket"),
    ("Uttara Ashadha", "Sun", "Vishvadevas", "Elephant tusk"), ("Shravana", "Moon", "Vishnu", "Ear"),
    ("Dhanishta", "Mars", "Vasus", "Drum"), ("Shatabhisha", "Rahu", "Varuna", "Empty circle"),
    ("Purva Bhadrapada", "Jupiter", "Aja Ekapada", "Front of a funeral cot"),
    ("Uttara Bhadrapada", "Saturn", "Ahir Budhnya", "Back of a funeral cot"),
    ("Revati", "Mercury", "Pushan", "Fish / drum"),
)
NAK_SPAN = 360 / 27

DASHA_ORDER = ("Ketu", "Venus", "Sun", "Moon", "Mars", "Rahu", "Jupiter", "Saturn", "Mercury")
DASHA_YEARS = {"Ketu": 7, "Venus": 20, "Sun": 6, "Moon": 10, "Mars": 7, "Rahu": 18,
               "Jupiter": 16, "Saturn": 19, "Mercury": 17}
DASHA_THEMES = {
    "Ketu": "detachment, spirituality, sudden endings and inner searching",
    "Venus": "love, marriage, comfort, art, vehicles and material pleasures",
    "Sun": "authority, career recognition, father figures and self-confidence",
    "Moon": "emotions, mother, home, public life and mental peace",
    "Mars": "energy, property, courage, siblings, competition and conflict",
    "Rahu": "ambition, foreign links, unconventional paths, obsession and sudden rise",
    "Jupiter": "wisdom, expansion, children, teachers, wealth and good fortune",
    "Saturn": "hard work, discipline, delays that teach, longevity and lasting results",
    "Mercury": "learning, business, communication, trade and intelligence",
}
YEAR_DAYS = 365.25

GRAHAS = ("Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu")
GRAHA_SHORT = {"Sun": "Su", "Moon": "Mo", "Mars": "Ma", "Mercury": "Me", "Jupiter": "Ju",
               "Venus": "Ve", "Saturn": "Sa", "Rahu": "Ra", "Ketu": "Ke", "Lagna": "Asc"}

TITHIS = ("Pratipada", "Dwitiya", "Tritiya", "Chaturthi", "Panchami", "Shashthi", "Saptami",
          "Ashtami", "Navami", "Dashami", "Ekadashi", "Dwadashi", "Trayodashi", "Chaturdashi")
YOGAS = ("Vishkambha", "Priti", "Ayushman", "Saubhagya", "Shobhana", "Atiganda", "Sukarma",
         "Dhriti", "Shula", "Ganda", "Vriddhi", "Dhruva", "Vyaghata", "Harshana", "Vajra",
         "Siddhi", "Vyatipata", "Variyan", "Parigha", "Shiva", "Siddha", "Sadhya", "Shubha",
         "Shukla", "Brahma", "Indra", "Vaidhriti")
INAUSPICIOUS_YOGAS = {"Vishkambha", "Atiganda", "Shula", "Ganda", "Vyaghata", "Vajra",
                      "Vyatipata", "Parigha", "Vaidhriti"}
KARANAS_MOVABLE = ("Bava", "Balava", "Kaulava", "Taitila", "Garaja", "Vanija", "Vishti")
VARAS = ("Somavara (Monday)", "Mangalavara (Tuesday)", "Budhavara (Wednesday)",
         "Guruvara (Thursday)", "Shukravara (Friday)", "Shanivara (Saturday)", "Ravivara (Sunday)")


def sidereal(lon: float, jd: float) -> float:
    return astro.norm(lon - astro.lahiri_ayanamsa(jd))


def nakshatra_of(lon: float) -> dict:
    idx = int(lon // NAK_SPAN)
    within = lon - idx * NAK_SPAN
    name, lord, deity, symbol = NAKSHATRAS[idx]
    return {"index": idx, "name": name, "lord": lord, "deity": deity, "symbol": symbol,
            "pada": int(within // (NAK_SPAN / 4)) + 1, "fraction": within / NAK_SPAN}


def graha_positions(jd: float) -> dict[str, float]:
    """Sidereal longitudes of the nine grahas."""
    out = {}
    for g in GRAHAS:
        out[g] = sidereal(astro.planet_longitude(g, jd), jd)
    return out


def _add_years(dt: datetime, years: float) -> datetime:
    return dt + timedelta(days=years * YEAR_DAYS)


def vimshottari(moon_sid: float, birth: datetime, ref: datetime, levels: int = 2) -> dict:
    """Vimshottari mahadashas (and antardashas) from birth, each tagged past,
    current or future relative to ``ref``."""
    nak = nakshatra_of(moon_sid)
    first = nak["lord"]
    start_idx = DASHA_ORDER.index(first)
    # The part of the first dasha already "used up" before birth.
    elapsed = nak["fraction"] * DASHA_YEARS[first]
    cursor = _add_years(birth, -elapsed)

    def status(start, end):
        return "past" if end <= ref else ("current" if start <= ref else "future")

    periods = []
    for k in range(9):
        lord = DASHA_ORDER[(start_idx + k) % 9]
        span = DASHA_YEARS[lord]
        start, end = cursor, _add_years(cursor, span)
        entry = {"lord": lord, "start": start.isoformat(), "end": end.isoformat(),
                 "years": span, "status": status(start, end), "theme": DASHA_THEMES[lord]}
        if levels > 1:
            subs, sub_cursor = [], start
            for j in range(9):
                sub_lord = DASHA_ORDER[(DASHA_ORDER.index(lord) + j) % 9]
                sub_span = span * DASHA_YEARS[sub_lord] / 120
                s_end = _add_years(sub_cursor, sub_span)
                subs.append({"lord": sub_lord, "start": sub_cursor.isoformat(), "end": s_end.isoformat(),
                             "status": status(sub_cursor, s_end)})
                sub_cursor = s_end
            entry["antardashas"] = subs
        periods.append(entry)
        cursor = end
    current = next((p for p in periods if p["status"] == "current"), None)
    current_sub = next((s for s in current.get("antardashas", []) if s["status"] == "current"), None) if current else None
    reading = None
    if current:
        reading = (f"On {ref.date().isoformat()} you are in {current['lord']} Mahadasha"
                   + (f" / {current_sub['lord']} Antardasha" if current_sub else "")
                   + f". The main period highlights {current['theme']}"
                   + (f", coloured by {DASHA_THEMES[current_sub['lord']]}." if current_sub else "."))
    return {"birth_nakshatra": nak["name"], "start_lord": first,
            "balance_years": round(DASHA_YEARS[first] - elapsed, 2),
            "periods": periods, "current": current and current["lord"],
            "current_sub": current_sub and current_sub["lord"], "reading": reading}


def kundli(jd: float, lat: float, lon: float, birth: datetime, ref: datetime) -> dict:
    """A Vedic birth chart (Rashi chart, whole-sign houses from Lagna)."""
    pos = graha_positions(jd)
    lagna = sidereal(astro.angles(jd, lat, lon)["asc"], jd)
    lagna_sign = int(lagna // 30)
    grahas = []
    for g, lon_ in pos.items():
        sign = int(lon_ // 30)
        nak = nakshatra_of(lon_)
        retro = g not in ("Sun", "Moon", "Rahu", "Ketu") and astro.speed(g, jd) < 0
        grahas.append({"name": g, "short": GRAHA_SHORT[g], "lon": round(lon_, 4),
                       "rashi": RASHIS[sign], "sign": sign, "degree": round(lon_ % 30, 2),
                       "house": (sign - lagna_sign) % 12 + 1, "nakshatra": nak["name"],
                       "pada": nak["pada"], "retro": retro})
    moon_sign = int(pos["Moon"] // 30)
    moon_nak = nakshatra_of(pos["Moon"])
    mars_house = (int(pos["Mars"] // 30) - lagna_sign) % 12 + 1
    mars_from_moon = (int(pos["Mars"] // 30) - moon_sign) % 12 + 1
    manglik_houses = (1, 2, 4, 7, 8, 12)
    manglik = mars_house in manglik_houses
    manglik_moon = mars_from_moon in manglik_houses
    return {
        "ayanamsa": round(astro.lahiri_ayanamsa(jd), 4),
        "lagna": {"lon": round(lagna, 4), "rashi": RASHIS[lagna_sign], "sign": lagna_sign,
                  "degree": round(lagna % 30, 2), "lord": RASHI_LORDS[lagna_sign],
                  "nakshatra": nakshatra_of(lagna)["name"]},
        "moon_sign": {"rashi": RASHIS[moon_sign], "sign": moon_sign, "lord": RASHI_LORDS[moon_sign]},
        "sun_sign": RASHIS[int(pos["Sun"] // 30)],
        "nakshatra": moon_nak,
        "grahas": grahas,
        "manglik": {
            "from_lagna": manglik, "from_moon": manglik_moon, "mars_house": mars_house,
            "text": ("Mangal Dosha is present" if manglik else "No Mangal Dosha from the Lagna")
                    + f" (Mars in house {mars_house} from Lagna, {mars_from_moon} from the Moon). "
                    + ("Traditionally it is matched with a partner who also has it, and its effect is "
                       "said to soften after age 28." if manglik or manglik_moon else ""),
        },
        "dasha": vimshottari(pos["Moon"], birth, ref),
        "sade_sati": sade_sati(moon_sign, jd, ref),
    }


def sade_sati(moon_sign: int, birth_jd: float, ref: datetime, years: int = 100) -> dict:
    """Sade Sati (Saturn transiting the 12th, 1st and 2nd signs from the
    natal Moon) periods across a lifetime, plus the Dhaiya (4th and 8th)."""
    targets = {(moon_sign - 1) % 12: "rising (12th from Moon)", moon_sign: "peak (over the Moon)",
               (moon_sign + 1) % 12: "setting (2nd from Moon)"}
    dhaiya = {(moon_sign + 3) % 12: "Kantaka Shani (4th)", (moon_sign + 7) % 12: "Ashtama Shani (8th)"}
    end_jd = birth_jd + years * YEAR_DAYS
    sign_at = lambda x: int(sidereal(astro.planet_longitude("Saturn", x), x) // 30)
    spans = []
    start_sign = sign_at(birth_jd)
    cur_start = birth_jd
    for ev in astro.ingresses("Saturn", birth_jd, end_jd, step=5.0, sidereal=True):
        spans.append((cur_start, ev["jd"], start_sign))
        cur_start, start_sign = ev["jd"], ev["to"]
    spans.append((cur_start, end_jd, start_sign))

    def merge(keys):
        merged = []
        for s, e, sign in spans:
            if sign in keys:
                if merged and s - merged[-1][1] < 1:
                    merged[-1][1] = e
                else:
                    merged.append([s, e])
        # Saturn's retrograde dips out of a sign briefly; bridge gaps < 1.2 years.
        out = []
        for s, e in merged:
            if out and s - out[-1][1] < 1.2 * YEAR_DAYS:
                out[-1][1] = e
            else:
                out.append([s, e])
        return out

    ref_jd = astro.julian_day(ref)

    def tag(s, e):
        return "past" if e <= ref_jd else ("current" if s <= ref_jd else "future")

    periods = [{"start": astro.from_julian_day(s).date().isoformat(), "end": astro.from_julian_day(e).date().isoformat(),
                "status": tag(s, e), "open_start": s <= birth_jd + 1, "open_end": e >= end_jd - 1}
               for s, e in merge(set(targets))]
    dh = [{"start": astro.from_julian_day(s).date().isoformat(), "end": astro.from_julian_day(e).date().isoformat(),
           "status": tag(s, e), "kind": dhaiya[sign]}
          for s, e, sign in spans if sign in dhaiya and e - s > 30]
    now_sign = sign_at(ref_jd)
    if now_sign in targets:
        now = f"Sade Sati is active on this date — the {targets[now_sign]} phase."
    elif now_sign in dhaiya:
        now = f"Sade Sati is not active, but {dhaiya[now_sign]} Dhaiya is running."
    else:
        now = "Sade Sati is not active on this date."
    return {"periods": periods, "dhaiya": dh, "status_text": now,
            "saturn_now": RASHIS[now_sign],
            "about": "Sade Sati is the roughly 7½-year transit of Saturn over the signs around your "
                     "natal Moon — traditionally a time of pressure, responsibility and lasting lessons."}


def panchang(jd: float, local: datetime) -> dict:
    """The five limbs of the Hindu almanac for a moment."""
    sun = sidereal(astro.sun_longitude(jd), jd)
    moon = sidereal(astro.moon_longitude(jd), jd)
    elong = astro.norm(moon - sun)
    t_idx = int(elong // 12)
    paksha = "Shukla (waxing)" if t_idx < 15 else "Krishna (waning)"
    if t_idx == 14:
        tithi = "Purnima (Full Moon)"
    elif t_idx == 29:
        tithi = "Amavasya (New Moon)"
    else:
        tithi = TITHIS[t_idx % 15]
    k_idx = int(elong // 6)  # 0..59
    if k_idx == 0:
        karana = "Kimstughna"
    elif k_idx >= 57:
        karana = ("Shakuni", "Chatushpada", "Naga")[k_idx - 57]
    else:
        karana = KARANAS_MOVABLE[(k_idx - 1) % 7]
    yoga = YOGAS[int(astro.norm(sun + moon) // NAK_SPAN)]
    nak = nakshatra_of(moon)
    return {
        "vara": VARAS[local.weekday()],
        "tithi": tithi, "tithi_number": t_idx + 1, "paksha": paksha,
        "tithi_progress": round((elong % 12) / 12 * 100, 1),
        "nakshatra": nak["name"], "nakshatra_pada": nak["pada"], "nakshatra_lord": nak["lord"],
        "yoga": yoga, "yoga_auspicious": yoga not in INAUSPICIOUS_YOGAS,
        "karana": karana, "karana_auspicious": karana != "Vishti",
        "moon_rashi": RASHIS[int(moon // 30)], "sun_rashi": RASHIS[int(sun // 30)],
    }


# -- Ashtakoota (Guna Milan) -------------------------------------------------
_VARNA_NAMES = ("Brahmin", "Kshatriya", "Vaishya", "Shudra")
# Element-based varna: water signs Brahmin, fire Kshatriya, earth Vaishya, air Shudra.
_VARNA = tuple({0: 1, 1: 2, 2: 3, 3: 0}[i % 4] for i in range(12))
_VASHYA_NAMES = ("Chatushpada", "Manava", "Jalachara", "Vanachara", "Keeta")
_VASHYA_TABLE = ((2, 1, 1, 0.5, 1), (1, 2, 0.5, 0, 1), (1, 0.5, 2, 1, 1),
                 (0.5, 0, 1, 2, 0), (1, 1, 1, 0, 2))
_YONI = ("Horse", "Elephant", "Sheep", "Serpent", "Serpent", "Dog", "Cat", "Sheep", "Cat", "Rat",
         "Rat", "Cow", "Buffalo", "Tiger", "Buffalo", "Tiger", "Deer", "Deer", "Dog", "Monkey",
         "Mongoose", "Monkey", "Lion", "Horse", "Lion", "Cow", "Elephant")
_YONI_ENEMIES = {frozenset(p) for p in (("Horse", "Buffalo"), ("Elephant", "Lion"), ("Sheep", "Monkey"),
                                         ("Serpent", "Mongoose"), ("Dog", "Deer"), ("Cat", "Rat"),
                                         ("Cow", "Tiger"))}
_FRIENDS = {
    "Sun": ({"Moon", "Mars", "Jupiter"}, {"Mercury"}),
    "Moon": ({"Sun", "Mercury"}, {"Mars", "Jupiter", "Venus", "Saturn"}),
    "Mars": ({"Sun", "Moon", "Jupiter"}, {"Venus", "Saturn"}),
    "Mercury": ({"Sun", "Venus"}, {"Mars", "Jupiter", "Saturn"}),
    "Jupiter": ({"Sun", "Moon", "Mars"}, {"Saturn"}),
    "Venus": ({"Mercury", "Saturn"}, {"Mars", "Jupiter"}),
    "Saturn": ({"Mercury", "Venus"}, {"Jupiter"}),
}
_GANA = "DMRMDMDDRRMMDRDRDRRMMDRRMMD"  # Deva / Manushya / Rakshasa per nakshatra
_GANA_NAMES = {"D": "Deva", "M": "Manushya", "R": "Rakshasa"}
_NADI = ("Aadi", "Madhya", "Antya", "Antya", "Madhya", "Aadi")


def _vashya(sign: int, deg: float) -> int:
    if sign in (0, 1):
        return 0
    if sign == 8:
        return 1 if deg < 15 else 0
    if sign == 9:
        return 0 if deg < 15 else 2
    if sign in (3, 11):
        return 2
    if sign == 4:
        return 3
    if sign == 7:
        return 4
    return 1  # Gemini, Virgo, Libra, Aquarius


def _relation(a: str, b: str) -> str:
    friends, neutral = _FRIENDS[a]
    return "friend" if b in friends or a == b else ("neutral" if b in neutral else "enemy")


def guna_milan(boy_moon: float, girl_moon: float) -> dict:
    """Ashtakoota matching on two sidereal Moon longitudes (out of 36)."""
    bs, gs = int(boy_moon // 30), int(girl_moon // 30)
    bn, gn = int(boy_moon // NAK_SPAN), int(girl_moon // NAK_SPAN)
    kootas = []

    varna = 1 if _VARNA[bs] <= _VARNA[gs] else 0
    kootas.append(("Varna", 1, varna, f"{_VARNA_NAMES[_VARNA[bs]]} / {_VARNA_NAMES[_VARNA[gs]]}",
                   "spiritual compatibility and ego"))
    bv, gv = _vashya(bs, boy_moon % 30), _vashya(gs, girl_moon % 30)
    kootas.append(("Vashya", 2, _VASHYA_TABLE[bv][gv], f"{_VASHYA_NAMES[bv]} / {_VASHYA_NAMES[gv]}",
                   "mutual attraction and influence"))
    t1, t2 = ((bn - gn) % 27) % 9 + 1, ((gn - bn) % 27) % 9 + 1
    tara = (0 if t1 in (3, 5, 7) else 1.5) + (0 if t2 in (3, 5, 7) else 1.5)
    kootas.append(("Tara", 3, tara, f"{t1} / {t2}", "health and well-being of the couple"))
    by, gy = _YONI[bn], _YONI[gn]
    yoni = 4 if by == gy else (0 if frozenset((by, gy)) in _YONI_ENEMIES else 2)
    kootas.append(("Yoni", 4, yoni, f"{by} / {gy}", "physical and intimate compatibility"))
    bl, gl = RASHI_LORDS[bs], RASHI_LORDS[gs]
    rel = sorted((_relation(bl, gl), _relation(gl, bl)))
    maitri = {("friend", "friend"): 5, ("friend", "neutral"): 4, ("neutral", "neutral"): 3,
              ("enemy", "friend"): 1, ("enemy", "neutral"): 0.5, ("enemy", "enemy"): 0}[tuple(rel)]
    kootas.append(("Graha Maitri", 5, maitri, f"{bl} / {gl}", "mental compatibility and friendship"))
    bg, gg = _GANA[bn], _GANA[gn]
    gana_scores = {("D", "D"): 6, ("M", "M"): 6, ("R", "R"): 6, ("D", "M"): 6, ("M", "D"): 5,
                   ("D", "R"): 1, ("R", "D"): 0, ("M", "R"): 0, ("R", "M"): 0}
    kootas.append(("Gana", 6, gana_scores[(bg, gg)], f"{_GANA_NAMES[bg]} / {_GANA_NAMES[gg]}",
                   "temperament and nature"))
    dist = (gs - bs) % 12 + 1
    bad = {(2, 12), (12, 2), (5, 9), (9, 5), (6, 8), (8, 6)}
    bhakoot = 0 if (dist, (bs - gs) % 12 + 1) in bad else 7
    kootas.append(("Bhakoot", 7, bhakoot, f"{RASHIS[bs].split()[0]} / {RASHIS[gs].split()[0]}",
                   "family welfare, finances and growth"))
    bnadi, gnadi = _NADI[bn % 6], _NADI[gn % 6]
    nadi = 0 if bnadi == gnadi else 8
    kootas.append(("Nadi", 8, nadi, f"{bnadi} / {gnadi}", "health, genes and progeny"))

    total = sum(k[2] for k in kootas)
    if total >= 28:
        verdict = "Excellent match"
    elif total >= 24:
        verdict = "Very good match"
    elif total >= 18:
        verdict = "Acceptable match"
    else:
        verdict = "Not recommended traditionally"
    doshas = []
    if nadi == 0:
        doshas.append("Nadi Dosha (same Nadi)")
    if bhakoot == 0:
        doshas.append("Bhakoot Dosha")
    return {"kootas": [{"name": n, "max": m, "score": s, "detail": d, "about": a} for n, m, s, d, a in kootas],
            "total": total, "max": 36, "verdict": verdict, "doshas": doshas}
