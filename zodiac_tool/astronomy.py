"""Astronomical positions needed for astrology, standard library only.

Accuracy is "astrology grade": the Sun and planets come from the JPL
approximate Keplerian elements (valid 1800-2050, usable well beyond with a
small loss of accuracy), the Moon from the main terms of Meeus' lunar
theory. Positions agree with full ephemerides to within a few arc-minutes
for the Sun and planets and roughly a tenth of a degree for the Moon.

All longitudes are geocentric ecliptic longitudes in degrees, measured
from the tropical (moving) equinox of date unless stated otherwise.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

J2000 = 2451545.0
PLANETS = ("Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn",
           "Uranus", "Neptune", "Pluto")

# JPL "Keplerian Elements for Approximate Positions of the Major Planets",
# table 1 (1800-2050 AD). Per planet: (value at J2000, rate per century) for
# a [au], e, I [deg], L [deg], long. of perihelion [deg], long. of node [deg].
_ELEMENTS = {
    "Mercury": ((0.38709927, 0.00000037), (0.20563593, 0.00001906), (7.00497902, -0.00594749),
                (252.25032350, 149472.67411175), (77.45779628, 0.16047689), (48.33076593, -0.12534081)),
    "Venus": ((0.72333566, 0.00000390), (0.00677672, -0.00004107), (3.39467605, -0.00078890),
              (181.97909950, 58517.81538729), (131.60246718, 0.00268329), (76.67984255, -0.27769418)),
    "Earth": ((1.00000261, 0.00000562), (0.01671123, -0.00004392), (-0.00001531, -0.01294668),
              (100.46457166, 35999.37244981), (102.93768193, 0.32327364), (0.0, 0.0)),
    "Mars": ((1.52371034, 0.00001847), (0.09339410, 0.00007882), (1.84969142, -0.00813131),
             (-4.55343205, 19140.30268499), (-23.94362959, 0.44441088), (49.55953891, -0.29257343)),
    "Jupiter": ((5.20288700, -0.00011607), (0.04838624, -0.00013253), (1.30439695, -0.00183714),
                (34.39644051, 3034.74612775), (14.72847983, 0.21252668), (100.47390909, 0.20469106)),
    "Saturn": ((9.53667594, -0.00125060), (0.05386179, -0.00050991), (2.48599187, 0.00193609),
               (49.95424423, 1222.49362201), (92.59887831, -0.41897216), (113.66242448, -0.28867794)),
    "Uranus": ((19.18916464, -0.00196176), (0.04725744, -0.00004397), (0.77263783, -0.00242939),
               (313.23810451, 428.48202785), (170.95427630, 0.40805281), (74.01692503, 0.04240589)),
    "Neptune": ((30.06992276, 0.00026291), (0.00859048, 0.00005105), (1.77004347, 0.00035372),
                (-55.12002969, 218.45945325), (44.96476227, -0.32241464), (131.78422574, -0.00508664)),
    "Pluto": ((39.48211675, -0.00031596), (0.24882730, 0.00005170), (17.14001206, 0.00004818),
              (238.92903833, 145.20780515), (224.06891629, -0.04062942), (110.30393684, -0.01183482)),
}

# Main periodic terms of the Moon's longitude (Meeus, Astronomical
# Algorithms, table 47.A): multiples of D, M, M', F and the coefficient in
# millionths of a degree.
_MOON_TERMS = (
    (0, 0, 1, 0, 6288774), (2, 0, -1, 0, 1274027), (2, 0, 0, 0, 658314), (0, 0, 2, 0, 213618),
    (0, 1, 0, 0, -185116), (0, 0, 0, 2, -114332), (2, 0, -2, 0, 58793), (2, -1, -1, 0, 57066),
    (2, 0, 1, 0, 53322), (2, -1, 0, 0, 45758), (0, 1, -1, 0, -40923), (1, 0, 0, 0, -34720),
    (0, 1, 1, 0, -30383), (2, 0, 0, -2, 15327), (0, 0, 1, 2, -12528), (0, 0, 1, -2, 10980),
    (4, 0, -1, 0, 10675), (0, 0, 3, 0, 10034), (4, 0, -2, 0, 8548), (2, 1, -1, 0, -7888),
    (2, 1, 0, 0, -6766), (1, 0, -1, 0, -5163), (1, 1, 0, 0, 4987), (2, -1, 1, 0, 4036),
    (2, 0, 2, 0, 3994), (4, 0, 0, 0, 3861), (2, 0, -3, 0, 3665), (0, 1, -2, 0, -2689),
    (2, 0, -1, 2, -2602), (2, -1, -2, 0, 2390), (1, 0, 1, 0, -2348), (2, -2, 0, 0, 2236),
    (0, 1, 2, 0, -2120), (0, 2, 0, 0, -2069), (2, -2, -1, 0, 2048), (2, 0, 1, -2, -1773),
    (2, 0, 0, 2, -1595), (4, -1, -1, 0, 1215), (0, 0, 2, 2, -1110), (3, 0, -1, 0, -892),
    (2, 1, 1, 0, -810), (4, -1, -2, 0, 759), (0, 2, -1, 0, -713), (2, 2, -1, 0, -700),
    (2, 1, -2, 0, 691), (2, -1, 0, -2, 596), (4, 0, 1, 0, 549), (0, 0, 4, 0, 537),
    (4, -1, 0, 0, 520), (1, 0, -2, 0, -487),
)


def norm(deg: float) -> float:
    """Wrap an angle into [0, 360)."""
    deg = math.fmod(deg, 360.0)
    return deg + 360.0 if deg < 0 else deg


def diff(a: float, b: float) -> float:
    """Signed smallest difference a - b in (-180, 180]."""
    d = norm(a - b)
    return d - 360.0 if d > 180.0 else d


def julian_day(dt: datetime) -> float:
    """Julian Day for an aware (or naive UTC) datetime."""
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    y, m = dt.year, dt.month
    d = dt.day + (dt.hour + dt.minute / 60 + dt.second / 3600 + dt.microsecond / 3.6e9) / 24
    if m <= 2:
        y -= 1
        m += 12
    a = y // 100
    b = 2 - a + a // 4
    return math.floor(365.25 * (y + 4716)) + math.floor(30.6001 * (m + 1)) + d + b - 1524.5


def from_julian_day(jd: float) -> datetime:
    """UTC datetime (aware) for a Julian Day."""
    return datetime(2000, 1, 1, 12, tzinfo=timezone.utc) + timedelta(days=jd - J2000)


def _centuries(jd: float) -> float:
    return (jd - J2000) / 36525.0


def _delta_t_days(jd: float) -> float:
    """Approximate TT - UT in days (Espenak & Meeus polynomials, coarse)."""
    year = 2000 + (jd - J2000) / 365.25
    if 1986 <= year < 2005:
        t = year - 2000
        sec = 63.86 + 0.3345 * t - 0.060374 * t ** 2
    elif 2005 <= year < 2150:
        t = year - 2000
        sec = 62.92 + 0.32217 * t + 0.005589 * t ** 2
    elif 1961 <= year < 1986:
        t = year - 1975
        sec = 45.45 + 1.067 * t - t ** 2 / 260 - t ** 3 / 718
    elif 1941 <= year < 1961:
        t = year - 1950
        sec = 29.07 + 0.407 * t - t ** 2 / 233 + t ** 3 / 2547
    elif 1920 <= year < 1941:
        t = year - 1920
        sec = 21.20 + 0.84493 * t - 0.076100 * t ** 2 + 0.0020936 * t ** 3
    elif 1900 <= year < 1920:
        t = year - 1900
        sec = -2.79 + 1.494119 * t - 0.0598939 * t ** 2 + 0.0061966 * t ** 3 - 0.000197 * t ** 4
    else:
        u = (year - 1820) / 100
        sec = -20 + 32 * u * u
    return sec / 86400.0


def obliquity(jd: float) -> float:
    t = _centuries(jd)
    return 23.439291 - 0.0130042 * t - 1.64e-7 * t * t


def _nutation_longitude(t: float) -> float:
    omega = math.radians(125.04452 - 1934.136261 * t)
    return -0.00478 * math.sin(omega)


def _helio(name: str, t: float) -> tuple[float, float, float]:
    """Heliocentric ecliptic J2000 rectangular coordinates of a planet."""
    (a0, ar), (e0, er), (i0, ir), (l0, lr), (w0, wr), (o0, orr) = _ELEMENTS[name]
    a, e = a0 + ar * t, e0 + er * t
    inc, mean_l = math.radians(i0 + ir * t), l0 + lr * t
    peri, node = w0 + wr * t, o0 + orr * t
    m = math.radians(norm(mean_l - peri))
    w, o = math.radians(peri - node), math.radians(node)
    ecc = m + e * math.sin(m)
    for _ in range(10):  # Newton iterations for Kepler's equation
        d_ecc = (m - (ecc - e * math.sin(ecc))) / (1 - e * math.cos(ecc))
        ecc += d_ecc
        if abs(d_ecc) < 1e-10:
            break
    xp = a * (math.cos(ecc) - e)
    yp = a * math.sqrt(1 - e * e) * math.sin(ecc)
    cw, sw, co, so, ci, si = math.cos(w), math.sin(w), math.cos(o), math.sin(o), math.cos(inc), math.sin(inc)
    x = (cw * co - sw * so * ci) * xp + (-sw * co - cw * so * ci) * yp
    y = (cw * so + sw * co * ci) * xp + (-sw * so + cw * co * ci) * yp
    z = (sw * si) * xp + (cw * si) * yp
    return x, y, z


def sun_longitude(jd: float) -> float:
    """Apparent tropical longitude of the Sun (Meeus ch. 25)."""
    t = _centuries(jd + _delta_t_days(jd))
    l0 = 280.46646 + 36000.76983 * t + 0.0003032 * t * t
    m = math.radians(357.52911 + 35999.05029 * t - 0.0001537 * t * t)
    c = ((1.914602 - 0.004817 * t - 0.000014 * t * t) * math.sin(m)
         + (0.019993 - 0.000101 * t) * math.sin(2 * m) + 0.000289 * math.sin(3 * m))
    return norm(l0 + c - 0.00569 + _nutation_longitude(t))


def moon_longitude(jd: float) -> float:
    """Apparent tropical longitude of the Moon (Meeus ch. 47, main terms)."""
    t = _centuries(jd + _delta_t_days(jd))
    lp = 218.3164477 + 481267.88123421 * t - 0.0015786 * t * t
    d = math.radians(297.8501921 + 445267.1114034 * t - 0.0018819 * t * t)
    m = math.radians(357.5291092 + 35999.0502909 * t - 0.0001536 * t * t)
    mp = math.radians(134.9633964 + 477198.8675055 * t + 0.0087414 * t * t)
    f = math.radians(93.2720950 + 483202.0175233 * t - 0.0036539 * t * t)
    e = 1 - 0.002516 * t - 0.0000074 * t * t
    total = 0.0
    for cd, cm, cmp, cf, coef in _MOON_TERMS:
        term = coef * math.sin(cd * d + cm * m + cmp * mp + cf * f)
        if abs(cm) == 1:
            term *= e
        elif abs(cm) == 2:
            term *= e * e
        total += term
    a1 = math.radians(119.75 + 131.849 * t)
    total += 3958 * math.sin(a1) + 1962 * math.sin(math.radians(lp) - f)
    total += 318 * math.sin(math.radians(53.09 + 479264.290 * t))
    return norm(lp + total / 1e6 + _nutation_longitude(t))


def mean_node(jd: float) -> float:
    """Mean longitude of the Moon's ascending node (Rahu / North Node)."""
    t = _centuries(jd + _delta_t_days(jd))
    return norm(125.0445479 - 1934.1362891 * t + 0.0020754 * t * t)


