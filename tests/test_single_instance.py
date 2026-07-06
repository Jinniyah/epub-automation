"""TDD tests for pipeline/single_instance.py -- ADR-0007's stale-lock
detection is explicitly called out in docs/requirements/09-testing-
strategy.md §Priority coverage areas: "a test simulating a lock file left
behind by a dead PID, proving the next launch clears it and proceeds
rather than refusing to start."
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import psutil
import pytest

from pipeline.single_instance import AlreadyRunningError, SingleInstanceLock


def _spawn_and_kill_process() -> int:
    """Return a PID that is guaranteed not to belong to any running
    process -- spawn a trivial subprocess, wait for it to exit, and hand
    back its now-dead PID."""
    proc = subprocess.Popen(
        [sys.executable, "-c", "pass"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    proc.wait()
    return proc.pid


def test_acquire_succeeds_with_no_existing_lock_file(tmp_path: Path) -> None:
    lock = SingleInstanceLock(tmp_path / "epub-automation.lock")

    lock.acquire()

    assert lock.path.exists()
    data = json.loads(lock.path.read_text())
    assert data["pid"] == os.getpid()


def test_acquire_raises_when_a_live_process_holds_the_lock(tmp_path: Path) -> None:
    lock_path = tmp_path / "epub-automation.lock"
    # This test process itself is unquestionably alive -- write a lock
    # file recording its own PID/name to simulate "another live instance".
    lock_path.write_text(
        json.dumps({"pid": os.getpid(), "process_name": psutil.Process().name()})
    )

    lock = SingleInstanceLock(lock_path)

    with pytest.raises(AlreadyRunningError):
        lock.acquire()


def test_acquire_clears_a_stale_lock_from_a_dead_pid(tmp_path: Path) -> None:
    """The core ADR-0007 proof: a lock file left behind by a process that
    has since exited (crash, forced restart, lost power) must not
    permanently block the next launch."""
    dead_pid = _spawn_and_kill_process()
    lock_path = tmp_path / "epub-automation.lock"
    lock_path.write_text(json.dumps({"pid": dead_pid, "process_name": "python"}))

    lock = SingleInstanceLock(lock_path)
    lock.acquire()  # must not raise

    data = json.loads(lock_path.read_text())
    assert data["pid"] == os.getpid()


def test_acquire_treats_pid_reuse_by_a_different_process_name_as_stale(
    tmp_path: Path,
) -> None:
    """Guards against PID reuse after a reboot: if the recorded image name
    no longer matches whatever process now holds that PID, the lock is
    stale, not held by our own (differently-named) process."""
    lock_path = tmp_path / "epub-automation.lock"
    lock_path.write_text(
        json.dumps({"pid": os.getpid(), "process_name": "some-other-process.exe"})
    )

    lock = SingleInstanceLock(lock_path)
    lock.acquire()  # must not raise -- name mismatch means "stale"

    data = json.loads(lock_path.read_text())
    assert data["pid"] == os.getpid()


def test_release_removes_the_lock_file(tmp_path: Path) -> None:
    lock = SingleInstanceLock(tmp_path / "epub-automation.lock")
    lock.acquire()

    lock.release()

    assert not lock.path.exists()


def test_release_does_not_remove_a_lock_now_held_by_someone_else(
    tmp_path: Path,
) -> None:
    """If this process's lock went stale and was already cleared/
    re-acquired by someone else, release() must not delete their lock."""
    lock_path = tmp_path / "epub-automation.lock"
    lock = SingleInstanceLock(lock_path)
    lock.acquire()

    # Simulate another process taking over the (now-different) lock.
    lock_path.write_text(json.dumps({"pid": os.getpid() + 1, "process_name": "other"}))

    lock.release()

    assert lock_path.exists()


def test_context_manager_acquires_and_releases(tmp_path: Path) -> None:
    lock_path = tmp_path / "epub-automation.lock"

    with SingleInstanceLock(lock_path):
        assert lock_path.exists()

    assert not lock_path.exists()


def test_second_cli_invocation_fails_fast_while_gui_lock_is_held(
    tmp_path: Path,
) -> None:
    """ADR-0007: the lock is shared identically by both front doors --
    simulates the GUI holding the lock and the CLI failing fast rather
    than queuing or proceeding anyway."""
    lock_path = tmp_path / "epub-automation.lock"
    gui_lock = SingleInstanceLock(lock_path)
    gui_lock.acquire()

    cli_lock = SingleInstanceLock(lock_path)
    with pytest.raises(AlreadyRunningError):
        cli_lock.acquire()
