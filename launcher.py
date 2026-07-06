"""GUI launcher -- starts Flask/waitress bound to `127.0.0.1` only
(ADR-0008), opens the default browser, and acquires the same
single-instance lock as main.py (ADR-0007).

Free-port discovery and the full retry-then-native-fallback browser-launch
behavior are Epic 6/10 work (docs/requirements/07-packaging-
deployment.md §Browser-launch fallback, docs/BACKLOG.md). This scaffold
wires the pieces Epic 0 owns -- the shared lock, the fixed localhost bind
-- around the minimal placeholder Flask app from backend/app.py so the
seam is real and testable now.
"""

from __future__ import annotations

import sys
import webbrowser
from pathlib import Path

from waitress import serve

from backend.app import create_app
from pipeline.single_instance import AlreadyRunningError, SingleInstanceLock

APPDATA_DIR = Path.home() / "AppData" / "Roaming" / "EpubAutomation"
LOCK_PATH = APPDATA_DIR / "epub-automation.lock"

# Fixed constant -- never a setting, environment variable, or CLI flag.
# See docs/requirements/01-architecture.md §Network Binding & Security.
HOST = "127.0.0.1"
PORT = 5757  # Placeholder port; real free-port discovery is Epic 6.


def main() -> int:
    lock = SingleInstanceLock(LOCK_PATH)
    try:
        lock.acquire()
    except AlreadyRunningError:
        # Per ADR-0007: a second launch while the GUI is already running
        # just opens a new tab to the existing server, not an error.
        webbrowser.open(f"http://{HOST}:{PORT}/")
        return 0

    try:
        webbrowser.open(f"http://{HOST}:{PORT}/")
        serve(create_app(), host=HOST, port=PORT)
        return 0
    finally:
        lock.release()


if __name__ == "__main__":
    sys.exit(main())
