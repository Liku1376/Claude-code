"""A local web-app version of the Roster Creator.

Runs a small HTTP server (Python standard library only - no Flask, no extra
packages) on 127.0.0.1 and serves a single-page app that reuses the same
roster engine, validator, storage, export and calendar code as the desktop
GUI. Start it with ``python roster_web.py``.

Nothing is installed and no executable is produced: it is plain Python source
plus static HTML/CSS/JS, so it runs anywhere a permitted Python interpreter
can, and the browser is the only UI.

This file is commented line by line. The browser (front end) sends small JSON
requests to the endpoints below; each returns JSON the page then renders.
"""

from __future__ import annotations

# ``io`` builds in-memory files (for CSV/zip); ``json`` (de)serialises requests;
# ``os``/``sys`` handle paths; ``threading`` opens the browser after a delay;
# ``webbrowser`` launches it; ``zipfile`` bundles the .ics files.
import io
import json
import os
import sys
import threading
import webbrowser
import zipfile
from datetime import date
# The standard-library HTTP server building blocks.
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# Reuse the existing engine/export/storage code unchanged.
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
# extraction folder when bundled. ``sys._MEIPASS`` only exists in a bundle.
_BASE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Prefer the web folder beside this file; fall back to the bundled location.
WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
if not os.path.isdir(WEB_DIR):
    WEB_DIR = os.path.join(_BASE, "roster_tool", "web")
# The bundled sample inputs.
SAMPLE = os.path.join(_BASE, "examples", "sample_config.json")
# Designation suggestions offered in the Team form.
DESIGNATIONS = ("Engineer", "Senior Engineer", "Lead Engineer", "SME", "Manager")


# -- (de)serialisation --------------------------------------------------------
def _cfg(inputs: dict) -> RosterConfig:
    # Build a validated config from the raw inputs dict the browser sent.
    return RosterConfig.from_dict(inputs)


def _locks(data: dict | None) -> Locks:
    # Rebuild a Locks object from its JSON form (or an empty one).
    return storage.locks_from_dict(data or {})


def roster_from_payload(cfg: RosterConfig, payload: dict) -> Roster:
    # Rebuild a Roster from the browser's payload, including its locks.
    return storage._roster_from_dict(cfg, payload or {}, _locks((payload or {}).get("locks")))


def roster_payload(roster: Roster) -> dict:
    # Serialise a Roster into the JSON shape the browser expects.
    cfg = roster.config
    return {
        "year": cfg.year,
        "month": cfg.month,
        # grid/on-call maps with ISO date keys (empty cells omitted).
        "grid": {n: {d.isoformat(): c for d, c in days.items() if c} for n, days in roster.grid.items()},
        "primary": {d.isoformat(): n for d, n in roster.primary.items() if n},
        "secondary": {d.isoformat(): n for d, n in roster.secondary.items() if n},
        "locks": storage.locks_to_dict(roster.locks),
        # Per-engineer tallies (this month) and totals (incl. carry-over).
        "counts": {n: roster.counts(n) for n in cfg.engineer_names},
        "totals": {n: roster.total_counts(n) for n in cfg.engineer_names},
    }


def day_meta(cfg: RosterConfig) -> list[dict]:
    # Per-day metadata the grid header needs (number, weekday, type, holiday).
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
    # Serialise a list of Issue objects into JSON dicts.
    return [{"severity": i.severity, "date": i.day.isoformat() if i.day else "", "message": i.message} for i in issues]


def analysis(roster: Roster, baseline: Roster | None) -> dict:
    # Everything the roster page needs to update after a generate/edit.
    cfg = roster.config
    issues = validate(roster)                       # rule check
    met, requested = preference_stats(roster)       # preference tally
    changes = storage.diff(baseline, roster) if baseline else []  # vs published
    return {
        "issues": issue_list(issues),
        "errors": count(issues, ERROR),
        "warnings": count(issues, WARNING),
        # Days with at least one error, for the red dots.
        "errorDays": sorted({i.day.isoformat() for i in issues if i.severity == ERROR and i.day}),
        "preferences": {"met": met, "requested": requested},
        "changes": [{"date": c.day.isoformat(), "who": c.who, "old": c.old, "new": c.new} for c in changes],
        "days": day_meta(cfg),
    }


# -- request handlers (each returns a JSON-able dict) -------------------------
def api_meta(_data):
    # Constants the front end needs: colours, shift/day names, blank inputs.
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
    # Return the bundled sample inputs.
    with open(SAMPLE, encoding="utf-8") as fh:
        return {"inputs": json.load(fh)}


