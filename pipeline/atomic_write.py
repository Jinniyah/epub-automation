"""Atomic write-to-temp-then-rename helper for settings.json and the state
file (ADR-0005, docs/requirements/05-data-settings-and-logging.md §Write
safety).

Hard requirement this implements: never `open(path, "w")` directly on a
live settings/state file. An in-place write is not instantaneous or
all-or-nothing -- if the process is killed partway through (power loss, a
forced restart, an AV lock, a crash), the file can be left truncated or
half-old/half-new, which fails to parse on next launch. A rename, by
contrast, either fully happens or fully doesn't.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def atomic_write_json(path: str | Path, data: dict[str, Any]) -> None:
    """Write `data` as JSON to `path` atomically.

    Writes to a temp file in the *same directory* as `path` first (so the
    final `os.replace()` is a same-filesystem rename, not a cross-device
    copy), flushes and fsyncs it, then performs a single atomic rename over
    the real file. If anything goes wrong before the rename, the original
    file at `path` is left completely untouched and the temp file is
    cleaned up on a best-effort basis.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)  # atomic on both Windows and POSIX
    except BaseException:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass
        raise


def atomic_read_json(path: str | Path) -> dict[str, Any] | None:
    """Read and parse JSON from `path`.

    Returns None if the file doesn't exist -- a normal, expected case (a
    fresh install with no prior settings/state file yet), not an error.
    Raises `json.JSONDecodeError` if the file exists but isn't valid JSON;
    callers own the corrupted-file recovery policy (schema_version
    handling lives in pipeline/config.py and pipeline/state_manager.py,
    not here -- this helper is deliberately just the write-safety
    primitive both of those build on).
    """
    path = Path(path)
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        data: dict[str, Any] = json.load(f)
        return data
