"""TDD tests for pipeline/atomic_write.py (docs/requirements/09-testing-
strategy.md §TDD workflow explicitly calls this out: "a real test that
simulates a crash mid-write is the actual proof").
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline.atomic_write import atomic_read_json, atomic_write_json


def test_write_then_read_round_trips(tmp_path: Path) -> None:
    target = tmp_path / "settings.json"
    atomic_write_json(target, {"a": 1, "b": [1, 2, 3]})

    assert atomic_read_json(target) == {"a": 1, "b": [1, 2, 3]}


def test_read_missing_file_returns_none(tmp_path: Path) -> None:
    assert atomic_read_json(tmp_path / "does_not_exist.json") is None


def test_write_creates_parent_directories(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "dir" / "state.json"
    atomic_write_json(target, {"ok": True})

    assert atomic_read_json(target) == {"ok": True}


def test_no_temp_file_left_behind_after_successful_write(tmp_path: Path) -> None:
    target = tmp_path / "settings.json"
    atomic_write_json(target, {"a": 1})

    leftovers = list(tmp_path.glob(".*.tmp"))
    assert leftovers == []


def test_overwrite_replaces_old_content_atomically(tmp_path: Path) -> None:
    target = tmp_path / "state.json"
    atomic_write_json(target, {"version": 1})
    atomic_write_json(target, {"version": 2})

    assert atomic_read_json(target) == {"version": 2}


def test_crash_mid_write_leaves_original_file_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The core write-safety proof: if the process dies after the temp
    file is written but *before* the atomic rename, the real file at
    `path` must be exactly what it was before this write was attempted --
    never truncated, never half-old/half-new.
    """
    target = tmp_path / "settings.json"
    atomic_write_json(target, {"books_folder": "C:\\original"})
    original_bytes = target.read_bytes()

    def boom(*args: object, **kwargs: object) -> None:
        raise OSError("simulated crash: power loss mid-write")

    monkeypatch.setattr("os.replace", boom)

    with pytest.raises(OSError):
        atomic_write_json(target, {"books_folder": "C:\\new-value"})

    # The live file is untouched -- still valid JSON, still the old value.
    assert target.read_bytes() == original_bytes
    assert json.loads(target.read_text()) == {"books_folder": "C:\\original"}


def test_crash_mid_write_cleans_up_its_temp_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "settings.json"

    def boom(*args: object, **kwargs: object) -> None:
        raise OSError("simulated crash")

    monkeypatch.setattr("os.replace", boom)

    with pytest.raises(OSError):
        atomic_write_json(target, {"a": 1})

    # No file at the target path (first-ever write never completed)...
    assert not target.exists()
    # ...and no orphaned .tmp file left behind either.
    assert list(tmp_path.glob(".*.tmp")) == []


def test_crash_during_json_serialization_leaves_no_partial_file(
    tmp_path: Path,
) -> None:
    """A value that can't be JSON-serialized (e.g. a stray non-serializable
    object landing in settings by mistake) must fail loudly before
    anything is renamed over the real file -- not produce a truncated
    settings.json."""
    target = tmp_path / "settings.json"
    atomic_write_json(target, {"a": 1})

    with pytest.raises(TypeError):
        atomic_write_json(target, {"bad": object()})

    # Original file (from the first, successful write) is untouched.
    assert atomic_read_json(target) == {"a": 1}
    assert list(tmp_path.glob(".*.tmp")) == []
