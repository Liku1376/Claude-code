"""Build a standalone Roster Creator desktop app with PyInstaller.

    pip install -r requirements-build.txt
    python build.py

Output (in dist/):
  Windows: RosterCreator.exe          (single file, no console window)
  macOS:   RosterCreator.app          (zipped as RosterCreator-macOS.zip)
  Linux:   RosterCreator              (single executable)

PyInstaller builds for the OS it runs on, so build on each target OS (the
GitHub Actions workflow in .github/workflows/build.yml does this).
"""

import os
import platform
import shutil
import sys

import PyInstaller.__main__

ROOT = os.path.dirname(os.path.abspath(__file__))
NAME = "RosterCreator"
SEP = os.pathsep  # PyInstaller --add-data uses ';' on Windows, ':' elsewhere


def main():
    system = platform.system()
    icon = os.path.join(ROOT, "assets", "icon.ico" if system == "Windows" else "icon.png")
    args = [
        os.path.join(ROOT, "roster_app.py"),
        "--name", NAME,
        "--windowed",
        "--noconfirm",
        "--clean",
        "--icon", icon,
        "--add-data", f"{os.path.join(ROOT, 'examples', 'sample_config.json')}{SEP}examples",
        "--add-data", f"{os.path.join(ROOT, 'assets', 'icon.png')}{SEP}assets",
        "--hidden-import", "openpyxl",
        # Not used by the app; keeps the bundle small.
        "--exclude-module", "PIL",
        "--exclude-module", "pytest",
    ]
    # A .app bundle is the normal format on macOS; elsewhere one file is simplest.
    if system != "Darwin":
        args.append("--onefile")
    PyInstaller.__main__.run(args)

    dist = os.path.join(ROOT, "dist")
    if system == "Darwin":
        shutil.make_archive(os.path.join(dist, f"{NAME}-macOS"), "zip", dist, f"{NAME}.app")
    print("\nBuilt:", ", ".join(sorted(os.listdir(dist))))


if __name__ == "__main__":
    sys.exit(main())
