"""A local web-app version of the Roster Creator.

Runs a small HTTP server (Python standard library only - no Flask, no extra
packages) on 127.0.0.1 and serves a single-page app that reuses the same
roster engine, validator, storage, export and calendar code as the desktop
GUI. Start it with ``python roster_web.py``.

Nothing is installed and no executable is produced: it is plain Python source
plus static HTML/CSS/JS, so it runs anywhere a permitted Python interpreter
can, and the browser is the only UI.
"""

from __future__ import annotations

import io
import json
import os
import sys
import threading
import webbrowser
import zipfile
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import export, ics, storage
from .model import (
    ALL_CODES,
    CODE_DESCRIPTIONS,
    DAY_TYPES,
    SHIFT_NAMES,
    SHIFTS,
    WEEKDAY_NAMES,
    Locks,
    Roster,
    RosterConfig,
    empty_config_dict,
)
from .scheduler import generate
from .validator import ERROR, INFO, WARNING, count, precheck, preference_stats, validate

# Static files sit next to this package from source, or in the PyInstaller
# extraction folder when bundled.
_BASE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
if not os.path.isdir(WEB_DIR):
    WEB_DIR = os.path.join(_BASE, "roster_tool", "web")
SAMPLE = os.path.join(_BASE, "examples", "sample_config.json")
DESIGNATIONS = ("Engineer", "Senior Engineer", "Lead Engineer", "SME", "Manager")


# -- (de)serialisation --------------------------------------------------------
def _cfg(inputs: dict) -> RosterConfig:
    return RosterConfig.from_dict(inputs)


def _locks(data: dict | None) -> Locks:
    return storage.locks_from_dict(data or {})


def roster_from_payload(cfg: RosterConfig, payload: dict) -> Roster:
    return storage._roster_from_dict(cfg, payload or {}, _locks((payload or {}).get("locks")))


def roster_payload(roster: Roster) -> dict:
    cfg = roster.config
    return {
        "year": cfg.year,
        "month": cfg.month,
        "grid": {n: {d.isoformat(): c for d, c in days.items() if c} for n, days in roster.grid.items()},
        "primary": {d.isoformat(): n for d, n in roster.primary.items() if n},
        "secondary": {d.isoformat(): n for d, n in roster.secondary.items() if n},
        "locks": storage.locks_to_dict(roster.locks),
        "counts": {n: roster.counts(n) for n in cfg.engineer_names},
        "totals": {n: roster.total_counts(n) for n in cfg.engineer_names},
    }


def day_meta(cfg: RosterConfig) -> list[dict]:
    out = []
    for d in cfg.days:
        out.append({
            "iso": d.isoformat(),
            "day": d.day,
            "weekday": WEEKDAY_NAMES[d.weekday()],
            "type": cfg.day_type(d),
            "holiday": cfg.holiday_name(d),
        })
    return out


def issue_list(issues) -> list[dict]:
    return [{"severity": i.severity, "date": i.day.isoformat() if i.day else "", "message": i.message} for i in issues]


def analysis(roster: Roster, baseline: Roster | None) -> dict:
    cfg = roster.config
    issues = validate(roster)
    met, requested = preference_stats(roster)
    changes = storage.diff(baseline, roster) if baseline else []
    return {
        "issues": issue_list(issues),
        "errors": count(issues, ERROR),
        "warnings": count(issues, WARNING),
        "errorDays": sorted({i.day.isoformat() for i in issues if i.severity == ERROR and i.day}),
        "preferences": {"met": met, "requested": requested},
        "changes": [{"date": c.day.isoformat(), "who": c.who, "old": c.old, "new": c.new} for c in changes],
        "days": day_meta(cfg),
    }


# -- request handlers ---------------------------------------------------------
def api_meta(_data):
    return {
        "codes": [{"code": c, "description": CODE_DESCRIPTIONS[c], "color": export.CODE_COLORS.get(c, "FFFFFF"),
                   "text": export.CODE_TEXT_COLORS.get(c, "111827")} for c in ALL_CODES],
        "dayTypeColors": export.DAYTYPE_COLORS,
        "shifts": [{"code": s, "name": SHIFT_NAMES[s]} for s in SHIFTS],
        "dayTypes": list(DAY_TYPES),
        "weekdays": list(WEEKDAY_NAMES),
        "designations": list(DESIGNATIONS),
        "empty": empty_config_dict(),
    }


def api_sample(_data):
    with open(SAMPLE, encoding="utf-8") as fh:
        return {"inputs": json.load(fh)}


def api_generate(data):
    cfg = _cfg(data["inputs"])
    locks = _locks(data.get("locks"))
    baseline = None
    if data.get("baseline"):
        baseline = roster_from_payload(cfg, data["baseline"])
        if (baseline.config.year, baseline.config.month) != (cfg.year, cfg.month):
            baseline = None
    roster, _issues = generate(cfg, locks, baseline)
    return {"roster": roster_payload(roster), "analysis": analysis(roster, baseline)}


def api_precheck(data):
    cfg = _cfg(data["inputs"])
    return {"issues": issue_list(precheck(cfg, _locks(data.get("locks"))))}


def api_validate(data):
    cfg = _cfg(data["inputs"])
    roster = roster_from_payload(cfg, data["roster"])
    baseline = roster_from_payload(cfg, data["baseline"]) if data.get("baseline") else None
    return {"roster": roster_payload(roster), "analysis": analysis(roster, baseline)}