def api_generate(data):
    # Build a roster from inputs, honouring locks and an optional published baseline.
    cfg = _cfg(data["inputs"])
    locks = _locks(data.get("locks"))
    baseline = None
    if data.get("baseline"):
        baseline = roster_from_payload(cfg, data["baseline"])
        # Ignore a baseline from a different month.
        if (baseline.config.year, baseline.config.month) != (cfg.year, cfg.month):
            baseline = None
    roster, _issues = generate(cfg, locks, baseline)
    return {"roster": roster_payload(roster), "analysis": analysis(roster, baseline)}


def api_precheck(data):
    # Run the pre-generate capacity check and return any warnings.
    cfg = _cfg(data["inputs"])
    return {"issues": issue_list(precheck(cfg, _locks(data.get("locks"))))}


def api_validate(data):
    # Re-check a hand-edited roster (no regeneration) and refresh its analysis.
    cfg = _cfg(data["inputs"])
    roster = roster_from_payload(cfg, data["roster"])
    baseline = roster_from_payload(cfg, data["baseline"]) if data.get("baseline") else None
    return {"roster": roster_payload(roster), "analysis": analysis(roster, baseline)}


def api_swap(data):
    # Preview a swap: return the swapped roster, the changes, and any new errors.
    cfg = _cfg(data["inputs"])
    roster = roster_from_payload(cfg, data["roster"])
    d = date.fromisoformat(data["day"])
    new = storage.swap(roster, data["a"], data["b"], d)
    # Errors that exist after the swap but not before are the ones it introduced.
    before = {i.message for i in validate(roster) if i.severity == ERROR}
    new_errors = [i.message for i in validate(new) if i.severity == ERROR and i.message not in before]
    preview = [{"date": c.day.isoformat(), "who": c.who, "old": c.old, "new": c.new} for c in storage.diff(roster, new)]
    return {"roster": roster_payload(new), "preview": preview, "newErrors": new_errors}


def api_open(data):
    # Open an uploaded roster file and return its inputs, roster and published copy.
    rf = storage.roster_file_from_dict(data["file"])
    return {
        "inputs": rf.inputs,
        "roster": roster_payload(rf.roster),
        "published": roster_payload(rf.published) if rf.published else None,
        "publishedAt": rf.published_at,
    }


def api_save(data):
    # Build the roster-file dict the browser will download.
    cfg = _cfg(data["inputs"])
    roster = roster_from_payload(cfg, data["roster"])
    published = roster_from_payload(cfg, data["published"]) if data.get("published") else None
    return {"file": storage.roster_file_dict(data["inputs"], roster, published, data.get("publishedAt", ""))}


def api_carry_over(data):
    # Build the carry-over block from an uploaded previous-month roster file.
    rf = storage.roster_file_from_dict(data["file"])
    ny, nm = storage.next_month(rf.roster.config.year, rf.roster.config.month)
    return {"carryOver": storage.carry_over_from(rf.roster), "prevInputs": rf.inputs, "nextYear": ny, "nextMonth": nm}


# Map each POST path to the function that handles it.
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
    # Rebuild the config and roster from the request.
    cfg = _cfg(data["inputs"])
    roster = roster_from_payload(cfg, data["roster"])
    # Apply any shift timings the page sent (used by the calendar export).
    if data.get("shiftTimes"):
        from .model import parse_time, parse_shift
        for name, t in data["shiftTimes"].items():
            roster.config.shift_times[parse_shift(name)] = (parse_time(t["start"]), parse_time(t["end"]))
    # A "YYYY_MM" tag for the download filename.
    tag = f"{cfg.year}_{cfg.month:02d}"
    if fmt == "csv":
        # Write the table into an in-memory text buffer.
        buf = io.StringIO()
        import csv as _csv
        w = _csv.writer(buf)
        w.writerows(export.table_rows(roster))
        return buf.getvalue().encode("utf-8"), "text/csv", f"roster_{tag}.csv"
    if fmt == "xlsx":
        # openpyxl writes to a path, so use a temporary file then read it back.
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
            path = tmp.name
        try:
            export.to_excel(roster, path, validate(roster))
            with open(path, "rb") as fh:
                content = fh.read()
        finally:
            os.unlink(path)   # always clean up the temp file
        return content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", f"roster_{tag}.xlsx"
    if fmt == "ics":
        # Build a zip in memory containing one .ics per engineer plus the team.
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for name in cfg.engineer_names + [None]:
                label = name or "Team"
                zf.writestr(f"{label} - roster {cfg.year}-{cfg.month:02d}.ics", ics.build_calendar(roster, name))
        return buf.getvalue(), "application/zip", f"roster_{tag}_calendars.zip"
    # Any other format string is a programming error.
    raise ValueError(f"unknown export format '{fmt}'")


