"""The analysis engine: the Value Investing Process, stage by stage.

Every number below follows the "Value Investing Process — Indian Equities"
guide and the Screener.in workbook it was built from:

* Stage 2  - the 11-point 2-minute test
* Stage 3  - financial health, cash flow, income statement, profitability
             (DuPont ROE, ROCE, FCF/sales, the workbook's SSGR formula)
* Stage 5  - the profitability matrix and the Moat x Growth matrix
             (moat judged from the numbers: sustained ROCE, cash, stable margins)
* Stage 6  - five cheapness checks, five valuation models averaged into one
             intrinsic value, the entry and exit ladders
* Scorecard - the rows of the one-page scorecard that can be computed

What a computer cannot do - circle of competence, reading annual reports, the
forensic and management judgements, the behavioural gate - is listed in each
result under ``manual_checks`` so it is never silently skipped.
"""

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .model import Company, Series


@dataclass
class Settings:
    disc: float = 0.12  # discount rate (guide §6.5: 14-15% for no moat, cyclicals, < ₹2,000 cr)
    bond: float = 0.0668  # 10-year G-sec yield
    exit_pe: float = 20.0  # exit P/E for the Total Returns model
    min_cap: float = 500.0  # ₹ crore, the minimum quality hurdle
    sweet_spot_cap: float = 5000.0  # ₹ crore, under-covered hunting ground (guide: operating philosophy)
    min_capital_gain: float = 0.15  # workbook's floor for projected capital gain
    min_score_pct: float = 70.0  # scorecard threshold to reach valuation
    agree_spread: float = 1.6  # max/min of the five models; above this they "disagree"


# ---------------------------------------------------------------- helpers

def _ok(v) -> bool:
    return v is not None and isinstance(v, (int, float)) and math.isfinite(v)


def clean(a: Series) -> List[float]:
    return [v for v in a if _ok(v)]


def mean(a: Series) -> Optional[float]:
    c = clean(a)
    return sum(c) / len(c) if c else None


def median(a: Series) -> Optional[float]:
    c = sorted(clean(a))
    if not c:
        return None
    m = len(c) // 2
    return c[m] if len(c) % 2 else (c[m - 1] + c[m]) / 2


def stdev(a: Series) -> Optional[float]:
    c = clean(a)
    if len(c) < 2:
        return None
    m = sum(c) / len(c)
    return math.sqrt(sum((v - m) ** 2 for v in c) / (len(c) - 1))


def last(a: Series) -> Optional[float]:
    for v in reversed(a):
        if _ok(v):
            return v
    return None


def total(a: Series) -> float:
    return sum(clean(a))


def div(a, b) -> Optional[float]:
    if _ok(a) and _ok(b) and b != 0:
        return a / b
    return None


def ratio(a: Series, b: Series) -> Series:
    return [div(x, y) for x, y in zip(a, b)]


def cagr(series: Series, periods: int) -> Optional[float]:
    n = len(series)
    if periods <= 0 or periods > n - 1:
        return None
    end, start = series[n - 1], series[n - 1 - periods]
    if not (_ok(end) and _ok(start)) or start <= 0 or end <= 0:
        return None
    return (end / start) ** (1 / periods) - 1


def _add(a, b):
    return None if a is None or b is None else a + b


# ---------------------------------------------------------------- result

@dataclass
class Result:
    company: Company
    metrics: Dict[str, object] = field(default_factory=dict)
    two_minute: List[dict] = field(default_factory=list)
    gates: List[dict] = field(default_factory=list)
    score: List[dict] = field(default_factory=list)
    relative: List[dict] = field(default_factory=list)
    valuation: Dict[str, object] = field(default_factory=dict)
    matrix: Dict[str, object] = field(default_factory=dict)
    red_flags: List[str] = field(default_factory=list)
    manual_checks: List[str] = field(default_factory=list)
    verdict: str = "reject"  # "buy" | "watch" | "reject" | "skip"
    reasons: List[str] = field(default_factory=list)
    error: Optional[str] = None

    @property
    def name(self) -> str:
        return self.company.name

    @property
    def score_got(self) -> float:
        return sum(s["got"] for s in self.score)

    @property
    def score_max(self) -> float:
        return sum(s["max"] for s in self.score)

    @property
    def score_pct(self) -> float:
        return 100.0 * self.score_got / self.score_max if self.score_max else 0.0

    @property
    def failed_gates(self) -> List[dict]:
        return [g for g in self.gates if not g["pass"]]


