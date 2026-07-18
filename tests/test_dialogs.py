"""Tests for backend/dialogs.py -- native folder-picker bridge (ADR-0006).

Never creates a real Tk window (no display in CI) -- `tk_factory` and
`ask_directory` are injected fakes (backend/dialogs.py's own testing
seams), not monkeypatched stdlib internals.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import pytest

from backend.dialogs import open_folder, pick_folder, request_folder_pick


class _FakeRoot:
    def __init__(self) -> None:
        self.withdrawn = False
        self.topmost: bool | None = None
        self.destroyed = False

    def withdraw(self) -> None:
        self.withdrawn = True

    def attributes(self, name: str, value: bool) -> None:
        assert name == "-topmost"
        self.topmost = value

    def destroy(self) -> None:
        self.destroyed = True


@pytest.fixture
def fake_root() -> _FakeRoot:
    return _FakeRoot()


def test_pick_folder_returns_the_chosen_path(fake_root: _FakeRoot) -> None:
    result = pick_folder(
        tk_factory=lambda: fake_root,
        ask_directory=lambda **kwargs: "C:\\Users\\Mom\\Books",
    )

    assert result == "C:\\Users\\Mom\\Books"


def test_pick_folder_returns_none_when_cancelled(fake_root: _FakeRoot) -> None:
    result = pick_folder(
        tk_factory=lambda: fake_root, ask_directory=lambda **kwargs: ""
    )

    assert result is None


def test_pick_folder_hides_and_raises_the_hidden_root_above_the_browser(
    fake_root: _FakeRoot,
) -> None:
    pick_folder(tk_factory=lambda: fake_root, ask_directory=lambda **kwargs: "")

    assert fake_root.withdrawn is True
    assert fake_root.topmost is True
    assert fake_root.destroyed is True


def test_pick_folder_destroys_the_root_even_if_the_dialog_raises(
    fake_root: _FakeRoot,
) -> None:
    def _boom(**kwargs: Any) -> str:
        raise RuntimeError("dialog failed")

    with pytest.raises(RuntimeError):
        pick_folder(tk_factory=lambda: fake_root, ask_directory=_boom)

    assert fake_root.destroyed is True


def test_pick_folder_passes_title_and_initial_dir_through(fake_root: _FakeRoot) -> None:
    captured: dict[str, Any] = {}

    def _capture(**kwargs: Any) -> str:
        captured.update(kwargs)
        return ""

    pick_folder(
        title="Where are your books?",
        initial_dir="C:\\Books",
        tk_factory=lambda: fake_root,
        ask_directory=_capture,
    )

    assert captured["title"] == "Where are your books?"
    assert captured["initialdir"] == "C:\\Books"
    assert captured["parent"] is fake_root


def test_pick_folder_omits_initialdir_when_not_given(fake_root: _FakeRoot) -> None:
    captured: dict[str, Any] = {}

    def _capture(**kwargs: Any) -> str:
        captured.update(kwargs)
        return ""

    pick_folder(tk_factory=lambda: fake_root, ask_directory=_capture)

    assert "initialdir" not in captured
    assert captured["title"] == "Choose a folder"


# ---------------------------------------------------------------------------
# request_folder_pick() -- the thread-safe wrapper (docs/BACKLOG.md
# Epic 10 Phase A). The real bug this exists to fix (a route handler
# calling pick_folder() directly, on a fresh waitress worker thread every
# time, could hang forever) isn't reproducible with fakes -- these tests
# instead verify the specific property that fixes it: every call is
# actually serviced by the *same* background thread, not a new one per
# call, which is what real tkinter needs.
# ---------------------------------------------------------------------------


def test_request_folder_pick_returns_the_chosen_path(fake_root: _FakeRoot) -> None:
    result = request_folder_pick(
        tk_factory=lambda: fake_root,
        ask_directory=lambda **kwargs: "C:\\Users\\Mom\\Books",
    )

    assert result == "C:\\Users\\Mom\\Books"


def test_request_folder_pick_returns_none_when_cancelled(fake_root: _FakeRoot) -> None:
    result = request_folder_pick(
        tk_factory=lambda: fake_root, ask_directory=lambda **kwargs: ""
    )

    assert result is None


def test_request_folder_pick_passes_title_and_initial_dir_through(
    fake_root: _FakeRoot,
) -> None:
    captured: dict[str, Any] = {}

    def _capture(**kwargs: Any) -> str:
        captured.update(kwargs)
        return ""

    request_folder_pick(
        title="Where are your books?",
        initial_dir="C:\\Books",
        tk_factory=lambda: fake_root,
        ask_directory=_capture,
    )

    assert captured["title"] == "Where are your books?"
    assert captured["initialdir"] == "C:\\Books"


def test_request_folder_pick_reuses_the_same_background_thread_every_call() -> None:
    """The actual property that fixes the real bug (docs/BACKLOG.md
    Epic 10 Phase A): every call must be serviced by the same thread,
    never a fresh one -- unlike calling pick_folder() directly from a
    Flask route, which lands on whichever waitress worker thread handled
    that particular request."""
    seen_thread_ids: list[int | None] = []

    def _capture_thread(**kwargs: Any) -> str:
        seen_thread_ids.append(threading.get_ident())
        return ""

    request_folder_pick(tk_factory=lambda: _FakeRoot(), ask_directory=_capture_thread)
    request_folder_pick(tk_factory=lambda: _FakeRoot(), ask_directory=_capture_thread)
    request_folder_pick(tk_factory=lambda: _FakeRoot(), ask_directory=_capture_thread)

    assert len(seen_thread_ids) == 3
    assert len(set(seen_thread_ids)) == 1  # all three ran on the same thread
    assert (
        seen_thread_ids[0] != threading.get_ident()
    )  # a real background thread, not this one


def test_request_folder_pick_survives_a_dialog_exception_then_still_answers() -> None:
    """The background worker thread must never die or get stuck just
    because one dialog call raised -- a caller waiting on the response
    queue would otherwise hang forever, exactly the bug class this
    wrapper exists to fix in the first place."""

    def _boom(**kwargs: Any) -> str:
        raise RuntimeError("dialog failed")

    first = request_folder_pick(tk_factory=lambda: _FakeRoot(), ask_directory=_boom)
    assert first is None  # the exception is swallowed, not propagated to the caller

    second = request_folder_pick(
        tk_factory=lambda: _FakeRoot(), ask_directory=lambda **kwargs: "C:\\Books"
    )
    assert second == "C:\\Books"  # the same worker thread is still alive and answering


def test_open_folder_calls_the_opener_for_an_existing_directory(tmp_path: Path) -> None:
    calls: list[str] = []

    result = open_folder(str(tmp_path), opener=calls.append)

    assert result is True
    assert calls == [str(tmp_path)]


def test_open_folder_returns_false_for_a_missing_path(tmp_path: Path) -> None:
    calls: list[str] = []

    result = open_folder(str(tmp_path / "does-not-exist"), opener=calls.append)

    assert result is False
    assert calls == []


def test_open_folder_returns_false_for_a_file_not_a_directory(tmp_path: Path) -> None:
    file_path = tmp_path / "file.txt"
    file_path.write_text("hi")
    calls: list[str] = []

    result = open_folder(str(file_path), opener=calls.append)

    assert result is False
    assert calls == []
