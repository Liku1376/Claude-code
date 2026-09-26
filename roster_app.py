"""Launch the Roster Creator GUI: python roster_app.py

``--selftest`` generates the bundled sample roster and exercises exports
(Excel, CSV, calendar), saving/reopening a roster file and carry-over, without
opening a window; it exits 0 on success. Used to check packaged builds.
"""

import sys


def selftest() -> int:
    import json
    import os
    import tempfile

    from roster_tool import export, ics, storage
    from roster_tool.gui import SAMPLE_CONFIG
    from roster_tool.model import RosterConfig
    from roster_tool.scheduler import generate
    from roster_tool.validator import ERROR, count

    with open(SAMPLE_CONFIG, encoding="utf-8") as fh:
        inputs = json.load(fh)
    roster, issues = generate(RosterConfig.from_dict(inputs))
    with tempfile.TemporaryDirectory() as tmp:
        export.to_excel(roster, os.path.join(tmp, "roster.xlsx"), issues)
        export.to_csv(roster, os.path.join(tmp, "roster.csv"))
        ics.export_all(roster, os.path.join(tmp, "ics"))
        path = os.path.join(tmp, "roster.json")
        storage.save_roster_file(path, inputs, roster, roster.copy())
        reopened = storage.load_roster_file(path)
        if reopened.roster.grid != roster.grid:
            return 2
        storage.carry_over_from(reopened.roster)
    return 1 if count(issues, ERROR) else 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    from roster_tool.gui import main

    main()
