"""Tests for pipeline/retag_stage.py.

Covers: folder-name parsing (old standalone-tool shape and this pipeline's
own build_filename() shape), MP3 filename-suffix -> chapter-title/track
derivation, ID3 tag rewriting, the override-vs-parsed-metadata precedence
rule, and -- the star fix for this epic -- a regression test proving the
containing folder actually gets renamed, not just the MP3s inside it
(docs/requirements/09-testing-strategy.md §Priority coverage areas).
"""

from __future__ import annotations

from pathlib import Path

from mutagen.id3 import APIC, ID3, TALB, TIT2, TPE1

from pipeline.audit_logger import AuditLogRepository
from pipeline.retag_stage import (
    RetagStage,
    build_album_tag,
    build_title_tag,
    chapter_title_from_stem,
    parse_folder_metadata,
    parse_stem_metadata,
    track_number_from_tag,
)
from pipeline.stage import BookState

# ---------------------------------------------------------------------------
# parse_stem_metadata / parse_folder_metadata
# ---------------------------------------------------------------------------


def test_parse_stem_metadata_with_series() -> None:
    meta = parse_stem_metadata("Jacka, Benedict — Alex Verus #01 — Fated")
    assert meta == {
        "author_last": "Jacka",
        "author_first": "Benedict",
        "title": "Fated",
        "series": "Alex Verus",
        "series_number": "01",
    }


def test_parse_stem_metadata_without_series() -> None:
    meta = parse_stem_metadata("Doe, Jane — Standalone Novel")
    assert meta == {
        "author_last": "Doe",
        "author_first": "Jane",
        "title": "Standalone Novel",
        "series": None,
        "series_number": None,
    }


def test_parse_stem_metadata_bare_trailing_series_number() -> None:
    meta = parse_stem_metadata("Doe, Jane — Alex Verus 12 — Fated")
    assert meta is not None
    assert meta["series"] == "Alex Verus"
    assert meta["series_number"] == "12"


def test_parse_stem_metadata_too_ambiguous_returns_none() -> None:
    assert parse_stem_metadata("A — B — C — D") is None


def test_parse_folder_metadata_new_format() -> None:
    meta = parse_folder_metadata("Jacka, Benedict — Alex Verus #01 — Fated")
    assert meta is not None
    assert meta["author_last"] == "Jacka"
    assert meta["author_first"] == "Benedict"
    assert meta["series"] == "Alex Verus"
    assert meta["series_number"] == "01"
    assert meta["title"] == "Fated"


def test_parse_folder_metadata_old_format_with_leading_code_and_parenthetical() -> None:
    """Old epub-to-audio standalone-tool shape: 'AV01 - ' code prefix,
    series described parenthetically in the title."""
    meta = parse_folder_metadata("AV01 - Benedict, Jacka — Fated (Alex Verus Book 1)")
    assert meta is not None
    assert meta["title"] == "Fated"
    assert meta["series"] == "Alex Verus"
    assert meta["series_number"] == "1"


def test_parse_folder_metadata_old_format_no_series_number() -> None:
    meta = parse_folder_metadata("Benedict, Jacka — Risen (An Alex Verus Novel)")
    assert meta is not None
    assert meta["title"] == "Risen"
    assert meta["series"] == "Alex Verus"
    assert meta["series_number"] is None


def test_parse_folder_metadata_unparseable_returns_none() -> None:
    assert parse_folder_metadata("just some random folder name here") is None


# ---------------------------------------------------------------------------
# chapter_title_from_stem / track_number_from_tag
# ---------------------------------------------------------------------------


def test_chapter_title_from_stem_with_part() -> None:
    stem = "Jacka, Benedict — Alex Verus #01 — Fated - 013_10"
    assert chapter_title_from_stem(stem) == "Chapter 13, Part 10"


