"""Launch the Zodiac Studio web app locally:

    python zodiac_web.py            # opens your browser at http://127.0.0.1:8766/
    python zodiac_web.py --port 9000 --no-browser

Standard library only - nothing to install.
"""

from zodiac_tool.webapp import main

if __name__ == "__main__":
    main()
