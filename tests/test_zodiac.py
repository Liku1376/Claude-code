"""Tests for the Zodiac Studio calculations and API (no HTTP server)."""

from datetime import date, datetime, timedelta, timezone

import pytest

from zodiac_tool import astronomy as astro
from zodiac_tool import chinese, numerology, vedic, webapp, western

IST = timezone(timedelta(hours=5, minutes=30))
PERSON = {"name": "Asha Rao", "date": "1990-05-15", "time": "08:30", "lat": 20.2961, "lon": 85.8245, "tz": "+05:30"}
PARTNER = {"name": "Ravi", "date": "1992-11-03", "time": "21:10", "lat": 28.6139, "lon": 77.209, "tz": "+05:30"}


def jd(*args, tz=timezone.utc):
    return astro.julian_day(datetime(*args, tzinfo=tz))


def test_julian_day_roundtrip():
    assert jd(2000, 1, 1, 12) == pytest.approx(2451545.0)
    dt = astro.from_julian_day(2460000.25)
    assert astro.julian_day(dt) == pytest.approx(2460000.25, abs=1e-6)


def test_sun_at_equinox_and_solstice():
    # March equinox 2024: 03:06 UTC; June solstice 2025: 02:42 UTC.
    assert abs(astro.diff(astro.sun_longitude(jd(2024, 3, 20, 3, 6)), 0)) < 0.02
    assert abs(astro.diff(astro.sun_longitude(jd(2025, 6, 21, 2, 42)), 90)) < 0.02


def test_planets_reference_positions():
    # Reference apparent longitudes (equinox of date) for 2000-01-01 12:00 UT.
    j = jd(2000, 1, 1, 12)
    expected = {"Moon": 223.32, "Mercury": 271.89, "Venus": 241.57, "Mars": 327.96,
                "Jupiter": 25.25, "Saturn": 40.40}
    for name, lon in expected.items():
        assert abs(astro.diff(astro.planet_longitude(name, j), lon)) < 0.3, name


def test_eclipses_and_retrogrades_2026():
    lun = astro.lunations(jd(2026, 1, 1), jd(2027, 1, 1))
    eclipses = [(astro.from_julian_day(l["jd"]).date(), l["eclipse"]) for l in lun if l["eclipse"]]
    assert eclipses == [(date(2026, 2, 17), "Solar eclipse"), (date(2026, 3, 3), "Lunar eclipse"),
                        (date(2026, 8, 12), "Solar eclipse"), (date(2026, 8, 28), "Lunar eclipse")]
    st = astro.stations("Mercury", jd(2026, 1, 1), jd(2027, 1, 1))
    retro = [astro.from_julian_day(s["jd"]).date() for s in st if s["type"] == "retrograde"]
    assert retro == [date(2026, 2, 26), date(2026, 6, 29), date(2026, 10, 24)]


def test_ascendant_basic_geometry():
    # At the equator with RAMC 0 the Ascendant is 0 Cancer and MC is 0 Aries.
    j = jd(2024, 3, 20, 12)
    lon = -astro.sidereal_time(j, 0)
    ang = astro.angles(j, 0.0, lon)
    assert abs(astro.diff(ang["mc"], 0)) < 0.01
    assert abs(astro.diff(ang["asc"], 90)) < 0.01


def test_sun_sign_by_date():
    assert western.SIGN_NAMES[western.sun_sign_for_date(1, 5)] == "Capricorn"
    assert western.SIGN_NAMES[western.sun_sign_for_date(3, 21)] == "Aries"
    assert western.SIGN_NAMES[western.sun_sign_for_date(5, 15)] == "Taurus"
    assert western.SIGN_NAMES[western.sun_sign_for_date(12, 25)] == "Capricorn"


def test_natal_chart_shape():
    j = astro.julian_day(datetime(1990, 5, 15, 8, 30, tzinfo=IST))
    chart = western.natal_chart(j, 20.2961, 85.8245, "whole")
    assert len(chart["cusps"]) == 12 and len(chart["planets"]) == 11
    sun = next(p for p in chart["planets"] if p["name"] == "Sun")
    assert sun["sign"] == "Taurus"
    assert all(1 <= p["house"] <= 12 for p in chart["planets"])
    assert sum(chart["elements"].values()) == 11


def test_vimshottari_spans_120_years():
    birth = datetime(1990, 5, 15, 8, 30, tzinfo=IST)
    d = vedic.vimshottari(200.0, birth, birth + timedelta(days=365 * 30))
    assert sum(p["years"] for p in d["periods"]) == 120
    assert sum(1 for p in d["periods"] if p["status"] == "current") == 1
    first = d["periods"][0]
    assert datetime.fromisoformat(first["start"]) <= birth < datetime.fromisoformat(first["end"])
    for p in d["periods"]:
        assert p["antardashas"][-1]["end"] == p["end"] or abs(
            (datetime.fromisoformat(p["antardashas"][-1]["end"]) - datetime.fromisoformat(p["end"])).total_seconds()) < 1