MANUAL_CHECKS = [
    "Stage 0: is the business inside your circle of competence?",
    "Stage 2 check 7: do you understand what the debt was raised for and how it is repaid?",
    "Stage 4: forensic checklist and the 18-point Satyam test (annual report, auditor, related parties)",
    "Stage 4: fragility test - raw material doubles, top customer leaves, +300bps refinancing",
    "Stage 5: name the moat, judge its trend and runway; industry structure (CAP matrix)",
    "Stage 5.5: management - promise vs delivery, candour, capital allocation, succession",
    "Promoter pledge, auditor changes, qualified opinions, SEBI/ASM surveillance",
    "Stage 7: write the 5-sentence thesis, run the behavioural gate, wait 48 hours",
]


# ---------------------------------------------------------------- analysis

def analyse(c: Company, opt: Optional[Settings] = None) -> Result:
    opt = opt or Settings()
    r = Result(company=c, manual_checks=list(MANUAL_CHECKS))
    if c.is_financial:
        r.verdict = "skip"
        r.reasons = ["Bank / NBFC / insurer - this process uses a different sheet for lenders (guide §3.1)"]
        return r
    if len(c.years) < 3 or not clean(c.series("sales")) or not clean(c.series("pat")):
        r.verdict = "skip"
        r.reasons = ["Not enough history to analyse"]
        return r

    S = c.series
    years = c.years
    n = len(years)
    sales, pat, pbt, interest, dep = S("sales"), S("pat"), S("pbt"), S("interest"), S("dep")
    equity = [_add(a, b) for a, b in zip(S("equity_capital"), S("reserves"))]
    borrow = [v if _ok(v) else 0.0 for v in S("borrowings")]
    cap_emp = [_add(e, b) for e, b in zip(equity, borrow)]
    total_assets = S("total_assets")
    net_block, cwip = S("net_block"), S("cwip")
    cfo = S("cfo")

    # --- Stage 3.4 profitability: DuPont ROE and ROCE
    net_margin = ratio(pat, sales)
    asset_turn = ratio(sales, total_assets)
    fin_lev = ratio(total_assets, equity)
    roe = ratio(pat, equity)
    ebit = [_add(p, i if _ok(i) else 0.0) if _ok(p) else None for p, i in zip(pbt, interest)]
    roce = ratio(ebit, cap_emp)
    opm = ratio(S("op_profit"), sales)

    # --- Stage 3.1 / 3.2 health and cash flow
    icr = ratio(ebit, interest)
    de = ratio(borrow, equity)
    capex: Series = [None]
    for i in range(1, n):
        a = _add(net_block[i], cwip[i] if _ok(cwip[i]) else 0.0)
        b = _add(net_block[i - 1], cwip[i - 1] if _ok(cwip[i - 1]) else 0.0)
        capex.append(a - b + (dep[i] if _ok(dep[i]) else 0.0) if _ok(a) and _ok(b) else None)
    fcf = [v - k if _ok(v) and _ok(k) else None for v, k in zip(cfo, capex)]
    fcf_sales = ratio(fcf, sales)
    cfo_pat = ratio(cfo, pat)
    div_amt = S("div_amt")
    dpr = [(d / p if _ok(d) else 0.0) if _ok(p) and p > 0 else None for d, p in zip(div_amt, pat)]

    # --- SSGR = NFAT x NPM x (1 - DPR) - Dep%NFA, on rolling 3-year averages
    nfat: Series = [None] + [
        div(sales[i], (net_block[i] + net_block[i - 1]) / 2)
        if _ok(net_block[i]) and _ok(net_block[i - 1]) else None
        for i in range(1, n)
    ]
    dep_nfa = ratio(dep, net_block)
    ssgr: Series = []
    for i in range(n):
        if i < 3:
            ssgr.append(None)
            continue
        w = lambda s: mean(s[i - 2:i + 1])  # noqa: E731
        a, b, d, e = w(nfat), w(net_margin), w(dpr), w(dep_nfa)
        ssgr.append(a * b * (1 - d) - e if None not in (a, b, d, e) else None)

    # --- working capital days (raw lines if present, else Screener's ratios)
    recv_days = [div(rv, s) * 365 if div(rv, s) is not None else None for rv, s in zip(S("receivables"), sales)]
    if not clean(recv_days):
        recv_days = S("debtor_days")
    inv_days = [div(iv, s) * 365 if div(iv, s) is not None else None for iv, s in zip(S("inventory"), sales)]
    if not clean(inv_days):
        inv_days = S("inventory_days")

    # --- per-share history (split-adjusted price / today's share count)
    shares = c.shares or None
    eps_hist = [div(p, shares) for p in pat]
    year_price = S("year_price")
    pe_hist = [div(p, e) if _ok(e) and e > 0 else None for p, e in zip(year_price, eps_hist)]
    ps_hist = [div(p * shares, s) if _ok(p) and shares else None for p, s in zip(year_price, sales)]
    pb_hist = [div(p * shares, e) if _ok(p) and shares else None for p, e in zip(year_price, equity)]

    # --- dilution, ignoring split/bonus steps
    dilution = _dilution(S("share_count")) if clean(S("share_count")) else _dilution(
        [div(p, e) if _ok(e) and e > 0 else None for p, e in zip(pat, S("eps"))])

    m = r.metrics
    span = min(10, n - 1)
    m.update(
        years=f"{years[0]}-{years[-1]}",
        mcap=c.mcap,
        price=c.price,
        roe10=mean(roe[-10:]),
        roe5=mean(roe[-5:]),
        roce_med=median(roce[-10:]),
        roce_min=min(clean(roce[-10:]), default=None),
        fcf_sales5=mean(fcf_sales[-5:]),
        cfo_pat_avg=div(total(cfo[-10:]), total(pat[-10:])) if total(pat[-10:]) > 0 else None,
        cum_cfo=total(cfo[-10:]),
        cum_fcf=total(fcf[-10:]),
        cum_pat=total(pat[-10:]),
        de=last(de),
        icr=last(icr),
        fin_lev=last(fin_lev),
        ta_tl=div(last(total_assets), _add(last(borrow), last(S("other_liab")))),
        ssgr=last(ssgr),
        opm_sd=stdev([v * 100 if _ok(v) else None for v in opm[-10:]]),
        opm_avg=mean(opm[-10:]),
        sales_cagr={k: cagr(sales, p) for k, p in (("3y", 3), ("5y", 5), ("7y", 7), ("10y", span))},
        pat_cagr={k: cagr(pat, p) for k, p in (("3y", 3), ("5y", 5), ("7y", 7), ("10y", span))},
        other_inc_share=div(last(S("other_income")), last(pbt)),
        tax_rate=div(last(S("tax")), last(pbt)),
        recv_drift=_drift(recv_days),
        inv_drift=_drift(inv_days),
        debt_fcf=div(last(borrow), mean(fcf[-3:])) if (mean(fcf[-3:]) or 0) > 0 else None,
        cfo_capex=mean(ratio(cfo, capex)),
        avg_net_margin=mean(net_margin[-10:]),
        dilution=dilution,
        pe5=mean(pe_hist[-5:]),
        pe10_med=median(pe_hist[-10:]),
        ps5=mean(ps_hist[-5:]),
        pb5=mean(pb_hist[-5:]),
        promoter=last(S("promoter_holding")),
        series=dict(roe=roe, roce=roce, fcf=fcf, ssgr=ssgr, opm=opm, capex=capex, dpr=dpr),
    )
    m["pe_now"] = c.pe_now if _ok(c.pe_now) and c.pe_now > 0 else (
        div(c.price, last(eps_hist)) if (last(eps_hist) or 0) > 0 else None)
    m["ps_now"] = div(c.mcap, last(sales))
    m["pb_now"] = div(c.mcap, last(equity))
    debt_free = _ok(m["de"]) and m["de"] < 0.05
    m["debt_free"] = debt_free
    m["icr_ok"] = debt_free or (_ok(m["icr"]) and m["icr"] > 10)
    m["sweet_spot"] = c.mcap < opt.sweet_spot_cap
    m["debt_grade"] = _debt_grade(m["de"], m["icr"], m["fin_lev"])

    _valuation(r, c, opt, fcf, equity, borrow, dpr, eps_hist)
    _relative(r, c, opt)
    _two_minute(r, c, opt)
    _matrices(r)
    _red_flags(r, c, S)
    _gates(r, c, opt)
    _scorecard(r)
    _verdict(r, c, opt)
    return r


