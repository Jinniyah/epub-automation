"""Adversarial tests for pipeline/sanitize_stage.py.

All ten security controls are tested with crafted malicious fixtures, not
just mocked inputs (docs/requirements/09-testing-strategy.md §Priority
coverage areas: "target near-100%, with actual crafted malicious fixture
files").

Includes a test proving the ReDoS timeout *actually fires* (not just that
the except branch exists) via a very short injected timeout against a
text with thousands of replacement candidates.
"""

from __future__ import annotations

import csv
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from pipeline.sanitize_stage import MAX_PROFANITY_WORDS, SanitizeStage, _repack_epub
from pipeline.stage import BookState

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_TIMESTAMP = datetime(2026, 1, 1, 0, 0, 0)

_CLEAN_XHTML = """\
<?xml version='1.0' encoding='UTF-8'?>
<html xmlns="http://www.w3.org/1999/xhtml">
  <body><p>This is clean text with no flagged words.</p></body>
</html>"""

_DIRTY_XHTML = """\
<?xml version='1.0' encoding='UTF-8'?>
<html xmlns="http://www.w3.org/1999/xhtml">
  <body>
    <p>This contains badword and junk text.</p>
    <p>But badwords and junkier should not be replaced.</p>
  </body>
</html>"""

# "badword" = 7 chars → "*******", "junk" = 4 chars → "****"
_WORDS = ["badword", "junk"]


def _make_stage(tmp_path: Path, *, words: list[str] = _WORDS) -> SanitizeStage:
    return SanitizeStage(
        input_folder=tmp_path,
        output_folder=tmp_path / "output",
        report_dir=tmp_path / "reports",
        profanity_words=words,
        _run_timestamp=_TIMESTAMP,
    )


def _make_epub(
    path: Path,
    content_files: dict[str, str | bytes],
    *,
    add_mimetype: bool = True,
) -> Path:
    """Build a minimal EPUB at path."""
    with zipfile.ZipFile(path, "w") as zf:
        if add_mimetype:
            zf.writestr("mimetype", "application/epub+zip")
        for name, data in content_files.items():
            zf.writestr(name, data if isinstance(data, bytes) else data.encode())
    return path


def _read_out(tmp_path: Path, arc_name: str) -> str:
    out = tmp_path / "output" / "book_cln.epub"
    with zipfile.ZipFile(out) as zf:
        return zf.read(arc_name).decode("utf-8")


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_basic_replacement_replaces_whole_words(tmp_path: Path) -> None:
    """Words in the profanity list are asterisked; partial matches are not."""
    _make_epub(tmp_path / "book.epub", {"OEBPS/chapter.xhtml": _DIRTY_XHTML})
    stage = _make_stage(tmp_path)
    result = stage.run(BookState("book", "pending", {"filename": "book.epub"}))

    assert result.status == "sanitized"
    # "badword" (1×) + "junk" (1×) = 2
    assert result.data["words_replaced"] == 2

    content = _read_out(tmp_path, "OEBPS/chapter.xhtml")
    # Standalone words replaced (check surrounding context to avoid matching substrings)
    assert "contains ******* and" in content  # "badword" (7 chars) → *******
    assert "******* and **** text" in content  # "junk" (4 chars) → ****
    assert "contains badword" not in content  # standalone replaced
    assert "and junk text" not in content  # standalone replaced
    # Partial matches must survive untouched
    assert "badwords" in content
    assert "junkier" in content


def test_clean_epub_unchanged(tmp_path: Path) -> None:
    """An EPUB with no profanity words passes through with 0 replacements."""
    _make_epub(tmp_path / "book.epub", {"OEBPS/chapter.xhtml": _CLEAN_XHTML})
    stage = _make_stage(tmp_path)
    result = stage.run(BookState("book", "pending", {"filename": "book.epub"}))

    assert result.status == "sanitized"
    assert result.data["words_replaced"] == 0


def test_case_insensitive_replacement(tmp_path: Path) -> None:
    """Replacement is case-insensitive (control 6)."""
    xhtml = """\
<?xml version='1.0' encoding='UTF-8'?>
<html xmlns="http://www.w3.org/1999/xhtml">
  <body><p>BADWORD Badword badword</p></body>
</html>"""
    _make_epub(tmp_path / "book.epub", {"OEBPS/chapter.xhtml": xhtml})
    stage = _make_stage(tmp_path, words=["badword"])
    result = stage.run(BookState("book", "pending", {"filename": "book.epub"}))

    assert result.status == "sanitized"
    assert result.data["words_replaced"] == 3


