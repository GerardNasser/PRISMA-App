"""PrismAPI — desktop GUI entry point.

Run from source:

    python app.py

PyInstaller-bundled (.app or .exe) launches this file. There is no separate
sidecar — the prismapi engine runs in-process and the GUI calls it directly
through the same dispatcher used by the tests.
"""

from __future__ import annotations

import sys

import customtkinter as ctk

from gui.main import PrismAPIApp


def run() -> int:
    ctk.set_appearance_mode("light")
    ctk.set_default_color_theme("blue")
    app = PrismAPIApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(run())