def api_swap(data):
    cfg = _cfg(data["inputs"])
    roster = roster_from_payload(cfg, data["roster"])
    d = date.fromisoformat(data["day"])
    new = storage.swap(roster, data["a"], data["b"], d)
    before = {i.message for i in validate(roster) if i.severity == ERROR}
    new_errors = [i.message for i in validate(new) if i.severity == ERROR and i.message not in before]
    preview = [{"date": c.day.isoformat(), "who": c.who, "old": c.old, "new": c.new} for c in storage.diff(roster, new)]
    return {"roster": roster_payload(new), "preview": preview, "newErrors": new_errors}


def api_open(data):
    rf = storage.roster_file_from_dict(data["file"])
    return {
        "inputs": rf.inputs,
        "roster": roster_payload(rf.roster),
        "published": roster_payload(rf.published) if rf.published else None,
        "publishedAt": rf.published_at,
    }


def api_save(data):
    cfg = _cfg(data["inputs"])
    roster = roster_from_payload(cfg, data["roster"])
    published = roster_from_payload(cfg, data["published"]) if data.get("published") else None
    return {"file": storage.roster_file_dict(data["inputs"], roster, published, data.get("publishedAt", ""))}


def api_carry_over(data):
    rf = storage.roster_file_from_dict(data["file"])
    ny, nm = storage.next_month(rf.roster.config.year, rf.roster.config.month)
    return {"carryOver": storage.carry_over_from(rf.roster), "prevInputs": rf.inputs, "nextYear": ny, "nextMonth": nm}


JSON_ROUTES = {
    "/api/meta": api_meta,
    "/api/sample": api_sample,
    "/api/generate": api_generate,
    "/api/precheck": api_precheck,
    "/api/validate": api_validate,
    "/api/swap": api_swap,
    "/api/open": api_open,
    "/api/save": api_save,
    "/api/carry-over": api_carry_over,
}


def export_bytes(fmt: str, data: dict) -> tuple[bytes, str, str]:
    """Return (bytes, content-type, filename) for a roster export."""
    cfg = _cfg(data["inputs"])
    roster = roster_from_payload(cfg, data["roster"])
    if data.get("shiftTimes"):
        from .model import parse_time, parse_shift
        for name, t in data["shiftTimes"].items():
            roster.config.shift_times[parse_shift(name)] = (parse_time(t["start"]), parse_time(t["end"]))
    tag = f"{cfg.year}_{cfg.month:02d}"
    if fmt == "csv":
        buf = io.StringIO()
        import csv as _csv
        w = _csv.writer(buf)
        w.writerows(export.table_rows(roster))
        return buf.getvalue().encode("utf-8"), "text/csv", f"roster_{tag}.csv"
    if fmt == "xlsx":
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
            path = tmp.name
        try:
            export.to_excel(roster, path, validate(roster))
            with open(path, "rb") as fh:
                content = fh.read()
        finally:
            os.unlink(path)
        return content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", f"roster_{tag}.xlsx"
    if fmt == "ics":
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for name in cfg.engineer_names + [None]:
                label = name or "Team"
                zf.writestr(f"{label} - roster {cfg.year}-{cfg.month:02d}.ics", ics.build_calendar(roster, name))
        return buf.getvalue(), "application/zip", f"roster_{tag}_calendars.zip"
    raise ValueError(f"unknown export format '{fmt}'")


CONTENT_TYPES = {".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml", ".png": "image/png"}


class Handler(BaseHTTPRequestHandler):
    server_version = "RosterCreator"

    def log_message(self, *_args):
        pass  # keep the console quiet

    def _send(self, status, body: bytes, content_type: str, extra: dict | None = None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, status=200):
        self._send(status, json.dumps(obj).encode("utf-8"), "application/json")

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/meta":
            self._json(api_meta(None))
            return
        if path == "/api/sample":
            self._json(api_sample(None))
            return
        rel = "index.html" if path in ("/", "") else path.lstrip("/")
        full = os.path.normpath(os.path.join(WEB_DIR, rel))
        if not full.startswith(WEB_DIR) or not os.path.isfile(full):
            self._send(404, b"Not found", "text/plain")
            return
        with open(full, "rb") as fh:
            body = fh.read()
        self._send(200, body, CONTENT_TYPES.get(os.path.splitext(full)[1], "application/octet-stream"))

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        try:
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, TypeError):
            self._json({"error": "Bad request"}, 400)
            return
        try:
            if path in JSON_ROUTES:
                self._json(JSON_ROUTES[path](data))
                return
            if path.startswith("/api/export/"):
                content, ctype, filename = export_bytes(path.rsplit("/", 1)[1], data)
                self._send(200, content, ctype, {"Content-Disposition": f'attachment; filename="{filename}"'})
                return
        except ValueError as exc:
            self._json({"error": str(exc)}, 400)
            return
        except Exception as exc:  # pragma: no cover - surfaced to the user
            self._json({"error": f"{type(exc).__name__}: {exc}"}, 500)
            return
        self._json({"error": "Unknown endpoint"}, 404)


def serve(host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True) -> None:
    httpd = ThreadingHTTPServer((host, port), Handler)
    url = f"http://{host}:{port}/"
    print(f"Roster Creator is running at {url}")
    print("Leave this window open while you use it. Press Ctrl+C here to stop.")
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Roster Creator.")
    finally:
        httpd.server_close()


def main(argv=None):
    import argparse

    ap = argparse.ArgumentParser(description="Run the Roster Creator web app locally.")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--no-browser", action="store_true", help="do not open a browser automatically")
    args = ap.parse_args(argv)
    serve(args.host, args.port, not args.no_browser)


if __name__ == "__main__":
    main()
