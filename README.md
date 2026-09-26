# Roster Creator

A desktop (Tkinter) tool that builds a monthly shift and on-call roster for an
engineering team. You enter the team, leave, shift requests and calendar, and
it generates a roster that meets the mandatory rules. Any rule it can't meet
is listed so you can fix it.

![Roster tab](docs/roster_screenshot.png)

![Team tab](docs/team_screenshot.png)

## Running

Needs Python 3.10+ with Tkinter (`sudo apt install python3-tk` on
Debian/Ubuntu; the python.org installers for Windows/macOS already include it).

```bash
pip install -r requirements.txt   # optional, only for Excel export
python roster_app.py
```

Use **File → Load sample data** to see a filled-in example, then press
**Generate roster** (top right).

To generate without the GUI, run
`python roster_cli.py examples/sample_config.json -o roster.xlsx`.

## Inputs (one step each in the left sidebar)

| Step | What you enter |
| --- | --- |
| 1. Team | Name, designation, and whether the engineer is an **SME** |
| 2. Calendar | Roster month/year, weekend days, holidays, freeze periods |
| 3. Leave | Engineer + date or date range (shown as `L`) |
| 4. Long Leave | Engineer + date range (shown as `LL`) |
| 5. Shift Requirements | Engineer + dates + Morning/Evening/Night + **Must** (must work that shift) or **Avoid** (never on that shift, e.g. no nights) |
| 6. On-Call | Optional: fix the primary/secondary on-call engineer for a given day. Every other day is assigned automatically, rotating fairly |
| 7. Rules | Minimum engineers per shift for each day type; generator settings |

Dates can be typed as `YYYY-MM-DD`, `DD/MM/YYYY`, or just the day number
(e.g. `14`) within the selected month. Use **File → Save inputs** to save
everything as a JSON file you can reopen and reuse next month.

## Mandatory rules

1. **Coverage:** at least 1 engineer on Morning and 1 on Night on working days.
   Freeze periods, weekends and holidays are excluded. The minimums can be
   changed per day type on the Rules tab.
2. **Comp off:** the day after every night shift is a comp off (`CO`). A night
   on the last day of the month is flagged as a carry-over into next month.
3. **Primary on-call** (every day, including weekends and holidays): a
   **non-SME** engineer who is **not** on Morning or Night shift that day.
   On working days they are on the Evening shift.
4. **Secondary on-call:** an **SME** engineer. Not needed on weekends and
   holidays.

The tool also honours leave, long leave and Must/Avoid shift requests. It
balances nights, mornings, evenings and on-call duty across the team.

## Roster tab

- Summary tiles show whether all rules are met, the number of violations and
  warnings, and how evenly nights and primary on-call are spread.
- Cells are colour-coded: `M` Morning, `E` Evening, `N` Night, `CO` Comp off,
  `L` Leave, `LL` Long leave, `WO` Weekend off, `H` Holiday. A small indigo dot
  marks primary on-call and a teal dot marks secondary on-call. Weekend, holiday
  and freeze columns are shaded.
- Hover over a cell to see details in the status bar. Click a cell to change
  it by hand. The roster is re-checked straight away, and any day that breaks
  a rule gets a red dot under its date.
- The issues panel lists **Errors** (a mandatory rule is broken), **Warnings**
  (a request could not be honoured) and **Info** notes.
- **Export Excel** creates a colour-coded sheet with a legend and an Issues
  sheet. **Export CSV** creates a plain table.

## How generation works

The generator fills the month day by day in priority order:

1. leave and comp offs
2. Must requests
3. primary on-call
4. secondary on-call
5. Night
6. Morning
7. Evening
8. everyone else, split between Morning and Evening

When several engineers qualify, it picks the one with the fewest of that duty
so far. It does this for several hundred randomised attempts and keeps the one
with the fewest rule violations and the most even workload. Set a random seed
on the Rules tab to get the same roster every time.

## Development

```bash
pip install pytest openpyxl
python -m pytest
```

| Path | Purpose |
| --- | --- |
| `roster_tool/model.py` | Data model, input parsing, calendar helpers |
| `roster_tool/scheduler.py` | Roster generation |
| `roster_tool/validator.py` | Rule checks (used for generated and hand-edited rosters) |
| `roster_tool/export.py` | CSV / Excel export |
| `roster_tool/gui.py` | Tkinter user interface |
| `roster_tool/theme.py` | Colours, fonts and widget styles |
