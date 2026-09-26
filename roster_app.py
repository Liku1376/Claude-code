"""Launch the Roster Creator GUI: python roster_app.py

``--selftest`` generates the bundled sample roster and exercises exports
(Excel, CSV, calendar), saving/reopening a roster file and carry-over, without
opening a window; it exits 0 on success. Used to check packaged builds.

This file is commented line by line.
"""

# ``sys`` is used to read the command-line arguments and set the exit code.
import sys


def selftest() -> int:
    # A headless check that the packaged app's core paths work end to end.
    import json
    import os
    import tempfile

    # Import lazily so the GUI is not loaded during the self-test.
    from roster_tool import export, ics, storage
    from roster_tool.gui import SAMPLE_CONFIG
    from roster_tool.model import RosterConfig
    from roster_tool.scheduler import generate
    from roster_tool.validator import ERROR, count

    # Load the bundled sample inputs and generate a roster.
    with open(SAMPLE_CONFIG, encoding="utf-8") as fh:
        inputs = json.load(fh)
    roster, issues = generate(RosterConfig.from_dict(inputs))
    # Exercise every export and the save/reopen/carry-over paths in a temp dir.
    with tempfile.TemporaryDirectory() as tmp:
        export.to_excel(roster, os.path.join(tmp, "roster.xlsx"), issues)
        export.to_csv(roster, os.path.join(tmp, "roster.csv"))
        ics.export_all(roster, os.path.join(tmp, "ics"))
        path = os.path.join(tmp, "roster.json")
        storage.save_roster_file(path, inputs, roster, roster.copy())
        reopened = storage.load_roster_file(path)
        # A reopened roster must match what was saved.
        if reopened.roster.grid != roster.grid:
            return 2
        storage.carry_over_from(reopened.roster)
    # Exit 1 if the sample somehow broke a rule, else 0.
    return 1 if count(issues, ERROR) else 0


# When run directly: run the self-test if asked, otherwise open the GUI.
if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    from roster_tool.gui import main

    main()
