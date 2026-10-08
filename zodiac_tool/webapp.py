"""Zodiac Studio web app: a small standard-library HTTP server on 127.0.0.1
serving a single-page app plus a JSON API. Start it with
``python zodiac_web.py``.

Every ``api_*`` function takes the decoded JSON request and returns a
JSON-friendly dict, so they can be tested without running a server.
"""

from __future__ import annotations

import json
import os
import re
import threading
import webbrowser
from datetime import date, datetime, timedelta, timezone, tzinfo
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import astronomy as astro
from . import chinese, forecast, numerology, vedic, western

WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
CONTENT_TYPES = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
                 ".js": "application/javascript; charset=utf-8", ".svg": "image/svg+xml",
                 ".png": "image/png", ".ico": "image/x-icon"}

# A handful of cities to make entering a birthplace quick: name, lat, lon, tz.
CITIES = (
    ("Bhubaneswar, India", 20.2961, 85.8245, "Asia/Kolkata"), ("Cuttack, India", 20.4625, 85.8830, "Asia/Kolkata"),
    ("Puri, India", 19.8135, 85.8312, "Asia/Kolkata"), ("Baripada, India", 21.9347, 86.7350, "Asia/Kolkata"),
    ("Balasore, India", 21.4942, 86.9317, "Asia/Kolkata"), ("Berhampur, India", 19.3150, 84.7941, "Asia/Kolkata"),
    ("Sambalpur, India", 21.4669, 83.9812, "Asia/Kolkata"), ("Rourkela, India", 22.2604, 84.8536, "Asia/Kolkata"), ("Kolkata, India", 22.5726, 88.3639, "Asia/Kolkata"),
    ("New Delhi, India", 28.6139, 77.2090, "Asia/Kolkata"), ("Mumbai, India", 19.0760, 72.8777, "Asia/Kolkata"),
    ("Bengaluru, India", 12.9716, 77.5946, "Asia/Kolkata"), ("Chennai, India", 13.0827, 80.2707, "Asia/Kolkata"),
    ("Hyderabad, India", 17.3850, 78.4867, "Asia/Kolkata"), ("Pune, India", 18.5204, 73.8567, "Asia/Kolkata"),
    ("Ahmedabad, India", 23.0225, 72.5714, "Asia/Kolkata"), ("Jaipur, India", 26.9124, 75.7873, "Asia/Kolkata"),
    ("Lucknow, India", 26.8467, 80.9462, "Asia/Kolkata"), ("Patna, India", 25.5941, 85.1376, "Asia/Kolkata"),
    ("Varanasi, India", 25.3176, 82.9739, "Asia/Kolkata"), ("Guwahati, India", 26.1445, 91.7362, "Asia/Kolkata"),
    ("Kathmandu, Nepal", 27.7172, 85.3240, "Asia/Kathmandu"), ("Dhaka, Bangladesh", 23.8103, 90.4125, "Asia/Dhaka"),
    ("Colombo, Sri Lanka", 6.9271, 79.8612, "Asia/Colombo"), ("Karachi, Pakistan", 24.8607, 67.0011, "Asia/Karachi"),
    ("Dubai, UAE", 25.2048, 55.2708, "Asia/Dubai"), ("Singapore", 1.3521, 103.8198, "Asia/Singapore"),
    ("Beijing, China", 39.9042, 116.4074, "Asia/Shanghai"), ("Hong Kong", 22.3193, 114.1694, "Asia/Hong_Kong"),
    ("Tokyo, Japan", 35.6762, 139.6503, "Asia/Tokyo"), ("Seoul, South Korea", 37.5665, 126.9780, "Asia/Seoul"),
    ("Bangkok, Thailand", 13.7563, 100.5018, "Asia/Bangkok"), ("Jakarta, Indonesia", -6.2088, 106.8456, "Asia/Jakarta"),
    ("Sydney, Australia", -33.8688, 151.2093, "Australia/Sydney"), ("Melbourne, Australia", -37.8136, 144.9631, "Australia/Melbourne"),
    ("Auckland, New Zealand", -36.8485, 174.7633, "Pacific/Auckland"), ("Moscow, Russia", 55.7558, 37.6173, "Europe/Moscow"),
    ("Istanbul, Turkey", 41.0082, 28.9784, "Europe/Istanbul"), ("Cairo, Egypt", 30.0444, 31.2357, "Africa/Cairo"),
    ("Nairobi, Kenya", -1.2921, 36.8219, "Africa/Nairobi"), ("Lagos, Nigeria", 6.5244, 3.3792, "Africa/Lagos"),
    ("Johannesburg, South Africa", -26.2041, 28.0473, "Africa/Johannesburg"), ("London, UK", 51.5074, -0.1278, "Europe/London"),
    ("Paris, France", 48.8566, 2.3522, "Europe/Paris"), ("Berlin, Germany", 52.5200, 13.4050, "Europe/Berlin"),
    ("Madrid, Spain", 40.4168, -3.7038, "Europe/Madrid"), ("Rome, Italy", 41.9028, 12.4964, "Europe/Rome"),
    ("Amsterdam, Netherlands", 52.3676, 4.9041, "Europe/Amsterdam"), ("New York, USA", 40.7128, -74.0060, "America/New_York"),
    ("Chicago, USA", 41.8781, -87.6298, "America/Chicago"), ("Denver, USA", 39.7392, -104.9903, "America/Denver"),
    ("Los Angeles, USA", 34.0522, -118.2437, "America/Los_Angeles"), ("San Francisco, USA", 37.7749, -122.4194, "America/Los_Angeles"),
    ("Toronto, Canada", 43.6532, -79.3832, "America/Toronto"), ("Vancouver, Canada", 49.2827, -123.1207, "America/Vancouver"),
    ("Mexico City, Mexico", 19.4326, -99.1332, "America/Mexico_City"), ("São Paulo, Brazil", -23.5505, -46.6333, "America/Sao_Paulo"),
    ("Buenos Aires, Argentina", -34.6037, -58.3816, "America/Argentina/Buenos_Aires"),
)