def test_tail_text_is_also_processed(tmp_path: Path) -> None:
    """Words in tail text (between closing tags and siblings) are replaced."""
    xhtml = """\
<?xml version='1.0' encoding='UTF-8'?>
<html xmlns="http://www.w3.org/1999/xhtml">
  <body><p>Hello <b>world</b> badword here.</p></body>
</html>"""
    _make_epub(tmp_path / "book.epub", {"OEBPS/chapter.xhtml": xhtml})
    stage = _make_stage(tmp_path, words=["badword"])
    result = stage.run(BookState("book", "pending", {"filename": "book.epub"}))

    assert result.status == "sanitized"
    assert result.data["words_replaced"] == 1


def test_only_xhtml_htm_html_files_processed(tmp_path: Path) -> None:
    """A .txt file containing profanity is left untouched (control 8)."""
    _make_epub(
        tmp_path / "book.epub",
        {
            "notes.txt": "badword here",
            "OEBPS/chapter.xhtml": _CLEAN_XHTML,
        },
    )
    stage = _make_stage(tmp_path, words=["badword"])
    result = stage.run(BookState("book", "pending", {"filename": "book.epub"}))

    assert result.status == "sanitized"
    assert result.data["words_replaced"] == 0

    with zipfile.ZipFile(tmp_path / "output" / "book_cln.epub") as zf:
        assert zf.read("notes.txt") == b"badword here"


def test_multiple_content_files(tmp_path: Path) -> None:
    """Words across multiple content files are all replaced and aggregated."""
    _make_epub(
        tmp_path / "book.epub",
        {
            "OEBPS/ch1.xhtml": _DIRTY_XHTML,
            "OEBPS/ch2.htm": _DIRTY_XHTML,
        },
    )
    stage = _make_stage(tmp_path)
    result = stage.run(BookState("book", "pending", {"filename": "book.epub"}))

    assert result.status == "sanitized"
    assert result.data["words_replaced"] == 4  # 2 replacements × 2 files


def test_book_id_used_when_filename_not_in_data(tmp_path: Path) -> None:
    """Falls back to book_id + '.epub' when 'filename' is absent from data."""
    _make_epub(tmp_path / "mybook.epub", {"OEBPS/ch.xhtml": _CLEAN_XHTML})
    stage = _make_stage(tmp_path)
    result = stage.run(BookState("mybook", "pending", {}))
    assert result.status == "sanitized"


# ---------------------------------------------------------------------------
# Security controls
# ---------------------------------------------------------------------------