def test_sade_sati_sagittarius_moon():
    # Saturn moved through sidereal Scorpio-Capricorn from late 2014 to early 2023.
    birth = jd(1990, 5, 15)
    res = vedic.sade_sati(8, birth, datetime(2026, 10, 8, tzinfo=timezone.utc))
    starts = [p["start"][:4] for p in res["periods"]]
    assert "2014" in starts
    period = next(p for p in res["periods"] if p["start"].startswith("2014"))
    assert period["end"].startswith("2023") and period["status"] == "past"


def test_guna_milan_bounds():
    for a in range(0, 360, 37):
        for b in range(0, 360, 41):
            g = vedic.guna_milan(a + 0.5, b + 0.5)
            assert 0 <= g["total"] <= 36
            assert len(g["kootas"]) == 8
    same = vedic.guna_milan(100.0, 100.0)
    assert any(k["name"] == "Nadi" and k["score"] == 0 for k in same["kootas"])


def test_panchang_full_moon():
    p = vedic.panchang(jd(2026, 3, 3, 11, 38), datetime(2026, 3, 3, 17, 8, tzinfo=IST))
    assert p["tithi"] in ("Purnima (Full Moon)", "Pratipada")


def test_chinese_new_year_dates():
    assert chinese.lunar_new_year(2024) == date(2024, 2, 10)
    assert chinese.lunar_new_year(2026) == date(2026, 2, 17)
    assert chinese.lunar_new_year(2033) == date(2033, 1, 31)
    assert chinese.profile(date(1990, 1, 20))["label"] == "Earth Snake"  # before LNY 1990
    assert chinese.profile(date(1990, 5, 15))["label"] == "Metal Horse"


def test_numerology():
    assert numerology.life_path(date(1990, 5, 15)) == 3
    assert numerology.reduce(29) == 11 and numerology.reduce(29, keep_master=False) == 2
    prof = numerology.profile(date(1990, 5, 15), "Asha Rao")
    assert prof["expression"]["number"] in numerology.MEANINGS
    assert 1 <= numerology.personal_year(date(1990, 5, 15), 2026) <= 9


def test_parse_tz():
    assert webapp.parse_tz("+05:30").utcoffset(None) == timedelta(hours=5, minutes=30)
    assert webapp.parse_tz("-4").utcoffset(None) == timedelta(hours=-4)
    assert webapp.parse_tz(5.75).utcoffset(None) == timedelta(hours=5, minutes=45)
    with pytest.raises(ValueError):
        webapp.parse_tz("Not/AZone")


def test_api_endpoints():
    chart = webapp.api_chart({"person": PERSON})
    assert chart["sun_sign"]["name"] == "Taurus"
    k = webapp.api_vedic({"person": PERSON, "on": "2026-10-08"})
    assert k["dasha"]["current"] in vedic.DASHA_ORDER
    h = webapp.api_horoscope({"sign": 4, "period": "week", "date": "2026-10-08", "tz": "+05:30"})
    assert h["from"] == "2026-10-05" and set(h["scores"]) == {"love", "career", "money", "health"}
    f = webapp.api_forecast({"person": PERSON, "on": "2035-01-01"})
    assert f["when"] == "future" and f["transits"]["headline"]
    t = webapp.api_timeline({"person": PERSON, "years": 60, "on": "2026-10-08"})
    titles = [e["title"] for e in t["events"]]
    assert "Saturn Return" in titles and "Jupiter Return" in titles
    assert {e["status"] for e in t["events"]} >= {"past", "future"}
    c = webapp.api_compatibility({"a": PERSON, "b": PARTNER})
    assert 0 <= c["overall"] <= 100
    p = webapp.api_panchang({"date": "2026-10-08", "time": "06:00", "tz": "+05:30", "lat": 20.3, "lon": 85.8})
    assert len(p["planets"]) == 11
    s = webapp.api_sky({"year": 2026, "tz": "+05:30"})
    assert s["chinese_year"] == "Fire Horse"
    assert sum(1 for e in s["events"] if e["title"] == "Sun enters Aries — March equinox") == 1


def test_api_validation_errors():
    with pytest.raises(ValueError):
        webapp.api_chart({"person": {**PERSON, "date": ""}})
    with pytest.raises(ValueError):
        webapp.api_chart({"person": {**PERSON, "time": "25:00"}})
    with pytest.raises(ValueError):
        webapp.api_chart({"person": {**PERSON, "lat": 123}})
