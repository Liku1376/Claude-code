"""Launch the Roster Creator GUI: python roster_app.py

``--selftest`` generates the bundled sample roster and exports it to Excel
and CSV without opening a window; it exits 0 on success. Used to check
packaged builds.
"""

import sys


def selftest() -> int:
    import json
    import os
    import tempfile

    from roster_tool import export
    from roster_tool.gui import SAMPLE_CONFIG
    from roster_tool.model import RosterConfig
    from roster_tool.scheduler import generate
    from roster_tool.validator import ERROR, count

    with open(SAMPLE_CONFIG, encoding="utf-8") as fh:
        cfg = RosterConfig.from_dict(json.load(fh))
    roster, issues = generate(cfg)
    with tempfile.TemporaryDirectory() as tmp:
        export.to_excel(roster, os.path.join(tmp, "roster.xlsx"), issues)
        export.to_csv(roster, os.path.join(tmp, "roster.csv"))
    return 1 if count(issues, ERROR) else 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    from roster_tool.gui import main

    main()
