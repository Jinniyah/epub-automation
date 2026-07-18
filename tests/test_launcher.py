"""Tests for launcher.py -- free-port discovery, browser-launch
retry/fallback, and the port-file bookkeeping that lets a second launch
reopen a tab to an already-running instance despite dynamic port
selection (docs/requirements/07-packaging-deployment.md §Browser-launch
fallback, docs/requirements/01-architecture.md §Single-instance
behavior)."""

from __future__ import annotations

import socket
import sys
from pathlib import Path
from typing import Any

import pytest

import launcher
from pipeline.single_instance import AlreadyRunningError


def _recording_opener(sink: list[str]) -> Any:
    def _opener(url: str) -> bool:
        sink.append(url)
        return True

    return _opener


def test_find_free_port_returns_a_bindable_port() -> None:
    port = launcher.find_free_port()

    assert 1 <= port <= 65535
    # Prove it's genuinely free right now by binding to it ourselves.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((launcher.HOST, port))


def test_find_free_port_returns_different_ports_across_calls() -> None:
    # Not a hard guarantee of the OS, but overwhelmingly true in practice
    # and worth a smoke test that we're not hardcoding anything.
    ports = {launcher.find_free_port() for _ in range(5)}
    assert len(ports) > 1


# ---------------------------------------------------------------------------
# _ensure_stdio_streams -- pythonw.exe/windowed-exe None-stdio guard
# ---------------------------------------------------------------------------


def test_ensure_stdio_streams_replaces_none_stdout_and_stderr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)

    launcher._ensure_stdio_streams()

    assert sys.stdout is not None
    assert sys.stderr is not None
    # Real bug this guards against: kokoro's own `__init__.py` calls
    # `loguru.logger.add(sys.stderr, ...)` at import time, which only
    # accepts an object with a real `.write()` -- proving that here is a
    # closer regression test than merely asserting "not None".
    sys.stdout.write("x")
    sys.stderr.write("x")


def test_ensure_stdio_streams_leaves_real_streams_untouched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_stdout = object()
    real_stderr = object()
    monkeypatch.setattr(sys, "stdout", real_stdout)
    monkeypatch.setattr(sys, "stderr", real_stderr)

    launcher._ensure_stdio_streams()

    assert sys.stdout is real_stdout
    assert sys.stderr is real_stderr


# ---------------------------------------------------------------------------
# open_browser -- retry-then-fallback
# ---------------------------------------------------------------------------


def test_open_browser_succeeds_on_first_try_without_sleeping_or_fallback() -> None:
    calls: list[str] = []

    result = launcher.open_browser(
        "http://127.0.0.1:1234/",
        opener=_recording_opener(calls),
        sleep=lambda s: (_ for _ in ()).throw(AssertionError("should not sleep")),
        show_fallback_dialog=lambda url: (_ for _ in ()).throw(
            AssertionError("should not show fallback")
        ),
    )

    assert result is True
    assert calls == ["http://127.0.0.1:1234/"]


def test_open_browser_retries_once_after_a_delay_then_succeeds() -> None:
    attempts: list[str] = []
    slept: list[float] = []

    def _opener(url: str) -> bool:
        attempts.append(url)
        return len(attempts) == 2  # fails first, succeeds second

    result = launcher.open_browser(
        "http://127.0.0.1:1234/",
        opener=_opener,
        sleep=slept.append,
        show_fallback_dialog=lambda url: (_ for _ in ()).throw(
            AssertionError("should not show fallback")
        ),
    )

    assert result is True
    assert len(attempts) == 2
    assert slept == [launcher.BROWSER_RETRY_DELAY_SECONDS]


def test_open_browser_shows_fallback_dialog_after_both_attempts_fail() -> None:
    fallback_calls: list[str] = []

    result = launcher.open_browser(
        "http://127.0.0.1:1234/",
        opener=lambda url: False,
        sleep=lambda s: None,
        show_fallback_dialog=fallback_calls.append,
    )

    assert result is False
    assert fallback_calls == ["http://127.0.0.1:1234/"]


# ---------------------------------------------------------------------------
# main() -- lock acquisition, port bookkeeping, second-launch behavior
# ---------------------------------------------------------------------------


def test_first_launch_picks_a_port_writes_it_and_opens_the_browser(
    tmp_path: Path,
) -> None:
    lock_path = tmp_path / "epub-automation.lock"
    port_file = tmp_path / "epub-automation.port"
    opened: list[str] = []
    served: list[dict[str, Any]] = []

    def _fake_serve(app: Any, *, host: str, port: int) -> None:
        served.append({"host": host, "port": port})

    result = launcher.main(
        lock_path=lock_path,
        port_file_path=port_file,
        serve_fn=_fake_serve,
        open_browser_fn=_recording_opener(opened),
    )

    assert result == 0
    assert len(served) == 1
    assert served[0]["host"] == launcher.HOST
    assert opened == [f"http://{launcher.HOST}:{served[0]['port']}/"]
    # Port file is cleaned up once the (fake, instantly-returning) serve
    # loop exits -- a real server exiting means the process is shutting
    # down, so a stale port file must not survive it.
    assert not port_file.exists()


class _AlreadyHeldLock:
    """Stands in for SingleInstanceLock -- always reports another live
    instance already holds the lock, without touching the real
    PID/process-name liveness machinery (that's ADR-0007's own test
    suite's job, not this one's)."""

    def __init__(self, path: Path) -> None:
        pass

    def acquire(self) -> None:
        raise AlreadyRunningError("already running")


def test_second_launch_reopens_a_tab_to_the_existing_port_not_a_new_server(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock_path = tmp_path / "epub-automation.lock"
    port_file = tmp_path / "epub-automation.port"
    port_file.parent.mkdir(parents=True, exist_ok=True)
    port_file.write_text("54321")
    monkeypatch.setattr(launcher, "SingleInstanceLock", _AlreadyHeldLock)

    opened: list[str] = []
    served: list[Any] = []
    result = launcher.main(
        lock_path=lock_path,
        port_file_path=port_file,
        serve_fn=lambda *a, **kw: served.append(1),
        open_browser_fn=_recording_opener(opened),
    )

    assert result == 0
    assert opened == ["http://127.0.0.1:54321/"]
    assert served == []  # never starts a second server


def test_second_launch_with_no_readable_port_file_does_not_crash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock_path = tmp_path / "epub-automation.lock"
    port_file = tmp_path / "epub-automation.port"  # never created
    monkeypatch.setattr(launcher, "SingleInstanceLock", _AlreadyHeldLock)

    opened: list[str] = []
    result = launcher.main(
        lock_path=lock_path,
        port_file_path=port_file,
        serve_fn=lambda *a, **kw: None,
        open_browser_fn=_recording_opener(opened),
    )

    assert result == 0
    assert opened == []  # nothing to open a tab to -- no crash either