def _drift(days: Series) -> Optional[float]:
    avg5, now = mean(days[-5:]), last(days)
    return now / avg5 - 1 if _ok(avg5) and avg5 > 0 and _ok(now) else None


def _dilution(counts: Series) -> Optional[float]:
    """Compound annual growth in share count, skipping split/bonus jumps.

    A step of 1.9x or more that sits near a whole multiple (2x, 5x, 10x...) is
    treated as a corporate action, not dilution - the guide's Andhra Sugars
    example (2.71 cr -> 13.55 cr shares) is a face-value split.
    """
    c = clean(counts)
    if len(c) < 2:
        return None
    growth, steps = 1.0, 0
    for a, b in zip(c, c[1:]):
        if a <= 0:
            continue
        k = b / a
        if k >= 1.9 and abs(k - round(k)) / round(k) < 0.05:
            k = 1.0
        growth *= k
        steps += 1
    return growth ** (1 / steps) - 1 if steps else None


def _debt_grade(de, icr, lev) -> str:
    if not _ok(de):
        return "UNKNOWN"
    if de < 0.05:
        return "DEBT-FREE"
    if de < 0.25 and (icr or 0) > 10:
        return "LOW"
    if de < 0.5:
        return "MODERATELY-LOW"
    if de < 1:
        return "MODERATE"
    if de < 2 and (lev or 0) < 6:
        return "MODERATELY-HIGH"
    return "HIGH DEBT"


