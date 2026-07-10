"""Tests for pipeline/rename_stage.py.

Covers: FILENAME_PATTERN / build_filename (ported from epub-renamer/tests/
test_renamer.py, ADR-0014), the ADR-0016 filesystem-sanitization seam,
already-normalized skip, dry-run, name-conflict handling, and the silent
per-file NullProvider fallback on AI failure
(docs/requirements/02-pipeline-stages.md §Stage 1 Failure handling).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from ebooklib import epub

from pipeline.ai_providers.null_provider import NullProvider
from pipeline.audit_logger import AuditLogRepository
from pipeline.rename_stage import FILENAME_PATTERN, RenameStage, build_filename
from pipeline.stage import BookState

# ---------------------------------------------------------------------------
# build_filename
# ---------------------------------------------------------------------------


def test_build_filename_with_series() -> None:
    meta = {
        "author_last": "Doe",
        "author_first": "Jane",
        "series": "My Series",
        "series_number": 3,
        "title": "The Book",
    }
    assert build_filename(meta) == "Doe, Jane — My Series #03 — The Book.epub"


def test_build_filename_without_series() -> None:
    meta = {"author_last": "Doe", "author_first": "Jane", "title": "Standalone Novel"}
    assert build_filename(meta) == "Doe, Jane — Standalone Novel.epub"


def test_build_filename_series_without_number() -> None:
    meta = {
        "author_last": "Doe",
        "author_first": "Jane",
        "series": "Orphan Series",
        "series_number": None,
        "title": "Unknown Position",
    }
    assert (
        build_filename(meta) == "Doe, Jane — Orphan Series #ZZ — Unknown Position.epub"
    )


def test_build_filename_missing_author_fields() -> None:
    result = build_filename({"title": "X"})
    assert result.startswith("Unknown, Unknown")
    assert result.endswith("X.epub")


def test_build_filename_zero_pads_series_number() -> None:
    meta = {
        "author_last": "Smith",
        "author_first": "Bob",
        "series": "S",
        "series_number": 1,
        "title": "T",
    }
    assert "#01" in build_filename(meta)


def test_build_filename_sanitizes_illegal_characters_in_title() -> None:
    """ADR-0016: real book metadata routinely contains Windows-illegal
    characters -- each component is sanitized before assembly."""
    meta = {
        "author_last": "Preston",
        "author_first": "Douglas",
        "title": "Who Framed Roger Rabbit?",
    }
    result = build_filename(meta)
    assert "?" not in result
    assert result == "Preston, Douglas — Who Framed Roger Rabbit.epub"


def test_build_filename_sanitizes_colon_in_series() -> None:
    meta = {
        "author_last": "Doe",
        "author_first": "Jane",
        "series": "Spider-Man: Homecoming",
        "series_number": 2,
        "title": "T",
    }
    result = build_filename(meta)
    assert ":" not in result


# ---------------------------------------------------------------------------
# FILENAME_PATTERN -- already-normalized detection
# ---------------------------------------------------------------------------


def test_pattern_matches_series_format() -> None:
    assert FILENAME_PATTERN.match("Cornwell, Patricia — Kay Scarpetta #13 — Trace.epub")


def test_pattern_matches_standalone_format() -> None:
    assert FILENAME_PATTERN.match("Doe, Jane — Standalone Novel.epub")


def test_pattern_rejects_raw_filename() -> None:
    name = "Trace_ Scarpetta (Book 13) (Kay Scarpetta)_nodrm.epub"
    assert not FILENAME_PATTERN.match(name)


# ---------------------------------------------------------------------------
# RenameStage -- fixtures
# ---------------------------------------------------------------------------


def _make_epub(
    path: Path, *, title: str = "Some Title", author: str = "Some Author"
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    book = epub.EpubBook()
    book.set_identifier("id123")
    book.set_title(title)
    book.set_language("en")
    book.add_author(author)

    chapter = epub.EpubHtml(title="Chapter 1", file_name="chap1.xhtml", lang="en")
    chapter.content = "<html><body><p>Some sample book content.</p></body></html>"
    book.add_item(chapter)
    book.toc = (chapter,)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", chapter]

    epub.write_epub(str(path), book)
    return path


class _FakeProvider:
    def __init__(
        self, result: dict[str, Any] | None = None, raise_on_call: bool = False
    ) -> None:
        self._result = result or {}
        self._raise = raise_on_call

    def identify_book(
        self, filename: str, metadata: dict[str, Any], text_sample: str
    ) -> dict[str, Any]:
        if self._raise:
            raise RuntimeError("simulated AI provider failure")
        return self._result


def _make_stage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    fake_provider: _FakeProvider | None = None,
    dry_run: bool = False,
) -> tuple[RenameStage, AuditLogRepository]:
    def fake_get_provider(name: str, api_key: str = "") -> Any:
        if (name or "none").lower() == "none" or fake_provider is None:
            return NullProvider()
        return fake_provider

    monkeypatch.setattr("pipeline.rename_stage.get_provider", fake_get_provider)

    audit_log = AuditLogRepository(tmp_path / "audit_log.csv")
    stage = RenameStage(
        input_folder=tmp_path / "input",
        output_folder=tmp_path / "output",
        audit_log=audit_log,
        ai_provider="fake" if fake_provider else "none",
        ai_api_key="key",
        dry_run=dry_run,
    )
    return stage, audit_log


# ---------------------------------------------------------------------------
# RenameStage.applies_to
# ---------------------------------------------------------------------------


def test_construction_falls_back_to_null_provider_on_bad_config(
    tmp_path: Path,
) -> None:
    """A misconfigured provider (e.g. `ai_provider="openai"` with no key)
    must not crash the stage's construction -- it falls back to
    NullProvider for the whole run, same as a per-file runtime failure."""
    audit_log = AuditLogRepository(tmp_path / "audit_log.csv")
    stage = RenameStage(
        input_folder=tmp_path / "input",
        output_folder=tmp_path / "output",
        audit_log=audit_log,
        ai_provider="openai",
        ai_api_key="",  # missing key -> OpenAIProvider() raises ValueError
    )
    assert isinstance(stage._provider, NullProvider)


def test_applies_to_respects_fix_names_toggle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stage, _ = _make_stage(tmp_path, monkeypatch)
    book = BookState("b1")

    assert stage.applies_to(book, {"fix_names": True}) is True
    assert stage.applies_to(book, {"fix_names": False}) is False
    assert stage.applies_to(book, {}) is True  # default true


# ---------------------------------------------------------------------------
# RenameStage.run -- happy paths
# ---------------------------------------------------------------------------


def test_run_renames_using_null_provider_metadata_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _make_epub(tmp_path / "input" / "book.epub", title="My Book", author="Jane Doe")
    stage, audit_log = _make_stage(tmp_path, monkeypatch)

    result = stage.run(BookState("b1", "pending", {"filename": "book.epub"}))

    assert result.status == "renamed"
    out_path = tmp_path / "output" / result.data["filename"]
    assert out_path.exists()
    assert result.data["title"] == "My Book"

    rows = audit_log.read_all()
    assert len(rows) == 1
    assert rows[0]["ai_used"] == "no"
    assert rows[0]["renamed"] == "yes"


def test_run_enriches_with_ai_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _make_epub(tmp_path / "input" / "book.epub", title="Trace", author="unused")
    fake = _FakeProvider(
        {
            "title": "Trace",
            "author_first": "Patricia",
            "author_last": "Cornwell",
            "series": "Kay Scarpetta",
            "series_number": 13,
        }
    )
    stage, audit_log = _make_stage(tmp_path, monkeypatch, fake_provider=fake)

    result = stage.run(BookState("b1", "pending", {"filename": "book.epub"}))

    assert result.status == "renamed"
    expected_name = "Cornwell, Patricia — Kay Scarpetta #13 — Trace.epub"
    assert result.data["filename"] == expected_name
    assert (tmp_path / "output" / result.data["filename"]).exists()

    rows = audit_log.read_all()
    assert rows[0]["ai_used"] == "yes"
    assert rows[0]["author"] == "Patricia Cornwell"


def test_run_sanitizes_illegal_characters_from_ai_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR-0016 end-to-end: AI-returned metadata with Windows-illegal
    characters still produces a filesystem-safe filename."""
    _make_epub(tmp_path / "input" / "book.epub")
    fake = _FakeProvider({"title": "Who Framed Roger Rabbit?", "author_last": "X"})
    stage, _ = _make_stage(tmp_path, monkeypatch, fake_provider=fake)

    result = stage.run(BookState("b1", "pending", {"filename": "book.epub"}))

    assert "?" not in result.data["filename"]
    assert (tmp_path / "output" / result.data["filename"]).exists()


