"""Tests for the multibagger screener.

screener.in is not contacted: the web parser is tested on a page built in the
same shape as Screener's, the Excel reader on a workbook built with zipfile,
and the engine on the guide's own worked example (The Andhra Sugars Ltd).
"""

import os
import zipfile

import pytest

from multibagger import Settings, analyse, rank
from multibagger.model import Company
from multibagger.screener_web import apply_other_assets, apply_price_history, parse_company_page

YEARS = ["Mar %d" % y for y in range(2017, 2027)]

# The Andhra Sugars Ltd, FY17-FY26, from the guide's Screener workbook.
ANDHRA = dict(
    sales=[1278.63, 1307.6, 1376.38, 1477.48, 1509.11, 1961.65, 2367.59, 1894.04, 2019.69, 2466],
    costs=[[520.39, 541.5, 700.8, 634.28, 712.6, 998.77, 1195.68, 970.74, 1075.14, 1331.89],
           [-47.81, -50.54, 147.31, -11.2, -32.34, 1.67, -14.45, -12.53, -42.45, -109.16],
           [212.5, 214.49, 210.44, 215.05, 215.24, 307.21, 423.62, 395.04, 369.31, 367.79],
           [130.16, 132.81, 132.61, 149.52, 149.03, 182.23, 206.53, 199.87, 203.14, 0],
           [116.17, 123.93, 142.51, 151.74, 149.8, 170.79, 182.8, 165.61, 181.32, 182.3],
           [12.73, 13.92, 12.33, 16.22, 13.52, 20.47, 17.82, 16.74, 17, 0],
           [20.57, 18.52, 21.71, 20.8, 20.37, 22.13, 18.91, 19.97, 31.27, 271.98]],
    other_income=[26.28, 44.22, 61.67, 43.62, 42.63, 115.54, 24.84, 54.23, 20.64, 3.15],
    dep=[51.27, 55.17, 55.45, 62.41, 61.24, 63.96, 75.76, 75.65, 80.75, 83.15],
    interest=[26.57, 33.13, 31.14, 28.94, 27.37, 13.47, 4.12, 1.9, 2.39, 2.48],
    pbt=[166.74, 167.81, 278.37, 230.94, 170.23, 299.83, 252.74, 90.22, 37.56, 120.4],
    tax=[41.97, 49.26, 86.43, 20.41, 28.94, 54.28, 62.18, 14.22, 11, 33.27],
    pat=[121.41, 116.54, 190.48, 203.09, 134.97, 242.21, 185.96, 75.1, 25.88, 83.22],
    div_amt=[27.11, 27.11, 27.11, 54.22, 27.11, 54.22, 27.11, 13.56, 10.84, 16.27],
    equity_capital=[27.11] * 10,
    reserves=[905.64, 960.34, 1103.71, 1126.46, 1270.42, 1491.45, 1514.16, 1555.76, 1565.14, 1644.44],
    borrowings=[369, 255.36, 301.21, 260.72, 159.42, 55.05, 23.61, 30.96, 13.35, 0.56],
    other_liab=[414.6, 389.64, 427.15, 393.28, 421.89, 465.77, 469.75, 461.27, 502.01, 502.09],
    total_assets=[1716.35, 1632.45, 1859.18, 1807.57, 1878.84, 2039.38, 2034.63, 2075.1, 2107.61, 2174.2],
    net_block=[657.66, 650.24, 699.7, 710.81, 716.24, 712.18, 805.88, 813.13, 952.45, 930.99],
    cwip=[29.66, 98.47, 58.46, 32.28, 51.67, 71.03, 125.41, 181.03, 56.98, 41.96],
    investments=[357.86, 260.54, 355.67, 266.58, 366.17, 408.58, 306.52, 316.88, 322.3, 529.39],
    receivables=[184.89, 176.38, 184.19, 212.64, 217.78, 239.95, 231.54, 188.66, 193.5, 227.69],
    inventory=[302.43, 280.1, 428.39, 442.42, 423.8, 467.53, 413.88, 433.97, 445.47, 298.73],
    cash=[42.62, 50.3, 59.9, 63.1, 26.69, 38.42, 60.21, 55.57, 56.57, 68.93],
    shares_raw=[27113091] * 5 + [135535390] * 5,
    fv=[10] * 5 + [2] * 5,
    cfo=[245.41, 202.42, 113.51, 181.23, 252.52, 176.46, 285.83, 141.69, 127.8, 278.33],
    year_price=[61.89, 81.7, 68.64, 35.41, 58.17, 152.9, 108.5, 92.75, 66.74, 71.46],
)


