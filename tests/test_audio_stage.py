"""Tests for pipeline/audio_stage.py.

Covers: chapter/chunk generation loop, filename conventions
(02-pipeline-stages.md §Stage 3), the per-chunk resume-by-size-threshold
mechanism (06-safety-error-handling.md §Long-run resilience), retry-then-
error on persistent TTS failure, ID3 tagging, and the audit log's `voice`
column. Never touches the real Kokoro model -- every test supplies a fake
TTS engine.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import numpy as np
from ebooklib import epub
from mutagen.id3 import ID3

from pipeline.audio_stage import MIN_VALID_MP3_BYTES, AudioStage
from pipeline.audit_logger import AuditLogRepository
from pipeline.epub_utils import chunk_text, extract_chapters, group_chunks_into_parts
from pipeline.stage import BookState
from pipeline.tts_engine import DEFAULT_VOICE, KOKORO_SAMPLE_RATE, encode_mp3

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
    """Stands in for TTSEngine -- returns deterministic, genuinely valid
    PCM audio (short silence) via generate_pcm(), the method AudioStage
    actually calls now (ADR-0020) to accumulate a part's audio before a
    single real encode_mp3() call; optionally failing the first N calls
    before succeeding, or always."""

    def __init__(self, fail_first_n: int = 0, always_fail: bool = False) -> None:
        self.calls: list[tuple[str, str]] = []
        self._fail_first_n = fail_first_n
        self._always_fail = always_fail

    def generate_pcm(self, text: str, voice: str) -> np.ndarray:
        self.calls.append((text, voice))
        if self._always_fail or len(self.calls) <= self._fail_first_n:
            raise RuntimeError("simulated TTS failure")
        # 0.2s of silence at Kokoro's native rate -- encodes to comfortably
        # more than MIN_VALID_MP3_BYTES, so resume-detection tests can
        # tell a "real" generated file from a too-small leftover.
        return np.zeros(int(KOKORO_SAMPLE_RATE * 0.2), dtype=np.float32)

    def generate(self, text: str, voice: str) -> bytes:
        return encode_mp3(self.generate_pcm(text, voice))


def _make_stage(
    tmp_path: Path,
    *,
    tts_engine: _FakeTTSEngine | None = None,
    default_voice: str = DEFAULT_VOICE,
    max_chunk_chars: int = 4000,
    max_part_chars: int | None = None,
    max_chunk_retries: int = 3,
) -> tuple[AudioStage, AuditLogRepository]:
    audit_log = AuditLogRepository(tmp_path / "audit_log.csv")
    kwargs: dict[str, Any] = {}
    if max_part_chars is not None:
        kwargs["max_part_chars"] = max_part_chars
    stage = AudioStage(
        input_folder=tmp_path / "input",
        output_folder=tmp_path / "output",
        audit_log=audit_log,
        tts_engine=tts_engine or _FakeTTSEngine(),
        default_voice=default_voice,
        max_chunk_chars=max_chunk_chars,
        max_chunk_retries=max_chunk_retries,
        retry_backoff_seconds=0.0,
        **kwargs,
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


def test_run_uses_part_suffix_only_when_chapter_has_multiple_parts(
    tmp_path: Path,
) -> None:
    long_chapter = "Sentence content here. " * 400  # forces multiple chunks
    _make_epub(
        tmp_path / "input" / "book.epub",
        [("Chapter 1", _SHORT_CHAPTER_TEXT), ("Chapter 2", long_chapter)],
    )
    # max_part_chars roughly 2-3x max_chunk_chars -- chapter 2's several
    # ~500-char chunks group a few at a time into fewer, larger parts
    # (ADR-0020) rather than either all merging into one or staying 1:1.
    stage, _ = _make_stage(tmp_path, max_chunk_chars=500, max_part_chars=1200)

    result = stage.run(BookState("b1", "sanitized", _meta()))

    book_dir = Path(result.data["audio_folder"])
    files = sorted(p.name for p in book_dir.glob("*.mp3"))
    # Chapter 1 has one part -> no "_N" suffix; Chapter 2 has several.
    assert any(f.endswith("- 001.mp3") for f in files)
    assert any("- 002_001.mp3" in f for f in files)
    assert any("- 002_002.mp3" in f for f in files)
    # The core point of ADR-0020: fewer physical files than text chunks.
    assert len(files) < result.data["chunks_total"]


def test_part_suffix_is_zero_padded_so_filename_sort_matches_playback_order(
    tmp_path: Path,
) -> None:
    """Real bug found via real-world listening (2026-07-20): an unpadded
    suffix ("_1", "_2", ..., "_10") sorts alphabetically as 1, 10,
    11, ..., 2, 20, ... on any player/device that orders files by name
    rather than by ID3 track number (most basic media players, phone
    default apps, USB car stereos) -- which scrambles playback for any
    chapter with 10+ parts, sounding like the audio jumps to the middle
    of an unrelated sentence. A real chapter in "The Risen Empire" had 53
    chunks (now grouped into far fewer parts, ADR-0020, but the same
    sort-order risk applies at whatever granularity actually lands on
    disk). Zero-padding to 3 digits (matching the existing chapter-index
    width) keeps alphabetical order identical to numeric/playback order
    for up to 999 parts per chapter."""
    long_chapter = "Sentence content here. " * 900  # forces 12+ chunks at 500 chars
    _make_epub(tmp_path / "input" / "book.epub", [("Chapter 1", long_chapter)])
    stage, _ = _make_stage(tmp_path, max_chunk_chars=500, max_part_chars=500)

    result = stage.run(BookState("b1", "sanitized", _meta()))

    book_dir = Path(result.data["audio_folder"])
    files = [p.name for p in book_dir.glob("*.mp3")]
    assert len(files) >= 12
    part_num = re.compile(r"_(\d+)\.mp3$")
    assert sorted(files) == sorted(
        files, key=lambda f: int(part_num.search(f).group(1))  # type: ignore[union-attr]
    )


def test_run_id3_track_total_counts_parts_not_chunks(tmp_path: Path) -> None:
    long_chapter = "Sentence content here. " * 400
    _make_epub(tmp_path / "input" / "book.epub", [("Chapter 1", long_chapter)])
    stage, _ = _make_stage(tmp_path, max_chunk_chars=500, max_part_chars=1200)

    result = stage.run(BookState("b1", "sanitized", _meta()))

    total_chunks = result.data["chunks_total"]
    book_dir = Path(result.data["audio_folder"])
    files = sorted(book_dir.glob("*.mp3"))
    assert len(files) < total_chunks  # merging actually happened

    total_tracks_seen = {ID3(str(f))["TRCK"].text[0].split("/")[1] for f in files}
    assert total_tracks_seen == {
        str(len(files))
    }  # every file agrees: parts, not chunks


def test_run_chunk_larger_than_max_part_chars_still_forms_exactly_one_part(
    tmp_path: Path,
) -> None:
    """A single chunk larger than max_part_chars must still produce
    exactly one valid part -- never split, never dropped, never an
    infinite loop (group_chunks_into_parts() itself already covers this
    in isolation; this proves AudioStage wires it through correctly)."""
    _make_epub(tmp_path / "input" / "book.epub", [("Chapter 1", _LONG_TEXT)])
    # max_chunk_chars deliberately larger than max_part_chars -- the
    # chapter's single chunk exceeds the part budget on its own.
    stage, _ = _make_stage(tmp_path, max_chunk_chars=4000, max_part_chars=100)

    result = stage.run(BookState("b1", "sanitized", _meta()))

    assert result.status == "audio_generated"
    book_dir = Path(result.data["audio_folder"])
    files = list(book_dir.glob("*.mp3"))
    assert len(files) == 1
    assert files[0].stat().st_size > MIN_VALID_MP3_BYTES


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


def test_run_resume_skips_generation_entirely_for_a_fully_flushed_part(
    tmp_path: Path,
) -> None:
    """A resume check now operates at the *part* level (ADR-0020) -- a
    hit must skip the TTS engine for every one of that part's chunks,
    not just avoid rewriting the file."""
    long_chapter = "Sentence content here. " * 400
    epub_path = tmp_path / "input" / "book.epub"
    _make_epub(epub_path, [("Chapter 1", long_chapter)])
    chapters, _, _ = extract_chapters(str(epub_path))
    chunks = chunk_text(chapters[0]["text"], max_chars=500)
    parts = group_chunks_into_parts(chunks, max_part_chars=1200)
    assert len(parts[0]) >= 2  # sanity check this test's own setup

    book_dir = tmp_path / "output" / "Jacka, Benedict — Alex Verus #01 — Fated"
    book_dir.mkdir(parents=True)
    # The first part's file already exists and is valid -- covers several
    # chunks at once.
    (book_dir / "Jacka, Benedict — Alex Verus #01 — Fated - 001_001.mp3").write_bytes(
        b"x" * (MIN_VALID_MP3_BYTES + 1)
    )

    fake_engine = _FakeTTSEngine()
    stage, _ = _make_stage(
        tmp_path, tts_engine=fake_engine, max_chunk_chars=500, max_part_chars=1200
    )

    result = stage.run(BookState("b1", "sanitized", _meta()))

    assert result.status == "audio_generated"
    # None of the first part's chunks were ever sent to the TTS engine.
    assert len(fake_engine.calls) == result.data["chunks_total"] - len(parts[0])


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
    # The underlying exception's detail is appended -- this is the only
    # channel `current_error_detail()`/the support bundle ever reads (see
    # `backend/bridge.py`), so a bare "chapter 1, chunk 1" sentence with
    # nothing underneath it left a real failure undiagnosable.
    assert "RuntimeError: simulated TTS failure" in result.data["error"]

    rows = audit_log.read_all()
    assert rows[0]["skipped_reason"] == "generation_failed"


def test_run_stops_at_first_unrecoverable_chunk_leaving_chapter_1_intact(
    tmp_path: Path,
) -> None:
    long_chapter = "Sentence content here. " * 400
    _make_epub(
        tmp_path / "input" / "book.epub",
        [("Chapter 1", _SHORT_CHAPTER_TEXT), ("Chapter 2", long_chapter)],
    )

    class _FailOnSecondCall(_FakeTTSEngine):
        def generate_pcm(self, text: str, voice: str) -> np.ndarray:
            if len(self.calls) >= 1:
                self.calls.append((text, voice))
                raise RuntimeError("simulated failure")
            return super().generate_pcm(text, voice)

    fake_engine = _FailOnSecondCall()
    stage, _ = _make_stage(
        tmp_path, tts_engine=fake_engine, max_chunk_chars=500, max_chunk_retries=1
    )

    result = stage.run(BookState("b1", "sanitized", _meta()))

    assert result.status == "error"
    book_dir = tmp_path / "output" / "Jacka, Benedict — Alex Verus #01 — Fated"
    # Chapter 1's part succeeded and is still on disk for a future resume.
    assert (book_dir / "Jacka, Benedict — Alex Verus #01 — Fated - 001.mp3").exists()
    # Chapter 2's part failed on its very first chunk -- never flushed at all
    # (ADR-0020: nothing is written to disk until every chunk in a part
    # succeeds).
    assert not any(book_dir.glob("Jacka, Benedict — Alex Verus #01 — Fated - 002*.mp3"))


def test_run_error_mid_part_discards_an_earlier_succeeded_chunk_in_same_part(
    tmp_path: Path,
) -> None:
    """ADR-0020's bounded resume-loss tradeoff applies to a generation
    failure, not just Pause/Cancel: an earlier chunk that already
    succeeded (its PCM held only in memory) is discarded, not partially
    written, when a later chunk in the SAME part fails."""
    long_chapter = "Sentence content here. " * 60  # forces a handful of chunks
    _make_epub(tmp_path / "input" / "book.epub", [("Chapter 1", long_chapter)])

    class _FailOnSecondCall(_FakeTTSEngine):
        def generate_pcm(self, text: str, voice: str) -> np.ndarray:
            if len(self.calls) >= 1:
                self.calls.append((text, voice))
                raise RuntimeError("simulated failure")
            return super().generate_pcm(text, voice)

    fake_engine = _FailOnSecondCall()
    # max_part_chars comfortably larger than max_chunk_chars -- keeps at
    # least the first two chunks in the SAME part.
    stage, _ = _make_stage(
        tmp_path,
        tts_engine=fake_engine,
        max_chunk_chars=300,
        max_part_chars=100_000,
        max_chunk_retries=1,
    )

    result = stage.run(BookState("b1", "sanitized", _meta()))

    assert result.status == "error"
    assert len(fake_engine.calls) == 2  # chunk 1 succeeded, chunk 2 failed
    book_dir = tmp_path / "output" / "Jacka, Benedict — Alex Verus #01 — Fated"
    assert list(book_dir.glob("*.mp3")) == []  # nothing written -- part discarded


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


# ---------------------------------------------------------------------------
# Observer hooks (Epic 6) -- on_progress / should_stop
# ---------------------------------------------------------------------------


def test_on_progress_is_called_once_per_chunk_with_running_totals(
    tmp_path: Path,
) -> None:
    long_chapter = "Sentence content here. " * 400  # forces multiple chunks
    _make_epub(
        tmp_path / "input" / "book.epub",
        [("Chapter 1", _SHORT_CHAPTER_TEXT), ("Chapter 2", long_chapter)],
    )
    audit_log = AuditLogRepository(tmp_path / "audit_log.csv")
    calls: list[tuple[str, int, int]] = []
    stage = AudioStage(
        input_folder=tmp_path / "input",
        output_folder=tmp_path / "output",
        audit_log=audit_log,
        tts_engine=_FakeTTSEngine(),
        max_chunk_chars=500,
        on_progress=lambda book_id, done, total: calls.append((book_id, done, total)),
    )

    result = stage.run(BookState("b1", "sanitized", _meta()))

    assert result.status == "audio_generated"
    total_tracks = result.data["chunks_total"]
    assert total_tracks > 1  # forced multiple chunks via max_chunk_chars=500
    assert len(calls) == total_tracks
    assert all(book_id == "b1" for book_id, _, _ in calls)
    assert all(total == total_tracks for _, _, total in calls)
    assert [done for _, done, _ in calls] == list(range(1, total_tracks + 1))
    # on_progress still counts original chunks (unaffected, no frontend
    # change needed) even though far fewer physical files land on disk
    # under the default (large) max_part_chars -- ADR-0020's key
    # frontend-compatibility guarantee.
    book_dir = Path(result.data["audio_folder"])
    files = list(book_dir.glob("*.mp3"))
    assert len(files) < total_tracks


def test_should_stop_halts_before_the_next_chunk_leaving_earlier_ones_intact(
    tmp_path: Path,
) -> None:
    long_chapter = "Sentence content here. " * 400
    _make_epub(tmp_path / "input" / "book.epub", [("Chapter 1", long_chapter)])
    audit_log = AuditLogRepository(tmp_path / "audit_log.csv")
    stage = AudioStage(
        input_folder=tmp_path / "input",
        output_folder=tmp_path / "output",
        audit_log=audit_log,
        tts_engine=_FakeTTSEngine(),
        max_chunk_chars=500,
        # Stop as soon as the first chunk would have been produced.
        should_stop=lambda book_id: "paused",
    )

    result = stage.run(BookState("b1", "sanitized", _meta()))

    assert result.status == "paused"
    assert result.data["chunks_done"] == 0
    book_dir = Path(result.data["audio_folder"])
    assert list(book_dir.glob("*.mp3")) == []


def test_should_stop_mid_part_discards_progress_and_resume_redoes_the_whole_part(
    tmp_path: Path,
) -> None:
    """ADR-0020's bounded resume-loss tradeoff: stopping partway through
    an in-progress part discards every chunk generated so far for that
    part (nothing was ever written to disk) -- resuming regenerates the
    WHOLE part from scratch, not just the missing tail. This is a
    deliberate change from the old per-chunk-file resume unit -- see the
    test below for the (unchanged) case of a part that fully completed
    before the stop request, which IS safely skipped on resume."""
    long_chapter = "Sentence content here. " * 400
    _make_epub(tmp_path / "input" / "book.epub", [("Chapter 1", long_chapter)])
    audit_log = AuditLogRepository(tmp_path / "audit_log.csv")

    # First run: stop after exactly one chunk has completed -- still well
    # short of a full part under the default (large) max_part_chars, so
    # the whole chapter is one big, still-in-progress part.
    written: list[int] = []
    stage1 = AudioStage(
        input_folder=tmp_path / "input",
        output_folder=tmp_path / "output",
        audit_log=audit_log,
        tts_engine=_FakeTTSEngine(),
        max_chunk_chars=500,
        on_progress=lambda book_id, done, total: written.append(done),
        should_stop=lambda book_id: "cancelled" if len(written) >= 1 else None,
    )
    first = stage1.run(BookState("b1", "sanitized", _meta()))

    assert first.status == "cancelled"
    assert first.data["chunks_done"] == 0  # nothing flushed -- part discarded
    book_dir = Path(first.data["audio_folder"])
    assert list(book_dir.glob("*.mp3")) == []  # nothing on disk at all

    # Second run: no stop requested -- must regenerate every chunk of the
    # interrupted part, not resume partway through it.
    fake_engine2 = _FakeTTSEngine()
    stage2 = AudioStage(
        input_folder=tmp_path / "input",
        output_folder=tmp_path / "output",
        audit_log=audit_log,
        tts_engine=fake_engine2,
        max_chunk_chars=500,
    )
    second = stage2.run(BookState("b1", "sanitized", _meta()))

    assert second.status == "audio_generated"
    assert len(fake_engine2.calls) == second.data["chunks_total"]  # every chunk redone


def test_should_stop_after_a_full_part_flushes_resume_skips_that_part_entirely(
    tmp_path: Path,
) -> None:
    """The counterpart to the test above: a part that fully completed
    (flushed to disk) before the stop request is genuinely safe and must
    not be regenerated on resume -- only the still-incomplete remainder
    is."""
    long_chapter = "Sentence content here. " * 400
    epub_path = tmp_path / "input" / "book.epub"
    _make_epub(epub_path, [("Chapter 1", long_chapter)])
    # Ground truth for exactly how many chunks the first part contains,
    # computed the same way the stage itself does.
    chapters, _, _ = extract_chapters(str(epub_path))
    chunks = chunk_text(chapters[0]["text"], max_chars=500)
    parts = group_chunks_into_parts(chunks, max_part_chars=1200)
    assert len(parts) >= 2  # sanity check this test's own setup
    first_part_chunk_count = len(parts[0])

    audit_log = AuditLogRepository(tmp_path / "audit_log.csv")
    written: list[int] = []
    stage1 = AudioStage(
        input_folder=tmp_path / "input",
        output_folder=tmp_path / "output",
        audit_log=audit_log,
        tts_engine=_FakeTTSEngine(),
        max_chunk_chars=500,
        max_part_chars=1200,
        on_progress=lambda book_id, done, total: written.append(done),
        should_stop=lambda book_id: (
            "cancelled" if len(written) >= first_part_chunk_count else None
        ),
    )
    first = stage1.run(BookState("b1", "sanitized", _meta()))

    assert first.status == "cancelled"
    assert first.data["chunks_done"] == first_part_chunk_count
    book_dir = Path(first.data["audio_folder"])
    assert len(list(book_dir.glob("*.mp3"))) == 1  # exactly the first (flushed) part

    fake_engine2 = _FakeTTSEngine()
    stage2 = AudioStage(
        input_folder=tmp_path / "input",
        output_folder=tmp_path / "output",
        audit_log=audit_log,
        tts_engine=fake_engine2,
        max_chunk_chars=500,
        max_part_chars=1200,
    )
    second = stage2.run(BookState("b1", "sanitized", _meta()))

    assert second.status == "audio_generated"
    # Only the remaining part(s)' chunks were (re)generated -- the first
    # part's chunks were never touched.
    assert (
        len(fake_engine2.calls) == second.data["chunks_total"] - first_part_chunk_count
    )
