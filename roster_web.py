"""Launch the Roster Creator web app locally:

    python roster_web.py            # opens your browser at http://127.0.0.1:8765/
    python roster_web.py --port 9000 --no-browser

No installation and no executable: this runs the tool as a local web page
served by Python's standard library, so it works wherever a permitted Python
interpreter can run.
"""

from roster_tool.webapp import main

if __name__ == "__main__":
    main()
