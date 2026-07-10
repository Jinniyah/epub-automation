"""Audio stage -- ports epub-to-audio's per-book generation loop to the
Stage protocol (docs/design/PATTERNS.md §1), with the TTS engine swapped
for local Kokoro (ADR-0002) and the browser/Selenium/ID3 mechanics
otherwise reused (ADR-0014).

See docs/requirements/02-pipeline-stages.md §Stage 3 and
docs/requirements/04-tts-engine.md.

Adapted from the original epub-to-audio, for concrete, nameable reasons
(ADR-0014):
  - Chapter extraction / chunking (`extract_chapters`, `chunk_text`) and
    the per-chunk "skip if MP3 already exists and is above a minimum size"
    resume logic are ported verbatim (pipeline/epub_utils.py).
  - ID3 tagging (`_apply_tags`) is ported from `apply_tags()`, adapted to
    this project's metadata shape (`author_first`/`author_last`, produced
    by RenameStage, rather than the original's single `author` string).
  - The book folder / MP3 base filename reuses `rename_stage.build_filename()`
    directly (minus the `.epub` suffix) rather than a separate
    `build_basename()` -- 02-pipeline-stages.md §Stage 3 requires the same
    naming convention as the renamed EPUB, and every component still goes
    through `sanitize_filesystem_name()` (ADR-0016) this way, for free.
  - The original's Selenium retry loop (reload the page, re-select the
    voice, try again) is replaced by a plain function-call retry -- Kokoro
    is an in-process call, not a browser session, so there is no page to
    reload (04-tts-engine.md §Interface sketch).
  - Voice selection is per-book, supplied by the caller via
    `book.data["voice"]` (falling back to a constructor-level
    `default_voice` only for standalone/CLI/test use) -- this stage never
    picks a voice itself; that's the GUI's voice-assignment step
    (02-pipeline-stages.md §Stage 3 point 4), which happens before this
    stage's `run()` is ever called for a given book.

**Scope note:** the "session-local same-series voice default" backlog item
(docs/BACKLOG.md Epic 4, ADR-0010) is a batch-runner/voice-picker UX
concern -- it requires knowing which books in the *current batch* share a
series, which `Stage.run()`'s per-book signature has no visibility into.
Same reasoning Epic 3 used to defer `MAX_FILES` enforcement to Epic 6/8.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from mutagen.id3 import APIC, ID3, TALB, TIT2, TPE1, TRCK, ID3NoHeaderError

from pipeline.audit_logger import AuditLogRepository
from pipeline.epub_reader import extract_cover_bytes
from pipeline.epub_utils import MAX_CHUNK_CHARS, chunk_text, extract_chapters
from pipeline.rename_stage import build_filename
from pipeline.stage import BookState
from pipeline.tts_engine import DEFAULT_VOICE, VOICES, TTSEngine

# Any existing MP3 above this size is treated as already-generated and
# skipped -- ported verbatim from epub-to-audio's resume check (`mp3_path
# .stat().st_size > 1024`), the mechanism that makes Pause/Cancel/
# interruption recovery safe (06-safety-error-handling.md §Long-run
# resilience).
MIN_VALID_MP3_BYTES = 1024

# A plain function-call retry, not the original's "reload the browser
# page" retry -- see module docstring.
DEFAULT_MAX_CHUNK_RETRIES = 3
DEFAULT_RETRY_BACKOFF_SECONDS = 1.0


class AudioStage:
    """Stage 3: audio -- per-book chapter/chunk TTS generation via Kokoro.

    Implements the Stage protocol (pipeline/stage.py). Configuration is
    injected at construction; run() processes one book at a time.

    `on_progress`/`should_stop` (Epic 6) are optional Observer-pattern
    hooks -- this stage still has no idea an HTTP server or a batch runner
    exists; it just calls them, if given, once per chunk.
    """

    name = "audio"

    def __init__(
        self,
        input_folder: Path,
        output_folder: Path,
        audit_log: AuditLogRepository,
        tts_engine: TTSEngine,
        default_voice: str = DEFAULT_VOICE,
        max_chunk_chars: int = MAX_CHUNK_CHARS,
        max_chunk_retries: int = DEFAULT_MAX_CHUNK_RETRIES,
        retry_backoff_seconds: float = DEFAULT_RETRY_BACKOFF_SECONDS,
        on_progress: Callable[[str, int, int], None] | None = None,
        should_stop: Callable[[str], str | None] | None = None,
    ) -> None:
        self._input_folder = input_folder
        self._output_folder = output_folder
        self._audit_log = audit_log
        self._tts_engine = tts_engine
        self._default_voice = default_voice
        self._max_chunk_chars = max_chunk_chars
        self._max_chunk_retries = max_chunk_retries
        self._retry_backoff_seconds = retry_backoff_seconds
        # Observer pattern (docs/design/PATTERNS.md §1): this stage never
        # knows an HTTP server or a batch runner exists -- it just calls
        # these two optional hooks, if given, after each chunk. The batch
        # runner (Epic 6) is what turns `on_progress` into the polling
        # contract's `progress` field and `should_stop` into Pause/Cancel
        # (docs/requirements/06-safety-error-handling.md §Cancel design).
        self._on_progress = on_progress
        self._should_stop = should_stop

    def applies_to(self, book: BookState, settings: dict[str, Any]) -> bool:
        # No skip toggle exists for the audio stage -- Screen 1's mockup
        # (03-gui-ux-design.md §Screen 1: Add Books) has exactly two
        # toggles ("Fix messy file names", "Clean up bad language"), not
        # three. Turning a book into an audiobook is this app's whole
        # purpose, unlike rename/sanitize which are genuinely optional
        # cleanup passes.
        return True

    def run(self, book: BookState) -> BookState:
        filename = book.data.get("filename") or (book.book_id + ".epub")
        epub_path = self._input_folder / filename

        if not epub_path.exists():
            return BookState(
                book.book_id,
                "error",
                {**book.data, "error": f"Input EPUB not found: {epub_path}"},
            )

        meta: dict[str, Any] = {
            "title": book.data.get("title"),
            "author_first": book.data.get("author_first"),
            "author_last": book.data.get("author_last"),
            "series": book.data.get("series"),
            "series_number": book.data.get("series_number"),
        }

        voice = book.data.get("voice") or self._default_voice
        if voice not in VOICES:
            return BookState(
                book.book_id,
                "error",
                {**book.data, "error": f"Unknown voice: {voice!r}"},
            )

        try:
            chapters, _skipped, _stopped_at = extract_chapters(str(epub_path))
        except Exception as exc:
            self._audit_log.append(
                self._audit_row(
                    filename, "", meta, voice, skipped_reason="epub_read_error"
                )
            )
            return BookState(
                book.book_id,
                "error",
                {**book.data, "error": f"Could not read EPUB: {exc}"},
            )

        if not chapters:
            self._audit_log.append(
                self._audit_row(filename, "", meta, voice, skipped_reason="no_chapters")
            )
            return BookState(
                book.book_id,
                "error",
                {**book.data, "error": "No chapters extracted from EPUB."},
            )

        base_name = build_filename(meta).removesuffix(".epub")
        book_dir = self._output_folder / base_name
        book_dir.mkdir(parents=True, exist_ok=True)

        try:
            cover_bytes = extract_cover_bytes(epub_path)
        except Exception:
            # Non-fatal -- the audiobook still generates without cover art,
            # same as the original tool's "no cover" warning path.
            cover_bytes = None

        chunked_chapters = [
            (chapter, chunk_text(chapter["text"], self._max_chunk_chars))
            for chapter in chapters
        ]
        total_tracks = sum(len(chunks) for _, chunks in chunked_chapters)

        track_num = 0
        for ch_idx, (chapter, chunks) in enumerate(chunked_chapters, start=1):
            for ck_idx, chunk in enumerate(chunks, start=1):
                track_num += 1

                if self._should_stop is not None:
                    stop_reason = self._should_stop(book.book_id)
                    if stop_reason is not None:
                        # Stop before starting the next chunk -- already-
                        # written chunks are untouched, which is exactly
                        # what makes the existing per-chunk resume check
                        # above safe to rely on for Pause/Cancel-keep-
                        # partial recovery (06-safety-error-handling.md
                        # §Cancel design).
                        return BookState(
                            book.book_id,
                            stop_reason,
                            {
                                **book.data,
                                "audio_folder": str(book_dir),
                                "voice": voice,
                                "chunks_done": track_num - 1,
                                "chunks_total": total_tracks,
                            },
                        )

                mp3_name = (
                    f"{base_name} - {ch_idx:03}_{ck_idx}.mp3"
                    if len(chunks) > 1
                    else f"{base_name} - {ch_idx:03}.mp3"
                )
                mp3_path = book_dir / mp3_name

                if mp3_path.exists() and mp3_path.stat().st_size > MIN_VALID_MP3_BYTES:
                    continue  # resume: already generated in a prior run

                mp3_bytes = self._generate_with_retry(chunk, voice)
                if mp3_bytes is None:
                    self._audit_log.append(
                        self._audit_row(
                            filename,
                            base_name,
                            meta,
                            voice,
                            skipped_reason="generation_failed",
                        )
                    )
                    return BookState(
                        book.book_id,
                        "error",
                        {
                            **book.data,
                            "error": (
                                f"Audio generation failed at chapter {ch_idx}, "
                                f"chunk {ck_idx} (track {track_num}/{total_tracks})"
                            ),
                            "audio_folder": str(book_dir),
                        },
                    )

                mp3_path.write_bytes(mp3_bytes)
                _apply_tags(
                    mp3_path,
                    meta,
                    track_number=track_num,
                    total_tracks=total_tracks,
                    chapter_title=chapter["title"],
                    cover_bytes=cover_bytes,
                )

                if self._on_progress is not None:
                    self._on_progress(book.book_id, track_num, total_tracks)

        self._audit_log.append(self._audit_row(filename, base_name, meta, voice))
        return BookState(
            book.book_id,
            "audio_generated",
            {
                **book.data,
                "audio_folder": str(book_dir),
                "voice": voice,
                "chunks_total": total_tracks,
            },
        )

    def _generate_with_retry(self, text: str, voice: str) -> bytes | None:
        for attempt in range(1, self._max_chunk_retries + 1):
            try:
                return self._tts_engine.generate(text, voice)
            except Exception:
                if attempt == self._max_chunk_retries:
                    return None
                time.sleep(self._retry_backoff_seconds)
        return None

    def _audit_row(
        self,
        original_filename: str,
        new_name: str,
        meta: dict[str, Any],
        voice: str,
        *,
        skipped_reason: str = "",
    ) -> dict[str, Any]:
        author = " ".join(
            part for part in (meta.get("author_first"), meta.get("author_last")) if part
        )
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "stage": self.name,
            "original_filename": original_filename,
            "new_filename": new_name,
            "title": meta.get("title") or "",
            "author": author,
            "series": meta.get("series") or "",
            "series_number": meta.get("series_number") or "",
            "voice": voice,
            "skipped_reason": skipped_reason,
        }


def _apply_tags(
    mp3_path: Path,
    meta: dict[str, Any],
    *,
    track_number: int,
    total_tracks: int,
    chapter_title: str,
    cover_bytes: bytes | None,
) -> None:
    """Write ID3v2.3 tags (title, artist, album, track, cover) to an MP3.

    Ported from epub-to-audio\\epub2audio.py's `apply_tags()`, adapted to
    this project's `author_first`/`author_last` metadata shape (ADR-0014).
    Tag values are the raw (unsanitized) metadata -- ID3 free text can hold
    any Unicode; only filenames/folder names go through
    `sanitize_filesystem_name()` (ADR-0016).
    """
    try:
        tags = ID3(str(mp3_path))
    except ID3NoHeaderError:
        tags = ID3()

    display = chapter_title or f"Chapter {track_number}"
    last = meta.get("author_last") or "Unknown"
    first = meta.get("author_first") or "Unknown"
    author = f"{last}, {first}"
    title = meta.get("title") or "Unknown"
    album = meta.get("series") or title

    tags.add(TIT2(encoding=3, text=f"{track_number:03} {title} — {display}"))
    tags.add(TPE1(encoding=3, text=author))
    tags.add(TALB(encoding=3, text=album))
    tags.add(TRCK(encoding=3, text=f"{track_number}/{total_tracks}"))

    if cover_bytes:
        tags.add(
            APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=cover_bytes)
        )

    tags.save(str(mp3_path), v2_version=3)
