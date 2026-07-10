"""Native folder-picker bridge (`tkinter.filedialog`), called from Flask
(ADR-0006, docs/requirements/01-architecture.md §Why these specific
technology choices).

Flask runs natively on her machine (not sandboxed), so it can pop a real
Windows dialog and hand the chosen path back to the page, which is the
whole reason this bridge exists instead of relying on the browser's own
file input (browsers cannot open native OS folder pickers or read
arbitrary filesystem paths directly).
"""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog
from typing import Any, Callable

# Injectable seams -- default to the real tkinter calls, replaced in
# tests with fakes so no test ever creates a real Tk window (no display
# in CI). Same pattern as pipeline/tts_engine.py's `pipeline_factory` and
# pipeline/rename_stage.py's injectable AI provider. Typed `Any` rather
# than a `tk.Tk`-shaped Protocol deliberately -- `tk.Tk`'s own typeshed
# stub (e.g. `attributes(self, *args: Any) -> Any`) doesn't structurally
# match a narrower Protocol cleanly, and the whole point of this seam is
# accepting a plain duck-typed fake in tests anyway.
TkFactory = Callable[[], Any]
AskDirectory = Callable[..., str]


def pick_folder(
    title: str = "",
    initial_dir: str = "",
    *,
    tk_factory: TkFactory = tk.Tk,
    ask_directory: AskDirectory = filedialog.askdirectory,
) -> str | None:
    """Open a native folder-picker dialog and return the chosen absolute
    path, or None if cancelled.

    A hidden, topmost root window is created and destroyed per call --
    this dialog is popped rarely (first-run setup, "Change my folders"),
    so there's no reason to keep a persistent Tk root alive for the whole
    life of the Flask process. `-topmost` makes sure the native dialog
    actually appears above her browser window rather than opening behind
    it, unnoticed.
    """
    root = tk_factory()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        if initial_dir:
            chosen = ask_directory(
                title=title or "Choose a folder", initialdir=initial_dir, parent=root
            )
        else:
            chosen = ask_directory(title=title or "Choose a folder", parent=root)
    finally:
        root.destroy()
    return chosen or None
