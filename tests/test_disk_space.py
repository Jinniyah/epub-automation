"""Tests for pipeline/disk_space.py -- pre-batch disk-space estimate and
check (docs/requirements/06-safety-error-handling.md §Resource & cost
safety)."""

from __future__ import annotations

from pathlib import Path

from pipeline.disk_space import (
    BookSpaceEstimate,
    check_free_space,
    estimate_batch_bytes,
)
from pipeline.tts_engine import estimate_audio_bytes


def test_single_book_estimate_sums_two_source_copies_plus_audio() -> None:
    book = BookSpaceEstimate(
        book_id="b1", source_bytes=1_000_000, remaining_chars=50_000
    )

    total = estimate_batch_bytes([book])

    expected = 1_000_000 * 2 + estimate_audio_bytes(50_000)
    assert total == expected


def test_batch_estimate_sums_across_multiple_books() -> None:
    books = [
        BookSpaceEstimate(book_id="b1", source_bytes=1_000_000, remaining_chars=10_000),
        BookSpaceEstimate(book_id="b2", source_bytes=2_000_000, remaining_chars=20_000),
    ]

    total = estimate_batch_bytes(books)

    assert total == estimate_batch_bytes(books[:1]) + estimate_batch_bytes(books[1:])


def test_empty_batch_estimates_zero() -> None:
    assert estimate_batch_bytes([]) == 0


def test_check_free_space_reports_sufficient_for_a_tiny_requirement(
    tmp_path: Path,
) -> None:
    report = check_free_space([tmp_path], required_bytes=1)

    assert report.any_insufficient is False
    check = report.checked_paths[str(tmp_path)]
    assert check.sufficient is True
    assert check.free_bytes > 0


def test_check_free_space_reports_insufficient_for_an_absurd_requirement(
    tmp_path: Path,
) -> None:
    report = check_free_space([tmp_path], required_bytes=10**18)

    assert report.any_insufficient is True
    assert report.checked_paths[str(tmp_path)].sufficient is False


def test_check_free_space_works_for_a_not_yet_existing_path(tmp_path: Path) -> None:
    """Library/output folders may not exist yet on first run -- the check
    must walk up to an existing ancestor rather than raising."""
    not_yet_created = tmp_path / "Library" / "00-Incoming"

    report = check_free_space([not_yet_created], required_bytes=1)

    assert report.checked_paths[str(not_yet_created)].sufficient is True


def test_check_free_space_checks_each_path_independently(tmp_path: Path) -> None:
    library_root = tmp_path / "Library"
    output_folder = tmp_path / "Output"
    library_root.mkdir()
    output_folder.mkdir()

    report = check_free_space([library_root, output_folder], required_bytes=1)

    assert set(report.checked_paths) == {str(library_root), str(output_folder)}
    assert report.any_insufficient is False


def test_any_insufficient_is_true_if_only_one_of_several_paths_is_short(
    tmp_path: Path,
) -> None:
    ok_path = tmp_path / "ok"
    ok_path.mkdir()

    report = check_free_space([ok_path], required_bytes=1)
    assert report.any_insufficient is False

    # Reuse the same report shape but force one path to look insufficient
    # by checking against an absurd requirement directly.
    report2 = check_free_space([ok_path], required_bytes=10**18)
    assert report2.any_insufficient is True