def andhra() -> Company:
    d = ANDHRA
    c = Company(name="The Andhra Sugars Ltd", symbol="ANDHRSUGAR", years=list(YEARS), price=88.15, mcap=1194.74)
    for k in ("sales", "other_income", "dep", "interest", "pbt", "tax", "pat", "div_amt", "equity_capital",
              "reserves", "borrowings", "other_liab", "total_assets", "net_block", "cwip", "investments",
              "receivables", "inventory", "cash", "cfo", "year_price"):
        setattr(c, k, list(d[k]))
    c.op_profit = [s - sum(row[i] for row in d["costs"]) for i, s in enumerate(d["sales"])]
    c.share_count = [n * f / 2 for n, f in zip(d["shares_raw"], d["fv"])]
    return c


def compounder(price_mult=1.0) -> Company:
    """A fictional high-ROE, cash-rich, growing business."""
    c = Company(name="Compounder Ltd", symbol="COMPOUND", years=list(YEARS))
    sales, pat, eq, nb = 1000.0, 150.0, 600.0, 300.0
    for _ in YEARS:
        c.sales.append(sales); c.pat.append(pat); c.op_profit.append(sales * 0.22)
        c.pbt.append(pat / 0.75); c.tax.append(pat / 0.75 - pat); c.other_income.append(sales * 0.005)
        c.interest.append(1.0); c.dep.append(nb * 0.08); c.div_amt.append(pat * 0.25)
        c.equity_capital.append(10.0); c.reserves.append(eq - 10); c.borrowings.append(5.0)
        c.other_liab.append(200.0); c.total_assets.append(eq + 205); c.net_block.append(nb); c.cwip.append(10.0)
        c.investments.append(50.0); c.cash.append(30.0); c.cfo.append(pat * 1.15)
        c.receivables.append(sales * 0.1); c.inventory.append(sales * 0.1)
        c.share_count.append(10.0); c.promoter_holding.append(55.0)
        c.year_price.append(pat / 10 * 40)
        sales *= 1.17; pat *= 1.18; eq += pat * 0.75 * 0.9; nb = sales / 3.5
    eps = c.pat[-1] / 10
    c.price = eps * 40 * price_mult
    c.mcap = c.price * 10
    return c


# ---------------------------------------------------------------- engine

def test_andhra_sugars_matches_the_guide():
    r = analyse(andhra())
    m = r.metrics
    # Guide: "10-year average ROE 10.9% — fails the 15% hurdle"; 5-yr ROE 7.87%
    assert m["roe10"] == pytest.approx(0.109, abs=0.002)
    assert m["roe5"] == pytest.approx(0.0787, abs=0.002)
    # Guide: CFO/net profit 1.96 (10-yr average of yearly ratios); cumulative CFO ₹2,005 cr
    assert m["cum_cfo"] == pytest.approx(2005, abs=1)
    # Guide: PAT CAGR 3/5/10-year -23.5% / -9.2% / -4.1%
    assert m["pat_cagr"]["3y"] == pytest.approx(-0.235, abs=0.003)
    assert m["pat_cagr"]["5y"] == pytest.approx(-0.092, abs=0.003)
    # the face-value split must not read as dilution
    assert abs(m["dilution"]) < 0.001
    # SSGR turned negative (guide: -0.6% and -3.8%)
    assert m["ssgr"] < 0
    assert r.matrix["profitability"] == "Worst company"
    assert r.matrix["quadrant"] == "Wealth destroyer"
    assert r.verdict == "reject"
    assert "10-yr average ROE ≥ 15%" in [g["k"] for g in r.failed_gates]
    assert m["two_minute_verdict"] == "AVOID"
    # yet every relative-cheapness check except earnings yield passes - the value trap
    assert m["relative_cheap"] >= 4
    # valuation models against the workbook (guide §6.4)
    models = r.valuation["models"]
    assert models["dhandho_worst"] == pytest.approx(160.33, abs=0.05)
    assert models["dhandho_best"] == pytest.approx(212.40, abs=0.05)
    assert models["dcf"] == pytest.approx(108.36, rel=0.01)
    assert models["pe_g"] == pytest.approx(44.85, rel=0.01)
    # guide §6.2: speculative return 14.2% - most of the return needs a re-rating
    assert r.valuation["speculative_return"] == pytest.approx(0.142, abs=0.002)
    assert r.valuation["spread"] > 4  # the five models "disagree violently"


