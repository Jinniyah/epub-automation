"""Tests for pipeline/audit_logger.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.audit_logger import COLUMNS, AuditLogRepository


def test_append_creates_file_with_header(tmp_path: Path) -> None:
    repo = AuditLogRepository(tmp_path / "audit_log.csv")

    repo.append({"stage": "sanitize", "original_filename": "Fated.epub"})

    rows = repo.read_all()
    assert len(rows) == 1
    assert rows[0]["stage"] == "sanitize"
    assert rows[0]["original_filename"] == "Fated.epub"
    # Every column exists on the row even when not supplied -- written blank.
    assert set(rows[0].keys()) == set(COLUMNS)
    assert rows[0]["voice"] == ""


def test_append_multiple_rows_preserves_order(tmp_path: Path) -> None:
    repo = AuditLogRepository(tmp_path / "audit_log.csv")

    repo.append({"stage": "rename", "original_filename": "a.epub"})
    repo.append({"stage": "sanitize", "original_filename": "a.epub"})
    repo.append({"stage": "audio", "original_filename": "a.epub", "voice": "am_george"})

    rows = repo.read_all()
    assert [r["stage"] for r in rows] == ["rename", "sanitize", "audio"]
    assert rows[2]["voice"] == "am_george"


def test_unknown_column_raises_instead_of_silently_dropping(tmp_path: Path) -> None:
    repo = AuditLogRepository(tmp_path / "audit_log.csv")

    with pytest.raises(ValueError):
        repo.append({"stage": "sanitize", "totally_made_up_column": "oops"})


def test_read_all_on_nonexistent_file_returns_empty_list(tmp_path: Path) -> None:
    repo = AuditLogRepository(tmp_path / "audit_log.csv")

    assert repo.read_all() == []


def test_ai_api_key_is_not_an_allowed_column(tmp_path: Path) -> None:
    """Secrets must never be writable to the audit log (05-data-settings-
    and-logging.md's explicit exclusion) -- enforced here structurally: it
    simply isn't in COLUMNS, so passing it raises like any other typo."""
    repo = AuditLogRepository(tmp_path / "audit_log.csv")

    with pytest.raises(ValueError):
        repo.append({"stage": "rename", "ai_api_key": "sk-should-never-be-here"})