def test_chapter_title_from_stem_without_part() -> None:
    stem = "Jacka, Benedict — Alex Verus #01 — Fated - 003"
    assert chapter_title_from_stem(stem) == "Chapter 3"


def test_chapter_title_from_stem_no_suffix_at_all() -> None:
    assert chapter_title_from_stem("No suffix here") == "Chapter ?"


def test_track_number_from_tag_extracts_leading_number() -> None:
    assert track_number_from_tag("100 Fated (Alex Verus #01) — Chapter 100") == "100"


def test_track_number_from_tag_returns_none_when_absent() -> None:
    assert track_number_from_tag("No leading number") is None


# ---------------------------------------------------------------------------
# build_album_tag / build_title_tag
# ---------------------------------------------------------------------------


def test_build_album_tag_with_series() -> None:
    assert build_album_tag("Fated", "Alex Verus", 1) == "Fated (Alex Verus #01)"


def test_build_album_tag_without_series() -> None:
    assert build_album_tag("Fated", None, None) == "Fated"


def test_build_title_tag_shape() -> None:
    result = build_title_tag("013", "Fated", "Alex Verus", 1, "Chapter 13, Part 10")
    assert result == "013 Fated (Alex Verus #01) — Chapter 13, Part 10"


# ---------------------------------------------------------------------------
# RetagStage -- fixtures
# ---------------------------------------------------------------------------


def _make_mp3(
    path: Path,
    *,
    title: str = "",
    artist: str = "",
    album: str = "",
    cover_bytes: bytes | None = None,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"FAKE-MP3-CONTENT-" + b"-" * 2000)
    tags = ID3()
    if title:
        tags.add(TIT2(encoding=3, text=title))
    if artist:
        tags.add(TPE1(encoding=3, text=artist))
    if album:
        tags.add(TALB(encoding=3, text=album))
    if cover_bytes is not None:
        tags.add(
            APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=cover_bytes)
        )
    tags.save(str(path), v2_version=3)
    return path


def _make_stage(
    tmp_path: Path, *, dry_run: bool = False
) -> tuple[RetagStage, AuditLogRepository]:
    audit_log = AuditLogRepository(tmp_path / "audit_log.csv")
    return RetagStage(audit_log, dry_run=dry_run), audit_log


# ---------------------------------------------------------------------------
# RetagStage.applies_to
# ---------------------------------------------------------------------------


def test_applies_to_is_always_false() -> None:
    stage, _ = _make_stage(Path("."))
    book = BookState("b1")
    assert stage.applies_to(book, {}) is False
    assert stage.applies_to(book, {"anything": True}) is False


# ---------------------------------------------------------------------------
# RetagStage.run -- happy path / folder-rename regression test
# ---------------------------------------------------------------------------


def test_run_renames_folder_not_just_files(tmp_path: Path) -> None:
    """The star fix for this epic: the original script only renamed MP3s,
    never the containing folder -- a real regression waiting to happen if
    this ever quietly reverted.

    Note: the legacy folder's "Benedict, Jacka" author segment carries
    forward as-is (author_last="Benedict", author_first="Jacka") -- the
    original script has no real first/last semantics either (see
    retag_stage.py's module docstring), so this is a faithful structural
    port, not an attempt to also fix name-ordering ambiguity that isn't
    resolvable from text alone.
    """
    old_folder = tmp_path / "Benedict, Jacka — Fated (Alex Verus Book 1)"
    _make_mp3(
        old_folder / "Benedict, Jacka — Fated (Alex Verus Book 1) - 013_10.mp3",
        title="100 Fated (Alex Verus Book 1) — Chapter 100",
        artist="Jacka Benedict",
        album="Fated (Alex Verus Book 1)",
    )
    stage, audit_log = _make_stage(tmp_path)

    result = stage.run(
        BookState("b1", "audio_generated", {"audio_folder": str(old_folder)})
    )

    assert result.status == "retagged"
    new_folder = Path(result.data["audio_folder"])
    assert new_folder != old_folder
    assert new_folder.name == "Benedict, Jacka — Alex Verus #01 — Fated"
    assert new_folder.exists()
    assert not old_folder.exists()  # the containing folder itself moved

    new_mp3 = new_folder / "Benedict, Jacka — Alex Verus #01 — Fated - 013_10.mp3"
    assert new_mp3.exists()

    tags = ID3(str(new_mp3))
    assert tags["TIT2"].text == ["100 Fated (Alex Verus #01) — Chapter 13, Part 10"]
    assert tags["TPE1"].text == ["Benedict, Jacka"]
    assert tags["TALB"].text == ["Fated (Alex Verus #01)"]

    rows = audit_log.read_all()
    assert len(rows) == 1
    assert rows[0]["renamed"] == "yes"
    assert rows[0]["original_filename"] == old_folder.name
    assert rows[0]["new_filename"] == new_folder.name