def planet_longitude(name: str, jd: float) -> float:
    """Apparent geocentric tropical longitude of any body in PLANETS (and nodes)."""
    if name == "Sun":
        return sun_longitude(jd)
    if name == "Moon":
        return moon_longitude(jd)
    if name in ("Rahu", "North Node"):
        return mean_node(jd)
    if name in ("Ketu", "South Node"):
        return norm(mean_node(jd) + 180)
    t = _centuries(jd + _delta_t_days(jd))
    px, py, pz = _helio(name, t)
    ex, ey, ez = _helio("Earth", t)
    dx, dy, dz = px - ex, py - ey, pz - ez
    # Light time (first-order) correction: see the planet where it was.
    dist = math.sqrt(dx * dx + dy * dy + dz * dz)
    t2 = t - dist * 0.0057755183 / 36525
    px, py, pz = _helio(name, t2)
    lon = math.degrees(math.atan2(py - ey, px - ex))
    # Precess from the J2000 ecliptic to the equinox of date.
    precession = 1.396971 * t + 0.0003086 * t * t
    return norm(lon + precession - 0.00569 + _nutation_longitude(t))


def speed(name: str, jd: float) -> float:
    """Daily motion in longitude (degrees/day); negative means retrograde."""
    return diff(planet_longitude(name, jd + 0.5), planet_longitude(name, jd - 0.5))