# ---------------------------------------------------------------- Stage 6 valuation

def _valuation(r: Result, c: Company, opt: Settings, fcf, equity, borrow, dpr, eps_hist):
    m = r.metrics
    disc = opt.disc
    g_terminal = 0.15 * 0.25  # terminal ROE x terminal retention, as in the template
    avg_fcf3 = mean(fcf[-3:])
    excess_cash = (last(c.series("investments")) or 0) + (last(c.series("cash")) or 0)
    sh = c.shares
    v = r.valuation
    v.update(ok=bool(_ok(avg_fcf3) and avg_fcf3 > 0 and sh), avg_fcf3=avg_fcf3, excess_cash=excess_cash)
    if not v["ok"]:
        v["why"] = "Average free cash flow over the last three years is not positive"
        return

    def dhandho(g1, g2, g3, mult):
        f, pv = avg_fcf3, excess_cash
        for t in range(1, 11):
            f *= 1 + (g1 if t <= 3 else g2 if t <= 6 else g3)
            pv += f / (1 + disc) ** t
        return (pv + f * mult / (1 + disc) ** 10) / sh

    v["dhandho_worst"] = dhandho(0.15, 0.10, 0.05, 10)
    v["dhandho_best"] = dhandho(0.15, 0.12, 0.10, 15)

    # Model 3: DCF, fundamental growth fading to terminal over years 6-10
    roe_base = max(0.0, m["roe10"] or 0.0)
    dpr_now = min(max(last(dpr) or 0.0, 0.0), 0.95)
    g_f = max(0.0, roe_base * (1 - dpr_now))
    v["g_fundamental"] = g_f
    # SSGR is the ceiling on a believable growth assumption (guide §3.4): the
    # model runs as the workbook does, but says when it assumes more than SSGR.
    v["growth_above_ssgr"] = _ok(m["ssgr"]) and g_f > max(m["ssgr"], 0.0) + 0.01

    def growth_at(t):
        return g_f if t <= 5 else g_f - (g_f - g_terminal) * (t - 5) / 5

    f, pv = avg_fcf3, 0.0
    for t in range(1, 11):
        f *= 1 + growth_at(t)
        pv += f / (1 + disc) ** t
    tv = f * (1 + g_terminal) / (disc - g_terminal)
    v["dcf"] = (pv + tv / (1 + disc) ** 10) / sh
    g_implied = (f / avg_fcf3) ** (1 / 10) - 1
    v["g_implied"] = g_implied

    # Model 4: Total Returns on normalised earnings (latest sales x 10-yr avg net margin)
    np_norm = (last(c.series("sales")) * m["avg_net_margin"]) if _ok(m["avg_net_margin"]) else None
    if _ok(np_norm) and np_norm > 0:
        np10 = np_norm * (1 + g_implied) ** 10
        cap10 = np10 * opt.exit_pe
        v["capital_gain"] = (cap10 / c.mcap) ** (1 / 10) - 1 if c.mcap > 0 else None
        e, dpv = np_norm / sh, 0.0
        for t in range(1, 11):
            d = dpr_now if t <= 5 else dpr_now + (0.25 - dpr_now) * (t - 5) / 5
            e *= 1 + growth_at(t)
            dpv += e * d / (1 + disc) ** t
        v["total_returns"] = (cap10 / (1 + disc) ** 10) / sh + dpv
        div_yield = div(last(c.series("div_amt")) or 0.0, c.mcap) or 0.0
        v["investment_return"] = g_implied + div_yield
        if _ok(v["capital_gain"]):
            v["speculative_return"] = v["capital_gain"] - g_implied

    # Model 5: Peter Lynch P/E = G price
    eps_now = last(eps_hist)
    v["pe_g"] = eps_now * g_implied * 100 if _ok(eps_now) and eps_now > 0 else None

    parts = {k: v.get(k) for k in ("dhandho_worst", "dhandho_best", "dcf", "total_returns", "pe_g")}
    good = [x for x in parts.values() if _ok(x) and x > 0]
    v["models"] = parts
    if not good:
        v["ok"] = False
        v["why"] = "No valuation model produced a positive value"
        return
    iv = sum(good) / len(good)
    spread = max(good) / min(good)
    v["iv"], v["spread"] = iv, spread
    v["agree"] = spread <= opt.agree_spread
    # Guide §7.4: when the five disagree, anchor on the lowest two, not the average
    anchor = iv if v["agree"] or len(good) < 2 else sum(sorted(good)[:2]) / 2
    v["anchor"] = anchor
    v["entry"] = [anchor * 0.90, anchor * 0.80, anchor * 0.75]
    hi = max(good)
    v["exit"] = [iv * 1.25, hi * 1.35, hi * 1.50]
    v["upside"] = anchor / c.price - 1 if c.price > 0 else None
    if _ok(eps_now) and eps_now > 0:
        v["entry_pe"] = [p / eps_now for p in v["entry"]]


