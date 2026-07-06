"""Single-instance lock, acquired identically by main.py (CLI) and
launcher.py (GUI) -- ADR-0007.

Protects the shared state file / audit log from concurrent writes, and
prevents two simultaneous Kokoro inference jobs on the same machine (a
real resource-contention problem on its own, independent of data
integrity -- see docs/design/adr/0007-single-instance-lock-shared-
across-frontends.md).

Includes PID-based stale-lock detection: a lock file left behind by a
process that died without releasing it (crash, forced restart, lost
power -- all explicitly expected scenarios, see
docs/requirements/06-safety-error-handling.md §Long-run resilience) must
not permanently block the next launch. This is a liveness check only, not
a crash-recovery mechanism -- actual recovery of in-progress work is the
state-file-driven "Welcome back" flow (pipeline/state_manager.py),
unaffected by this module.

Implementation note: PID liveness (and the image-name check that guards
against PID reuse after a reboot) is checked via `psutil` rather than
hand-rolled `ctypes`/`os.kill` calls -- it's a small, well-established,
cross-platform dependency that keeps this module's actual logic (the
stale-lock policy) readable, rather than tangled up with OS-specific
process-inspection code.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psutil


class AlreadyRunningError(Exception):
    """Raised when acquire() finds another live instance already holding
    the lock.

    Per ADR-0007: the GUI handles this by opening a new browser tab to the
    existing server instead of erroring; the CLI fails fast with a clear
    message rather than queuing, blocking silently, or proceeding anyway.
    """


@dataclass
class SingleInstanceLock:
    """A PID-and-process-name lock file at `path`.

    Usage (identical for main.py and launcher.py)::

        lock = SingleInstanceLock(lock_path)
        try:
            lock.acquire()
        except AlreadyRunningError:
            ...  # front-door-specific handling, see module docstring
        else:
            try:
                ...  # do the work
            finally:
                lock.release()

    Or as a context manager: `with SingleInstanceLock(lock_path): ...`
    (only use this form where an `AlreadyRunningError` propagating and
    ending the process is the desired behavior).
    """

    path: Path

    def _read_lock(self) -> dict[str, Any] | None:
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data: dict[str, Any] = json.load(f)
                return data
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def _holder_is_alive(self, lock_data: dict[str, Any]) -> bool:
        pid = lock_data.get("pid")
        recorded_name = lock_data.get("process_name")
        if pid is None:
            return False
        try:
            proc = psutil.Process(pid)
        except psutil.NoSuchProcess:
            return False
        if not proc.is_running():
            return False
        # Guard against PID reuse by an unrelated process after a reboot:
        # only trust the liveness check if the recorded image name still
        # matches what's actually running under that PID today.
        if recorded_name and proc.name() != recorded_name:
            return False
        return True

    def acquire(self) -> None:
        """Acquire the lock, automatically clearing a stale (dead-holder)
        lock first.

        Raises `AlreadyRunningError` if a live process already holds it.
        """
        existing = self._read_lock()
        if existing is not None and self._holder_is_alive(existing):
            raise AlreadyRunningError(
                "epub-automation is already running -- finish or quit " "that first"
            )
        # Either there's no lock file, or it's stale (holder no longer
        # alive) -- clear it and proceed. Logging "a stale lock was
        # cleared" is the caller's job (e.g. via the audit log), since this
        # module deliberately has no logging dependency of its own.
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(
                {"pid": os.getpid(), "process_name": psutil.Process().name()},
                f,
            )

    def release(self) -> None:
        """Release the lock -- only if this process is still its recorded
        holder (so a stale lock cleared and re-acquired by someone else
        can never be released out from under them)."""
        existing = self._read_lock()
        if existing is not None and existing.get("pid") == os.getpid():
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass

    def __enter__(self) -> SingleInstanceLock:
        self.acquire()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.release()
