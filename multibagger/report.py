"""Outputs: a console table, a CSV of every metric, and a self-contained HTML report."""

import csv
import html
import json
from datetime import datetime
from typing import List

from .engine import Result, fmt_num as F, fmt_pct as P

VERDICT_LABEL = {"buy": "BUY", "watch": "WATCH", "reject": "REJECT", "skip": "SKIP"}


def _row(r: Result) -> dict:
    m, v, c = r.metrics, r.valuation, r.company
    sc, pc = m.get("sales_cagr", {}), m.get("pat_cagr", {})
    return {
        "symbol": c.symbol, "company": c.name, "verdict": VERDICT_LABEL[r.verdict],
        "score_pct": round(r.score_pct, 1), "quadrant": r.matrix.get("quadrant", ""),
        "profitability": r.matrix.get("profitability", ""),
        "two_minute": m.get("two_minute_verdict", ""),
        "mcap_cr": c.mcap, "price": c.price, "sweet_spot_lt_5000cr": m.get("sweet_spot", ""),
        "roe_10y": m.get("roe10"), "roe_5y": m.get("roe5"), "roce_median": m.get("roce_med"),
        "fcf_sales_5y": m.get("fcf_sales5"), "cfo_pat": m.get("cfo_pat_avg"),
        "sales_cagr_3y": sc.get("3y"), "sales_cagr_10y": sc.get("10y"),
        "pat_cagr_3y": pc.get("3y"), "pat_cagr_5y": pc.get("5y"), "pat_cagr_10y": pc.get("10y"),
        "ssgr": m.get("ssgr"), "debt_equity": m.get("de"), "interest_cover": m.get("icr"),
        "opm_sd_pp": m.get("opm_sd"), "promoter_pct": m.get("promoter"),
        "pe_now": m.get("pe_now"), "pe_5y": m.get("pe5"), "relative_cheap_of_5": m.get("relative_cheap"),
        "intrinsic_value": v.get("iv"), "models_agree": v.get("agree"), "model_spread": v.get("spread"),
        "buy_phase1": (v.get("entry") or [None])[0], "buy_phase2": (v.get("entry") or [None, None])[1],
        "buy_phase3": (v.get("entry") or [None] * 3)[2],
        "sell_phase1": (v.get("exit") or [None])[0], "upside": v.get("upside"),
        "capital_gain_10y": v.get("capital_gain"), "investment_return": v.get("investment_return"),
        "speculative_return": v.get("speculative_return"),
        "failed_gates": "; ".join(g["k"] for g in r.failed_gates),
        "red_flags": "; ".join(r.red_flags), "reasons": "; ".join(r.reasons),
        "years": m.get("years", ""), "source": c.source, "error": r.error or "",
    }


def _entry1(r: Result):
    """Phase-1 buy price - only for businesses that cleared the quality gate (guide §7.3)."""
    return (r.valuation.get("entry") or [None])[0] if r.verdict in ("buy", "watch") else None


def write_csv(results: List[Result], path: str) -> None:
    rows = [_row(r) for r in results]
    if not rows:
        return
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        for row in rows:
            w.writerow({k: (round(v, 4) if isinstance(v, float) else v) for k, v in row.items()})


def write_json(results: List[Result], path: str) -> None:
    def clean(o):
        if isinstance(o, dict):
            return {k: clean(v) for k, v in o.items() if k != "series"}
        if isinstance(o, list):
            return [clean(x) for x in o]
        return o
    out = [dict(_row(r), metrics=clean(r.metrics), valuation=clean(r.valuation), gates=r.gates,
                score=r.score, two_minute=r.two_minute, relative=r.relative) for r in results]
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, default=str)


def console(results: List[Result]) -> str:
    head = "%-4s %-28s %-7s %5s %7s %7s %8s %7s %-22s %11s %11s" % (
        "#", "Company", "Verdict", "Score", "ROE10", "FCF/S", "PAT10y", "D/E", "Quadrant", "Price", "Buy ≤")
    lines = [head, "-" * len(head)]
    for i, r in enumerate(results, 1):
        m, v = r.metrics, r.valuation
        lines.append("%-4d %-28s %-7s %5.0f %7s %7s %8s %7s %-22s %11s %11s" % (
            i, (r.company.symbol or r.name)[:28], VERDICT_LABEL[r.verdict], r.score_pct,
            P(m.get("roe10")), P(m.get("fcf_sales5")), P((m.get("pat_cagr") or {}).get("10y")),
            F(m.get("de"), 2), r.matrix.get("quadrant", r.reasons[0] if r.reasons else "")[:22],
            F(r.company.price, 2), F(_entry1(r), 2)))
    return "\n".join(lines)