def _relative(r: Result, c: Company, opt: Settings):
    m, v = r.metrics, r.valuation
    ey = 1 / m["pe_now"] if _ok(m["pe_now"]) and m["pe_now"] > 0 else None
    ev = c.mcap + (last(c.series("borrowings")) or 0) - (last(c.series("investments")) or 0) - (
        last(c.series("cash")) or 0)
    cr = div(v.get("avg_fcf3"), ev) if ev > 0 else None
    rows = [
        ("Earnings yield vs G-sec", ey, opt.bond, ey is not None and ey >= opt.bond),
        ("Cash return vs G-sec", cr, opt.bond, cr is not None and cr >= opt.bond),
        ("P/E vs 5-yr average", m["pe_now"], m["pe5"], _ok(m["pe_now"]) and _ok(m["pe5"]) and m["pe_now"] <= m["pe5"]),
        ("P/S vs 5-yr average", m["ps_now"], m["ps5"], _ok(m["ps_now"]) and _ok(m["ps5"]) and m["ps_now"] <= m["ps5"]),
        ("P/B vs 5-yr average", m["pb_now"], m["pb5"], _ok(m["pb_now"]) and _ok(m["pb5"]) and m["pb_now"] <= m["pb5"]),
    ]
    r.relative = [dict(check=k, value=a, benchmark=b, cheap=bool(p)) for k, a, b, p in rows]
    m["relative_cheap"] = sum(1 for x in r.relative if x["cheap"])
    m["earnings_yield"], m["cash_return"] = ey, cr


# ---------------------------------------------------------------- Stage 2

def _two_minute(r: Result, c: Company, opt: Settings):
    m = r.metrics
    pc = m["pat_cagr"]
    erratic = sum(1 for k in ("3y", "5y", "7y", "10y") if _ok(pc[k]) and pc[k] > 0)
    r.two_minute = [
        dict(n=1, q="Passes the minimum quality hurdle (mcap ≥ ₹%d cr)?" % opt.min_cap, pass_=c.mcap >= opt.min_cap),
        dict(n=2, q="Has the firm ever made a net profit?", pass_=m["cum_pat"] > 0),
        dict(n=3, q="Consistent cash flow from operations?", pass_=m["cum_cfo"] > 0),
        dict(n=4, q="10-year average ROE ≥ 15%?", pass_=_ok(m["roe10"]) and m["roe10"] >= 0.15),
        dict(n=5, q="Earnings growth consistent (PAT CAGR positive at 3/5/7/10y)?", pass_=erratic == 4),
        dict(n=6, q="Clean balance sheet (%s)?" % m["debt_grade"], pass_=_ok(m["de"]) and m["de"] < 1),
        dict(n=7, q="Do you understand the debt?", pass_=True if m["debt_free"] else None),
        dict(n=8, q="Generates free cash flow?", pass_=m["cum_fcf"] > 0),
        dict(n=9, q="P/E below its 5-year average?",
             pass_=_ok(m["pe_now"]) and _ok(m["pe5"]) and m["pe_now"] <= m["pe5"]),
        dict(n=10, q="Little 'other' income (< 10% of PBT)?",
             pass_=_ok(m["other_inc_share"]) and m["other_inc_share"] < 0.10),
        dict(n=11, q="Share count growth ≤ 2% a year?", pass_=m["dilution"] is None or m["dilution"] <= 0.02),
    ]
    for t in r.two_minute:
        t["pass"] = t.pop("pass_")
    # the workbook's BUY / HOLD / SELL / AVOID verdict
    fails = [t["n"] for t in r.two_minute if t["pass"] is False]
    core = {1, 2, 3, 4, 8}
    if core & set(fails):
        m["two_minute_verdict"] = "AVOID"
    elif not fails:
        m["two_minute_verdict"] = "BUY"
    elif fails == [9] or set(fails) <= {9, 10}:
        m["two_minute_verdict"] = "HOLD"
    else:
        m["two_minute_verdict"] = "SELL" if len(fails) >= 3 else "HOLD"