# ---------------------------------------------------------------------------
# RenameStage.run -- already normalized
# ---------------------------------------------------------------------------


def test_run_skips_ai_call_for_already_normalized_filename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    normalized_name = "Doe, Jane — Standalone Novel.epub"
    _make_epub(tmp_path / "input" / normalized_name)
    fake = _FakeProvider(raise_on_call=True)  # would blow up if ever called
    stage, audit_log = _make_stage(tmp_path, monkeypatch, fake_provider=fake)

    result = stage.run(BookState("b1", "pending", {"filename": normalized_name}))

    assert result.status == "renamed"
    assert result.data["filename"] == normalized_name
    assert (tmp_path / "output" / normalized_name).exists()

    rows = audit_log.read_all()
    assert rows[0]["skipped_reason"] == "already_normalized"
    assert rows[0]["ai_used"] == "no"
    assert rows[0]["renamed"] == "no"


# ---------------------------------------------------------------------------
# RenameStage.run -- AI failure fallback
# ---------------------------------------------------------------------------


def test_run_falls_back_to_null_provider_silently_on_ai_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _make_epub(tmp_path / "input" / "book.epub", title="Fallback Title")
    fake = _FakeProvider(raise_on_call=True)
    stage, audit_log = _make_stage(tmp_path, monkeypatch, fake_provider=fake)

    result = stage.run(BookState("b1", "pending", {"filename": "book.epub"}))

    # Never blocks the batch -- falls back to EPUB-only metadata.
    assert result.status == "renamed"
    assert result.data["title"] == "Fallback Title"

    rows = audit_log.read_all()
    assert rows[0]["ai_used"] == "no"