_OFFSET = re.compile(r"^(?:UTC|GMT)?\s*([+-])(\d{1,2})(?::?(\d{2}))?$", re.I)


def parse_tz(value) -> tzinfo:
    """A tzinfo from an IANA name ("Asia/Kolkata") or an offset ("+05:30", 5.5)."""
    if value is None or value == "":
        return timezone.utc
    if isinstance(value, (int, float)):
        return timezone(timedelta(hours=float(value)))
    text = str(value).strip()
    if text.upper() in ("UTC", "GMT", "Z"):
        return timezone.utc
    m = _OFFSET.match(text)
    if m:
        sign = -1 if m.group(1) == "-" else 1
        return timezone(sign * timedelta(hours=int(m.group(2)), minutes=int(m.group(3) or 0)))
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(text)
    except Exception:
        raise ValueError(f"Unknown time zone '{text}'. Use a UTC offset such as +05:30.") from None


def _float(data: dict, key: str, default=None, lo=None, hi=None) -> float:
    raw = data.get(key, default)
    if raw in (None, ""):
        if default is None:
            raise ValueError(f"Please enter the {key.replace('_', ' ')}.")
        raw = default
    try:
        val = float(raw)
    except (TypeError, ValueError):
        raise ValueError(f"'{raw}' is not a valid {key}.") from None
    if (lo is not None and val < lo) or (hi is not None and val > hi):
        raise ValueError(f"{key.capitalize()} must be between {lo} and {hi}.")
    return val


def parse_moment(data: dict, date_key: str = "date", time_key: str = "time") -> tuple[datetime, tzinfo]:
    """An aware local datetime from {date, time, tz}."""
    raw = (data or {}).get(date_key)
    if not raw:
        raise ValueError("Please enter a date.")
    try:
        d = date.fromisoformat(str(raw))
    except ValueError:
        raise ValueError(f"'{raw}' is not a valid date (use YYYY-MM-DD).") from None
    t = str(data.get(time_key) or "12:00")
    try:
        hh, mm = (int(x) for x in t.split(":")[:2])
        if not (0 <= hh < 24 and 0 <= mm < 60):
            raise ValueError
    except ValueError:
        raise ValueError(f"'{t}' is not a valid time (use HH:MM).") from None
    tz = parse_tz(data.get("tz"))
    return datetime(d.year, d.month, d.day, hh, mm, tzinfo=tz), tz


class Person:
    def __init__(self, data: dict | None):
        data = data or {}
        self.name = str(data.get("name") or "").strip()
        self.local, self.tz = parse_moment(data)
        self.time_known = data.get("time_known", True) not in (False, "false", 0)
        self.lat = _float(data, "lat", 0.0, -90, 90)
        self.lon = _float(data, "lon", 0.0, -180, 180)
        self.jd = astro.julian_day(self.local)
        self.birth_date = self.local.date()