def sidereal_time(jd: float, lon_east: float) -> float:
    """Local apparent sidereal time in degrees (the RAMC)."""
    t = _centuries(jd)
    gmst = (280.46061837 + 360.98564736629 * (jd - J2000) + 0.000387933 * t * t - t ** 3 / 38710000)
    eps = math.radians(obliquity(jd))
    return norm(gmst + _nutation_longitude(t) * math.cos(eps) + lon_east)


def angles(jd: float, lat: float, lon_east: float) -> dict:
    """Ascendant and Midheaven (tropical) for a time and place."""
    ramc = math.radians(sidereal_time(jd, lon_east))
    eps = math.radians(obliquity(jd))
    lat = max(-89.9, min(89.9, lat))
    asc = math.degrees(math.atan2(math.cos(ramc),
                                  -(math.sin(ramc) * math.cos(eps) + math.tan(math.radians(lat)) * math.sin(eps))))
    mc = math.degrees(math.atan2(math.sin(ramc), math.cos(ramc) * math.cos(eps)))
    return {"asc": norm(asc), "mc": norm(mc), "ramc": math.degrees(ramc)}


def lahiri_ayanamsa(jd: float) -> float:
    """Lahiri (Chitrapaksha) ayanamsa in degrees, linearised about J2000."""
    t = _centuries(jd)
    return 23.85306 + 1.39697 * t + 0.000308 * t * t


