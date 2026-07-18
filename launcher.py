"""GUI launcher -- starts Flask/waitress bound to `127.0.0.1` only
(ADR-0008), finds a free local port automatically, opens the default
browser (with retry + native-dialog fallback,
docs/requirements/07-packaging-deployment.md §Browser-launch fallback),
and acquires the same single-instance lock as main.py (ADR-0007).

Free-port discovery (Epic 6) means a second launch can no longer assume
a fixed, well-known port when reopening a tab to an already-running
instance (docs/requirements/01-architecture.md §Single-instance behavior)
-- the chosen port is written to a small sidecar file next to the lock
file, read back by the second launch. This lives entirely in
launcher.py, not pipeline/single_instance.py, so ADR-0007's lock module
stays scoped to what it already owns (liveness), not port bookkeeping.
"""

from __future__ import annotations

import os
import socket
import sys
import time
import tkinter as tk
import webbrowser
from pathlib import Path
from typing import Any, Callable

from waitress import serve as waitress_serve

from backend.app import create_app
from pipeline.single_instance import AlreadyRunningError, SingleInstanceLock

APPDATA_DIR = Path.home() / "AppData" / "Roaming" / "EpubAutomation"
LOCK_PATH = APPDATA_DIR / "epub-automation.lock"
PORT_FILE_PATH = APPDATA_DIR / "epub-automation.port"

# Fixed constant -- never a setting, environment variable, or CLI flag.
# See docs/requirements/01-architecture.md §Network Binding & Security.
HOST = "127.0.0.1"

BROWSER_RETRY_DELAY_SECONDS = 1.0


def _ensure_stdio_streams() -> None:
    """`pythonw.exe` (this launcher's no-console entry point, `run_gui.vbs`)
    and a windowed PyInstaller build (Phase B) both detach stdio entirely
    -- `sys.stdout`/`sys.stderr` are `None`, not just redirected. Several
    lazily-imported dependencies assume a real stream exists at their own
    *import* time -- `kokoro/__init__.py` unconditionally does
    `from loguru import logger; logger.add(sys.stderr, ...)` the moment
    it's first imported (`pipeline/tts_engine.py`'s lazy `_get_pipeline()`,
    deep inside the first real audio-generation request, well after this
    module has finished importing) -- and crashes with `TypeError: Cannot
    log to objects of type 'NoneType'` instead. Real bug, real user
    report, 2026-07-18: reproduced every time under `run_gui.vbs`, never
    under a console-attached `python launcher.py`, which is exactly why a
    live repro against the same text/voice via a console-attached script
    didn't catch it. Called at module level below, right after every
    import this module itself needs -- none of those imports anything
    stdio-sensitive at *their* import time, only later, at request time,
    which is what makes calling this here (rather than needing to run
    before this module's own imports) safe.
    """
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")


_ensure_stdio_streams()


def find_free_port(host: str = HOST) -> int:
    """Ask the OS for an unused local port by binding to port 0 -- only
    the port varies launch to launch; the host is always the fixed
    `127.0.0.1` constant (ADR-0008), never chosen dynamically."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def _read_existing_port(port_file_path: Path) -> int | None:
    try:
        return int(port_file_path.read_text().strip())
    except (FileNotFoundError, ValueError):
        return None


def _show_fallback_dialog(url: str, *, tk_factory: Callable[[], Any] = tk.Tk) -> None:
    """Native dialog with the address in large plain text, auto-copied to
    clipboard, and a "Try Again" button
    (07-packaging-deployment.md §Browser-launch fallback) -- shown only
    once both the automatic open and the one retry have failed."""
    root = tk_factory()
    root.title("epub-automation")
    root.attributes("-topmost", True)
    root.clipboard_clear()
    root.clipboard_append(url)

    tk.Label(
        root,
        text=(
            "Couldn't open your browser automatically.\n"
            "This address has been copied -- paste it into your browser:"
        ),
        justify="left",
        padx=20,
        pady=10,
    ).pack()
    tk.Label(root, text=url, font=("Segoe UI", 14, "bold"), padx=20).pack()
    tk.Button(
        root, text="Try Again", command=lambda: webbrowser.open(url), padx=20, pady=10
    ).pack(pady=10)
    tk.Button(root, text="Close", command=root.destroy, padx=20, pady=10).pack(
        pady=(0, 10)
    )
    root.mainloop()


def open_browser(
    url: str,
    *,
    opener: Callable[[str], bool] = webbrowser.open,
    sleep: Callable[[float], None] = time.sleep,
    show_fallback_dialog: Callable[[str], None] = _show_fallback_dialog,
) -> bool:
    """Retry once automatically after ~1 second; if still failing, show
    the native fallback dialog. Returns True once the browser was
    (probably) launched, False if the fallback dialog had to be shown
    instead. The Flask server is already running by the time this is
    ever called, so a failed/slow browser launch never blocks it.
    """
    if opener(url):
        return True
    sleep(BROWSER_RETRY_DELAY_SECONDS)
    if opener(url):
        return True
    show_fallback_dialog(url)
    return False


def main(
    *,
    lock_path: Path = LOCK_PATH,
    port_file_path: Path = PORT_FILE_PATH,
    serve_fn: Callable[..., None] = waitress_serve,
    open_browser_fn: Callable[[str], bool] = open_browser,
) -> int:
    lock = SingleInstanceLock(lock_path)
    try:
        lock.acquire()
    except AlreadyRunningError:
        # Per ADR-0007: a second launch while the GUI is already running
        # just opens a new tab to the existing server, not an error.
        existing_port = _read_existing_port(port_file_path)
        if existing_port is not None:
            open_browser_fn(f"http://{HOST}:{existing_port}/")
        return 0

    port = find_free_port()
    port_file_path.parent.mkdir(parents=True, exist_ok=True)
    port_file_path.write_text(str(port))
    try:
        open_browser_fn(f"http://{HOST}:{port}/")
        serve_fn(create_app(), host=HOST, port=port)
        return 0
    finally:
        port_file_path.unlink(missing_ok=True)
        lock.release()


if __name__ == "__main__":
    sys.exit(main())
