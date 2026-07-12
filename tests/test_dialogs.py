"""Tests for backend/dialogs.py -- native folder-picker bridge (ADR-0006).

Never creates a real Tk window (no display in CI) -- `tk_factory` and
`ask_directory` are injected fakes (backend/dialogs.py's own testing
seams), not monkeypatched stdlib internals.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from backend.dialogs import open_folder, pick_folder


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
