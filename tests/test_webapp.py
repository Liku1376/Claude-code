"""Tests for the web-app API layer (called directly, no HTTP server)."""

import json
import os

import pytest

from roster_tool import webapp

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def sample_inputs():
    with open(os.path.join(ROOT, "examples", "sample_config.json")) as fh:
        return json.load(fh)


def generated():
    return webapp.api_generate({"inputs": sample_inputs()})


def test_meta_and_sample():
    meta = webapp.api_meta(None)
    assert {c["code"] for c in meta["codes"]} >= {"M", "E", "N", "CO"}
    assert meta["empty"]["engineers"] == []
    assert len(webapp.api_sample(None)["inputs"]["engineers"]) == 7


def test_generate_returns_clean_roster():
    res = generated()
    assert res["analysis"]["errors"] == 0
    assert len(res["analysis"]["days"]) == 31
    assert len(res["roster"]["grid"]) == 7
    assert res["roster"]["counts"]["Asha"]["N"] >= 0


def test_precheck_and_validate():
    inputs = sample_inputs()
    assert webapp.api_precheck({"inputs": inputs})["issues"] == []
    roster = generated()["roster"]
    res = webapp.api_validate({"inputs": inputs, "roster": roster, "baseline": roster})
    assert res["analysis"]["errors"] == 0
    assert res["analysis"]["changes"] == []


def test_swap_endpoint():
    inputs = sample_inputs()
    roster = generated()["roster"]
    # find a day/engineer to swap
    day = roster["primary"] and next(iter(roster["primary"]))
    a = roster["primary"][day]
    b = next(n for n in roster["grid"] if n != a)
    res = webapp.api_swap({"inputs": inputs, "roster": roster, "a": a, "b": b, "day": day})
    assert any(c["who"] == "Primary on-call" for c in res["preview"])
    assert res["roster"]["locks"]["cells"]


def test_save_open_roundtrip():
    inputs = sample_inputs()
    roster = generated()["roster"]
    saved = webapp.api_save({"inputs": inputs, "roster": roster, "published": roster, "publishedAt": "now"})
    assert saved["file"]["format"] == "roster-creator/roster"
    opened = webapp.api_open({"file": saved["file"]})
    assert len(opened["roster"]["grid"]) == 7
    assert opened["published"] is not None


def test_carry_over_endpoint():
    inputs = sample_inputs()
    roster = generated()["roster"]
    saved = webapp.api_save({"inputs": inputs, "roster": roster})
    res = webapp.api_carry_over({"file": saved["file"]})
    assert (res["nextYear"], res["nextMonth"]) == (2026, 11)
    assert "source" in res["carryOver"]


@pytest.mark.parametrize("fmt,head", [("csv", b"Engineer"), ("ics", b"PK"), ("xlsx", b"PK")])
def test_exports(fmt, head):
    if fmt == "xlsx":
        pytest.importorskip("openpyxl")
    inputs = sample_inputs()
    roster = generated()["roster"]
    content, ctype, filename = webapp.export_bytes(fmt, {"inputs": inputs, "roster": roster})
    assert content[: len(head)] == head
    assert filename.endswith("." + ("zip" if fmt == "ics" else fmt))


def test_web_files_present():
    for name in ("index.html", "app.js", "style.css"):
        assert os.path.isfile(os.path.join(webapp.WEB_DIR, name))