def test_compounder_is_a_true_wealth_creator():
    r = analyse(compounder())
    assert r.matrix["quadrant"] == "True wealth creator"
    assert r.matrix["profitability"] == "Great company"
    assert not r.failed_gates, r.failed_gates
    assert r.score_pct >= 70
    assert r.verdict in ("buy", "watch")
    v = r.valuation
    assert v["iv"] > 0 and len(v["entry"]) == 3
    assert v["entry"][0] > v["entry"][1] > v["entry"][2]


def test_price_decides_buy_versus_watch():
    cheap = analyse(compounder(price_mult=0.2))
    dear = analyse(compounder(price_mult=5.0))
    assert cheap.verdict == "buy", cheap.reasons
    assert dear.verdict == "watch"
    assert [r.verdict for r in rank([dear, analyse(andhra()), cheap])] == ["buy", "watch", "reject"]


def test_financials_are_skipped():
    c = compounder()
    c.is_financial = True
    assert analyse(c).verdict == "skip"


def test_promoter_selling_is_a_hard_veto():
    c = compounder(price_mult=0.2)
    c.promoter_holding = [60, 60, 60, 60, 60, 60, 58, 55, 52, 49]
    r = analyse(c)
    assert r.verdict == "reject"
    assert any("Promoter stake" in g["k"] for g in r.failed_gates)


def test_discount_rate_lowers_value():
    lo = analyse(compounder(), Settings(disc=0.12)).valuation["iv"]
    hi = analyse(compounder(), Settings(disc=0.15)).valuation["iv"]
    assert hi < lo


# ---------------------------------------------------------------- web parser

def _table(header, rows):
    th = "".join("<th>%s</th>" % h for h in [""] + header)
    trs = "".join("<tr><td class='text'>%s&nbsp;<span>+</span></td>%s</tr>" % (
        k, "".join("<td>%s</td>" % v for v in vals)) for k, vals in rows.items())
    return "<table class='data-table'><thead><tr>%s</tr></thead><tbody>%s</tbody></table>" % (th, trs)


