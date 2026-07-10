"""Tests for pipeline/input_validation.py -- Screen-1 file validation
(docs/requirements/06-safety-error-handling.md §Input validation)."""

from __future__ import annotations

import zipfile
from pathlib import Path

from pipeline.input_validation import (
    DEFAULT_MAX_FILES,
    DRM_MARKER,
    RejectionReason,
    check_batch_capacity,
    validate_epub_file,
)


def _make_zip(path: Path, entries: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return path


def _valid_epub(path: Path) -> Path:
    return _make_zip(
        path,
        {
            "mimetype": b"application/epub+zip",
            "content.opf": b"<?xml version='1.0'?><package></package>",
        },
    )


def test_a_well_formed_epub_passes(tmp_path: Path) -> None:
    epub = _valid_epub(tmp_path / "book.epub")

    result = validate_epub_file(epub)

    assert result.ok is True
    assert result.reason is None


def test_wrong_extension_is_rejected(tmp_path: Path) -> None:
    txt = tmp_path / "notes.txt"
    txt.write_text("hello")

    result = validate_epub_file(txt)

    assert result.ok is False
    assert result.reason is RejectionReason.NOT_EPUB
    assert "book file" in result.message


def test_extension_check_is_case_insensitive(tmp_path: Path) -> None:
    epub = _valid_epub(tmp_path / "book.EPUB")

    result = validate_epub_file(epub)

    assert result.ok is True


def test_renamed_txt_file_is_rejected_as_damaged_not_wrong_extension(
    tmp_path: Path,
) -> None:
    """A .txt file renamed to .epub passes the extension check but must
    fail real-zip validation -- exactly the case
    06-safety-error-handling.md calls out by name."""
    fake = tmp_path / "fake.epub"
    fake.write_text("this is not a zip file at all")

    result = validate_epub_file(fake)

    assert result.ok is False
    assert result.reason is RejectionReason.DAMAGED
    assert "damaged" in result.message


def test_corrupted_zip_is_rejected_as_damaged(tmp_path: Path) -> None:
    epub = _valid_epub(tmp_path / "corrupt.epub")
    # Truncate the file after it's a real zip, corrupting its central
    # directory -- a more realistic "corrupted download" than garbage bytes.
    data = epub.read_bytes()
    epub.write_bytes(data[: len(data) // 2])

    result = validate_epub_file(epub)

    assert result.ok is False
    assert result.reason is RejectionReason.DAMAGED


def test_zip_missing_mimetype_member_is_rejected_as_damaged(tmp_path: Path) -> None:
    not_really_epub = _make_zip(
        tmp_path / "notabook.epub", {"readme.txt": b"just a random zip"}
    )

    result = validate_epub_file(not_really_epub)

    assert result.ok is False
    assert result.reason is RejectionReason.DAMAGED


def test_drm_protected_epub_is_rejected_distinctly(tmp_path: Path) -> None:
    drm_epub = _make_zip(
        tmp_path / "drm.epub",
        {
            "mimetype": b"application/epub+zip",
            DRM_MARKER: b"<encryption/>",
        },
    )

    result = validate_epub_file(drm_epub)

    assert result.ok is False
    assert result.reason is RejectionReason.DRM_PROTECTED
    assert "protected" in result.message


def test_path_traversal_zip_is_rejected_as_damaged_not_leaked_as_security(
    tmp_path: Path,
) -> None:
    """Zip-safety guard failures (path traversal, zip bomb, XXE) surface
    as the same friendly "damaged" message, not a security-specific one --
    06-safety-error-handling.md never asks for that distinction, and not
    revealing "this tripped a guard" is the safer default for adversarial
    input."""
    evil = tmp_path / "evil.epub"
    with zipfile.ZipFile(evil, "w") as zf:
        zf.writestr("mimetype", b"application/epub+zip")
        zf.writestr(zipfile.ZipInfo("../../escape.txt"), b"pwned")

    result = validate_epub_file(evil)

    assert result.ok is False
    assert result.reason is RejectionReason.DAMAGED


def test_batch_capacity_allows_up_to_the_cap(tmp_path: Path) -> None:
    result = check_batch_capacity(DEFAULT_MAX_FILES - 1)

    assert result.ok is True


def test_batch_capacity_rejects_once_cap_is_reached() -> None:
    result = check_batch_capacity(DEFAULT_MAX_FILES)

    assert result.ok is False
    assert result.reason is RejectionReason.MAX_FILES_EXCEEDED
    assert str(DEFAULT_MAX_FILES) in result.message


def test_batch_capacity_honors_a_custom_max_files() -> None:
    assert check_batch_capacity(4, max_files=5).ok is True
    assert check_batch_capacity(5, max_files=5).ok is False