def test_path_traversal_epub_returns_error(tmp_path: Path) -> None:
    """Control 1: an EPUB with a path-traversal entry is rejected (status=error)."""
    evil = tmp_path / "evil.epub"
    with zipfile.ZipFile(evil, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")
        zf.writestr(zipfile.ZipInfo("../../escape.txt"), b"pwned")

    stage = _make_stage(tmp_path)
    result = stage.run(BookState("evil", "pending", {"filename": "evil.epub"}))

    assert result.status == "error"
    assert "traversal" in result.data["error"].lower()


def test_zip_bomb_returns_error(tmp_path: Path) -> None:
    """Control 3: an EPUB that would exceed the extracted-size cap is rejected."""
    bomb = tmp_path / "bomb.epub"
    with zipfile.ZipFile(bomb, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")
        zf.writestr("large.txt", b"x" * 2000)

    # Set cap to 1 byte so the 2000-byte entry triggers the guard.
    stage = SanitizeStage(
        input_folder=tmp_path,
        output_folder=tmp_path / "output",
        report_dir=tmp_path / "reports",
        profanity_words=["badword"],
        max_extracted_mb=0,
        _run_timestamp=_TIMESTAMP,
    )
    result = stage.run(BookState("bomb", "pending", {"filename": "bomb.epub"}))

    assert result.status == "error"
    assert any(
        kw in result.data["error"].lower() for kw in ("bomb", "exceed", "cap", "size")
    )


def test_xxe_epub_returns_error(tmp_path: Path) -> None:
    """Control 4: an EPUB with a DOCTYPE/ENTITY declaration in XML is rejected."""
    xxe = tmp_path / "xxe.epub"
    with zipfile.ZipFile(xxe, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")
        zf.writestr(
            "content.opf",
            b"<?xml version='1.0'?>"
            b"<!DOCTYPE foo [<!ENTITY xxe SYSTEM 'file:///etc/passwd'>]>"
            b"<package>&xxe;</package>",
        )

    stage = _make_stage(tmp_path)
    result = stage.run(BookState("xxe", "pending", {"filename": "xxe.epub"}))

    assert result.status == "error"
    assert any(kw in result.data["error"] for kw in ("DOCTYPE", "ENTITY", "XXE"))


def test_profanity_list_too_large_raises(tmp_path: Path) -> None:
    """Control 5: a word list exceeding MAX_PROFANITY_WORDS raises ValueError."""
    with pytest.raises(ValueError, match="exceeding the cap"):
        SanitizeStage(
            input_folder=tmp_path,
            output_folder=tmp_path / "output",
            report_dir=tmp_path / "reports",
            profanity_words=["word"] * (MAX_PROFANITY_WORDS + 1),
        )


def test_profanity_list_empty_raises(tmp_path: Path) -> None:
    """Control 5: an empty word list raises ValueError."""
    with pytest.raises(ValueError, match="empty"):
        SanitizeStage(
            input_folder=tmp_path,
            output_folder=tmp_path / "output",
            report_dir=tmp_path / "reports",
            profanity_words=[],
        )


def test_whole_word_boundary_respected_at_ascii_level(tmp_path: Path) -> None:
    """Control 6: the word is matched only at whole-word boundaries."""
    xhtml = """\
<?xml version='1.0' encoding='UTF-8'?>
<html xmlns="http://www.w3.org/1999/xhtml">
  <body><p>standalone leads standalone2 ends 2standalone embed2standalone2</p></body>
</html>"""
    _make_epub(tmp_path / "book.epub", {"OEBPS/ch.xhtml": xhtml})
    stage = _make_stage(tmp_path, words=["standalone"])
    result = stage.run(BookState("book", "pending", {"filename": "book.epub"}))

    assert result.status == "sanitized"
    assert result.data["words_replaced"] == 1  # only the bare "standalone"

    content = _read_out(tmp_path, "OEBPS/ch.xhtml")
    # Exact standalone word replaced
    assert "**********" in content  # 10 asterisks
    # Embedded occurrences must survive
    assert "standalone2" in content
    assert "2standalone" in content
    assert "2standalone2" in content


def test_redos_timeout_actually_fires_and_is_handled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Control 6: regex.TimeoutError fires on a slow substitution and the
    stage continues rather than hanging (node is skipped, status='sanitized').

    Uses a 1-microsecond timeout injected via monkeypatch so the engine
    cannot finish 50 000 substitutions in time — proving the timeout
    actually fires, not just that the except branch exists.
    """
    import pipeline.sanitize_stage as ss

    # The regex package raises the built-in TimeoutError; 1 µs is too short
    # for 50 000 substitutions, so the timeout is guaranteed to fire.
    monkeypatch.setattr(ss, "_REDOS_TIMEOUT", 1e-6)

    many = "badword " * 50_000  # ~350 KB with 50 k matches
    xhtml = (
        "<?xml version='1.0' encoding='UTF-8'?>"
        '<html xmlns="http://www.w3.org/1999/xhtml">'
        f"<body><p>{many}</p></body></html>"
    )
    _make_epub(tmp_path / "book.epub", {"OEBPS/ch.xhtml": xhtml})
    stage = _make_stage(tmp_path, words=["badword"])
    result = stage.run(BookState("book", "pending", {"filename": "book.epub"}))

    # Stage must complete (not hang) and succeed; timed-out nodes yield 0 replacements.
    assert result.status == "sanitized"
    assert result.data["words_replaced"] == 0


def test_asterisk_replacement_length_matches_word(tmp_path: Path) -> None:
    """Control 7: replacement asterisks equal the matched word's character count."""
    xhtml = """\
<?xml version='1.0' encoding='UTF-8'?>
<html xmlns="http://www.w3.org/1999/xhtml">
  <body><p>short and averagelen here</p></body>
</html>"""
    _make_epub(tmp_path / "book.epub", {"OEBPS/ch.xhtml": xhtml})
    stage = _make_stage(tmp_path, words=["short", "averagelen"])
    result = stage.run(BookState("book", "pending", {"filename": "book.epub"}))

    assert result.status == "sanitized"
    content = _read_out(tmp_path, "OEBPS/ch.xhtml")
    assert "*****" in content  # "short"      → 5 asterisks
    assert "**********" in content  # "averagelen" → 10 asterisks


def test_mimetype_first_and_stored(tmp_path: Path) -> None:
    """Control 9: repacked EPUB has mimetype as first entry with ZIP_STORED."""
    _make_epub(tmp_path / "book.epub", {"OEBPS/ch.xhtml": _CLEAN_XHTML})
    stage = _make_stage(tmp_path)
    stage.run(BookState("book", "pending", {"filename": "book.epub"}))

    with zipfile.ZipFile(tmp_path / "output" / "book_cln.epub") as zf:
        names = zf.namelist()
        infos = zf.infolist()

    assert names[0] == "mimetype"
    assert infos[0].compress_type == zipfile.ZIP_STORED


def test_temp_dir_cleaned_up_on_success(tmp_path: Path) -> None:
    """Control 10: temp directory is removed after a successful run."""
    import tempfile

    created_dirs: list[str] = []
    original_mkdtemp = tempfile.mkdtemp

    def _tracking_mkdtemp(**kwargs: Any) -> str:
        d = str(original_mkdtemp(**kwargs))
        created_dirs.append(d)
        return d

    # Can't use monkeypatch fixture here — use direct patching instead.
    import unittest.mock as mock

    _make_epub(tmp_path / "book.epub", {"OEBPS/ch.xhtml": _CLEAN_XHTML})
    stage = _make_stage(tmp_path)

    with mock.patch(
        "pipeline.sanitize_stage.tempfile.mkdtemp", side_effect=_tracking_mkdtemp
    ):
        stage.run(BookState("book", "pending", {"filename": "book.epub"}))

    assert created_dirs, "mkdtemp was never called"
    for d in created_dirs:
        assert not Path(d).exists(), f"Temp dir not cleaned up: {d}"


def test_temp_dir_cleaned_up_on_error(tmp_path: Path) -> None:
    """Control 10: temp directory is removed even when an error occurs."""
    import unittest.mock as mock

    created_dirs: list[str] = []
    import tempfile

    original_mkdtemp = tempfile.mkdtemp

    def _tracking_mkdtemp(**kwargs: Any) -> str:
        d = str(original_mkdtemp(**kwargs))
        created_dirs.append(d)
        return d

    # Use a path-traversal EPUB so extraction fails
    evil = tmp_path / "evil.epub"
    with zipfile.ZipFile(evil, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")
        zf.writestr(zipfile.ZipInfo("../../esc.txt"), b"x")

    stage = _make_stage(tmp_path)

    with mock.patch(
        "pipeline.sanitize_stage.tempfile.mkdtemp", side_effect=_tracking_mkdtemp
    ):
        stage.run(BookState("evil", "pending", {"filename": "evil.epub"}))

    assert created_dirs
    for d in created_dirs:
        assert not Path(d).exists(), f"Temp dir not cleaned up on error: {d}"


def test_missing_mimetype_returns_error(tmp_path: Path) -> None:
    """Control 9: an EPUB without a mimetype file cannot be repacked."""
    _make_epub(
        tmp_path / "book.epub",
        {"OEBPS/ch.xhtml": _CLEAN_XHTML},
        add_mimetype=False,
    )
    stage = _make_stage(tmp_path)
    result = stage.run(BookState("book", "pending", {"filename": "book.epub"}))

    assert result.status == "error"
    assert "mimetype" in result.data["error"].lower()


# ---------------------------------------------------------------------------
# Sidecar report
# ---------------------------------------------------------------------------


def test_write_report_produces_correct_csv(tmp_path: Path) -> None:
    """write_report() produces a CSV with (Epub, File, Word, Count) columns."""
    _make_epub(tmp_path / "book.epub", {"OEBPS/ch.xhtml": _DIRTY_XHTML})
    stage = _make_stage(tmp_path)
    stage.run(BookState("book", "pending", {"filename": "book.epub"}))

    report_path = stage.write_report()

    assert report_path is not None
    assert report_path.exists()

    with open(report_path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    assert len(rows) == 2  # "badword" and "junk", one row each
    words_in_report = {r["Word"] for r in rows}
    assert words_in_report == {"badword", "junk"}
    for row in rows:
        assert row["Epub"] == "book.epub"
        assert int(row["Count"]) == 1


def test_write_report_returns_none_when_no_replacements(tmp_path: Path) -> None:
    """write_report() returns None when no profanity was found."""
    _make_epub(tmp_path / "clean.epub", {"OEBPS/ch.xhtml": _CLEAN_XHTML})
    stage = _make_stage(tmp_path)
    stage.run(BookState("clean", "pending", {"filename": "clean.epub"}))
    assert stage.write_report() is None


def test_report_path_stored_in_bookstate(tmp_path: Path) -> None:
    """BookState.data carries sanitize_detail_report for the audit log."""
    _make_epub(tmp_path / "book.epub", {"OEBPS/ch.xhtml": _DIRTY_XHTML})
    stage = _make_stage(tmp_path)
    result = stage.run(BookState("book", "pending", {"filename": "book.epub"}))

    assert "sanitize_detail_report" in result.data
    assert result.data["sanitize_detail_report"].endswith(".csv")


def test_report_accumulates_across_multiple_books(tmp_path: Path) -> None:
    """Rows from multiple books accumulate in a single per-run report."""
    for name in ("alpha.epub", "beta.epub"):
        _make_epub(tmp_path / name, {"OEBPS/ch.xhtml": _DIRTY_XHTML})

    stage = _make_stage(tmp_path)
    stage.run(BookState("alpha", "pending", {"filename": "alpha.epub"}))
    stage.run(BookState("beta", "pending", {"filename": "beta.epub"}))

    report_path = stage.write_report()
    assert report_path is not None

    with open(report_path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    epubs = {r["Epub"] for r in rows}
    assert "alpha.epub" in epubs
    assert "beta.epub" in epubs


# ---------------------------------------------------------------------------
# Stage protocol surface
# ---------------------------------------------------------------------------


def test_applies_to_respects_clean_language_setting(tmp_path: Path) -> None:
    stage = _make_stage(tmp_path)
    book = BookState("x", "pending", {})

    assert stage.applies_to(book, {"clean_language": True}) is True
    assert stage.applies_to(book, {"clean_language": False}) is False
    assert stage.applies_to(book, {}) is True  # default


def test_name_attribute_is_sanitize(tmp_path: Path) -> None:
    stage = _make_stage(tmp_path)
    assert stage.name == "sanitize"


def test_input_not_found_returns_error(tmp_path: Path) -> None:
    stage = _make_stage(tmp_path)
    result = stage.run(BookState("ghost", "pending", {"filename": "ghost.epub"}))
    assert result.status == "error"
    assert "not found" in result.data["error"].lower()


def test_output_equals_source_returns_error(tmp_path: Path) -> None:
    """If the output path would equal the source, the stage returns an error."""
    _make_epub(tmp_path / "book_cln.epub", {"OEBPS/ch.xhtml": _CLEAN_XHTML})
    # Input folder and output folder are the same; output suffix is "_cln",
    # so "book_cln.epub" → stem "book_cln" + "_cln" + ".epub" = "book_cln_cln.epub".
    # To trigger the exact collision, make stem + suffix = input stem.
    stage = SanitizeStage(
        input_folder=tmp_path,
        output_folder=tmp_path,  # same folder
        report_dir=tmp_path / "reports",
        profanity_words=["badword"],
        output_suffix="",  # empty suffix → output name == input name
        _run_timestamp=_TIMESTAMP,
    )
    result = stage.run(BookState("book_cln", "pending", {"filename": "book_cln.epub"}))
    assert result.status == "error"
    assert "source" in result.data["error"].lower()


# ---------------------------------------------------------------------------
# _repack_epub unit tests
# ---------------------------------------------------------------------------


def test_repack_mimetype_stored_and_first(tmp_path: Path) -> None:
    """_repack_epub stores mimetype as the first ZIP entry, uncompressed."""
    work = tmp_path / "work"
    work.mkdir()
    (work / "mimetype").write_text("application/epub+zip")
    (work / "content.opf").write_text("<pkg/>")

    out = tmp_path / "out.epub"
    _repack_epub(work, out)

    with zipfile.ZipFile(out) as zf:
        assert zf.namelist()[0] == "mimetype"
        assert zf.infolist()[0].compress_type == zipfile.ZIP_STORED


def test_repack_raises_on_missing_mimetype(tmp_path: Path) -> None:
    """_repack_epub raises ValueError when the mimetype file is absent."""
    work = tmp_path / "work"
    work.mkdir()
    (work / "content.opf").write_text("<pkg/>")

    with pytest.raises(ValueError, match="mimetype"):
        _repack_epub(work, tmp_path / "out.epub")