# File extension -> HTTP content type, for serving the static files.
CONTENT_TYPES = {".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml", ".png": "image/png"}


class Handler(BaseHTTPRequestHandler):
    # Handles one HTTP request. The server creates a fresh Handler per request.
    server_version = "RosterCreator"

    def log_message(self, *_args):
        pass  # keep the console quiet (no per-request logging)

    def _send(self, status, body: bytes, content_type: str, extra: dict | None = None):
        # Send a full HTTP response: status line, headers, then the body bytes.
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")   # never cache app data
        for k, v in (extra or {}).items():
            self.send_header(k, v)                       # any extra headers
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, status=200):
        # Convenience: send a Python object as a JSON response.
        self._send(status, json.dumps(obj).encode("utf-8"), "application/json")

    def do_GET(self):
        # Handle GET requests: a couple of read-only API calls, else static files.
        path = self.path.split("?", 1)[0]      # drop any query string
        if path == "/api/meta":
            self._json(api_meta(None))
            return
        if path == "/api/sample":
            self._json(api_sample(None))
            return
        # Map "/" to index.html; otherwise use the requested relative path.
        rel = "index.html" if path in ("/", "") else path.lstrip("/")
        full = os.path.normpath(os.path.join(WEB_DIR, rel))
        # Guard against path escapes and missing files.
        if not full.startswith(WEB_DIR) or not os.path.isfile(full):
            self._send(404, b"Not found", "text/plain")
            return
        # Read and serve the file with the right content type.
        with open(full, "rb") as fh:
            body = fh.read()
        self._send(200, body, CONTENT_TYPES.get(os.path.splitext(full)[1], "application/octet-stream"))

    def do_POST(self):
        # Handle POST requests: the JSON API and the export endpoints.
        path = self.path.split("?", 1)[0]
        try:
            # Read the request body (a JSON object) using its Content-Length.
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, TypeError):
            self._json({"error": "Bad request"}, 400)
            return
        try:
            # A plain JSON endpoint.
            if path in JSON_ROUTES:
                self._json(JSON_ROUTES[path](data))
                return
            # A file-download endpoint like /api/export/csv.
            if path.startswith("/api/export/"):
                content, ctype, filename = export_bytes(path.rsplit("/", 1)[1], data)
                self._send(200, content, ctype, {"Content-Disposition": f'attachment; filename="{filename}"'})
                return
        except ValueError as exc:
            # Expected, user-facing errors become a 400 with the message.
            self._json({"error": str(exc)}, 400)
            return
        except Exception as exc:  # pragma: no cover - surfaced to the user
            # Anything unexpected becomes a 500 with a short description.
            self._json({"error": f"{type(exc).__name__}: {exc}"}, 500)
            return
        # No route matched.
        self._json({"error": "Unknown endpoint"}, 404)


def serve(host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True) -> None:
    # Start the threaded server (each request handled on its own thread).
    httpd = ThreadingHTTPServer((host, port), Handler)
    url = f"http://{host}:{port}/"
    print(f"Roster Creator is running at {url}")
    print("Leave this window open while you use it. Press Ctrl+C here to stop.")
    # Open the browser shortly after the server starts listening.
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        # Run until interrupted.
        httpd.serve_forever()
    except KeyboardInterrupt:
        # Ctrl+C is the normal way to stop it.
        print("\nStopping Roster Creator.")
    finally:
        httpd.server_close()


def main(argv=None):
    # Parse command-line options and start the server.
    import argparse

    ap = argparse.ArgumentParser(description="Run the Roster Creator web app locally.")
    ap.add_argument("--port", type=int, default=8765)                 # which port to listen on
    ap.add_argument("--host", default="127.0.0.1")                    # localhost by default
    ap.add_argument("--no-browser", action="store_true", help="do not open a browser automatically")
    args = ap.parse_args(argv)
    serve(args.host, args.port, not args.no_browser)


# When run directly (``python -m roster_tool.webapp``), start the server.
if __name__ == "__main__":
    main()
