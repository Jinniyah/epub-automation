"""Tests for pipeline/audio_stage.py.

Covers: chapter/chunk generation loop, filename conventions
(02-pipeline-stages.md §Stage 3), the per-chunk resume-by-size-threshold
mechanism (06-safety-error-handling.md §Long-run resilience), retry-then-
error on persistent TTS failure, ID3 tagging, and the audit log's `voice`
column. Never touches the real Kokoro model -- every test supplies a fake
TTS engine.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ebooklib import epub
from mutagen.id3 import ID3

from pipeline.audio_stage import MIN_VALID_MP3_BYTES, AudioStage
from pipeline.audit_logger import AuditLogRepository
from pipeline.epub_utils import chunk_text, extract_chapters
from pipeline.stage import BookState
from pipeline.tts_engine import DEFAULT_VOICE

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_epub(
    path: Path,
    chapters: list[tuple[str, str]],
    *,
    cover_bytes: bytes | None = None,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    book = epub.EpubBook()
    book.set_identifier("id-audio-test")
    book.set_title("Ignored -- meta comes from book.data")
    book.set_language("en")
    book.add_author("Ignored")

    if cover_bytes is not None:
        img = epub.EpubImage(uid="cover-img", file_name="images/cover.jpg")
        img.media_type = "image/jpeg"
        img.content = cover_bytes
        book.add_item(img)

    toc_items = []
    spine = ["nav"]
    for i, (title, text) in enumerate(chapters, start=1):
        doc = epub.EpubHtml(title=title, file_name=f"chap{i}.xhtml", lang="en")
        doc.content = f"<html><body><h1>{title}</h1><p>{text}</p></body></html>"
        book.add_item(doc)
        toc_items.append(doc)
        spine.append(doc)

    book.toc = tuple(toc_items)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = spine

    epub.write_epub(str(path), book)
    return path


class _FakeTTSEngine:
    """Stands in for TTSEngine -- returns deterministic fake MP3 bytes,
    optionally failing the first N calls before succeeding, or always."""

    def __init__(self, fail_first_n: int = 0, always_fail: bool = False) -> None:
        self.calls: list[tuple[str, str]] = []
        self._fail_first_n = fail_first_n
        self._always_fail = always_fail

    def generate(self, text: str, voice: str) -> bytes:
        self.calls.append((text, voice))
        if self._always_fail or len(self.calls) <= self._fail_first_n:
            raise RuntimeError("simulated TTS failure")
        # Padded well past MIN_VALID_MP3_BYTES so resume-detection tests
        # can tell a "real" generated file from a too-small leftover.
        return b"FAKE-MP3-CONTENT-" + str(len(self.calls)).encode() + b"-" * 2000


def _make_stage(
    tmp_path: Path,
    *,
    tts_engine: _FakeTTSEngine | None = None,
    default_voice: str = DEFAULT_VOICE,
    max_chunk_chars: int = 4000,
    max_chunk_retries: int = 3,
) -> tuple[AudioStage, AuditLogRepository]:
    audit_log = AuditLogRepository(tmp_path / "audit_log.csv")
    stage = AudioStage(
        input_folder=tmp_path / "input",
        output_folder=tmp_path / "output",
        audit_log=audit_log,
        tts_engine=tts_engine or _FakeTTSEngine(),
        default_voice=default_voice,
        max_chunk_chars=max_chunk_chars,
        max_chunk_retries=max_chunk_retries,
        retry_backoff_seconds=0.0,
    )
    return stage, audit_log


_LONG_TEXT = "Some real narrative content, sentence by sentence. " * 20
# Long enough (combined with its <h1> heading) to clear extract_chapters'
# 50-char "too short, skip" floor, short enough to stay a single chunk.
_SHORT_CHAPTER_TEXT = (
    "Short chapter with just enough narrative content to pass the minimum length "
    "filter."
)


def _meta(**overrides: Any) -> dict[str, Any]:
    base = {
        "filename": "book.epub",
        "title": "Fated",
        "author_first": "Benedict",
        "author_last": "Jacka",
        "series": "Alex Verus",
        "series_number": 1,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# applies_to
# ---------------------------------------------------------------------------


def test_applies_to_is_always_true_regardless_of_settings(tmp_path: Path) -> None:
    stage, _ = _make_stage(tmp_path)
    book = BookState("b1")
    assert stage.applies_to(book, {}) is True
    assert stage.applies_to(book, {"make_audio": False}) is True


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_run_generates_single_chunk_mp3_and_tags_it(tmp_path: Path) -> None:
    _make_epub(tmp_path / "input" / "book.epub", [("Chapter 1", _LONG_TEXT)])
    fake_engine = _FakeTTSEngine()
    stage, audit_log = _make_stage(tmp_path, tts_engine=fake_engine)

    result = stage.run(BookState("b1", "sanitized", _meta()))

    assert result.status == "audio_generated"
    book_dir = Path(result.data["audio_folder"])
    assert book_dir == tmp_path / "output" / "Jacka, Benedict — Alex Verus #01 — Fated"
    mp3_path = book_dir / "Jacka, Benedict — Alex Verus #01 — Fated - 001.mp3"
    assert mp3_path.exists()

    tags = ID3(str(mp3_path))
    assert tags["TPE1"].text == ["Jacka, Benedict"]
    assert tags["TALB"].text == ["Alex Verus"]
    assert tags["TRCK"].text == ["1/1"]
    assert "Fated" in tags["TIT2"].text[0]

    assert result.data["voice"] == DEFAULT_VOICE
    assert result.data["chunks_total"] == 1

    rows = audit_log.read_all()
    assert len(rows) == 1
    assert rows[0]["voice"] == DEFAULT_VOICE
    assert rows[0]["skipped_reason"] == ""


def test_run_embeds_cover_art_when_present(tmp_path: Path) -> None:
    _make_epub(
        tmp_path / "input" / "book.epub",
        [("Chapter 1", _LONG_TEXT)],
        cover_bytes=b"FAKEJPEGDATA",
    )
    stage, _ = _make_stage(tmp_path)

    result = stage.run(BookState("b1", "sanitized", _meta()))

    mp3_path = Path(result.data["audio_folder"]) / (
        "Jacka, Benedict — Alex Verus #01 — Fated - 001.mp3"
    )
    tags = ID3(str(mp3_path))
    assert tags.get("APIC:Cover") is not None
    assert tags.get("APIC:Cover").data == b"FAKEJPEGDATA"


def test_run_without_cover_still_succeeds(tmp_path: Path) -> None:
    _make_epub(tmp_path / "input" / "book.epub", [("Chapter 1", _LONG_TEXT)])
    stage, _ = _make_stage(tmp_path)

    result = stage.run(BookState("b1", "sanitized", _meta()))

    assert result.status == "audio_generated"


def test_run_uses_chunk_suffix_only_when_chapter_has_multiple_chunks(
    tmp_path: Path,
) -> None:
    long_chapter = "Sentence content here. " * 400  # forces multiple chunks
    _make_epub(
        tmp_path / "input" / "book.epub",
        [("Chapter 1", _SHORT_CHAPTER_TEXT), ("Chapter 2", long_chapter)],
    )
    stage, _ = _make_stage(tmp_path, max_chunk_chars=500)

    result = stage.run(BookState("b1", "sanitized", _meta()))

    book_dir = Path(result.data["audio_folder"])
    files = sorted(p.name for p in book_dir.glob("*.mp3"))
    # Chapter 1 has one chunk -> no "_N" suffix; Chapter 2 has several.
    assert any(f.endswith("- 001.mp3") for f in files)
    assert any("- 002_1.mp3" in f for f in files)
    assert any("- 002_2.mp3" in f for f in files)


def test_run_falls_back_to_default_voice_when_not_set(tmp_path: Path) -> None:
    _make_epub(tmp_path / "input" / "book.epub", [("Chapter 1", _LONG_TEXT)])
    stage, _ = _make_stage(tmp_path, default_voice="am_puck")

    result = stage.run(BookState("b1", "sanitized", _meta()))

    assert result.data["voice"] == "am_puck"


def test_run_uses_voice_from_book_data_when_present(tmp_path: Path) -> None:
    _make_epub(tmp_path / "input" / "book.epub", [("Chapter 1", _LONG_TEXT)])
    stage, _ = _make_stage(tmp_path, default_voice="am_puck")

    result = stage.run(BookState("b1", "sanitized", _meta(voice="bf_alice")))

    assert result.data["voice"] == "bf_alice"


# ---------------------------------------------------------------------------
# Resume
# ---------------------------------------------------------------------------


def test_run_skips_chunk_with_existing_mp3_above_size_threshold(tmp_path: Path) -> None:
    _make_epub(tmp_path / "input" / "book.epub", [("Chapter 1", _LONG_TEXT)])
    book_dir = tmp_path / "output" / "Jacka, Benedict — Alex Verus #01 — Fated"
    book_dir.mkdir(parents=True)
    existing = book_dir / "Jacka, Benedict — Alex Verus #01 — Fated - 001.mp3"
    existing.write_bytes(b"x" * (MIN_VALID_MP3_BYTES + 1))
    existing_mtime = existing.stat().st_mtime

    fake_engine = _FakeTTSEngine()
    stage, _ = _make_stage(tmp_path, tts_engine=fake_engine)

    result = stage.run(BookState("b1", "sanitized", _meta()))

    assert result.status == "audio_generated"
    assert fake_engine.calls == []  # never regenerated
    assert existing.stat().st_mtime == existing_mtime  # untouched


def test_run_regenerates_chunk_with_undersized_leftover_mp3(tmp_path: Path) -> None:
    _make_epub(tmp_path / "input" / "book.epub", [("Chapter 1", _LONG_TEXT)])
    book_dir = tmp_path / "output" / "Jacka, Benedict — Alex Verus #01 — Fated"
    book_dir.mkdir(parents=True)
    stale = book_dir / "Jacka, Benedict — Alex Verus #01 — Fated - 001.mp3"
    stale.write_bytes(
        b"x" * (MIN_VALID_MP3_BYTES - 1)
    )  # too small -- a leftover partial

    fake_engine = _FakeTTSEngine()
    stage, _ = _make_stage(tmp_path, tts_engine=fake_engine)

    result = stage.run(BookState("b1", "sanitized", _meta()))

    assert result.status == "audio_generated"
    assert len(fake_engine.calls) == 1  # regenerated


def test_run_only_generates_missing_chunks_in_a_partially_done_book(
    tmp_path: Path,
) -> None:
    long_chapter = "Sentence content here. " * 400
    epub_path = tmp_path / "input" / "book.epub"
    _make_epub(
        epub_path,
        [("Chapter 1", _SHORT_CHAPTER_TEXT), ("Chapter 2", long_chapter)],
    )
    # Ground truth for "how many chunks does chapter 2 actually produce",
    # computed the same way the stage itself does, rather than a hardcoded
    # guess that would silently drift if extraction/normalisation changes.
    chapters, _, _ = extract_chapters(str(epub_path))
    expected_chapter2_chunks = len(chunk_text(chapters[1]["text"], max_chars=500))

    book_dir = tmp_path / "output" / "Jacka, Benedict — Alex Verus #01 — Fated"
    book_dir.mkdir(parents=True)
    # Chapter 1's single chunk already exists and is valid.
    (book_dir / "Jacka, Benedict — Alex Verus #01 — Fated - 001.mp3").write_bytes(
        b"x" * (MIN_VALID_MP3_BYTES + 1)
    )

    fake_engine = _FakeTTSEngine()
    stage, _ = _make_stage(tmp_path, tts_engine=fake_engine, max_chunk_chars=500)

    result = stage.run(BookState("b1", "sanitized", _meta()))

    assert result.status == "audio_generated"
    # Only chapter 2's chunks were (re)generated, not chapter 1's.
    assert len(fake_engine.calls) == expected_chapter2_chunks
    assert all("Chapter 1" not in text for text, _voice in fake_engine.calls)


# ---------------------------------------------------------------------------
# Retry / failure
# ---------------------------------------------------------------------------


def test_run_retries_transient_failure_then_succeeds(tmp_path: Path) -> None:
    _make_epub(tmp_path / "input" / "book.epub", [("Chapter 1", _LONG_TEXT)])
    fake_engine = _FakeTTSEngine(fail_first_n=2)  # fails twice, succeeds 3rd try
    stage, _ = _make_stage(tmp_path, tts_engine=fake_engine, max_chunk_retries=3)

    result = stage.run(BookState("b1", "sanitized", _meta()))

    assert result.status == "audio_generated"
    assert len(fake_engine.calls) == 3


def test_run_errors_after_exhausting_retries(tmp_path: Path) -> None:
    _make_epub(tmp_path / "input" / "book.epub", [("Chapter 1", _LONG_TEXT)])
    fake_engine = _FakeTTSEngine(always_fail=True)
    stage, audit_log = _make_stage(
        tmp_path, tts_engine=fake_engine, max_chunk_retries=2
    )

    result = stage.run(BookState("b1", "sanitized", _meta()))

    assert result.status == "error"
    assert len(fake_engine.calls) == 2  # respected max_chunk_retries
    assert "chapter 1" in result.data["error"].lower()

    rows = audit_log.read_all()
    assert rows[0]["skipped_reason"] == "generation_failed"


def test_run_stops_at_first_unrecoverable_chunk_leaving_earlier_chunks_intact(
    tmp_path: Path,
) -> None:
    long_chapter = "Sentence content here. " * 400
    _make_epub(
        tmp_path / "input" / "book.epub",
        [("Chapter 1", _SHORT_CHAPTER_TEXT), ("Chapter 2", long_chapter)],
    )

    class _FailOnSecondCall(_FakeTTSEngine):
        def generate(self, text: str, voice: str) -> bytes:
            if len(self.calls) >= 1:
                self.calls.append((text, voice))
                raise RuntimeError("simulated failure")
            return super().generate(text, voice)

    fake_engine = _FailOnSecondCall()
    stage, _ = _make_stage(
        tmp_path, tts_engine=fake_engine, max_chunk_chars=500, max_chunk_retries=1
    )

    result = stage.run(BookState("b1", "sanitized", _meta()))

    assert result.status == "error"
    book_dir = tmp_path / "output" / "Jacka, Benedict — Alex Verus #01 — Fated"
    # Chapter 1's chunk succeeded and is still on disk for a future resume.
    assert (book_dir / "Jacka, Benedict — Alex Verus #01 — Fated - 001.mp3").exists()
    # Chapter 2's second chunk was never attempted.
    assert not (
        book_dir / "Jacka, Benedict — Alex Verus #01 — Fated - 002_2.mp3"
    ).exists()


# ---------------------------------------------------------------------------
# Validation / error paths
# ---------------------------------------------------------------------------


def test_run_errors_on_unknown_voice_without_calling_tts(tmp_path: Path) -> None:
    _make_epub(tmp_path / "input" / "book.epub", [("Chapter 1", _LONG_TEXT)])
    fake_engine = _FakeTTSEngine()
    stage, _ = _make_stage(tmp_path, tts_engine=fake_engine)

    result = stage.run(BookState("b1", "sanitized", _meta(voice="not_a_real_voice")))

    assert result.status == "error"
    assert fake_engine.calls == []


def test_run_errors_when_input_file_missing(tmp_path: Path) -> None:
    stage, audit_log = _make_stage(tmp_path)

    result = stage.run(BookState("b1", "sanitized", _meta(filename="missing.epub")))

    assert result.status == "error"
    assert "not found" in result.data["error"]
    assert audit_log.read_all() == []  # no row for a missing-input error


def test_run_errors_on_corrupted_epub(tmp_path: Path) -> None:
    bad_path = tmp_path / "input" / "corrupt.epub"
    bad_path.parent.mkdir(parents=True)
    bad_path.write_bytes(b"not a real zip file")

    stage, audit_log = _make_stage(tmp_path)
    result = stage.run(BookState("b1", "sanitized", _meta(filename="corrupt.epub")))

    assert result.status == "error"
    rows = audit_log.read_all()
    assert rows[0]["skipped_reason"] == "epub_read_error"


def test_run_errors_when_no_chapters_extracted(tmp_path: Path) -> None:
    # Only a nav document -- everything gets filtered out by extract_chapters.
    _make_epub(tmp_path / "input" / "book.epub", [])
    stage, audit_log = _make_stage(tmp_path)

    result = stage.run(BookState("b1", "sanitized", _meta()))

    assert result.status == "error"
    assert "no chapters" in result.data["error"].lower()
    rows = audit_log.read_all()
    assert rows[0]["skipped_reason"] == "no_chapters"


def test_run_defaults_missing_metadata_fields_like_build_filename(
    tmp_path: Path,
) -> None:
    _make_epub(tmp_path / "input" / "book.epub", [("Chapter 1", _LONG_TEXT)])
    stage, _ = _make_stage(tmp_path)

    result = stage.run(BookState("b1", "sanitized", {"filename": "book.epub"}))

    assert result.status == "audio_generated"
    book_dir = Path(result.data["audio_folder"])
    assert book_dir.name == "Unknown, Unknown — Unknown"
