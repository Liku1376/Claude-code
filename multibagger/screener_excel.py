"""Read a Screener.in "Export to Excel" workbook.

Every Screener export has a "Data Sheet" tab with ten years of numbers laid
out in labelled sections (META, PROFIT & LOSS, BALANCE SHEET, CASH FLOW:,
PRICE:, DERIVED:). This reader uses only the standard library (zipfile +
ElementTree), so no Excel library is needed.

Use this when you have exports saved from a logged-in Screener account: it
carries a few lines the public web page does not (receivables, inventory,
cash, share count, dividend amount, year-end prices).
"""

import re
import zipfile
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from typing import Dict, Optional

from .model import Company

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
RNS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
SECTIONS = {"META": "meta", "PROFIT & LOSS": "pl", "Quarters": "q", "BALANCE SHEET": "bs",
            "CASH FLOW:": "cf", "PRICE:": "price", "DERIVED:": "derived"}


def _col(ref: str) -> int:
    n = 0
    for ch in ref:
        if "A" <= ch <= "Z":
            n = n * 26 + ord(ch) - 64
        else:
            break
    return n - 1


def _read_rows(path: str) -> Dict[int, Dict[int, object]]:
    with zipfile.ZipFile(path) as z:
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        rel = {r.get("Id"): r.get("Target") for r in rels}
        target = None
        for sh in wb.iter("{%s}sheet" % NS["m"]):
            if (sh.get("name") or "").strip().lower() == "data sheet":
                target = rel.get(sh.get(RNS))
                break
        if not target:
            raise ValueError("No 'Data Sheet' tab - this does not look like a Screener.in export")
        target = re.sub(r"^/?(xl/)?", "xl/", target)
        strings = []
        if "xl/sharedStrings.xml" in z.namelist():
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iter("{%s}si" % NS["m"]):
                strings.append("".join(t.text or "" for t in si.iter("{%s}t" % NS["m"])))
        sheet = ET.fromstring(z.read(target))
    rows: Dict[int, Dict[int, object]] = {}
    for c in sheet.iter("{%s}c" % NS["m"]):
        ref = c.get("r")
        if not ref:
            continue
        t = c.get("t")
        if t == "inlineStr":
            v = "".join(x.text or "" for x in c.iter("{%s}t" % NS["m"]))
        else:
            ve = c.find("m:v", NS)
            if ve is None or ve.text is None:
                continue
            if t == "s":
                v = strings[int(ve.text)]
            elif t in ("str", "e"):
                v = ve.text
            else:
                try:
                    v = float(ve.text)
                except ValueError:
                    continue
        rows.setdefault(int(re.sub(r"\D", "", ref)), {})[_col(ref)] = v
    return rows


def _fy_label(serial) -> str:
    if not isinstance(serial, float):
        return str(serial)
    d = date(1899, 12, 30) + timedelta(days=int(round(serial)))
    return d.strftime("%b %Y")


def read_export(path: str) -> Company:
    rows = _read_rows(path)
    order = sorted(rows)
    marks = [(rn, SECTIONS[rows[rn][0].strip()]) for rn in order
             if isinstance(rows[rn].get(0), str) and rows[rn][0].strip() in SECTIONS]

    def section_of(rn):
        s = "head"
        for r, nm in marks:
            if rn >= r:
                s = nm
        return s

    S: Dict[str, Dict[str, Dict[int, object]]] = {}
    for rn in order:
        lb = rows[rn].get(0)
        if isinstance(lb, str):
            S.setdefault(section_of(rn), {})[lb.strip()] = rows[rn]

    def cols(row):
        return sorted(i for i, v in (row or {}).items() if i > 0 and isinstance(v, float))

    pl_dates = S.get("pl", {}).get("Report Date")
    bs_dates = S.get("bs", {}).get("Report Date")
    if not pl_dates or not bs_dates:
        raise ValueError("The Data Sheet is missing its Profit & Loss or Balance Sheet rows")
    pc, bc = cols(pl_dates), cols(bs_dates)
    cc = cols(S.get("cf", {}).get("Report Date")) or pc

    def pick(sec, label, cs):
        row = S.get(sec, {}).get(label) or {}
        return [row.get(i) if isinstance(row.get(i), float) else None for i in cs]

    meta = S.get("meta", {})

    def g(label, default=0.0) -> Optional[float]:
        v = (meta.get(label) or {}).get(1)
        return v if isinstance(v, float) else default

    name = (rows.get(1) or {}).get(1) or path
    c = Company(name=str(name), source="Screener export: %s" % path,
                years=[_fy_label(pl_dates[i]) for i in pc])
    c.price, c.mcap, c.face_value = g("Current Price"), g("Market Capitalization"), g("Face Value", None)
    costs = ["Raw Material Cost", "Change in Inventory", "Power and Fuel", "Other Mfr. Exp",
             "Employee Cost", "Selling and admin", "Other Expenses"]
    c.sales = pick("pl", "Sales", pc)
    cost_rows = [pick("pl", lb, pc) for lb in costs]
    c.op_profit = [s - sum(r[i] or 0 for r in cost_rows) if s is not None else None for i, s in enumerate(c.sales)]
    c.other_income = pick("pl", "Other Income", pc)
    c.dep = pick("pl", "Depreciation", pc)
    c.interest = pick("pl", "Interest", pc)
    c.pbt = pick("pl", "Profit before tax", pc)
    c.tax = pick("pl", "Tax", pc)
    c.pat = pick("pl", "Net profit", pc)
    c.div_amt = pick("pl", "Dividend Amount", pc)
    c.equity_capital = pick("bs", "Equity Share Capital", bc)
    c.reserves = pick("bs", "Reserves", bc)
    c.borrowings = pick("bs", "Borrowings", bc)
    c.other_liab = pick("bs", "Other Liabilities", bc)
    c.total_assets = pick("bs", "Total", bc)
    c.net_block = pick("bs", "Net Block", bc)
    c.cwip = pick("bs", "Capital Work in Progress", bc)
    c.investments = pick("bs", "Investments", bc)
    c.receivables = pick("bs", "Receivables", bc)
    c.inventory = pick("bs", "Inventory", bc)
    c.cash = pick("bs", "Cash & Bank", bc)
    counts, fvs = pick("bs", "No. of Equity Shares", bc), pick("bs", "Face value", bc)
    fv_last = next((v for v in reversed(fvs) if v), None)
    # adjust share counts for face-value splits so a split is not read as dilution
    c.share_count = [n * f / fv_last if n and f and fv_last else n for n, f in zip(counts, fvs)]
    c.cfo = pick("cf", "Cash from Operating Activity", cc)
    c.year_price = pick("price", "PRICE:", pc)
    return c
