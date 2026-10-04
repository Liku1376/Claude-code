"""Fetch and parse Screener.in company pages.

A Screener company page (``https://www.screener.in/company/<SYMBOL>/consolidated/``)
carries 10-12 years of profit & loss, balance sheet, cash flow, ratios and
shareholding in plain HTML tables. This module downloads it with the
standard library, parses the tables, and returns a :class:`Company`.

Two optional Screener JSON endpoints add what the page leaves out:

* ``/api/company/<id>/schedules/`` - the breakdown of "Other Assets"
  (receivables, inventory, cash) and dividend amounts;
* ``/api/company/<id>/chart/`` - ten years of share prices, for the
  historical P/E, P/S and P/B averages.

If either fails (layout change, rate limit) the analysis still runs; the
affected checks are simply reported as unavailable.

Be polite: requests are spaced out (``delay``) and every response is cached
on disk, so re-running a screen does not hit Screener again for a day.
Respect Screener's terms of use and do not run huge universes in a hurry.
"""

import gzip
import hashlib
import http.cookiejar
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from html.parser import HTMLParser
from typing import Dict, List, Optional

from .model import Company

BASE = "https://www.screener.in"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


# ---------------------------------------------------------------- HTTP client

class ScreenerClient:
    """A small, polite HTTP client with an on-disk cache and optional login."""

    def __init__(self, cache_dir: Optional[str] = ".screener_cache", delay: float = 2.0,
                 max_age_hours: float = 24.0, timeout: float = 30.0):
        self.cache_dir = cache_dir
        self.delay = delay
        self.max_age = max_age_hours * 3600
        self.timeout = timeout
        self._last = 0.0
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        if cache_dir:
            os.makedirs(cache_dir, exist_ok=True)
        sid = os.environ.get("SCREENER_SESSIONID")
        if sid:
            self._set_cookie("sessionid", sid)

    def _set_cookie(self, name, value):
        self.jar.set_cookie(http.cookiejar.Cookie(
            0, name, value, None, False, "www.screener.in", True, False, "/", True,
            True, None, False, None, None, {}))

    def _cache_path(self, url):
        return os.path.join(self.cache_dir, hashlib.sha1(url.encode()).hexdigest() + ".cache")

    def get(self, url: str, use_cache: bool = True) -> str:
        if not url.startswith("http"):
            url = BASE + url
        path = self._cache_path(url) if self.cache_dir else None
        if use_cache and path and os.path.exists(path) and time.time() - os.path.getmtime(path) < self.max_age:
            with open(path, encoding="utf-8") as fh:
                return fh.read()
        text = self._fetch(url)
        if path:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
        return text

    def _fetch(self, url, data=None, headers=None, retries=3):
        for attempt in range(retries):
            wait = self.delay - (time.time() - self._last)
            if wait > 0:
                time.sleep(wait)
            req = urllib.request.Request(url, data=data, headers={
                "User-Agent": UA, "Accept-Encoding": "gzip", "Referer": BASE + "/", **(headers or {})})
            try:
                with self.opener.open(req, timeout=self.timeout) as resp:
                    self._last = time.time()
                    body = resp.read()
                    if resp.headers.get("Content-Encoding") == "gzip":
                        body = gzip.decompress(body)
                    return body.decode("utf-8", "replace")
            except urllib.error.HTTPError as e:
                self._last = time.time()
                if e.code == 429 and attempt < retries - 1:  # rate-limited: back off
                    time.sleep(10 * (attempt + 1))
                    continue
                raise
        raise RuntimeError("unreachable")

    def login(self, username: str, password: str) -> None:
        """Log in so that screen queries (``/screen/raw/``) work."""
        page = self._fetch(BASE + "/login/")
        m = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', page)
        if not m:
            raise RuntimeError("Could not find the login form on screener.in")
        data = urllib.parse.urlencode({
            "csrfmiddlewaretoken": m.group(1), "username": username, "password": password, "next": "/"}).encode()
        self._fetch(BASE + "/login/", data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
        if not any(c.name == "sessionid" for c in self.jar):
            raise RuntimeError("Screener login failed - check SCREENER_USERNAME / SCREENER_PASSWORD")


# ---------------------------------------------------------------- HTML parsing

class _PageParser(HTMLParser):
    """Collects every table inside each <section id=...>, the top ratios and the name."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.sections: Dict[str, List[List[List[str]]]] = {}
        self.table_ids: Dict[str, List[List[str]]] = {}
        self.top: Dict[str, str] = {}
        self.attrs: Dict[str, str] = {}
        self.name = ""
        self._sec_stack: List[Optional[str]] = []
        self._section = None
        self._table = None
        self._table_id = None
        self._row = None
        self._cell = None
        self._in_h1 = False
        self._in_top = False
        self._li = None
        self._span_cls = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "section":
            self._sec_stack.append(a.get("id"))
            if a.get("id"):
                self._section = a["id"]
        elif tag == "div" and a.get("id") == "company-info":
            self.attrs = {k: v for k, v in a.items() if k.startswith("data-")}
        elif tag == "h1" and not self.name:
            self._in_h1 = True
        elif tag == "ul" and a.get("id") == "top-ratios":
            self._in_top = True
        elif tag == "li" and self._in_top:
            self._li = {"name": "", "value": ""}
        elif tag == "span" and self._li is not None:
            if "name" in (a.get("class") or "").split():
                self._span_cls = "name"
        elif tag == "table":
            self._table = []
            self._table_id = a.get("id")
        elif tag == "tr" and self._table is not None:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = ""

    def handle_endtag(self, tag):
        if tag == "section":
            sid = self._sec_stack.pop() if self._sec_stack else None
            if sid:
                self._section = next((s for s in reversed(self._sec_stack) if s), None)
        elif tag == "h1":
            self._in_h1 = False
        elif tag == "ul" and self._in_top:
            self._in_top = False
        elif tag == "li" and self._li is not None:
            if self._li["name"].strip():
                self.top[_norm(self._li["name"])] = self._li["value"].strip()
            self._li = None
            self._span_cls = None
        elif tag == "span" and self._li is not None and self._span_cls == "name":
            self._span_cls = "value"
        elif tag in ("td", "th") and self._cell is not None:
            self._row.append(_norm(self._cell))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self._table.append(self._row)
            self._row = None
        elif tag == "table" and self._table is not None:
            if self._section:
                self.sections.setdefault(self._section, []).append(self._table)
            if self._table_id:
                self.table_ids[self._table_id] = self._table
            self._table = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell += data
        if self._in_h1:
            self.name += data
        if self._li is not None and self._span_cls:
            self._li[self._span_cls] += data


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("\xa0", " ")).strip()


def _num(s) -> Optional[float]:
    if s is None:
        return None
    s = str(s).replace(",", "").replace("₹", "").replace("%", "").replace("Cr.", "").strip()
    m = re.search(r"-?\d+(\.\d+)?", s)
    return float(m.group(0)) if m else None


def _label(s: str) -> str:
    # Screener appends a "+" to expandable rows: "Sales +", "Borrowings +"
    return re.sub(r"\s*\+$", "", s).strip()


def _table_to_rows(table: List[List[str]]):
    """Return (year headers, {label: [values]}) with the TTM column dropped."""
    if not table:
        return [], {}
    header = table[0]
    cols = [i for i, h in enumerate(header) if re.match(r"^[A-Z][a-z]{2} \d{4}$", h)]
    years = [header[i] for i in cols]
    rows = {}
    for row in table[1:]:
        if not row:
            continue
        rows[_label(row[0])] = [_num(row[i]) if i < len(row) else None for i in cols]
    return years, rows


def _pick(rows, *labels):
    for lb in labels:
        if lb in rows:
            return rows[lb]
    low = {k.lower(): v for k, v in rows.items()}
    for lb in labels:
        if lb.lower() in low:
            return low[lb.lower()]
    return None


def _align(years: List[str], src_years: List[str], values) -> List[Optional[float]]:
    if values is None:
        return [None] * len(years)
    look = dict(zip(src_years, values))
    return [look.get(y) for y in years]


def parse_company_page(html: str, symbol: str = "") -> Company:
    """Turn a Screener company page into a :class:`Company`."""
    p = _PageParser()
    p.feed(html)
    first = lambda sec: (p.sections.get(sec) or [[]])[0]  # noqa: E731
    years, pl = _table_to_rows(first("profit-loss"))
    if not years:
        raise ValueError("No profit & loss table found - is this a Screener company page?")
    by, bs = _table_to_rows(first("balance-sheet"))
    cy, cf = _table_to_rows(first("cash-flow"))
    ry, ra = _table_to_rows(first("ratios"))

    c = Company(name=_norm(p.name) or symbol, symbol=symbol, source="screener.in", years=years)
    c.price = _num(p.top.get("Current Price")) or 0.0
    c.mcap = _num(p.top.get("Market Cap")) or 0.0
    c.face_value = _num(p.top.get("Face Value"))
    c.pe_now = _num(p.top.get("Stock P/E"))

    c.is_financial = any(k in pl for k in ("Financing Profit", "Financing Margin %")) or "Deposits" in bs
    c.sales = _pick(pl, "Sales", "Revenue") or [None] * len(years)
    c.op_profit = _pick(pl, "Operating Profit", "Financing Profit") or [None] * len(years)
    c.other_income = _pick(pl, "Other Income") or [None] * len(years)
    c.interest = _pick(pl, "Interest") or [None] * len(years)
    c.dep = _pick(pl, "Depreciation") or [None] * len(years)
    c.pbt = _pick(pl, "Profit before tax") or [None] * len(years)
    tax_pct = _pick(pl, "Tax %") or [None] * len(years)
    c.tax = [b * t / 100 if b is not None and t is not None else None for b, t in zip(c.pbt, tax_pct)]
    c.pat = _pick(pl, "Net Profit") or [None] * len(years)
    c.eps = _pick(pl, "EPS in Rs") or [None] * len(years)
    payout = _pick(pl, "Dividend Payout %") or [None] * len(years)
    c.div_amt = [n * d / 100 if n is not None and d is not None and n > 0 else (0.0 if d is not None else None)
                 for n, d in zip(c.pat, payout)]

    c.equity_capital = _align(years, by, _pick(bs, "Equity Capital", "Share Capital"))
    c.reserves = _align(years, by, _pick(bs, "Reserves"))
    c.borrowings = _align(years, by, _pick(bs, "Borrowings", "Borrowing"))
    c.other_liab = _align(years, by, _pick(bs, "Other Liabilities"))
    c.total_assets = _align(years, by, _pick(bs, "Total Assets"))
    c.net_block = _align(years, by, _pick(bs, "Fixed Assets", "Net Block"))
    c.cwip = _align(years, by, _pick(bs, "CWIP", "Capital Work in Progress"))
    c.investments = _align(years, by, _pick(bs, "Investments"))
    c.cfo = _align(years, cy, _pick(cf, "Cash from Operating Activity"))
    c.debtor_days = _align(years, ry, _pick(ra, "Debtor Days"))
    c.inventory_days = _align(years, ry, _pick(ra, "Inventory Days"))

    # Shareholding: prefer the yearly table, fall back to quarterly
    shp = p.table_ids.get("yearly-shp") or p.table_ids.get("quarterly-shp")
    if shp is None:
        tabs = p.sections.get("shareholding") or []
        shp = tabs[-1] if tabs else None
    if shp:
        header = shp[0]
        for row in shp[1:]:
            if row and _label(row[0]).lower().startswith("promoter"):
                vals = [_num(x) for x in row[1:len(header)]]
                c.promoter_holding = vals[-10:]
                break

    c.notes.append("company id %s" % p.attrs.get("data-company-id", "?"))
    c._company_id = p.attrs.get("data-company-id")  # type: ignore[attr-defined]
    c._warehouse_id = p.attrs.get("data-warehouse-id")  # type: ignore[attr-defined]
    return c


# ---------------------------------------------------------------- JSON extras

def _fy_end(label: str) -> Optional[date]:
    m = re.match(r"([A-Z][a-z]{2}) (\d{4})", label)
    if not m:
        return None
    month = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"].index(m.group(1)) + 1
    return date(int(m.group(2)), month, 28)


def apply_price_history(c: Company, chart_json: str) -> None:
    """Fill ``year_price`` from Screener's chart API response."""
    data = json.loads(chart_json)
    pts = []
    for ds in data.get("datasets", []):
        if ds.get("metric") == "Price":
            for d, v in ds.get("values", []):
                try:
                    pts.append((date.fromisoformat(d[:10]), float(v)))
                except (TypeError, ValueError):
                    pass
    pts.sort()
    out = []
    for y in c.years:
        end = _fy_end(y)
        before = [v for d, v in pts if end and d <= end and (end - d).days < 40]
        out.append(before[-1] if before else None)
    c.year_price = out


def apply_other_assets(c: Company, schedule_json: str) -> None:
    """Fill receivables, inventory and cash from the "Other Assets" schedule."""
    data = json.loads(schedule_json)
    for key, attr in (("Trade receivables", "receivables"), ("Inventories", "inventory"),
                      ("Cash Equivalents", "cash")):
        row = next((v for k, v in data.items() if k.lower().startswith(key.lower())), None)
        if isinstance(row, dict):
            setattr(c, attr, [_num(row.get(y)) for y in c.years])


def fetch_company(client: ScreenerClient, symbol: str, consolidated: bool = True,
                  extras: bool = True) -> Company:
    """Download one company. Falls back to standalone figures if consolidated is empty."""
    path = "/company/%s/%s" % (urllib.parse.quote(symbol.upper()), "consolidated/" if consolidated else "")
    try:
        c = parse_company_page(client.get(path), symbol.upper())
    except ValueError:
        if not consolidated:
            raise
        return fetch_company(client, symbol, consolidated=False, extras=extras)
    if consolidated and not any(v for v in c.sales if v):
        return fetch_company(client, symbol, consolidated=False, extras=extras)
    c.source = "screener.in (%s)" % ("consolidated" if consolidated else "standalone")
    cid = getattr(c, "_company_id", None)
    if extras and cid:
        cons = "true" if consolidated else ""
        try:
            apply_price_history(c, client.get(
                "/api/company/%s/chart/?q=Price&days=4000&consolidated=%s" % (cid, cons)))
        except Exception as e:  # noqa: BLE001 - optional enrichment
            c.notes.append("price history unavailable: %s" % e)
        try:
            apply_other_assets(c, client.get(
                "/api/company/%s/schedules/?parent=Other+Assets&section=balance-sheet&consolidated=%s"
                % (cid, cons)))
        except Exception as e:  # noqa: BLE001
            c.notes.append("other-assets breakdown unavailable: %s" % e)
    return c


# ---------------------------------------------------------------- screens (needs login)

def run_screen(client: ScreenerClient, query: str, max_pages: int = 20) -> List[str]:
    """Run a Screener query and return the matching company symbols.

    Screener only serves query results to logged-in users, so call
    :meth:`ScreenerClient.login` first (or set ``SCREENER_SESSIONID``).
    """
    symbols: List[str] = []
    for page in range(1, max_pages + 1):
        url = "/screen/raw/?" + urllib.parse.urlencode({"query": query, "page": page, "limit": 50})
        html = client.get(url, use_cache=False)
        if "/login/" in html and "Login" in html and "data-row-company-id" not in html and page == 1 \
                and "/company/" not in html:
            raise RuntimeError("Screener needs you to be logged in to run screens")
        found = re.findall(r'href="/company/([^/"]+)/(?:consolidated/)?"', html)
        new = [s for s in dict.fromkeys(found) if s not in symbols]
        if not new:
            break
        symbols.extend(new)
    return symbols