def _ref(data: dict, tz: tzinfo) -> datetime:
    """The reference ("as of") moment: data["on"] (+ optional "on_time") or now."""
    on = (data or {}).get("on")
    if not on:
        return datetime.now(tz)
    return parse_moment({"date": on, "time": data.get("on_time") or "12:00", "tz": None})[0].replace(tzinfo=tz)


def _sign_profile(idx: int) -> dict:
    s = dict(western.SIGNS[idx])
    s["index"] = idx
    s["compatible"] = [western.SIGN_NAMES[i] for i in range(12)
                       if i != idx and western.SIGNS[i]["element"] in western.COMPATIBLE_ELEMENTS[s["element"]]]
    return s


# -- API -------------------------------------------------------------------------
def api_meta(_data=None) -> dict:
    return {"cities": [{"name": n, "lat": la, "lon": lo, "tz": tz} for n, la, lo, tz in CITIES],
            "signs": [_sign_profile(i) for i in range(12)]}


def api_chart(data: dict) -> dict:
    p = Person(data.get("person"))
    sidereal = data.get("zodiac") == "sidereal"
    chart = western.natal_chart(p.jd, p.lat, p.lon, data.get("house_system", "porphyry"), sidereal)
    sun_idx = western.sign_of(next(x["lon"] for x in chart["planets"] if x["name"] == "Sun"))
    return {
        "name": p.name, "birth": p.local.isoformat(), "time_known": p.time_known,
        "chart": chart, "sun_sign": _sign_profile(sun_idx),
        "moon_phase": astro.moon_phase(p.jd),
        "chinese": chinese.profile(p.birth_date),
        "numerology": numerology.profile(p.birth_date, p.name),
    }


def api_vedic(data: dict) -> dict:
    p = Person(data.get("person"))
    ref = _ref(data, p.tz)
    k = vedic.kundli(p.jd, p.lat, p.lon, p.local, ref)
    k["panchang_at_birth"] = vedic.panchang(p.jd, p.local)
    return k


def api_horoscope(data: dict) -> dict:
    tz = parse_tz(data.get("tz"))
    if data.get("sign") not in (None, ""):
        sign = int(data["sign"])
    else:
        bd = date.fromisoformat(str(data.get("birth_date")))
        sign = western.sun_sign_for_date(bd.month, bd.day)
    if not 0 <= sign < 12:
        raise ValueError("Sign must be 0-11.")
    day = date.fromisoformat(str(data.get("date") or datetime.now(tz).date().isoformat()))
    period = data.get("period", "day")
    if period == "week":
        day -= timedelta(days=day.weekday())
    elif period == "month":
        day = day.replace(day=1)
    elif period == "year":
        day = day.replace(month=1, day=1)
    jd = astro.julian_day(datetime(day.year, day.month, day.day, 0, 0, tzinfo=tz))
    return forecast.horoscope(sign, jd, period, tz)