# ---------------------------------------------------------------- Stage 5 matrices

def _matrices(r: Result):
    m = r.metrics
    roe_ok = (m["roe5"] or 0) >= 0.15
    fcf_ok = (m["fcf_sales5"] or 0) >= 0.05
    prof = ["Worst company", "Good ROE, weak cash", "Strong cash, weak ROE", "Great company"][
        (1 if roe_ok else 0) + (2 if fcf_ok else 0)]
    pat10 = m["pat_cagr"]["10y"]
    growth_high = _ok(pat10) and pat10 >= 0.10
    # "A moat is visible in the numbers before you can name it": ROCE above 20%
    # for the decade, cash conversion, and margins that did not swing.
    moat = ((m["roce_med"] or 0) >= 0.20 and (m["roce_min"] or 0) >= 0.15 and fcf_ok
            and _ok(m["opm_sd"]) and m["opm_sd"] < 6)
    if growth_high and moat:
        q, sub = "True wealth creator", "Enduring multibagger"
    elif growth_high:
        q, sub = "Growth trap", "Transitory multibagger"
    elif moat:
        q, sub = "Quality trap", "Underperformer"
    else:
        q, sub = "Wealth destroyer", "Permanent loss of capital"
    r.matrix = dict(profitability=prof, roe_ok=roe_ok, fcf_ok=fcf_ok, growth_high=growth_high,
                    moat_in_numbers=moat, quadrant=q, meaning=sub)


def _red_flags(r: Result, c: Company, S):
    """The forensic signals Stage 4 lists that can be read from the numbers."""
    m, f = r.metrics, r.red_flags
    pat, cfo = S("pat"), S("cfo")
    if _ok(m["cfo_pat_avg"]) and m["cfo_pat_avg"] < 0.8:
        f.append("Profit not turning into cash: 10-yr CFO/PAT %.2f" % m["cfo_pat_avg"])
    recv, sales = S("receivables"), S("sales")
    if len(clean(recv[-4:])) == 4 and len(clean(sales[-4:])) == 4:
        rg = [recv[i] / recv[i - 1] - sales[i] / sales[i - 1] for i in range(-3, 0) if recv[i - 1] and sales[i - 1]]
        if len(rg) == 3 and all(x > 0.05 for x in rg):
            f.append("Receivables growing faster than sales three years running")
    dd = S("debtor_days")
    if len(clean(dd[-4:])) == 4 and all(dd[i] > dd[i - 1] for i in range(-3, 0)):
        f.append("Debtor days rising three years running")
    if _ok(m["tax_rate"]) and (m["tax_rate"] < 0.15 or m["tax_rate"] > 0.40) and (last(S("pbt")) or 0) > 0:
        f.append("Tax rate %.0f%% far from the ~25%% statutory rate" % (m["tax_rate"] * 100))
    cw, nb = S("cwip"), S("net_block")
    if len(clean(cw[-4:])) == 4 and all((cw[i] or 0) > 0.25 * (nb[i] or 1e9) for i in range(-4, 0)):
        f.append("Capital work-in-progress above 25% of net block for 4 years")
    if m["dilution"] is not None and m["dilution"] > 0.02:
        f.append("Share count growing %.1f%% a year" % (m["dilution"] * 100))
    if _ok(m["other_inc_share"]) and m["other_inc_share"] > 0.25:
        f.append("Other income is %.0f%% of PBT" % (m["other_inc_share"] * 100))
    if len(clean(pat[-4:])) == 4 and len(clean(cfo[-4:])) == 4 and pat[-1] > pat[-4] * 1.3 and cfo[-1] < cfo[-4]:
        f.append("Profit rising while operating cash flow falls")
    ph = S("promoter_holding")
    m["promoter_falling_3y"] = len(clean(ph[-4:])) == 4 and all(ph[i] < ph[i - 1] - 0.01 for i in range(-3, 0))
    if m["promoter_falling_3y"]:
        f.append("Promoter stake falling three years running")
    if _ok(c.pledged_pct) and c.pledged_pct > 10:
        f.append("Promoter pledge %.1f%%" % c.pledged_pct)
    if _ok(m["promoter"]) and m["promoter"] < 40:
        f.append("Promoter holding %.1f%% (< 40%% skin in the game)" % m["promoter"])


