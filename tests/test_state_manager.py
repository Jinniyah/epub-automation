"""Tests for pipeline/state_manager.py -- the Repository wrapper and its
schema_version migration/mismatch policy (docs/requirements/05-data-
settings-and-logging.md §Schema versioning)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline.state_manager import (
    CURRENT_SCHEMA_VERSION,
    StateRepository,
    StateSchemaVersionError,
)


def test_load_with_no_existing_file_returns_default_state(tmp_path: Path) -> None:
    repo = StateRepository(tmp_path / "state.json")

    data = repo.load()

    assert data == {"schema_version": CURRENT_SCHEMA_VERSION, "books": {}}


def test_mark_and_check_stage_complete(tmp_path: Path) -> None:
    repo = StateRepository(tmp_path / "state.json")
    repo.load()

    assert repo.is_stage_complete("b1", "sanitize") is False

    repo.mark_stage_complete("b1", "sanitize")

    assert repo.is_stage_complete("b1", "sanitize") is True
    # A different stage on the same book is unaffected.
    assert repo.is_stage_complete("b1", "audio") is False


def test_reset_stage_marks_it_incomplete_again(tmp_path: Path) -> None:
    repo = StateRepository(tmp_path / "state.json")
    repo.load()
    repo.mark_stage_complete("b1", "audio")

    repo.reset_stage("b1", "audio")

    assert repo.is_stage_complete("b1", "audio") is False


def test_incomplete_book_ids_is_empty_for_a_fresh_state(tmp_path: Path) -> None:
    repo = StateRepository(tmp_path / "state.json")
    repo.load()

    assert repo.incomplete_book_ids() == []


def test_incomplete_book_ids_lists_a_book_still_missing_the_cleanup_stage(
    tmp_path: Path,
) -> None:
    repo = StateRepository(tmp_path / "state.json")
    repo.load()
    repo.mark_stage_complete("b1", "rename")
    repo.mark_stage_complete("b1", "sanitize")
    repo.mark_stage_complete("b1", "audio")
    # "cleanup" -- the terminal, ADR-0017 marker -- was never reached.

    assert repo.incomplete_book_ids() == ["b1"]


def test_incomplete_book_ids_excludes_a_book_that_reached_cleanup(
    tmp_path: Path,
) -> None:
    repo = StateRepository(tmp_path / "state.json")
    repo.load()
    repo.mark_stage_complete("b1", "rename")
    repo.mark_stage_complete("b1", "sanitize")
    repo.mark_stage_complete("b1", "audio")
    repo.mark_stage_complete("b1", "cleanup")

    assert repo.incomplete_book_ids() == []


def test_incomplete_book_ids_reflects_a_reset_cleanup_stage(tmp_path: Path) -> None:
    repo = StateRepository(tmp_path / "state.json")
    repo.load()
    repo.mark_stage_complete("b1", "cleanup")
    repo.reset_stage("b1", "cleanup")

    assert repo.incomplete_book_ids() == ["b1"]


def test_save_then_load_round_trips_through_disk(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    repo = StateRepository(path)
    repo.load()
    repo.mark_stage_complete("b1", "rename")
    repo.save()

    reloaded = StateRepository(path)
    reloaded.load()

    assert reloaded.is_stage_complete("b1", "rename") is True


def test_save_before_load_raises() -> None:
    repo = StateRepository(Path("unused.json"))

    with pytest.raises(RuntimeError):
        repo.save()


def test_file_with_no_schema_version_is_treated_as_version_1(
    tmp_path: Path,
) -> None:
    """Forward-compatible with any real install that predates the
    schema_version field (05-data-settings-and-logging.md §Schema
    versioning)."""
    path = tmp_path / "state.json"
    path.write_text(json.dumps({"books": {"b1": {"audio": {"status": "complete"}}}}))

    repo = StateRepository(path)
    data = repo.load()

    assert data["schema_version"] == CURRENT_SCHEMA_VERSION
    assert repo.is_stage_complete("b1", "audio") is True


def test_newer_schema_version_than_supported_raises(tmp_path: Path) -> None:
    """A newer schema_version than the running app expects (e.g. a
    downgrade, or drift between installs) must not be guessed at."""
    path = tmp_path / "state.json"
    path.write_text(json.dumps({"schema_version": 999, "books": {}}))

    repo = StateRepository(path)

    with pytest.raises(StateSchemaVersionError):
        repo.load()


def test_matching_schema_version_loads_normally(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": CURRENT_SCHEMA_VERSION,
                "books": {"b1": {"sanitize": {"status": "complete"}}},
            }
        )
    )

    repo = StateRepository(path)
    repo.load()

    assert repo.is_stage_complete("b1", "sanitize") is True