CSS = """
:root{--bg:#f4f6f6;--surface:#fff;--ink:#0d1a19;--muted:#5f716f;--line:#d2dbda;--accent:#0c6b59;
--pass:#0f7551;--pass-soft:#dcf0e6;--warn:#8f6206;--warn-soft:#f7ecd5;--fail:#9e2f2f;--fail-soft:#f8e2e0;--chip:#e6ebeb}
@media (prefers-color-scheme:dark){:root{--bg:#0b1110;--surface:#141d1c;--ink:#e3ebe9;--muted:#8fa29f;--line:#273433;
--accent:#3dbf9e;--pass:#42c79a;--pass-soft:#0f2e25;--warn:#d5a441;--warn-soft:#2e2615;--fail:#e37b76;--fail-soft:#331b1b;--chip:#1f2a29}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}
.wrap{max-width:1200px;margin:0 auto;padding:24px 16px 64px}h1{margin:0 0 4px;font-size:28px}.muted{color:var(--muted)}
.tiles{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:18px 0}.tile{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:12px}
.tile b{display:block;font-size:24px;font-variant-numeric:tabular-nums}.tw{overflow-x:auto;background:var(--surface);border:1px solid var(--line);border-radius:10px}
table{border-collapse:collapse;width:100%;min-width:900px}th,td{padding:8px 10px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}
th{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);cursor:pointer;position:sticky;top:0;background:var(--surface)}
th:nth-child(-n+2),td:nth-child(-n+2){text-align:left}td small{display:block;color:var(--muted)}
.pill{font-size:11px;font-weight:700;padding:2px 8px;border-radius:99px}.buy{background:var(--pass-soft);color:var(--pass)}
.watch{background:var(--warn-soft);color:var(--warn)}.reject{background:var(--fail-soft);color:var(--fail)}.skip{background:var(--chip);color:var(--muted)}
details{background:var(--surface);border:1px solid var(--line);border-radius:10px;margin:10px 0;padding:10px 14px}summary{cursor:pointer;font-weight:600}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:14px;margin-top:10px}
.grid table{min-width:0}.grid td,.grid th{white-space:normal}.ok{color:var(--pass)}.no{color:var(--fail)}
@media(max-width:700px){.tiles{grid-template-columns:repeat(2,1fr)}}
"""

JS = """
document.querySelectorAll('th[data-k]').forEach((th,i)=>th.onclick=()=>{const tb=th.closest('table').tBodies[0];
const rows=[...tb.rows];const dir=th.dataset.d=th.dataset.d==='1'?'-1':'1';
rows.sort((a,b)=>{const x=a.cells[i].dataset.v??a.cells[i].innerText,y=b.cells[i].dataset.v??b.cells[i].innerText;
const nx=parseFloat(x),ny=parseFloat(y);return (isNaN(nx)||isNaN(ny)?x.localeCompare(y):nx-ny)*dir});rows.forEach(r=>tb.appendChild(r))});
"""


def _e(s) -> str:
    return html.escape(str(s))


def _td(text, val=None):
    dv = "" if val is None or not isinstance(val, (int, float)) else ' data-v="%s"' % val
    return "<td%s>%s</td>" % (dv, _e(text))


def write_html(results: List[Result], path: str, settings=None) -> None:
    counts = {k: sum(1 for r in results if r.verdict == k) for k in ("buy", "watch", "reject", "skip")}
    cols = ["Company", "Verdict", "Score", "Quadrant", "ROE 10y", "ROCE med", "FCF/Sales", "PAT CAGR 10y",
            "SSGR", "D/E", "Mcap ₹cr", "Price", "Intrinsic", "Buy ≤ (P1)", "Upside"]
    body = []
    for r in results:
        m, v, c = r.metrics, r.valuation, r.company
        e1 = _entry1(r)
        body.append("<tr>" + "".join([
            "<td><b>%s</b><small>%s</small></td>" % (_e(c.symbol or c.name), _e(c.name if c.symbol else c.source)),
            '<td data-v="%d"><span class="pill %s">%s</span></td>' % (
                ["buy", "watch", "reject", "skip"].index(r.verdict), r.verdict, VERDICT_LABEL[r.verdict]),
            _td("%.0f" % r.score_pct, r.score_pct), _td(r.matrix.get("quadrant", "—")),
            _td(P(m.get("roe10")), m.get("roe10")), _td(P(m.get("roce_med")), m.get("roce_med")),
            _td(P(m.get("fcf_sales5")), m.get("fcf_sales5")),
            _td(P((m.get("pat_cagr") or {}).get("10y")), (m.get("pat_cagr") or {}).get("10y")),
            _td(P(m.get("ssgr")), m.get("ssgr")), _td(F(m.get("de"), 2), m.get("de")),
            _td(F(c.mcap, 0), c.mcap), _td(F(c.price, 2), c.price), _td(F(v.get("iv"), 2), v.get("iv")),
            _td(F(e1, 2), e1), _td(P(v.get("upside")), v.get("upside")),
        ]) + "</tr>")
    details = [_detail(r) for r in results if r.verdict in ("buy", "watch")]
    s = settings
    assumptions = "" if s is None else (
        "Discount rate %.1f%% · G-sec %.2f%% · exit P/E %.0f · min market cap ₹%s cr" % (
            s.disc * 100, s.bond * 100, s.exit_pe, F(s.min_cap, 0)))
    doc = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Multibagger Screen</title>
