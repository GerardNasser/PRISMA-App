#!/usr/bin/env python3
"""Build script for PrismAPI desktop.

  macOS    →  dist/PrismAPI.app  +  dist/PrismAPI.dmg
  Windows  →  dist/PrismAPI.exe  (single-file)

Usage:
  python build.py            # build the app (and DMG on macOS)
  python build.py --no-dmg   # macOS: skip the DMG step
"""

from __future__ import annotations

import argparse
import importlib
import os
import shutil
import subprocess
import sys


HERE = os.path.dirname(os.path.abspath(__file__))


def _package_dir(name: str) -> str:
    mod = importlib.import_module(name)
    return os.path.dirname(mod.__file__)


def _run(args: list[str]) -> None:
    print("$", " ".join(args))
    subprocess.run(args, check=True, cwd=HERE)


def build_app() -> None:
    sep = ";" if sys.platform == "win32" else ":"

    # YAML field configs need to ship inside the bundle.
    fields_src = os.path.join(HERE, "prismapi", "fields", "registry")

    args = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--name", "PrismAPI",
        # bundle entire prismapi package as data so YAML configs + Python land together
        "--add-data", f"{fields_src}{sep}prismapi/fields/registry",
        "--add-data", f"{_package_dir('customtkinter')}{sep}customtkinter",
        "--hidden-import", "customtkinter",
        "--hidden-import", "PIL._tkinter_finder",
        "--hidden-import", "aiosqlite",
        "--hidden-import", "pydantic",
        "--hidden-import", "pydantic_settings",
        "--collect-data", "customtkinter",
        "--collect-submodules", "prismapi",
        "--collect-submodules", "gui",
        "--collect-submodules", "sqlalchemy",
        "--collect-submodules", "pydantic",
        "--collect-submodules", "pydantic_settings",
    ]

    if sys.platform == "win32":
        args.append("--onefile")
        icon = os.path.join(HERE, "assets", "icon.ico")
        if os.path.exists(icon):
            args += ["--icon", icon]
    else:
        args.append("--onedir")
        icon = os.path.join(HERE, "assets", "icon.icns")
        if os.path.exists(icon):
            args += ["--icon", icon]

    args.append(os.path.join(HERE, "app.py"))

    print("=" * 60)
    print(f"Building PrismAPI for {sys.platform}")
    print("=" * 60)
    _run(args)


def build_dmg() -> None:
    app = os.path.join(HERE, "dist", "PrismAPI.app")
    dmg = os.path.join(HERE, "dist", "PrismAPI.dmg")
    if not os.path.exists(app):
        print(f"  Skipping DMG: {app} does not exist.")
        return
    if os.path.exists(dmg):
        os.remove(dmg)
    if shutil.which("hdiutil") is None:
        print("  Skipping DMG: hdiutil not found (macOS only).")
        return
    _run([
        "hdiutil", "create",
        "-volname", "PrismAPI",
        "-srcfolder", app,
        "-ov", "-format", "UDZO",
        dmg,
    ])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-dmg", action="store_true", help="(macOS) Skip the .dmg creation step.")
    opts = parser.parse_args()

    build_app()

    print()
    print("=" * 60)
    print("Build complete!")
    if sys.platform == "win32":
        print(f"  Output: {os.path.join(HERE, 'dist', 'PrismAPI.exe')}")
    else:
        print(f"  Output: {os.path.join(HERE, 'dist', 'PrismAPI.app')}")
        if not opts.no_dmg:
            print("Creating disk image…")
            build_dmg()
            dmg = os.path.join(HERE, "dist", "PrismAPI.dmg")
            if os.path.exists(dmg):
                print(f"  Output: {dmg}")
    print("=" * 60)


if __name__ == "__main__":
    main()
