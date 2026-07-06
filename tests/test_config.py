"""Tests for pipeline/config.py -- settings.json load/save and the
first-run-only profanity-list seeding mechanism (docs/requirements/05-
data-settings-and-logging.md §Profanity list)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline.config import (
    CURRENT_SCHEMA_VERSION,
    SettingsRepository,
    SettingsSchemaVersionError,
    load_bundled_profanity_words,
)


def test_bundled_profanity_list_loads_and_is_nonempty() -> None:
    words = load_bundled_profanity_words()

    assert len(words) > 0
    assert "damn" in words


def test_first_run_seeds_profanity_words_from_the_bundled_list(
    tmp_path: Path,
) -> None:
    repo = SettingsRepository(tmp_path / "settings.json")

    data = repo.load()

    assert data["profanity_words"] == load_bundled_profanity_words()


def test_defaults_include_both_screen_1_toggles_enabled(tmp_path: Path) -> None:
    repo = SettingsRepository(tmp_path / "settings.json")

    data = repo.load()

    assert data["fix_names"] is True
    assert data["clean_language"] is True


def test_default_ai_provider_is_none_not_gemini_or_openai(tmp_path: Path) -> None:
    """Neither provider is more 'default' than the other at the settings-
    schema level (08-open-questions-and-assumptions.md, backlog-kickoff
    confirmation) -- "none" is the pre-selected default, not a real
    provider choice."""
    repo = SettingsRepository(tmp_path / "settings.json")

    data = repo.load()

    assert data["ai_provider"] == "none"


def test_existing_settings_profanity_words_is_never_overwritten_on_reload(
    tmp_path: Path,
) -> None:
    """Her personal edits to the word list must stay independent of the
    bundled list after first run -- a future app update shipping an
    improved bundled list must not silently overwrite her customized copy.
    """
    path = tmp_path / "settings.json"
    repo = SettingsRepository(path)
    repo.load()
    repo._data["profanity_words"] = ["only-her-word"]
    repo.save()

    reloaded = SettingsRepository(path)
    data = reloaded.load()

    assert data["profanity_words"] == ["only-her-word"]


def test_save_then_load_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    repo = SettingsRepository(path)
    repo.load()
    repo._data["books_folder"] = "C:\\Users\\Mom\\Documents\\My Books"
    repo.save()

    reloaded = SettingsRepository(path)
    data = reloaded.load()

    assert data["books_folder"] == "C:\\Users\\Mom\\Documents\\My Books"


def test_save_before_load_raises() -> None:
    repo = SettingsRepository(Path("unused.json"))

    with pytest.raises(RuntimeError):
        repo.save()


def test_no_schema_version_is_treated_as_version_1(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"books_folder": "C:\\legacy"}))

    repo = SettingsRepository(path)
    data = repo.load()

    assert data["schema_version"] == CURRENT_SCHEMA_VERSION
    assert data["books_folder"] == "C:\\legacy"


def test_newer_schema_version_than_supported_raises(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"schema_version": 999}))

    repo = SettingsRepository(path)

    with pytest.raises(SettingsSchemaVersionError):
        repo.load()