def fake_page(c: Company) -> str:
    f = lambda xs: ["{:,.2f}".format(x) for x in xs]  # noqa: E731
    pl = {"Sales": f(c.sales) + ["9,999"], "Expenses": f([s - o for s, o in zip(c.sales, c.op_profit)]) + ["1"],
          "Operating Profit": f(c.op_profit) + ["1"], "OPM %": ["20%"] * 11, "Other Income": f(c.other_income) + ["1"],
          "Interest": f(c.interest) + ["1"], "Depreciation": f(c.dep) + ["1"], "Profit before tax": f(c.pbt) + ["1"],
          "Tax %": ["%d%%" % round(100 * t / p) for t, p in zip(c.tax, c.pbt)] + ["25%"],
          "Net Profit": f(c.pat) + ["1"], "EPS in Rs": f([p / 10 for p in c.pat]) + ["1"],
          "Dividend Payout %": ["%d%%" % round(100 * d / p) for d, p in zip(c.div_amt, c.pat)] + [""]}
    bs = {"Equity Capital": f(c.equity_capital), "Reserves": f(c.reserves), "Borrowings": f(c.borrowings),
          "Other Liabilities": f(c.other_liab), "Total Liabilities": f(c.total_assets),
          "Fixed Assets": f(c.net_block), "CWIP": f(c.cwip), "Investments": f(c.investments),
          "Other Assets": f([1] * 10), "Total Assets": f(c.total_assets)}
    cf = {"Cash from Operating Activity": f(c.cfo), "Net Cash Flow": f([1] * 10)}
    ra = {"Debtor Days": ["36"] * 10, "Inventory Days": ["40"] * 10, "ROCE %": ["30%"] * 10}
    shp = {"Promoters": ["%.2f%%" % p for p in c.promoter_holding]}
    return """<html><body><div id="company-info" data-company-id="1234" data-warehouse-id="99"></div>
<h1 class="margin-0">%s</h1>
<ul id="top-ratios">
<li><span class="name">Market Cap</span><span class="nowrap value">₹ <span class="number">%s</span> Cr.</span></li>
<li><span class="name">Current Price</span><span class="nowrap value">₹ <span class="number">%s</span></span></li>
<li><span class="name">Stock P/E</span><span class="nowrap value"><span class="number">%s</span></span></li>
<li><span class="name">Face Value</span><span class="nowrap value">₹ <span class="number">1.00</span></span></li>
</ul>
<section id="quarters">%s</section>
<section id="profit-loss">%s</section>
<section id="balance-sheet">%s</section>
<section id="cash-flow">%s</section>
<section id="ratios">%s</section>
<section id="shareholding"><div><table id="yearly-shp" class="data-table"><thead><tr><th></th>%s</tr></thead><tbody>
<tr><td><button>Promoters&nbsp;+</button></td>%s</tr></tbody></table></div></section>
</body></html>""" % (
        c.name, "{:,.0f}".format(c.mcap), "{:,.2f}".format(c.price), "{:.1f}".format(c.price / (c.pat[-1] / 10)),
        _table(["Jun 2025", "Sep 2025"], {"Sales": ["1", "2"]}),
        _table(c.years + ["TTM"], pl), _table(c.years, bs), _table(c.years, cf), _table(c.years, ra),
        "".join("<th>%s</th>" % y for y in c.years), "".join("<td>%s</td>" % v for v in shp["Promoters"]))


def test_parse_screener_page_round_trip():
    src = compounder()
    c = parse_company_page(fake_page(src), "COMPOUND")
    assert c.name == "Compounder Ltd"
    assert c.years == YEARS  # TTM column dropped, quarterly table ignored
    assert c.mcap == pytest.approx(src.mcap, rel=1e-3)
    assert c.price == pytest.approx(src.price, abs=0.01)
    assert c.sales == pytest.approx(src.sales, abs=0.01)
    assert c.pat == pytest.approx(src.pat, abs=0.01)
    assert c.net_block == pytest.approx(src.net_block, abs=0.01)
    assert c.cfo == pytest.approx(src.cfo, abs=0.01)
    assert c.promoter_holding == pytest.approx(src.promoter_holding)
    assert c.debtor_days == [36.0] * 10
    assert not c.is_financial
    assert getattr(c, "_company_id") == "1234"
    r = analyse(c)
    assert r.matrix["quadrant"] == "True wealth creator"
    assert r.verdict in ("buy", "watch")


def test_parse_detects_banks():
    page = fake_page(compounder()).replace("Operating Profit", "Financing Profit")
    assert parse_company_page(page).is_financial


def test_json_enrichment():
    c = parse_company_page(fake_page(compounder()))
    apply_price_history(c, '{"datasets":[{"metric":"Price","values":[%s]}]}' % ",".join(
        '["%d-03-27","%d"]' % (y, y - 2000) for y in range(2017, 2027)))
    assert c.year_price == [float(y - 2000) for y in range(2017, 2027)]
    apply_other_assets(c, '{"Trade receivables":{%s},"Inventories":{},"Cash Equivalents":{"Mar 2026":"12.5"}}' % (
        ",".join('"%s":"%d"' % (y, i) for i, y in enumerate(YEARS))))
    assert c.receivables == [float(i) for i in range(10)]
    assert c.cash[-1] == 12.5


# ---------------------------------------------------------------- Excel export reader