def api_forecast(data: dict) -> dict:
    """Everything about one date in a person's life: past, present or future."""
    p = Person(data.get("person"))
    ref = _ref(data, p.tz)
    jd = astro.julian_day(ref)
    natal = western.natal_chart(p.jd, p.lat, p.lon, "porphyry", False)
    moon_sid = vedic.sidereal(astro.moon_longitude(p.jd), p.jd)
    dasha = vedic.vimshottari(moon_sid, p.local, ref)
    sade = vedic.sade_sati(int(moon_sid // 30), p.jd, ref)
    age = (ref.date() - p.birth_date).days / 365.25
    return {
        "date": ref.date().isoformat(),
        "when": "past" if ref.date() < datetime.now(p.tz).date() else ("today" if ref.date() == datetime.now(p.tz).date() else "future"),
        "age": round(age, 1),
        "transits": forecast.personal_transits(natal, jd),
        "numerology": numerology.cycles(p.birth_date, ref.date()),
        "dasha": {"reading": dasha["reading"], "current": dasha["current"], "current_sub": dasha["current_sub"]},
        "sade_sati": sade["status_text"],
        "chinese": chinese.year_forecast(p.birth_date, chinese.chinese_year_for(ref.date())),
        "panchang": vedic.panchang(jd, ref),
    }


def api_timeline(data: dict) -> dict:
    p = Person(data.get("person"))
    ref = _ref(data, p.tz)
    years = int(_float(data, "years", 90, 1, 120))
    natal = western.natal_chart(p.jd, p.lat, p.lon, "porphyry", False)
    events = forecast.life_timeline(natal, p.jd, astro.julian_day(ref), p.tz, years)
    moon_sid = vedic.sidereal(astro.moon_longitude(p.jd), p.jd)
    dasha = vedic.vimshottari(moon_sid, p.local, ref, levels=1)
    end = p.local + timedelta(days=years * 365.25)
    for d in dasha["periods"]:
        start = datetime.fromisoformat(d["start"])
        if start <= p.local or start > end:
            continue
        events.append({"title": f"{d['lord']} Mahadasha begins", "kind": "dasha", "status": d["status"],
                       "date": start.astimezone(p.tz).date().isoformat(), "passes": [],
                       "age": round((start - p.local).days / 365.25, 1),
                       "text": f"{d['years']} years highlighting {d['theme']}.", "jd": astro.julian_day(start)})
    sade = vedic.sade_sati(int(moon_sid // 30), p.jd, ref, years)
    for s in sade["periods"]:
        sd = date.fromisoformat(s["start"])
        events.append({"title": "Sade Sati " + ("(continuing from birth)" if s["open_start"] else "begins"),
                       "kind": "sade_sati", "status": s["status"], "date": s["start"], "passes": [],
                       "age": round((sd - p.birth_date).days / 365.25, 1),
                       "text": f"Saturn's 7½-year transit around your Moon, until about {s['end']}.",
                       "jd": astro.julian_day(datetime(sd.year, sd.month, sd.day, tzinfo=timezone.utc))})
    events.sort(key=lambda e: e["jd"])
    for e in events:
        e.pop("jd", None)
    return {"events": events, "today": ref.date().isoformat(), "years": years}


def api_compatibility(data: dict) -> dict:
    a, b = Person(data.get("a")), Person(data.get("b"))
    ca = western.natal_chart(a.jd, a.lat, a.lon, "porphyry")
    cb = western.natal_chart(b.jd, b.lat, b.lon, "porphyry")
    pa = {x["name"]: x["lon"] for x in ca["planets"] if x["name"] in ("Sun", "Moon", "Mercury", "Venus", "Mars")}
    pb = {x["name"]: x["lon"] for x in cb["planets"] if x["name"] in ("Sun", "Moon", "Mercury", "Venus", "Mars")}
    syn = western.aspects_between(pa, pb, 0.8)
    harm = sum(1 for s in syn if s["nature"] == "harmonious") + sum(
        1 for s in syn if s["aspect"] == "Conjunction" and {s["a"], s["b"]} & {"Venus", "Moon", "Sun"})
    hard = sum(1 for s in syn if s["nature"] == "challenging")
    syn_score = max(10, min(98, 60 + 7 * harm - 6 * hard))
    sa, sb = western.sign_of(pa["Sun"]), western.sign_of(pb["Sun"])
    ea, eb = western.SIGNS[sa]["element"], western.SIGNS[sb]["element"]
    elem_score = 85 if eb in western.COMPATIBLE_ELEMENTS[ea] else (60 if (sa - sb) % 12 in (3, 9) else 50)
    # Guna Milan expects (boy, girl); the order given by the user is kept.
    ma = vedic.sidereal(astro.moon_longitude(a.jd), a.jd)
    mb = vedic.sidereal(astro.moon_longitude(b.jd), b.jd)
    guna = vedic.guna_milan(ma, mb)
    cha = chinese.profile(a.birth_date)
    chb = chinese.profile(b.birth_date)
    rel = chinese.relation(cha["animal_index"], chb["animal_index"])
    lpa = numerology.life_path(a.birth_date)
    lpb = numerology.life_path(b.birth_date)
    num = numerology.compatibility(lpa, lpb)
    overall = round(0.3 * syn_score + 0.15 * elem_score + 0.3 * guna["total"] / 36 * 100 + 0.15 * rel[1] + 0.1 * num[0])
    return {
        "names": [a.name or "Person A", b.name or "Person B"],
        "overall": overall,
        "sun_signs": {"a": western.SIGN_NAMES[sa], "b": western.SIGN_NAMES[sb], "elements": [ea, eb],
                      "score": elem_score},
        "synastry": {"aspects": syn, "score": syn_score},
        "guna_milan": guna,
        "chinese": {"a": cha["label"], "b": chb["label"], "relation": rel[0], "score": rel[1], "text": rel[2]},
        "numerology": {"a": lpa, "b": lpb, "score": num[0], "text": num[1]},
    }


def api_panchang(data: dict) -> dict:
    local, tz = parse_moment(data)
    jd = astro.julian_day(local)
    lat = _float(data, "lat", 0.0, -90, 90)
    lon = _float(data, "lon", 0.0, -180, 180)
    pos = western.positions(jd)
    lagna = astro.angles(jd, lat, lon)["asc"]
    return {
        "moment": local.isoformat(),
        "panchang": vedic.panchang(jd, local),
        "moon_phase": astro.moon_phase(jd),
        "lagna": {"tropical": western.fmt_pos(lagna), "sidereal": western.fmt_pos(vedic.sidereal(lagna, jd))},
        "planets": [{"name": n, "tropical": western.fmt_pos(v["lon"]),
                     "sidereal": western.fmt_pos(vedic.sidereal(v["lon"], jd)), "retro": v["retro"]}
                    for n, v in pos.items()],
    }


def api_sky(data: dict) -> dict:
    tz = parse_tz(data.get("tz"))
    year = int(_float(data, "year", datetime.now(tz).year, 1800, 2200))
    jd0 = astro.julian_day(datetime(year, 1, 1, tzinfo=tz))
    jd1 = astro.julian_day(datetime(year + 1, 1, 1, tzinfo=tz))
    events = forecast.sky_events(jd0, jd1, tz)
    for e in events:
        e.pop("jd", None)
        e.pop("lon", None)
    return {"year": year, "events": events, "chinese_year": chinese.year_info(year)["label"],
            "lunar_new_year": chinese.lunar_new_year(year).isoformat()}


JSON_ROUTES = {
    "/api/chart": api_chart, "/api/vedic": api_vedic, "/api/horoscope": api_horoscope,
    "/api/forecast": api_forecast, "/api/timeline": api_timeline,
    "/api/compatibility": api_compatibility, "/api/panchang": api_panchang, "/api/sky": api_sky,
}


class Handler(BaseHTTPRequestHandler):
    server_version = "ZodiacStudio"

    def log_message(self, *_args):
        pass

    def _send(self, status, body: bytes, content_type: str):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, status=200):
        self._send(status, json.dumps(obj).encode("utf-8"), "application/json")

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/meta":
            self._json(api_meta())
            return
        rel = "index.html" if path in ("/", "") else path.lstrip("/")
        full = os.path.normpath(os.path.join(WEB_DIR, rel))
        if not full.startswith(WEB_DIR + os.sep) or not os.path.isfile(full):
            self._send(404, b"Not found", "text/plain")
            return
        with open(full, "rb") as fh:
            self._send(200, fh.read(), CONTENT_TYPES.get(os.path.splitext(full)[1], "application/octet-stream"))

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        try:
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, TypeError):
            self._json({"error": "Bad request"}, 400)
            return
        if path not in JSON_ROUTES:
            self._json({"error": "Unknown endpoint"}, 404)
            return
        try:
            self._json(JSON_ROUTES[path](data))
        except (ValueError, KeyError, TypeError) as exc:
            self._json({"error": str(exc)}, 400)
        except Exception as exc:  # pragma: no cover - surfaced to the user
            self._json({"error": f"{type(exc).__name__}: {exc}"}, 500)


def serve(host: str = "127.0.0.1", port: int = 8766, open_browser: bool = True) -> None:
    httpd = ThreadingHTTPServer((host, port), Handler)
    url = f"http://{host}:{port}/"
    print(f"Zodiac Studio is running at {url}")
    print("Leave this window open while you use it. Press Ctrl+C here to stop.")
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Zodiac Studio.")
    finally:
        httpd.server_close()


def main(argv=None):
    import argparse

    ap = argparse.ArgumentParser(description="Run the Zodiac Studio web app locally.")
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8766)))
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--no-browser", action="store_true", help="do not open a browser automatically")
    args = ap.parse_args(argv)
    serve(args.host, args.port, not args.no_browser)


if __name__ == "__main__":
    main()