<style>%s</style></head><body><div class="wrap">
<h1>Multibagger Screen</h1><div class="muted">Value Investing Process — Indian Equities · run %s · %s</div>
<div class="tiles"><div class="tile"><b>%d</b>Analysed</div><div class="tile"><b class="ok">%d</b>Buy now</div>
<div class="tile"><b>%d</b>Watchlist — wait for price</div><div class="tile"><b class="no">%d</b>Rejected / skipped</div></div>
<div class="tw"><table><thead><tr>%s</tr></thead><tbody>%s</tbody></table></div>
<h2>Shortlist detail</h2>%s
<p class="muted">The numbers screen a business; they do not approve one. Before buying anything here, do the manual
stages of the process: circle of competence, the forensic checklist and annual reports, the moat and management
judgement, the written thesis and the 48-hour behavioural gate.</p>
</div><script>%s</script></body></html>""" % (
        CSS, datetime.now().strftime("%d %b %Y %H:%M"), _e(assumptions), len(results), counts["buy"],
        counts["watch"], counts["reject"] + counts["skip"],
        "".join('<th data-k="%d">%s</th>' % (i, _e(cn)) for i, cn in enumerate(cols)),
        "".join(body), "".join(details) or '<p class="muted">Nothing cleared the quality gate.</p>', JS)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(doc)


def _detail(r: Result) -> str:
    m, v = r.metrics, r.valuation
    yn = lambda b: '<span class="ok">✔</span>' if b else ('<span class="muted">judge</span>' if b is None  # noqa: E731
                                                         else '<span class="no">✘</span>')
    tm = "".join("<tr><td>%d</td><td>%s</td><td>%s</td></tr>" % (t["n"], _e(t["q"]), yn(t["pass"]))
                 for t in r.two_minute)
    sc = "".join("<tr><td>%s</td><td>%s</td><td>%.1f / %d</td></tr>" % (_e(s["label"]), _e(s["detail"]),
                                                                        s["got"], s["max"]) for s in r.score)
    models = v.get("models") or {}
    names = {"dhandho_worst": "Dhandho worst", "dhandho_best": "Dhandho best", "dcf": "DCF (fading)",
             "total_returns": "Total Returns", "pe_g": "P/E = G (Lynch)"}
    val = "".join("<tr><td>%s</td><td>%s</td></tr>" % (names[k], F(x, 2)) for k, x in models.items())
    if v.get("iv"):
        val += "<tr><td><b>Weighted intrinsic value</b></td><td><b>%s</b></td></tr>" % F(v["iv"], 2)
        val += "<tr><td>Spread (max/min)</td><td>%s×%s</td></tr>" % (
            F(v.get("spread"), 2), "" if v.get("agree") else " — disagree")
        val += "<tr><td>Buy ladder 90/80/75%%</td><td>%s</td></tr>" % " · ".join(F(x, 2) for x in v["entry"])
        val += "<tr><td>Sell ladder</td><td>%s</td></tr>" % " · ".join(F(x, 2) for x in v["exit"])
        val += "<tr><td>Capital gain / investment / speculative</td><td>%s / %s / %s</td></tr>" % (
            P(v.get("capital_gain")), P(v.get("investment_return")), P(v.get("speculative_return")))
    rel = "".join("<tr><td>%s</td><td>%s</td></tr>" % (_e(x["check"]), yn(x["cheap"])) for x in r.relative)
    flags = "".join("<li>%s</li>" % _e(f) for f in r.red_flags) or "<li>None found in the numbers</li>"
    manual = "".join("<li>%s</li>" % _e(x) for x in r.manual_checks)
    return """<details><summary>%s — %s · %s · score %.0f</summary>
<p>%s</p><div class="grid">
<div><h4>2-minute test (%s)</h4><table>%s</table></div>
<div><h4>Scorecard</h4><table>%s</table></div>
<div><h4>Valuation</h4><table>%s</table><h4>Relative cheapness</h4><table>%s</table></div>
<div><h4>Red flags from the numbers</h4><ul>%s</ul><h4>Still to do by hand</h4><ul>%s</ul></div>
</div></details>""" % (_e(r.company.symbol or r.name), VERDICT_LABEL[r.verdict], _e(r.matrix.get("quadrant")),
                       r.score_pct, _e(" · ".join(r.reasons)), _e(m.get("two_minute_verdict")), tm, sc, val, rel,
                       flags, manual)
