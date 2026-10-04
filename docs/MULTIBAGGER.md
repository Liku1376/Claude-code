# Multibagger Screener — Indian equities

A command-line tool that collects company data from
[Screener.in](https://www.screener.in) and runs every stock through the
**Value Investing Process — Indian Equities** guide, then ranks them so the
strongest candidates for an *enduring* multibagger appear first.

It uses only the Python standard library — nothing to install.

```bash
python multibagger_cli.py --symbols PIDILITIND ASTRAL PAGEIND
python multibagger_cli.py --symbols-file examples/watchlist.txt
```

Each run prints a ranked table and writes `multibagger_report.html` (open it
in a browser; click a column to sort, expand a shortlisted stock for its full
workings) and `multibagger_report.csv` (every metric, for Excel).

## Where the companies come from

| Option | What it does |
| --- | --- |
| `--symbols A B C` | Fetch these companies' Screener pages (the code in the URL, e.g. `TCS`). |
| `--symbols-file FILE` | One symbol per line, or a CSV with a `SYMBOL` column — e.g. NSE's full [EQUITY_L.csv](https://archives.nseindia.com/content/equities/EQUITY_L.csv) for the whole market. |
| `--stage1` | Run the guide's **Stage 1 quality screen** on Screener and analyse every result. Needs a free Screener login (below). |
| `--query "..."` | Run your own Screener query instead. Needs a login. |
| `--excel FILES` | Read Screener **Export to Excel** workbooks you've already downloaded (`exports/*.xlsx`). These carry a few extra lines (receivables, inventory, cash, share count) the public page doesn't. |

Screener only returns query results to logged-in users. For `--stage1` or
`--query`, set your credentials in the environment (they're only sent to
screener.in):

```bash
export SCREENER_USERNAME="you@example.com"
export SCREENER_PASSWORD="..."
python multibagger_cli.py --stage1
```

The Stage 1 query (no valuation filter, on purpose):

```
Market Capitalization > 500 AND
Average return on capital employed 10Years > 15 AND
Return on equity > 15 AND
Debt to equity < 0.6 AND
Sales growth 10Years > 10 AND
Profit growth 10Years > 10 AND
OPM 5Year > 12 AND
Promoter holding > 40 AND
Pledged percentage < 5
```

**Be polite to Screener.** Requests are spaced 2 seconds apart (`--delay`)
and cached for a day in `.screener_cache/`, so a re-run doesn't fetch again.
A full-market run of ~2,000 symbols takes a couple of hours; start with a
screen or a watchlist. Respect Screener's terms of use.

## What it checks, stage by stage

| Guide stage | Automated here |
| --- | --- |
| **Stage 2 — 2-minute test** | All 11 checks, with the workbook's BUY / HOLD / SELL / AVOID verdict. Check 7 ("do you understand the debt?") is left to you unless the company is debt-free. |
| **Stage 3 — quantitative gate** | Debt/equity, interest coverage, debt/FCF, financial leverage, total assets/liabilities; CFO/PAT, cumulative CFO and FCF (capex = Δ(net block + CWIP) + depreciation, as the workbook does); receivable and inventory day drift; operating margin stability; other-income share and tax rate; sales and profit CAGR at 3/5/7/10 years; DuPont ROE, ROCE, FCF/sales; **SSGR = NFAT × NPM × (1 − DPR) − Dep%NFA** on rolling 3-year averages. |
| **Stage 4 — forensic signals** | Only the ones visible in the numbers: profit not converting to cash, receivables outgrowing sales, debtor days rising, abnormal tax rate, idle CWIP, dilution, high other income, profit up while CFO falls, promoter stake falling or below 40%. |
| **Stage 5 — matrices** | Profitability matrix (ROE × FCF/sales). Moat × Growth matrix, with the moat judged *from the numbers*, as the guide suggests: median ROCE ≥ 20% and never below 15% over the decade, FCF/sales ≥ 5%, operating-margin σ < 6 pp. Growth = 10-year profit CAGR ≥ 10%. |
| **Stage 6 — valuation** | The five relative-cheapness checks; the five models (Dhandho worst/best, fading DCF, Total Returns, Lynch P/E = G) averaged into one intrinsic value; investment vs speculative return; the 90/80/75% entry ladder and 125/135/150% exit ladder. When the models are more than 1.6× apart, entry prices are anchored on the lowest two models instead of the average (guide §7.4). |
| **Scorecard** | Rows 4–15, 17 and 18 of the one-page scorecard (96 of the 130 points), as a percentage. |

### Verdicts

* **BUY** — clears every hard gate, scores ≥ 70%, price is at or below the
  phase-1 buy price, projected capital gain ≥ 15% a year, and the business
  (not a re-rating) supplies most of the return.
* **WATCH** — a business worth owning, but not at today's price. Put a price
  alert at the "Buy ≤" figure.
* **REJECT** — fails a hard gate (the reasons are listed) or scores under 70%.
* **SKIP** — banks, NBFCs and insurers (the guide uses a different sheet for
  lenders), too little history, or the page could not be fetched.

Hard gates: market cap ≥ ₹500 cr, ≥ 10 years of data, 10-year average ROE ≥
15%, positive cumulative CFO and FCF, D/E < 1, interest cover > 10× (or
debt-free), profit growing over the decade, dilution ≤ 2% a year, not a
wealth destroyer, promoter stake not falling three years running, fewer than
three forensic flags.

Results are sorted BUY → WATCH → REJECT → SKIP, best score first. The
"sweet spot" column marks companies under ₹5,000 crore — the under-covered
part of the market the guide says to hunt in.

### Assumptions you can change

| Option | Default | Guide's advice |
| --- | --- | --- |
| `--discount` | 12 | 14–15 for a moatless business, a cyclical, or anything under ₹2,000 cr |
| `--gsec` | 6.68 | Current 10-year government bond yield |
| `--exit-pe` | 20 | Exit P/E for the Total Returns model |
| `--min-cap` | 500 | Minimum market cap in ₹ crore |

## What it cannot do for you

A screen narrows the list; it doesn't make the decision. Every shortlisted
stock in the HTML report lists the manual stages still to do: circle of
competence, the forensic checklist and 18-point Satyam test from the annual
reports, naming the moat and judging management, the fragility test, pledge
and auditor history, and the written thesis with the 48-hour behavioural
gate. The guide's own warning applies: the process is backward-looking, can't
detect a well-executed fraud, and five averaged models can give false
confidence. Always look at the five values, not just the average.

## Code layout

| File | Purpose |
| --- | --- |
| `multibagger_cli.py` | Command-line entry point |
| `multibagger/screener_web.py` | Download and parse Screener company pages, price history, screens, login |
| `multibagger/screener_excel.py` | Read Screener "Export to Excel" workbooks (standard library only) |
| `multibagger/engine.py` | The process: tests, matrices, valuation, gates, scorecard, verdict |
| `multibagger/report.py` | Console table, CSV, JSON and HTML report |
| `tests/test_multibagger.py` | Tests, including the guide's Andhra Sugars worked example |

The tests check the engine against the guide's worked example (The Andhra
Sugars Ltd): 10-year ROE 10.9%, Dhandho values ₹160.33 / ₹212.40, DCF ≈
₹108, P/E = G ≈ ₹45, a 14.2% speculative return, the wealth-destroyer quadrant,
and a REJECT verdict despite passing the relative-cheapness checks.

If Screener changes its page layout, the parser in `screener_web.py`
is the only part that needs updating. Run with `MULTIBAGGER_DEBUG=1` to
see the full error for a symbol that fails.
