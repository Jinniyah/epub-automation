"""Core stateful batch-orchestration engine (Epic 6, docs/BACKLOG.md).

This is the "one tested core" both front doors build on (ADR-0001): the
interactive, multi-book workflow driven by the polling status contract
(docs/requirements/01-architecture.md §Status endpoint contract) --
adding/removing books, running rename -> sanitize automatically per book
(pausing at `needs_input` for her metadata review), per-book/per-batch
voice assignment, serial audio generation in a background thread
(ADR-0009), Pause/Cancel (docs/requirements/06-safety-error-handling.md
§Cancel design), output-collision handling, manually-triggered retag, and
ADR-0017's post-completion `Library/*` cleanup.

`backend/bridge.py` is a thin Adapter over this class (docs/design/
PATTERNS.md §1) -- every method here is plain Python, independently
testable without Flask/HTTP. `main.py`'s CLI does *not* use this class:
the CLI has no UI to answer a `needs_input` pause, so it drives the
underlying stages directly and non-interactively instead
(`pipeline.cli_runner.run_stage_over_folder`).

Threading model: identification (rename -> sanitize) and generation
(audio) each run in their own background `threading.Thread` so a long
audio job never blocks HTTP polling. Every method that mutates shared
state takes `self._lock` (a plain `threading.RLock`) around the mutation.
None of the pause points below (`needs_input` of any type, including an
output collision) block a background thread waiting for her answer --
the loop that hit the pause just moves on to the next book, and whatever
she eventually answers is applied synchronously, later, from the HTTP
request thread that carries her answer in. This keeps every method here
fast and keeps "closing the tab is safe, generation continues" true
without needing cross-thread signalling for the interactive steps.
"""

from __future__ import annotations

import shutil
import threading
import uuid
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from pipeline.audio_stage import AudioStage
from pipeline.audit_logger import AuditLogRepository
from pipeline.disk_space import (
    BookSpaceEstimate,
    DiskSpaceReport,
    check_free_space,
    estimate_batch_bytes,
)
from pipeline.epub_utils import extract_chapters
from pipeline.input_validation import (
    DEFAULT_MAX_FILES,
    ValidationResult,
    check_batch_capacity,
    validate_epub_file,
)
from pipeline.rename_stage import RenameStage
from pipeline.retag_stage import RetagStage
from pipeline.sanitize_stage import SanitizeStage
from pipeline.stage import BookState, Stage
from pipeline.state_manager import StateRepository
from pipeline.tts_engine import DEFAULT_VOICE, TTSEngineLike

# Per-book status vocabulary -- docs/requirements/01-architecture.md
# §Status endpoint contract. `needs_input`'s own `type` sub-field
# disambiguates *which* one-off screen a `needs_input` book is actually
# waiting on; see `NeedsInputType` below.
STATUS_PENDING = "pending"
STATUS_IDENTIFYING = "identifying"
STATUS_NEEDS_INPUT = "needs_input"
STATUS_IDENTIFIED = "identified"
STATUS_VOICE_PICK = "voice_pick"
STATUS_GENERATING = "generating"
STATUS_PAUSED = "paused"
STATUS_COMPLETE = "complete"
STATUS_CANCELLED = "cancelled"
STATUS_ERROR = "error"


