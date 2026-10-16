# Multibagger Screener — Indian equities

A command-line tool that collects company data from
[Screener.in](https://www.screener.in) and runs every stock through the
**Value Investing Process — Indian Equities** guide, then ranks them so the
strongest candidates for an *enduring* multibagger appear first
(BUY → WATCH → REJECT).

It uses only the Python standard library — nothing to install.

```bash
python multibagger_cli.py --symbols PIDILITIND ASTRAL PAGEIND
python multibagger_cli.py --symbols-file examples/watchlist.txt
python multibagger_cli.py --stage1          # the guide's Stage 1 screen (needs a Screener login)
python multibagger_cli.py --excel exports/*.xlsx
```

Each run prints a ranked table and writes `multibagger_report.html` and
`multibagger_report.csv`.

See [docs/MULTIBAGGER.md](docs/MULTIBAGGER.md) for what each stage checks, the
verdict rules and the options.

## Tests

```bash
pip install pytest
python -m pytest
```
