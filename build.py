"""Build a standalone Roster Creator desktop app with PyInstaller.

    pip install -r requirements-build.txt
    python build.py

Output (in dist/):
  Windows: RosterCreator.exe          (single file, no console window)
  macOS:   RosterCreator.app          (zipped as RosterCreator-macOS.zip)
  Linux:   RosterCreator              (single executable)

PyInstaller builds for the OS it runs on, so build on each target OS (the
GitHub Actions workflow in .github/workflows/build.yml does this).

This file is commented line by line. PyInstaller bundles Python, the code and
the data files into one self-contained executable.
"""

# ``os`` for paths; ``platform`` to detect the OS; ``shutil`` to zip the macOS
# app; ``sys`` for the exit code.
import os
import platform
import shutil
import sys

# PyInstaller's programmatic entry point (same as the ``pyinstaller`` command).
import PyInstaller.__main__

# The project root, the app name, and the list separator --add-data expects.
ROOT = os.path.dirname(os.path.abspath(__file__))
NAME = "RosterCreator"
SEP = os.pathsep  # PyInstaller --add-data uses ';' on Windows, ':' elsewhere


def main():
    # Which OS we are building on.
    system = platform.system()
    # Windows uses a .ico icon; other platforms use the .png.
    icon = os.path.join(ROOT, "assets", "icon.ico" if system == "Windows" else "icon.png")
    # The PyInstaller command-line arguments.
    args = [
        os.path.join(ROOT, "roster_app.py"),   # the entry-point script
        "--name", NAME,                         # output name
        "--windowed",                           # no console window (GUI app)
        "--noconfirm",                          # overwrite previous builds
        "--clean",                              # start from a clean cache
        "--icon", icon,                         # the app icon
        # Bundle the data files the app needs (source path -> destination folder).
        "--add-data", f"{os.path.join(ROOT, 'examples', 'sample_config.json')}{SEP}examples",
        "--add-data", f"{os.path.join(ROOT, 'assets', 'icon.png')}{SEP}assets",
        "--add-data", f"{os.path.join(ROOT, 'roster_tool', 'web')}{SEP}roster_tool/web",
        "--hidden-import", "openpyxl",          # ensure the Excel library is included
        # Not used by the app; keeps the bundle small.
        "--exclude-module", "PIL",
        "--exclude-module", "pytest",
    ]
    # A .app bundle is the normal format on macOS; elsewhere one file is simplest.
    if system != "Darwin":
        args.append("--onefile")
    # Run the build.
    PyInstaller.__main__.run(args)

    # On macOS, zip the .app bundle for a single downloadable file.
    dist = os.path.join(ROOT, "dist")
    if system == "Darwin":
        shutil.make_archive(os.path.join(dist, f"{NAME}-macOS"), "zip", dist, f"{NAME}.app")
    # Report what was built.
    print("\nBuilt:", ", ".join(sorted(os.listdir(dist))))


# When run directly, build and use main()'s return value as the exit code.
if __name__ == "__main__":
    sys.exit(main())