def _dedupe_path(path: Path) -> Path:
    """If `path` already exists, append " (2)", " (3)", ... before the
    suffix until a free name is found -- used both for two source books
    sharing a filename landing in `00-Incoming/` together, and for the
    "keep both" choice in an output collision
    (06-safety-error-handling.md §Concurrency & duplicate handling)."""
    if not path.exists():
        return path
    counter = 2
    while True:
        candidate = path.with_name(f"{path.stem} ({counter}){path.suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


class NeedsInputType:
    """`needs_input.type` values. The four named in 01-architecture.md's
    example are illustrative ("an object *like*"), not exhaustive --
    `OUTPUT_COLLISION` is this epic's own addition, needed to satisfy
    docs/BACKLOG.md Epic 6's explicit "distinct prompts for EPUB vs.
    audiobook" collision-handling requirement, which the four originally
    -listed types have no room for."""

    CONFIRM_METADATA = "confirm_metadata"
    AI_ENRICHMENT_FAILED = "ai_enrichment_failed"
    PICK_VOICE = "pick_voice"
    REVIEW_RESULT = "review_result"
    OUTPUT_COLLISION = "output_collision"


@dataclass(frozen=True)
class AddBookResult:
    ok: bool
    book: BookState | None = None
    reason: Any = None
    message: str = ""


class BatchRunner:
    """Owns one batch's worth of books from "Add Books" through Review.

    A fresh `BatchRunner` is a fresh batch -- the caller (bridge.py) is
    responsible for constructing one per run and for state-file-driven
    "Welcome back" reconstruction on backend restart (out of scope for
    this class itself, which only manages the *current* in-memory batch;
    see the module docstring's "not a second source of truth" framing in
    01-architecture.md, which state_repo already exists to satisfy).
    """

    def __init__(
        self,
        *,
        library_root: Path,
        output_folder: Path,
        report_dir: Path,
        state_repo: StateRepository,
        audit_log: AuditLogRepository,
        settings: dict[str, Any],
        tts_engine: TTSEngineLike,
        max_files: int = DEFAULT_MAX_FILES,
    ) -> None:
        self._incoming_dir = library_root / "00-Incoming"
        self._renamed_dir = library_root / "01-Renamed"
        self._sanitized_dir = library_root / "02-Sanitized"
        self._audio_dir = library_root / "03-Audio"
        self._output_folder = output_folder
        self._report_dir = report_dir
        self._state_repo = state_repo
        self._audit_log = audit_log
        self._settings = settings
        self._tts_engine = tts_engine
        self._max_files = max_files

        self._lock = threading.RLock()
        self._books: dict[str, BookState] = {}
        self._book_order: list[str] = []
        self._identification_thread: threading.Thread | None = None
        self._generation_thread: threading.Thread | None = None
        self._pause_requests: set[str] = set()
        self._cancel_requests: dict[str, str] = {}  # book_id -> "keep" | "discard"

    # ------------------------------------------------------------------
    # Screen 1: Add Books
    # ------------------------------------------------------------------

    def snapshot(self) -> list[BookState]:
        """A thread-safe, ordered copy of every book's current state --
        what backend/bridge.py's status endpoint reads to build the
        polling response."""
        with self._lock:
            return [self._books[bid] for bid in self._book_order]

    def add_book(
        self, source_path: Path, *, original_filename: str | None = None
    ) -> AddBookResult:
        """`original_filename` defaults to `source_path.name` -- correct
        for CLI-style callers where that *is* the real filename, but the
        GUI upload route must pass the browser's own multipart filename
        explicitly: it saves each upload to a collision-avoiding
        `<index>_<name>` temp path first
        (`backend/app.py::_safe_upload_path()`), and without this
        override that index prefix would otherwise leak into
        `original_filename` (what Screen 1 actually displays) -- a real
        bug found via a live browser smoke test, not by the unit suite,
        since every existing test happened to call this with a source
        path that was already the true filename.

        Deliberately used for *display only* -- the `00-Incoming/` copy
        itself still takes its filename from `source_path.name` (already
        sanitized by `_safe_upload_path()`), never from this
        attacker-controlled value, so a crafted `original_filename`
        can't reintroduce a path-traversal write via `_dedupe_path()`
        below.
        """
        with self._lock:
            capacity = check_batch_capacity(len(self._books), self._max_files)
            if not capacity.ok:
                return AddBookResult(
                    False, reason=capacity.reason, message=capacity.message
                )

            validation: ValidationResult = validate_epub_file(source_path)
            if not validation.ok:
                return AddBookResult(
                    False, reason=validation.reason, message=validation.message
                )

            display_name = original_filename or source_path.name
            book_id = uuid.uuid4().hex[:8]
            self._incoming_dir.mkdir(parents=True, exist_ok=True)
            dest = _dedupe_path(self._incoming_dir / source_path.name)
            shutil.copy2(source_path, dest)

            book = BookState(
                book_id=book_id,
                status=STATUS_PENDING,
                data={
                    "original_filename": display_name,
                    "filename": dest.name,
                    "source_bytes": source_path.stat().st_size,
                    # Per-stage-folder filename, keyed by stage -- what
                    # actually lets _cleanup_library_copies() find and
                    # delete the right file in each Library/* directory
                    # later, since sanitize's output filename differs from
                    # its input (an "_cln" suffix), so the final
                    # `filename` alone isn't enough to locate every copy.
                    "_trace": {"incoming": dest.name},
                },
            )
            self._books[book_id] = book
            self._book_order.append(book_id)
            return AddBookResult(True, book=book)

    def remove_book(self, book_id: str) -> bool:
        """Screen 1's per-row "Remove" -- instant, no confirmation needed
        (03-gui-ux-design.md §Screen 1). Only valid before that book has
        started processing; a book already mid-pipeline is removed via
        Cancel instead, not this method."""
        with self._lock:
            book = self._books.get(book_id)
            if book is None or book.status != STATUS_PENDING:
                return False
            filename = book.data.get("filename")
            if filename:
                (self._incoming_dir / filename).unlink(missing_ok=True)
            del self._books[book_id]
            self._book_order.remove(book_id)
            return True

    def disk_space_report(self) -> DiskSpaceReport:
        """Pre-Start disk-space estimate summed across every book
        currently in the batch (06-safety-error-handling.md §Resource &
        cost safety) -- callable any time after books are added, before
        Start."""
        estimates = []
        with self._lock:
            books = list(self.snapshot())
        for book in books:
            epub_path = self._current_epub_path(book)
            remaining_chars = 0
            if epub_path is not None and epub_path.exists():
                try:
                    chapters, _skipped, _stopped = extract_chapters(str(epub_path))
                    remaining_chars = sum(len(c["text"]) for c in chapters)
                except Exception:
                    remaining_chars = 0
            estimates.append(
                BookSpaceEstimate(
                    book_id=book.book_id,
                    source_bytes=int(book.data.get("source_bytes") or 0),
                    remaining_chars=remaining_chars,
                )
            )
        required = estimate_batch_bytes(estimates)
        return check_free_space(
            [self._incoming_dir.parent, self._output_folder], required
        )

    def _current_epub_path(self, book: BookState) -> Path | None:
        epub_path = book.data.get("epub_path")
        if epub_path:
            return Path(epub_path)
        filename = book.data.get("filename")
        if filename:
            return self._incoming_dir / str(filename)
        return None

    # ------------------------------------------------------------------
    # Per-book identification loop (rename -> sanitize)
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Kick off the identification loop for every `pending` book in
        the batch, in a background thread.

        Safe to call again at any time, including while a previous
        identification pass is still running: any newly-pending book is
        flipped to `identifying` immediately regardless, and the
        already-running thread's own loop (`_run_identification`) picks
        it up on its next pass -- rather than the book being silently
        stranded at `pending` forever unless `start()` happens to be
        called again *after* that thread has already exited.
        """
        with self._lock:
            pending_ids = [
                bid
                for bid in self._book_order
                if self._books[bid].status == STATUS_PENDING
            ]
            for bid in pending_ids:
                self._books[bid] = replace(self._books[bid], status=STATUS_IDENTIFYING)
            if (
                self._identification_thread is not None
                and self._identification_thread.is_alive()
            ):
                return
            has_work = any(
                self._books[bid].status == STATUS_IDENTIFYING
                for bid in self._book_order
            )
            if not has_work:
                return
            self._identification_thread = threading.Thread(
                target=self._run_identification, daemon=True
            )
            self._identification_thread.start()

    def _build_rename_stage(self) -> RenameStage:
        return RenameStage(
            self._incoming_dir,
            self._renamed_dir,
            self._audit_log,
            ai_provider=self._settings.get("ai_provider", "none"),
            ai_api_key=self._settings.get("ai_api_key", ""),
        )

    def _build_sanitize_stage(self) -> SanitizeStage | None:
        if not self._settings.get("clean_language", True):
            return None
        words = self._settings.get("profanity_words") or ["placeholder"]
        return SanitizeStage(
            self._renamed_dir, self._sanitized_dir, self._report_dir, words
        )

    def _run_identification(self) -> None:
        """Process every book currently at `identifying`, looping until
        none remain.

        Re-querying live state each pass (rather than a fixed list
        captured once at thread-start) is what lets `start()` safely
        hand more work to this *same* running thread instead of a book
        added mid-run needing a second thread -- see `start()`'s own
        docstring.
        """
        rename_stage = self._build_rename_stage()
        sanitize_stage = self._build_sanitize_stage()

        while True:
            with self._lock:
                book_ids = [
                    bid
                    for bid in self._book_order
                    if self._books[bid].status == STATUS_IDENTIFYING
                ]
            if not book_ids:
                break

            for book_id in book_ids:
                book = self._run_one_stage(
                    rename_stage,
                    book_id,
                    self._incoming_dir,
                    self._renamed_dir,
                    "renamed",
                    "rename",
                )
                if book.status == STATUS_ERROR:
                    continue

                if sanitize_stage is not None:
                    book = self._run_one_stage(
                        sanitize_stage,
                        book_id,
                        self._renamed_dir,
                        self._sanitized_dir,
                        "sanitized",
                        "sanitize",
                    )
                else:
                    book = self._pass_through(
                        book_id,
                        self._renamed_dir,
                        self._sanitized_dir,
                        "sanitized",
                        "sanitize",
                    )
                if book.status == STATUS_ERROR:
                    continue

                needs_type = (
                    NeedsInputType.CONFIRM_METADATA
                    if book.data.get("title")
                    else NeedsInputType.AI_ENRICHMENT_FAILED
                )
                with self._lock:
                    self._books[book_id] = replace(
                        book,
                        status=STATUS_NEEDS_INPUT,
                        data={**book.data, "needs_input_type": needs_type},
                    )

        if sanitize_stage is not None:
            sanitize_stage.write_report()

    def _run_one_stage(
        self,
        stage: Stage,
        book_id: str,
        input_dir: Path,
        output_dir: Path,
        stage_key: str,
        state_stage: str,
    ) -> BookState:
        with self._lock:
            book = self._books[book_id]
        if not stage.applies_to(book, self._settings):
            return self._pass_through(
                book_id, input_dir, output_dir, stage_key, state_stage
            )
        updated = self._record_trace(stage.run(book), stage_key)
        with self._lock:
            self._books[book_id] = updated
        if updated.status != STATUS_ERROR:
            self._mark_and_persist_stage_complete(book_id, state_stage)
        return updated

    def _pass_through(
        self,
        book_id: str,
        input_dir: Path,
        output_dir: Path,
        stage_key: str,
        state_stage: str,
    ) -> BookState:
        """A skipped stage (its Screen-1 toggle is off) still has to move
        the file forward unchanged (02-pipeline-stages.md §Stage 1: "files
        pass through to 01-Renamed/ unchanged")."""
        with self._lock:
            book = self._books[book_id]
        filename = book.data.get("filename") or (book.book_id + ".epub")
        src = input_dir / filename
        output_dir.mkdir(parents=True, exist_ok=True)
        dst = output_dir / filename
        if src.resolve() != dst.resolve():
            shutil.copy2(src, dst)
        updated = replace(
            book, data={**book.data, "filename": filename, "epub_path": str(dst)}
        )
        updated = self._record_trace(updated, stage_key)
        with self._lock:
            self._books[book_id] = updated
        self._mark_and_persist_stage_complete(book_id, state_stage)
        return updated

    def _mark_and_persist_stage_complete(self, book_id: str, stage_name: str) -> None:
        """Keep `state.json` genuinely current as each stage finishes --
        the "what's already done" data the "Welcome back" flow
        (docs/requirements/06-safety-error-handling.md §Long-run
        resilience, `StateRepository.incomplete_book_ids()`) depends on
        being real, not just updated at the very end via `_mark_complete`.
        """
        self._state_repo.mark_stage_complete(book_id, stage_name)
        self._state_repo.save()

    def _record_trace(self, book: BookState, stage_key: str) -> BookState:
        """Remember which filename this book has in the `stage_key`
        Library/* folder specifically -- a stage's output filename can
        differ from its input (sanitize adds an `_cln` suffix), so the
        book's final `filename` alone isn't enough to find every copy
        later (`_cleanup_library_copies`, ADR-0017)."""
        trace = dict(book.data.get("_trace") or {})
        trace[stage_key] = book.data.get("filename")
        return replace(book, data={**book.data, "_trace": trace})

    # ------------------------------------------------------------------
    # Confirm metadata / voice assignment
    # ------------------------------------------------------------------

    _METADATA_FIELDS = (
        "title",
        "author_first",
        "author_last",
        "series",
        "series_number",
    )

    def confirm_metadata(
        self, book_id: str, corrections: dict[str, Any] | None = None
    ) -> BookState:
        """The per-book "Confirm metadata" step (03-gui-ux-design.md
        §Per-book identification loop) -- accepts whatever she confirmed
        or corrected via the Field Correction Popup. Once every book in
        the batch has been confirmed, the whole batch advances to voice
        assignment together (03-gui-ux-design.md: "This loop completes for
        all books in the batch before generation starts for any of
        them")."""
        with self._lock:
            book = self._books[book_id]
            if book.status != STATUS_NEEDS_INPUT:
                raise ValueError(
                    f"Book {book_id!r} is not awaiting metadata confirmation"
                )

            data = dict(book.data)
            if corrections:
                for key in self._METADATA_FIELDS:
                    if key in corrections:
                        data[key] = corrections[key]
            data.pop("needs_input_type", None)
            updated = BookState(book_id, STATUS_IDENTIFIED, data)
            self._books[book_id] = updated

        self._maybe_enter_voice_pick()
        return updated

    def update_metadata(self, book_id: str, corrections: dict[str, Any]) -> BookState:
        """Correct a book's title/author/series while it's sitting at
        `voice_pick`, before any audio exists to retag -- the multi-book
        voice table's clickable book title reopens the same metadata
        review used during identification, without leaving that screen
        or derailing the rest of the batch (03-gui-ux-design.md §Voice
        assignment). Distinct from `retag_book()` below, which operates
        on an already-generated audiobook's files on disk; this just
        patches the in-memory metadata generation will use.
        """
        with self._lock:
            book = self._books[book_id]
            if book.status != STATUS_VOICE_PICK:
                raise ValueError(
                    f"Book {book_id!r} is not available for metadata edits"
                )
            data = dict(book.data)
            for key in self._METADATA_FIELDS:
                if key in corrections:
                    data[key] = corrections[key]
            updated = replace(book, data=data)
            self._books[book_id] = updated
        return updated

    def _maybe_enter_voice_pick(self) -> None:
        """Pre-fills every newly-identified book with her single global
        last-used voice (03-gui-ux-design.md §Voice assignment: "a
        suggestion only, not a lock"). Deliberately does **not** trigger
        the single-book auto-start itself -- that must wait for her
        actual selection via `assign_voice()` below (its own docstring:
        "picking a voice and pressing Next starts generating
        immediately"). Calling it from here too used to fire it the
        instant metadata was confirmed, before the single-book voice
        picker screen could ever matter -- a real bug found while
        building that screen (Epic 8), not a deliberate design choice.
        """
        with self._lock:
            active = [self._books[bid] for bid in self._book_order]
            still_identifying = any(
                b.status in (STATUS_PENDING, STATUS_IDENTIFYING, STATUS_NEEDS_INPUT)
                for b in active
            )
            if still_identifying:
                return
            identified = [b for b in active if b.status == STATUS_IDENTIFIED]
            if not identified:
                return

            default_voice = self._settings.get("last_voice") or DEFAULT_VOICE
            for book in identified:
                self._books[book.book_id] = replace(
                    book,
                    status=STATUS_VOICE_PICK,
                    data={**book.data, "voice": default_voice},
                )

    def assign_voice(self, book_id: str, voice: str) -> BookState:
        """ "Change Voice" on one row of the multi-book table, or the
        single-book voice picker's own selection."""
        with self._lock:
            book = self._books[book_id]
            if book.status != STATUS_VOICE_PICK:
                raise ValueError(f"Book {book_id!r} is not awaiting a voice pick")
            updated = replace(book, data={**book.data, "voice": voice})
            self._books[book_id] = updated

        self._settings["last_voice"] = voice
        self._maybe_auto_start_single_book_generation()
        return updated

    def _maybe_auto_start_single_book_generation(self) -> None:
        """Single-book batches skip the multi-book table's explicit "Start
        All Books" button entirely -- picking a voice and pressing Next
        starts generating immediately (03-gui-ux-design.md §Voice
        assignment)."""
        with self._lock:
            if len(self._book_order) != 1:
                return
            only = self._books[self._book_order[0]]
            if only.status != STATUS_VOICE_PICK:
                return
        self.start_generation()

    # ------------------------------------------------------------------
    # Audio generation
    # ------------------------------------------------------------------

    def start_generation(self) -> None:
        """ "Start All Books" -- kicks off serial audio generation
        (ADR-0009) for every book currently at `voice_pick`, and resumes
        any `paused` book by re-queueing it the same way: flipped back to
        `voice_pick` here, so a paused book and a never-started one are
        indistinguishable to `_run_generation` from this point on (this
        is also what makes resuming self-healing -- see below -- rather
        than needing its own separate case).

        Safe to call again at any time, including while a previous
        generation pass is still running: the already-running thread's
        own loop (`_run_generation`) re-checks for queued `voice_pick`
        books each pass, so a book that reaches `voice_pick` (or gets
        resumed) while generation is already underway still gets picked
        up automatically -- see `start()`'s identical reasoning for the
        identification loop. A currently-`generating` book is
        deliberately left untouched here: only Pause/Cancel are allowed
        to interrupt it (docs/requirements/06-safety-error-handling.md
        §Cancel design).
        """
        with self._lock:
            for bid in self._book_order:
                if self._books[bid].status == STATUS_PAUSED:
                    self._books[bid] = replace(
                        self._books[bid], status=STATUS_VOICE_PICK
                    )
            if (
                self._generation_thread is not None
                and self._generation_thread.is_alive()
            ):
                return
            has_work = any(
                self._books[bid].status == STATUS_VOICE_PICK for bid in self._book_order
            )
            if not has_work:
                return
            self._generation_thread = threading.Thread(
                target=self._run_generation, daemon=True
            )
            self._generation_thread.start()

    def _run_generation(self) -> None:
        default_voice = self._settings.get("last_voice") or DEFAULT_VOICE
        audio_stage = AudioStage(
            self._sanitized_dir,
            self._audio_dir,
            self._audit_log,
            self._tts_engine,
            default_voice=default_voice,
            on_progress=self._on_audio_progress,
            should_stop=self._should_stop_audio,
        )

        while True:
            with self._lock:
                book_ids = [
                    bid
                    for bid in self._book_order
                    if self._books[bid].status == STATUS_VOICE_PICK
                ]
            if not book_ids:
                break

            for book_id in book_ids:
                with self._lock:
                    book = self._books[book_id]
                    if book.status != STATUS_VOICE_PICK:
                        continue
                    self._books[book_id] = replace(book, status=STATUS_GENERATING)
                    book = self._books[book_id]

                updated = audio_stage.run(book)

                if updated.status == STATUS_CANCELLED:
                    keep = self._cancel_requests.pop(book_id, "keep") == "keep"
                    with self._lock:
                        self._books[book_id] = updated
                    self._finalize_cancel(book_id, keep_partial=keep)
                    continue

                if updated.status == STATUS_PAUSED:
                    with self._lock:
                        self._books[book_id] = updated
                    continue

                if updated.status == STATUS_ERROR:
                    with self._lock:
                        self._books[book_id] = updated
                    continue

                self._finish_generation(book_id, updated)

    def _on_audio_progress(
        self, book_id: str, chunks_done: int, chunks_total: int
    ) -> None:
        with self._lock:
            book = self._books.get(book_id)
            if book is None:
                return
            self._books[book_id] = replace(
                book,
                data={
                    **book.data,
                    "chunks_done": chunks_done,
                    "chunks_total": chunks_total,
                },
            )

    def _should_stop_audio(self, book_id: str) -> str | None:
        with self._lock:
            if book_id in self._cancel_requests:
                return STATUS_CANCELLED
            if book_id in self._pause_requests:
                self._pause_requests.discard(book_id)
                return STATUS_PAUSED
        return None

    def _finish_generation(self, book_id: str, updated: BookState) -> None:
        """Audio finished for this book -- copy the audiobook folder out
        to `output_folder` (handling an output collision if one exists),
        then pause at `needs_input: review_result`
        (03-gui-ux-design.md §Screen: Review)."""
        audio_folder = Path(updated.data["audio_folder"])
        collision = self._detect_collision(self._output_folder / audio_folder.name)
        if collision is not None:
            with self._lock:
                self._books[book_id] = replace(
                    updated,
                    status=STATUS_NEEDS_INPUT,
                    data={
                        **updated.data,
                        "needs_input_type": NeedsInputType.OUTPUT_COLLISION,
                        "collision": {"artifact": "audiobook", "path": collision},
                    },
                )
            return

        dest = self._copy_tree_to_output(audio_folder)
        # Persist "audio" complete to state.json *before* this book
        # becomes visible (via polling) as awaiting her review -- a fast
        # client answering the review immediately must never be able to
        # race ahead of this write (a real TOCTOU risk, since review's
        # own completion path and this one share the same state file).
        self._mark_and_persist_stage_complete(book_id, "audio")
        with self._lock:
            self._books[book_id] = replace(
                updated,
                status=STATUS_NEEDS_INPUT,
                data={
                    **updated.data,
                    "needs_input_type": NeedsInputType.REVIEW_RESULT,
                    "output_audio_folder": str(dest),
                },
            )

    def _detect_collision(self, target: Path) -> str | None:
        return str(target) if target.exists() else None

    def _copy_tree_to_output(self, folder: Path) -> Path:
        dest = self._output_folder / folder.name
        self._output_folder.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(folder, dest)
        return dest

    # ------------------------------------------------------------------
    # Pause / Cancel (06-safety-error-handling.md §Cancel design)
    # ------------------------------------------------------------------

    def request_pause(self, book_id: str) -> None:
        with self._lock:
            self._pause_requests.add(book_id)

    def request_cancel(self, book_id: str, *, keep_partial: bool = True) -> BookState:
        with self._lock:
            book = self._books[book_id]
            if book.status == STATUS_GENERATING:
                self._cancel_requests[book_id] = "keep" if keep_partial else "discard"
                return book
        return self._finalize_cancel(book_id, keep_partial=keep_partial)

    def _finalize_cancel(self, book_id: str, *, keep_partial: bool) -> BookState:
        with self._lock:
            book = self._books[book_id]
            data = dict(book.data)
            if not keep_partial:
                audio_folder = data.pop("audio_folder", None)
                if audio_folder:
                    shutil.rmtree(Path(audio_folder), ignore_errors=True)
                data.pop("chunks_done", None)
                data.pop("chunks_total", None)
            updated = BookState(book_id, STATUS_CANCELLED, data)
            self._books[book_id] = updated
        # 06-safety-error-handling.md §Cancel design: reset the state
        # file's record of this book's audio progress to match reality,
        # regardless of which choice she made, so a later run doesn't
        # think it's further along (or fully done) than it actually is.
        self._state_repo.reset_stage(book_id, "audio")
        self._state_repo.save()
        return updated

    # ------------------------------------------------------------------
    # Output collision resolution
    # ------------------------------------------------------------------

    def resolve_collision(self, book_id: str, choice: str) -> BookState:
        """`choice` is `"replace"` or `"keep_both"`
        (06-safety-error-handling.md §Concurrency & duplicate handling).
        Only ever called for a book currently paused on an
        `output_collision` -- performs the deferred copy, then proceeds
        exactly as `_finish_generation` would have if there'd been no
        collision."""
        with self._lock:
            book = self._books[book_id]
            if (
                book.status != STATUS_NEEDS_INPUT
                or book.data.get("needs_input_type") != NeedsInputType.OUTPUT_COLLISION
            ):
                raise ValueError(f"Book {book_id!r} has no pending output collision")
            collision = book.data["collision"]

        audio_folder = Path(book.data["audio_folder"])
        if choice == "keep_both":
            dest = _dedupe_path(self._output_folder / audio_folder.name)
            self._output_folder.mkdir(parents=True, exist_ok=True)
            shutil.copytree(audio_folder, dest)
        else:  # "replace"
            dest = Path(collision["path"])
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(audio_folder, dest)

        # Same ordering requirement as _finish_generation: persist "audio"
        # complete before this book becomes visible as awaiting review.
        self._mark_and_persist_stage_complete(book_id, "audio")
        with self._lock:
            data = dict(book.data)
            data.pop("collision", None)
            data["needs_input_type"] = NeedsInputType.REVIEW_RESULT
            data["output_audio_folder"] = str(dest)
            updated = replace(book, data=data)
            self._books[book_id] = updated
        return updated

    # ------------------------------------------------------------------
    # Review + retag (docs/requirements/02-pipeline-stages.md §Stage 4)
    # ------------------------------------------------------------------

    def review_result(self, book_id: str, *, looks_good: bool) -> BookState:
        with self._lock:
            book = self._books[book_id]
            if (
                book.status != STATUS_NEEDS_INPUT
                or book.data.get("needs_input_type") != NeedsInputType.REVIEW_RESULT
            ):
                raise ValueError(f"Book {book_id!r} has no pending review")

        if looks_good:
            return self._mark_complete(book_id)

        # "No, let me fix it" -- caller (bridge.py) collects her corrected
        # fields via the same Field Correction Popup flow, then calls
        # retag_book() directly with them; this method just leaves the
        # book parked at needs_input/review_result until that happens.
        return book

    def retag_book(self, book_id: str, overrides: dict[str, Any]) -> BookState:
        """ "No, let me fix it" (03-gui-ux-design.md) -- a fast, local
        rename/retag pass, not a regeneration. Runs synchronously (this is
        seconds of work, not minutes, per that section), directly on the
        HTTP request thread that carries her corrections in.

        Retag must operate on the copy in `output_folder`
        (`output_audio_folder`), not the internal `Library/03-Audio`
        working copy (`audio_folder`) -- ADR-0017 deletes the latter the
        moment this book reaches `complete`, so retagging it instead would
        silently discard her corrections the moment cleanup ran.
        """
        with self._lock:
            book = self._books[book_id]
        library_audio_folder = book.data.get("audio_folder")
        data = {**book.data, **{k: v for k, v in overrides.items() if v is not None}}
        data["audio_folder"] = book.data.get("output_audio_folder")
        stage = RetagStage(self._audit_log)
        updated = stage.run(BookState(book_id, book.status, data))

        if updated.status == STATUS_ERROR:
            with self._lock:
                self._books[book_id] = updated
            return updated

        # RetagStage renamed the *output* folder in place -- restore the
        # separate internal-Library-copy bookkeeping field so ADR-0017
        # cleanup still finds (and deletes) the right, now-superseded
        # internal copy, not the freshly-retagged output one.
        final_data = dict(updated.data)
        final_data["output_audio_folder"] = final_data["audio_folder"]
        final_data["audio_folder"] = library_audio_folder
        with self._lock:
            self._books[book_id] = replace(updated, data=final_data)
        return self._mark_complete(book_id)

    def _mark_complete(self, book_id: str) -> BookState:
        with self._lock:
            book = self._books[book_id]
            data = dict(book.data)
            data.pop("needs_input_type", None)
            updated = BookState(book_id, STATUS_COMPLETE, data)
            self._books[book_id] = updated
        self._cleanup_library_copies(book_id, updated)
        return updated

    # ------------------------------------------------------------------
    # ADR-0017: Library/* cleanup once a book is genuinely done
    # ------------------------------------------------------------------

    def _cleanup_library_copies(self, book_id: str, book: BookState) -> None:
        """Delete this book's working copies from every Library/* stage
        folder it passed through -- ADR-0017. Never called for a
        `cancelled`-with-keep-partial book (that path never reaches
        `_mark_complete` at all)."""
        try:
            trace = book.data.get("_trace") or {}
            for stage_dir, stage_key in (
                (self._incoming_dir, "incoming"),
                (self._renamed_dir, "renamed"),
                (self._sanitized_dir, "sanitized"),
            ):
                filename = trace.get(stage_key)
                if filename:
                    (stage_dir / filename).unlink(missing_ok=True)
            audio_folder = book.data.get("audio_folder")
            if audio_folder:
                shutil.rmtree(Path(audio_folder), ignore_errors=True)
            self._mark_and_persist_stage_complete(book_id, "cleanup")
        except OSError:
            # A failed cleanup attempt must never fail the batch that
            # already succeeded from her point of view -- log and move on,
            # retried on a later launch (ADR-0017 §Consequences).
            pass