def test_run_preserves_cover_art(tmp_path: Path) -> None:
    folder = tmp_path / "Doe, Jane — Standalone Novel"
    _make_mp3(
        folder / "Doe, Jane — Standalone Novel - 001.mp3",
        cover_bytes=b"FAKEJPEGDATA",
    )
    stage, _ = _make_stage(tmp_path)

    result = stage.run(
        BookState("b1", "audio_generated", {"audio_folder": str(folder)})
    )

    assert result.status == "retagged"
    mp3 = Path(result.data["audio_folder"]) / "Doe, Jane — Standalone Novel - 001.mp3"
    tags = ID3(str(mp3))
    assert tags.get("APIC:Cover") is not None
    assert tags.get("APIC:Cover").data == b"FAKEJPEGDATA"


def test_run_derives_track_number_from_position_when_tag_missing(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "Doe, Jane — Standalone Novel"
    _make_mp3(folder / "Doe, Jane — Standalone Novel - 001.mp3")  # no existing TIT2
    stage, _ = _make_stage(tmp_path)

    result = stage.run(
        BookState("b1", "audio_generated", {"audio_folder": str(folder)})
    )

    mp3 = Path(result.data["audio_folder"]) / "Doe, Jane — Standalone Novel - 001.mp3"
    tags = ID3(str(mp3))
    assert tags["TIT2"].text[0].startswith("001 ")


# ---------------------------------------------------------------------------
# RetagStage.run -- override precedence
# ---------------------------------------------------------------------------


def test_run_overrides_take_precedence_over_parsed_folder_name(tmp_path: Path) -> None:
    folder = tmp_path / "Doe, Jane — Standalone Novel"
    _make_mp3(folder / "Doe, Jane — Standalone Novel - 001.mp3")
    stage, _ = _make_stage(tmp_path)

    result = stage.run(
        BookState(
            "b1",
            "audio_generated",
            {
                "audio_folder": str(folder),
                "title": "Corrected Title",
                "author_last": "Smith",
                "author_first": "Bob",
            },
        )
    )

    assert result.status == "retagged"
    new_folder = Path(result.data["audio_folder"])
    assert new_folder.name == "Smith, Bob — Corrected Title"


def test_run_falls_back_to_parsed_folder_name_when_no_overrides(tmp_path: Path) -> None:
    folder = tmp_path / "Jacka, Benedict — Alex Verus #01 — Fated"
    _make_mp3(folder / "Jacka, Benedict — Alex Verus #01 — Fated - 001.mp3")
    stage, _ = _make_stage(tmp_path)

    result = stage.run(
        BookState("b1", "audio_generated", {"audio_folder": str(folder)})
    )

    assert result.status == "retagged"
    assert result.data["title"] == "Fated"
    assert result.data["author_last"] == "Jacka"


# ---------------------------------------------------------------------------
# RetagStage.run -- dry run
# ---------------------------------------------------------------------------


def test_dry_run_renames_nothing_but_logs(tmp_path: Path) -> None:
    old_folder = tmp_path / "Benedict, Jacka — Fated (Alex Verus Book 1)"
    mp3_path = old_folder / "Benedict, Jacka — Fated (Alex Verus Book 1) - 013_10.mp3"
    _make_mp3(mp3_path)
    stage, audit_log = _make_stage(tmp_path, dry_run=True)

    result = stage.run(
        BookState("b1", "audio_generated", {"audio_folder": str(old_folder)})
    )

    assert result.status == "retagged"
    assert old_folder.exists()  # folder untouched
    assert mp3_path.exists()  # original file untouched, no rename happened
    assert result.data["audio_folder"] == str(old_folder)

    rows = audit_log.read_all()
    assert rows[0]["skipped_reason"] == "dry_run"


# ---------------------------------------------------------------------------
# RetagStage.run -- error paths
# ---------------------------------------------------------------------------


def test_run_errors_when_audio_folder_missing_from_book_data(tmp_path: Path) -> None:
    stage, _ = _make_stage(tmp_path)
    result = stage.run(BookState("b1", "audio_generated", {}))
    assert result.status == "error"
    assert "audio_folder" in result.data["error"]


def test_run_errors_when_folder_does_not_exist(tmp_path: Path) -> None:
    stage, _ = _make_stage(tmp_path)
    result = stage.run(
        BookState("b1", "audio_generated", {"audio_folder": str(tmp_path / "nope")})
    )
    assert result.status == "error"


def test_run_errors_when_no_mp3_files_present(tmp_path: Path) -> None:
    folder = tmp_path / "Doe, Jane — Standalone Novel"
    folder.mkdir(parents=True)
    stage, audit_log = _make_stage(tmp_path)

    result = stage.run(
        BookState("b1", "audio_generated", {"audio_folder": str(folder)})
    )

    assert result.status == "error"
    rows = audit_log.read_all()
    assert rows[0]["skipped_reason"] == "no_mp3_files"


def test_run_errors_when_metadata_unresolvable_and_no_overrides(tmp_path: Path) -> None:
    folder = tmp_path / "totally unparseable folder name"
    _make_mp3(folder / "somefile.mp3")
    stage, audit_log = _make_stage(tmp_path)

    result = stage.run(
        BookState("b1", "audio_generated", {"audio_folder": str(folder)})
    )

    assert result.status == "error"
    assert folder.exists()  # never touched -- fail closed, don't rename to "Unknown"
    rows = audit_log.read_all()
    assert rows[0]["skipped_reason"] == "metadata_unresolved"


def test_run_succeeds_with_overrides_even_when_folder_name_unparseable(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "totally unparseable folder name"
    _make_mp3(folder / "somefile.mp3")
    stage, _ = _make_stage(tmp_path)

    result = stage.run(
        BookState(
            "b1",
            "audio_generated",
            {
                "audio_folder": str(folder),
                "title": "Supplied Title",
                "author_last": "Supplied",
            },
        )
    )

    assert result.status == "retagged"


# ---------------------------------------------------------------------------
# RetagStage.run -- idempotency
# ---------------------------------------------------------------------------


def test_run_is_idempotent_on_an_already_correct_folder(tmp_path: Path) -> None:
    folder = tmp_path / "Jacka, Benedict — Alex Verus #01 — Fated"
    _make_mp3(folder / "Jacka, Benedict — Alex Verus #01 — Fated - 001.mp3")
    stage, audit_log = _make_stage(tmp_path)

    first = stage.run(BookState("b1", "audio_generated", {"audio_folder": str(folder)}))
    second = stage.run(
        BookState("b1", "audio_generated", {"audio_folder": first.data["audio_folder"]})
    )

    assert first.data["audio_folder"] == second.data["audio_folder"]
    rows = audit_log.read_all()
    assert rows[1]["renamed"] == "no"  # nothing changed the second time