def _xlsx(path, rows):
    """Write a minimal workbook with a 'Data Sheet' tab using inline strings."""
    def cell(ref, v):
        if isinstance(v, str):
            return '<c r="%s" t="inlineStr"><is><t>%s</t></is></c>' % (ref, v.replace("&", "&amp;"))
        return '<c r="%s"><v>%s</v></c>' % (ref, v)
    xml_rows = []
    for rn, vals in enumerate(rows, 1):
        cells = "".join(cell("%s%d" % (chr(65 + i), rn), v) for i, v in enumerate(vals) if v is not None)
        xml_rows.append('<row r="%d">%s</row>' % (rn, cells))
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    rns = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("xl/workbook.xml", '<workbook %s %s><sheets><sheet name="Data Sheet" sheetId="1" r:id="rId1"/>'
                   '</sheets></workbook>' % (ns, rns))
        z.writestr("xl/_rels/workbook.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/'
                   '2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr("xl/worksheets/sheet1.xml", '<worksheet %s><sheetData>%s</sheetData></worksheet>' % (
            ns, "".join(xml_rows)))


def test_read_screener_excel_export(tmp_path):
    from multibagger.screener_excel import read_export
    d = ANDHRA
    dates = [42825 + 365 * i for i in range(10)]  # 31-Mar-2017 onwards (Excel serials)
    costs = ["Raw Material Cost", "Change in Inventory", "Power and Fuel", "Other Mfr. Exp", "Employee Cost",
             "Selling and admin", "Other Expenses"]
    rows = [["COMPANY NAME", "THE ANDHRA SUGARS LTD"], ["META"], ["Face Value", 2], ["Current Price", 88.15],
            ["Market Capitalization", 1194.74], ["PROFIT & LOSS"], ["Report Date"] + dates, ["Sales"] + d["sales"]]
    rows += [[lb] + d["costs"][i] for i, lb in enumerate(costs)]
    rows += [["Other Income"] + d["other_income"], ["Depreciation"] + d["dep"], ["Interest"] + d["interest"],
             ["Profit before tax"] + d["pbt"], ["Tax"] + d["tax"], ["Net profit"] + d["pat"],
             ["Dividend Amount"] + d["div_amt"], ["BALANCE SHEET"], ["Report Date"] + dates,
             ["Equity Share Capital"] + d["equity_capital"], ["Reserves"] + d["reserves"],
             ["Borrowings"] + d["borrowings"], ["Other Liabilities"] + d["other_liab"], ["Total"] + d["total_assets"],
             ["Net Block"] + d["net_block"], ["Capital Work in Progress"] + d["cwip"],
             ["Investments"] + d["investments"], ["Receivables"] + d["receivables"], ["Inventory"] + d["inventory"],
             ["Cash & Bank"] + d["cash"], ["No. of Equity Shares"] + d["shares_raw"], ["Face value"] + d["fv"],
             ["CASH FLOW:"], ["Report Date"] + dates, ["Cash from Operating Activity"] + d["cfo"],
             ["PRICE:"] + d["year_price"]]
    p = tmp_path / "andhra.xlsx"
    _xlsx(str(p), rows)
    c = read_export(str(p))
    assert c.name == "THE ANDHRA SUGARS LTD"
    assert c.years[0] == "Mar 2017" and c.years[-1] == "Mar 2026"
    assert c.op_profit == pytest.approx(andhra().op_profit)
    ref, got = analyse(andhra()), analyse(c)
    assert got.metrics["roe10"] == pytest.approx(ref.metrics["roe10"])
    assert got.verdict == "reject" and got.matrix["quadrant"] == "Wealth destroyer"

    # and end-to-end through the CLI
    import multibagger_cli
    out = tmp_path / "rep"
    assert multibagger_cli.main(["--excel", str(p), "-o", str(out), "--json"]) == 0
    assert os.path.exists(str(out) + ".html") and os.path.exists(str(out) + ".csv")
    assert "REJECT" in open(str(out) + ".csv", encoding="utf-8-sig").read()


def test_symbols_file_reads_nse_csv(tmp_path):
    import multibagger_cli
    p = tmp_path / "EQUITY_L.csv"
    p.write_text("SYMBOL,NAME OF COMPANY, SERIES\nTCS,Tata Consultancy,EQ\nINFY,Infosys,EQ\n")
    assert multibagger_cli.read_symbols(str(p)) == ["TCS", "INFY"]
    q = tmp_path / "list.txt"
    q.write_text("# comment\nTCS\n\nINFY  # note\n")
    assert multibagger_cli.read_symbols(str(q)) == ["TCS", "INFY"]