# ---------------------------------------------------------------------------
# RenameStage.run -- dry run
# ---------------------------------------------------------------------------


def test_dry_run_writes_no_file_but_logs_proposed_rename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _make_epub(tmp_path / "input" / "book.epub", title="My Book", author="Jane Doe")
    stage, audit_log = _make_stage(tmp_path, monkeypatch, dry_run=True)

    result = stage.run(BookState("b1", "pending", {"filename": "book.epub"}))

    assert result.status == "renamed"
    assert result.data["filename"] == "book.epub"  # unchanged, no copy made
    assert not (tmp_path / "output").exists() or not any(
        (tmp_path / "output").iterdir()
    )

    rows = audit_log.read_all()
    assert rows[0]["skipped_reason"] == "dry_run"
    assert rows[0]["renamed"] == "no"


# ---------------------------------------------------------------------------
# RenameStage.run -- name conflict
# ---------------------------------------------------------------------------


def test_name_conflict_keeps_original_filename_instead_of_overwriting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _make_epub(tmp_path / "input" / "book.epub", title="My Book", author="Jane Doe")
    # NullProvider only passes the title through (never splits an author
    # string into first/last), so this is the exact name RenameStage will
    # compute for this fixture -- derived via build_filename() rather than
    # hardcoded, so this test doesn't depend on NullProvider's author
    # behavior staying the same.
    conflict_name = build_filename({"title": "My Book"})
    (tmp_path / "output").mkdir(parents=True)
    (tmp_path / "output" / conflict_name).write_text("already here")

    stage, audit_log = _make_stage(tmp_path, monkeypatch)
    result = stage.run(BookState("b1", "pending", {"filename": "book.epub"}))

    assert result.status == "renamed"
    assert result.data["filename"] == "book.epub"  # kept original name
    assert (tmp_path / "output" / "book.epub").exists()
    # The pre-existing conflicting file is untouched.
    assert (tmp_path / "output" / conflict_name).read_text() == "already here"

    rows = audit_log.read_all()
    assert rows[0]["skipped_reason"] == "name_conflict"
    assert rows[0]["renamed"] == "no"


# ---------------------------------------------------------------------------
# RenameStage.run -- error paths
# ---------------------------------------------------------------------------


def test_run_errors_when_input_file_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stage, _ = _make_stage(tmp_path, monkeypatch)

    result = stage.run(BookState("b1", "pending", {"filename": "missing.epub"}))

    assert result.status == "error"
    assert "not found" in result.data["error"]


def test_run_errors_on_corrupted_epub(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bad_path = tmp_path / "input" / "corrupt.epub"
    bad_path.parent.mkdir(parents=True)
    bad_path.write_bytes(b"not a real zip file")

    stage, audit_log = _make_stage(tmp_path, monkeypatch)
    result = stage.run(BookState("b1", "pending", {"filename": "corrupt.epub"}))

    assert result.status == "error"
    rows = audit_log.read_all()
    assert rows[0]["skipped_reason"] == "epub_read_error"
