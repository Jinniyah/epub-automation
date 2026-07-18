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

import os
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog
from typing import Any, Callable, NamedTuple

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


# ---------------------------------------------------------------------------
# Thread-safe wrapper (docs/BACKLOG.md Epic 10 Phase A -- real bug found via
# live testing, not a design-time concern)
# ---------------------------------------------------------------------------


class _DialogJob(NamedTuple):
    title: str
    initial_dir: str
    tk_factory: TkFactory
    ask_directory: AskDirectory
    response: "queue.Queue[str | None]"


_dialog_jobs: "queue.Queue[_DialogJob]" = queue.Queue()
_dialog_thread: threading.Thread | None = None
_dialog_thread_lock = threading.Lock()


def _dialog_worker() -> None:
    while True:
        job = _dialog_jobs.get()
        try:
            result = pick_folder(
                title=job.title,
                initial_dir=job.initial_dir,
                tk_factory=job.tk_factory,
                ask_directory=job.ask_directory,
            )
        except Exception:
            result = None
        job.response.put(result)


def request_folder_pick(
    title: str = "",
    initial_dir: str = "",
    *,
    tk_factory: TkFactory = tk.Tk,
    ask_directory: AskDirectory = filedialog.askdirectory,
) -> str | None:
    """The route-facing entry point `backend/app.py::pick_folder_route`
    actually calls -- `pick_folder()` above stays the plain, directly
    testable dialog logic; this wrapper is what makes it safe to call
    from a Flask request handler at all.

    **Real bug, found via live testing against a real running server,
    not a theoretical concern:** every Flask route runs on one of
    `waitress`'s worker-thread pool threads -- never the actual process
    main thread `launcher.py`'s own `main()` blocks on inside
    `waitress.serve()`. Calling `pick_folder()` directly from a route
    handler intermittently hangs *forever*: reproduced live by calling
    `POST /api/dialogs/folder` against a real server and watching the
    request never return, while every other route kept responding
    normally -- proof that exactly one of `waitress`'s *finite* worker
    threads got permanently stuck, not that the whole server broke. A
    few unlucky clicks could eventually exhaust all of them and take the
    whole app down. Tcl/Tk's global interpreter state isn't safe to
    touch from a *different* thread on every call (a fresh `waitress`
    worker each time), but it's fine from one *consistent* thread reused
    for the life of the process -- the standard fix for this exact
    Flask+tkinter combination, and simpler than the alternative
    (spawning a subprocess per dialog, which also doesn't survive being
    frozen into a single PyInstaller `.exe` the way this app ships,
    Epic 10 Phase B).

    This function itself still runs on whichever `waitress` worker
    thread handled the request -- it just hands the actual `pick_folder`
    call off to the one dedicated background thread (started lazily, on
    first use, and kept alive for the rest of the process) and blocks
    waiting for the answer, which is exactly the behavior the route
    already needs (the request is *supposed* to block until she answers
    the dialog).
    """
    global _dialog_thread
    with _dialog_thread_lock:
        if _dialog_thread is None or not _dialog_thread.is_alive():
            _dialog_thread = threading.Thread(target=_dialog_worker, daemon=True)
            _dialog_thread.start()

    response: "queue.Queue[str | None]" = queue.Queue()
    _dialog_jobs.put(
        _DialogJob(title, initial_dir, tk_factory, ask_directory, response)
    )
    return response.get()


FolderOpener = Callable[[str], None]


def open_folder(path: str, *, opener: FolderOpener = os.startfile) -> bool:
    """Open *path* directly in File Explorer (03-gui-ux-design.md's
    "📂 See the audiobook files" / "📂 See all my finished books" links) --
    the same reasoning as `pick_folder()` above: a browser page cannot
    open a native Explorer window on an arbitrary local path itself, so
    Flask (unsandboxed, running natively on her machine) does it on the
    page's behalf. Windows-only (`00-overview-and-goals.md`'s confirmed
    v1 scope), hence `os.startfile` rather than a cross-platform `open`/
    `xdg-open` dispatch.

    Returns False (not an exception) for a path that doesn't exist --
    her book output can legitimately have moved or been deleted since
    the link was shown; the route this backs surfaces that as a friendly
    message rather than a raw OS error.
    """
    if not Path(path).is_dir():
        return False
    opener(path)
    return True