# ---------------------------------------------------------------- gates and scorecard

def _gates(r: Result, c: Company, opt: Settings):
    m = r.metrics
    r.gates = [
        dict(k="Market cap ≥ ₹%s cr" % format(int(opt.min_cap), ","), **{"pass": c.mcap >= opt.min_cap}),
        dict(k="≥ 10 years of data (has %d)" % len(c.years), **{"pass": len(c.years) >= 10}),
        dict(k="10-yr average ROE ≥ 15%", **{"pass": _ok(m["roe10"]) and m["roe10"] >= 0.15}),
        dict(k="Cumulative operating cash flow positive", **{"pass": m["cum_cfo"] > 0}),
        dict(k="Cumulative free cash flow positive", **{"pass": m["cum_fcf"] > 0}),
        dict(k="Debt/equity below 1.0", **{"pass": _ok(m["de"]) and m["de"] < 1}),
        dict(k="Interest coverage above 10× (or debt-free)", **{"pass": bool(m["icr_ok"])}),
        dict(k="Net profit growing over the decade", **{"pass": (m["pat_cagr"]["10y"] or -1) > 0}),
        dict(k="Share dilution under 2% a year", **{"pass": m["dilution"] is None or m["dilution"] <= 0.02}),
        dict(k="Not in the wealth-destroyer quadrant", **{"pass": r.matrix["quadrant"] != "Wealth destroyer"}),
        dict(k="Promoter stake not falling three years running", **{"pass": not m["promoter_falling_3y"]}),
        dict(k="Fewer than three forensic red flags", **{"pass": len(r.red_flags) < 3}),
    ]


def _scorecard(r: Result):
    """The computable rows of the guide's one-page scorecard (rows 4-15, 17, 18)."""
    m = r.metrics
    S = r.score

    def add(row, label, mx, got, detail):
        S.append(dict(row=row, label=label, max=mx, got=max(0.0, min(mx, got)), detail=detail))

    debt_fcf_ok = m["debt_free"] or (_ok(m["debt_fcf"]) and m["debt_fcf"] < 3)
    n_ok = sum([_ok(m["de"]) and m["de"] < 1, bool(m["icr_ok"]), bool(debt_fcf_ok)])
    add(4, "D/E < 1, coverage > 10×, debt/FCF < 3", 8, {3: 8, 2: 4}.get(n_ok, 0),
        "%s · ICR %s" % (m["debt_grade"], "n/a" if m["debt_free"] else _f(m["icr"], 1)))
    lev = m["fin_lev"]
    add(5, "Financial leverage < 4", 4, 4 if _ok(lev) and lev < 4 else 2 if _ok(lev) and lev < 6 else 0,
        _f(lev, 2) + "×")
    wc = [abs(x) < 0.2 for x in (m["recv_drift"], m["inv_drift"]) if _ok(x)]
    add(6, "Receivable and inventory days stable", 5, 5 if wc and all(wc) else 2 if any(wc) else 0,
        "debtors %s, inventory %s vs 5-yr" % (_p(m["recv_drift"]), _p(m["inv_drift"])))
    cp = m["cfo_pat_avg"] or 0
    add(7, "10-yr CFO/PAT > 1.0", 10, 10 if cp >= 1 else 5 if cp >= 0.8 else 0, _f(m["cfo_pat_avg"], 2) + "×")
    add(8, "Cumulative FCF positive; CFO covers capex", 7,
        (4 if m["cum_fcf"] > 0 else 0) + (3 if (m["cfo_capex"] or 0) > 1 else 0),
        "Σ FCF ₹%s cr" % _f(m["cum_fcf"], 0))
    fs = m["fcf_sales5"] or 0
    add(9, "FCF / sales > 5%", 8, 8 if fs >= 0.05 else 4 if fs >= 0.03 else 0, _p(m["fcf_sales5"]))
    sc, pc = m["sales_cagr"], m["pat_cagr"]
    add(10, "Sales CAGR positive, not decelerating", 5,
        (3 if (sc["10y"] or 0) > 0.10 else 1.5 if (sc["10y"] or 0) > 0.05 else 0)
        + (2 if _ok(sc["3y"]) and sc["3y"] >= (sc["10y"] or 0) else 0),
        "3y %s · 10y %s" % (_p(sc["3y"]), _p(sc["10y"])))
    add(11, "Profit CAGR positive, not decelerating", 8,
        (5 if (pc["10y"] or 0) > 0.12 else 2.5 if (pc["10y"] or 0) > 0 else 0)
        + (3 if _ok(pc["3y"]) and pc["3y"] >= (pc["10y"] or 0) else 0),
        "3y %s · 10y %s" % (_p(pc["3y"]), _p(pc["10y"])))
    sd = m["opm_sd"]
    add(12, "Operating margin stable", 5, 5 if _ok(sd) and sd < 4 else 2 if _ok(sd) and sd < 7 else 0,
        "σ %s pp" % _f(sd, 1))
    tr, oi = m["tax_rate"], m["other_inc_share"]
    add(13, "Earnings quality: low other income, normal tax", 5,
        (2.5 if _ok(oi) and oi < 0.10 else 0) + (2.5 if _ok(tr) and 0.18 < tr < 0.32 else 0),
        "other income %s of PBT · tax %s" % (_p(oi), _p(tr)))
    ss = m["ssgr"]
    add(14, "SSGR positive and stable", 8, 8 if _ok(ss) and ss > 0.10 else 4 if _ok(ss) and ss > 0 else 0, _p(ss))
    add(15, "Share dilution < 2% a year", 3, 3 if m["dilution"] is None or m["dilution"] <= 0.02 else 0,
        _p(m["dilution"]) + "/yr")
    add(17, "Profitability matrix", 8,
        {"Great company": 8, "Worst company": 0}.get(r.matrix["profitability"], 4), r.matrix["profitability"])
    add(18, "Moat × Growth matrix", 12,
        {"True wealth creator": 12, "Wealth destroyer": 0}.get(r.matrix["quadrant"], 6), r.matrix["quadrant"])


