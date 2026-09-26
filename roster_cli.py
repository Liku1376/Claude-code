"""Generate a roster without the GUI.

    python roster_cli.py examples/sample_config.json -o roster.xlsx
    python roster_cli.py november.json --previous october_roster.json --save november_roster.json --ics calendars/

This file is commented line by line. It reads an inputs JSON file, builds a
roster, prints it as a text grid, and optionally exports it.
"""

# ``argparse`` parses command-line options; ``json`` reads the inputs file;
# ``sys`` sets the process exit code.
import argparse
import json
import sys

# Reuse the same engine/exports/storage as the GUI and web app.
from roster_tool import export, ics, storage
from roster_tool.model import RosterConfig
from roster_tool.scheduler import generate
from roster_tool.validator import ERROR, count


def main(argv=None):
    # Define the command-line options.
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("config", help="inputs JSON (as saved from the GUI)")
    ap.add_argument("-o", "--output", help="write roster to .xlsx or .csv")
    ap.add_argument("--previous", help="previous month's roster file, for comp off carry-over and fairness")
    ap.add_argument("--save", help="save the roster file (can be reopened in the app)")
    ap.add_argument("--ics", metavar="DIR", help="write calendar invites (.ics) to this folder")
    args = ap.parse_args(argv)

    # Load the inputs file.
    with open(args.config, encoding="utf-8") as fh:
        inputs = json.load(fh)
    # If a previous month's roster was given, derive the carry-over block from it.
    if args.previous:
        inputs["carry_over"] = storage.carry_over_from(storage.load_roster_file(args.previous).roster)
    # Build the config and generate the roster.
    cfg = RosterConfig.from_dict(inputs)
    roster, issues = generate(cfg)

    # Print the grid: a header of day numbers, then one line per engineer.
    width = max(len(n) for n in cfg.engineer_names)   # width of the name column
    print(" " * width, " ".join(d.strftime("%d") for d in cfg.days))
    for n in cfg.engineer_names:
        print(n.ljust(width), " ".join(roster.code(n, d).rjust(2) for d in cfg.days))
    # Print the on-call assignments.
    for label, table in (("Primary", roster.primary), ("Secondary", roster.secondary)):
        print(f"\n{label} on-call:")
        for d in cfg.days:
            if table.get(d):
                print(f"  {d:%a %d %b}: {table[d]}")
    print()
    # Print every validation issue.
    for i in issues:
        print(i)
    # A clear "all good" line when there are no errors.
    if not count(issues, ERROR):
        print("All mandatory rules are satisfied.")

    # Optional exports.
    if args.output:
        # .csv exports as CSV; anything else as Excel.
        if args.output.lower().endswith(".csv"):
            export.to_csv(roster, args.output)
        else:
            export.to_excel(roster, args.output, issues)
        print(f"Saved {args.output}")
    if args.save:
        # Save a reopenable roster file.
        storage.save_roster_file(args.save, inputs, roster)
        print(f"Saved {args.save}")
    if args.ics:
        # Write one calendar file per engineer plus the team calendar.
        print(f"Wrote {len(ics.export_all(roster, args.ics))} calendar files to {args.ics}")
    # Exit code 1 if any mandatory rule is broken, else 0 (useful in scripts).
    return 1 if count(issues, ERROR) else 0


# When run directly, execute main() and use its return value as the exit code.
if __name__ == "__main__":
    sys.exit(main())
