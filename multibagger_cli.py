"""Screen Indian stocks for multibagger candidates using the Value Investing Process.

Examples
--------
  # A handful of symbols, fetched from screener.in:
  python multibagger_cli.py --symbols PIDILITIND ASTRAL NESTLEIND

  # A whole list (one symbol per line, or an NSE EQUITY_L.csv with a SYMBOL column):
  python multibagger_cli.py --symbols-file examples/watchlist.txt

  # Let screener.in pick the universe with the guide's Stage 1 query (needs a free login):
  SCREENER_USERNAME=me@example.com SCREENER_PASSWORD=... python multibagger_cli.py --stage1

  # Screener "Export to Excel" files you already downloaded:
  python multibagger_cli.py --excel exports/*.xlsx

Results are ranked BUY → WATCH → REJECT and written to an HTML report and a CSV.
"""

import argparse
import csv
import glob
import os
import sys
import traceback

from multibagger import STAGE1_QUERY, Settings, analyse, rank
from multibagger import report
from multibagger.engine import Result
from multibagger.model import Company


def read_symbols(path):
    with open(path, encoding="utf-8-sig") as fh:
        text = fh.read()
    lines = [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#")]
    if lines and "," in lines[0]:  # CSV, e.g. NSE's EQUITY_L.csv
        rows = list(csv.DictReader(lines))
        key = next((k for k in rows[0] if k.strip().upper() in ("SYMBOL", "NSE CODE", "TICKER")), None) if rows else None
        if key is None:
            sys.exit("%s: no SYMBOL column found" % path)
        return [r[key].strip() for r in rows if r[key].strip()]
    return [ln.split()[0] for ln in lines]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_argument_group("where the companies come from (combine freely)")
    src.add_argument("--symbols", nargs="*", default=[], help="NSE/BSE symbols as used in screener.in URLs")
    src.add_argument("--symbols-file", help="text file of symbols, or a CSV with a SYMBOL column")
    src.add_argument("--stage1", action="store_true", help="run the guide's Stage 1 query on screener.in (login needed)")
    src.add_argument("--query", help="run your own screener.in query instead (login needed)")
    src.add_argument("--excel", nargs="*", default=[], help="Screener 'Export to Excel' .xlsx files (globs ok)")
    ap.add_argument("--standalone", action="store_true", help="use standalone instead of consolidated figures")
    ap.add_argument("--limit", type=int, help="analyse at most this many companies")
    ap.add_argument("--delay", type=float, default=2.0, help="seconds between screener.in requests (default 2)")
    ap.add_argument("--cache", default=".screener_cache", help="cache folder ('' to disable)")
    ap.add_argument("--no-extras", action="store_true", help="skip price-history and other-assets API calls")
    val = ap.add_argument_group("assumptions (guide §6.5)")
    val.add_argument("--discount", type=float, default=12.0, help="discount rate %% (default 12)")
    val.add_argument("--gsec", type=float, default=6.68, help="10-yr G-sec yield %% (default 6.68)")
    val.add_argument("--exit-pe", type=float, default=20.0, help="exit P/E for Total Returns model (default 20)")
    val.add_argument("--min-cap", type=float, default=500.0, help="minimum market cap, ₹ crore (default 500)")
    out = ap.add_argument_group("output")
    out.add_argument("-o", "--out", default="multibagger_report", help="output path without extension")
    out.add_argument("--json", action="store_true", help="also write full detail as JSON")
    out.add_argument("--show", type=int, default=25, help="rows to print to the console (default 25)")
    args = ap.parse_args(argv)

    opt = Settings(disc=args.discount / 100, bond=args.gsec / 100, exit_pe=args.exit_pe, min_cap=args.min_cap)

    companies = []
    for pattern in args.excel:
        for path in sorted(glob.glob(pattern)) or [pattern]:
            from multibagger.screener_excel import read_export
            try:
                companies.append(read_export(path))
            except Exception as e:  # noqa: BLE001
                print("! %s: %s" % (path, e), file=sys.stderr)

    symbols = list(args.symbols)
    if args.symbols_file:
        symbols += read_symbols(args.symbols_file)

    client = None
    if symbols or args.stage1 or args.query:
        from multibagger.screener_web import ScreenerClient, fetch_company, run_screen
        client = ScreenerClient(cache_dir=args.cache or None, delay=args.delay)
        if args.stage1 or args.query:
            user, pw = os.environ.get("SCREENER_USERNAME"), os.environ.get("SCREENER_PASSWORD")
            if user and pw:
                client.login(user, pw)
            elif not os.environ.get("SCREENER_SESSIONID"):
                sys.exit("Screens need a screener.in login: set SCREENER_USERNAME and SCREENER_PASSWORD "
                         "(or SCREENER_SESSIONID).")
            found = run_screen(client, args.query or STAGE1_QUERY)
            print("Screen returned %d companies" % len(found))
            symbols += found

    symbols = list(dict.fromkeys(s.upper() for s in symbols))
    if args.limit:
        symbols = symbols[:max(0, args.limit - len(companies))]
    if not symbols and not companies:
        ap.print_help()
        return 2

    results = [analyse(c, opt) for c in companies]
    for i, sym in enumerate(symbols, 1):
        print("[%d/%d] %s" % (i, len(symbols), sym), file=sys.stderr)
        try:
            c = fetch_company(client, sym, consolidated=not args.standalone, extras=not args.no_extras)
            results.append(analyse(c, opt))
        except Exception as e:  # noqa: BLE001 - one bad symbol must not stop the run
            if os.environ.get("MULTIBAGGER_DEBUG"):
                traceback.print_exc()
            r = Result(company=Company(name=sym, symbol=sym), verdict="skip", error=str(e))
            r.reasons = ["Could not fetch: %s" % e]
            results.append(r)

    results = rank(results)
    print(report.console(results[:args.show]))
    report.write_csv(results, args.out + ".csv")
    report.write_html(results, args.out + ".html", opt)
    if args.json:
        report.write_json(results, args.out + ".json")
    print("\nWrote %s.html and %s.csv" % (args.out, args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