def moon_phase(jd: float) -> dict:
    """Moon phase: elongation, illuminated fraction, and a phase name."""
    elong = norm(moon_longitude(jd) - sun_longitude(jd))
    illum = (1 - math.cos(math.radians(elong))) / 2
    names = ("New Moon", "Waxing Crescent", "First Quarter", "Waxing Gibbous",
             "Full Moon", "Waning Gibbous", "Last Quarter", "Waning Crescent")
    name = names[int(((elong + 22.5) % 360) // 45)]
    return {"elongation": round(elong, 2), "illumination": round(illum * 100, 1),
            "name": name, "waxing": elong < 180}


def find_crossing(func, jd0: float, jd1: float, tol: float = 1e-5) -> float:
    """Bisection for a root of func (an angle difference) between jd0 and jd1."""
    f0 = func(jd0)
    for _ in range(60):
        mid = (jd0 + jd1) / 2
        fm = func(mid)
        if (fm < 0) == (f0 < 0):
            jd0, f0 = mid, fm
        else:
            jd1 = mid
        if jd1 - jd0 < tol:
            break
    return (jd0 + jd1) / 2


def lunations(jd_start: float, jd_end: float) -> list[dict]:
    """New and full moons between two Julian Days, with eclipse flags."""
    out = []
    step = 1.0
    jd = jd_start
    prev = {0: diff(moon_longitude(jd) - sun_longitude(jd), 0), 180: diff(moon_longitude(jd) - sun_longitude(jd), 180)}
    while jd < jd_end:
        nxt = jd + step
        el = moon_longitude(nxt) - sun_longitude(nxt)
        for target in (0, 180):
            cur = diff(el, target)
            if prev[target] < 0 <= cur and cur - prev[target] < 90:
                exact = find_crossing(lambda x, tg=target: diff(moon_longitude(x) - sun_longitude(x), tg), jd, nxt)
                sun = sun_longitude(exact)
                node_gap = abs(diff(sun, mean_node(exact)))
                node_gap = min(node_gap, 180 - node_gap)
                eclipse = None
                if target == 0 and node_gap < 17.0:
                    eclipse = "Solar eclipse"
                elif target == 180 and node_gap < 12.0:
                    eclipse = "Lunar eclipse"
                out.append({"jd": exact, "type": "New Moon" if target == 0 else "Full Moon",
                            "longitude": moon_longitude(exact), "eclipse": eclipse})
            prev[target] = cur
        jd = nxt
    return out


def stations(name: str, jd_start: float, jd_end: float, step: float = 1.0) -> list[dict]:
    """Retrograde and direct stations of a planet in a date range."""
    out = []
    jd = jd_start
    prev = speed(name, jd)
    while jd < jd_end:
        nxt = jd + step
        cur = speed(name, nxt)
        if (prev < 0) != (cur < 0):
            exact = find_crossing(lambda x: speed(name, x), jd, nxt, 1e-3)
            out.append({"jd": exact, "type": "retrograde" if cur < 0 else "direct",
                        "longitude": planet_longitude(name, exact)})
        prev, jd = cur, nxt
    return out


def ingresses(name: str, jd_start: float, jd_end: float, step: float = 1.0, sidereal: bool = False) -> list[dict]:
    """Sign changes of a body in a date range."""
    def lon(x):
        value = planet_longitude(name, x)
        return norm(value - lahiri_ayanamsa(x)) if sidereal else value

    out = []
    jd = jd_start
    prev = int(lon(jd) // 30)
    while jd < jd_end:
        nxt = jd + step
        cur = int(lon(nxt) // 30)
        if cur != prev:
            boundary = 30 * (cur if (cur - prev) % 12 == 1 else prev)
            exact = find_crossing(lambda x: diff(lon(x), boundary), jd, nxt, 1e-3)
            out.append({"jd": exact, "from": prev, "to": cur})
        prev, jd = cur, nxt
    return out