def _verdict(r: Result, c: Company, opt: Settings):
    v, m = r.valuation, r.metrics
    quality_ok = not r.failed_gates and r.score_pct >= opt.min_score_pct
    entry1 = v["entry"][0] if v.get("entry") else None
    price_ok = entry1 is not None and 0 < c.price <= entry1
    cg = v.get("capital_gain")
    spec, inv = v.get("speculative_return"), v.get("investment_return")
    return_ok = _ok(cg) and cg >= opt.min_capital_gain and not (_ok(spec) and _ok(inv) and spec > inv)
    if not quality_ok:
        r.verdict = "reject"
        r.reasons = [g["k"] for g in r.failed_gates][:4] or [
            "Scores %.0f%%, below the %.0f%% bar" % (r.score_pct, opt.min_score_pct)]
        return
    head = "Clears every gate, scores %.0f%% - %s" % (r.score_pct, r.matrix["quadrant"])
    if price_ok and return_ok:
        r.verdict = "buy"
        r.reasons = [head, "Price ₹%s ≤ phase-1 buy ₹%s" % (_f(c.price, 2), _f(entry1, 2))]
    else:
        r.verdict = "watch"
        why = []
        if entry1 is None:
            why.append(v.get("why", "Valuation not computable"))
        elif not price_ok:
            why.append("Price ₹%s above phase-1 buy ₹%s - set an alert" % (_f(c.price, 2), _f(entry1, 2)))
        if not return_ok:
            why.append("Projected capital gain %s, or most of it relies on a re-rating" % _p(cg))
        r.reasons = [head] + why
    if v.get("growth_above_ssgr"):
        r.reasons.append("Valuation assumes %s growth, above SSGR %s - where does the capital come from?" % (
            _p(v["g_fundamental"]), _p(m["ssgr"])))
    if not v.get("agree", True):
        r.reasons.append("Five models disagree (%.1f× spread) - entry anchored on the lowest two" % v["spread"])


# ---------------------------------------------------------------- formatting

def _f(v, d=1) -> str:
    return "—" if not _ok(v) else format(v, ",.%df" % d)


def _p(v, d=1) -> str:
    return "—" if not _ok(v) else "%.*f%%" % (d, v * 100)


fmt_num, fmt_pct = _f, _p


def rank(results: List[Result]) -> List[Result]:
    """Buy first, then watch, then reject, then skipped; best score first within each."""
    order = {"buy": 0, "watch": 1, "reject": 2, "skip": 3}
    return sorted(results, key=lambda r: (order.get(r.verdict, 9), -r.score_pct,
                                          -(r.valuation.get("upside") or -9)))
