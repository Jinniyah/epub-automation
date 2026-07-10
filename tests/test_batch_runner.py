"""Tests for pipeline/batch_runner.py -- the core stateful batch
orchestration engine (Epic 6, docs/BACKLOG.md).

Every stage this exercises (rename/sanitize/audio/retag) uses real Stage
implementations -- only the TTS engine is faked (never touches real
Kokoro), same discipline as tests/test_audio_stage.py.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

import pytest
from ebooklib import epub

from pipeline.audit_logger import AuditLogRepository
from pipeline.batch_runner import (
    STATUS_CANCELLED,
    STATUS_COMPLETE,
    STATUS_IDENTIFIED,
    STATUS_IDENTIFYING,
    STATUS_NEEDS_INPUT,
    STATUS_PAUSED,
    STATUS_VOICE_PICK,
    BatchRunner,
    NeedsInputType,
)
from pipeline.input_validation import RejectionReason
from pipeline.rename_stage import RenameStage, build_filename
from pipeline.stage import BookState
from pipeline.state_manager import StateRepository

_LONG_TEXT = "Some real narrative content, sentence by sentence. " * 20
_MULTI_CHUNK_TEXT = "Sentence content here. " * 400


def _make_epub(
    path: Path,
    *,
    title: str = "Fated",
    author: str = "Benedict Jacka",
    chapters: list[tuple[str, str]] | None = None,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    book = epub.EpubBook()
    book.set_identifier("id-batch-test")
    book.set_title(title)
    book.set_language("en")
    book.add_author(author)

    toc = []
    spine: list[Any] = ["nav"]
    for i, (ch_title, text) in enumerate(
        chapters or [("Chapter 1", _LONG_TEXT)], start=1
    ):
        doc = epub.EpubHtml(title=ch_title, file_name=f"chap{i}.xhtml", lang="en")
        doc.content = f"<html><body><h1>{ch_title}</h1><p>{text}</p></body></html>"
        book.add_item(doc)
        toc.append(doc)
        spine.append(doc)

    book.toc = tuple(toc)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = spine
    epub.write_epub(str(path), book)
    return path


class _FakeTTSEngine:
    """Deterministic fake -- never touches real Kokoro. `gate`, if closed,
    blocks every `generate()` call until opened, letting tests land a
    Pause/Cancel request precisely between chunks without racing a real
    background thread's timing."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.gate = threading.Event()
        self.gate.set()
        # Set the instant generate() is entered, *before* waiting on the
        # gate -- lets a test block until the background thread's
        # should_stop check for this chunk has already run (and returned
        # "keep going") before the test registers a pause/cancel request,
        # closing a real TOCTOU race: thread.start() doesn't guarantee the
        # background thread has reached its first should_stop check by the
        # time the calling thread's next line executes.
        self.entered = threading.Event()

    def generate(self, text: str, voice: str) -> bytes:
        self.entered.set()
        self.gate.wait(timeout=5)
        self.calls.append((text, voice))
        return b"FAKE-MP3-" + str(len(self.calls)).encode() + b"-" * 2000

    def generate_voice_sample(self, voice: str) -> bytes:
        return self.generate("sample", voice)


def _make_runner(
    tmp_path: Path,
    *,
    tts_engine: _FakeTTSEngine | None = None,
    settings: dict[str, Any] | None = None,
    max_files: int = 50,
) -> BatchRunner:
    library_root = tmp_path / "Library"
    output_folder = tmp_path / "Output"
    return BatchRunner(
        library_root=library_root,
        output_folder=output_folder,
        report_dir=tmp_path / "logs",
        state_repo=_loaded_state_repo(tmp_path),
        audit_log=AuditLogRepository(tmp_path / "audit_log.csv"),
        settings=settings if settings is not None else {"ai_provider": "none"},
        # _FakeTTSEngine duck-types TTSEngineLike (pipeline/tts_engine.py)
        # rather than subclassing the real TTSEngine -- never touches
        # real Kokoro.
        tts_engine=tts_engine or _FakeTTSEngine(),
        max_files=max_files,
    )


def _loaded_state_repo(tmp_path: Path) -> StateRepository:
    repo = StateRepository(tmp_path / "state.json")
    repo.load()
    return repo


def _wait_until(predicate: Any, timeout: float = 5.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("condition not met within timeout")


def _add_book(
    runner: BatchRunner, tmp_path: Path, name: str = "book.epub", **kw: Any
) -> str:
    src = _make_epub(tmp_path / "source" / name, **kw)
    result = runner.add_book(src)
    assert result.ok, result.message
    assert result.book is not None
    return result.book.book_id


def _run_identification_and_confirm(runner: BatchRunner, book_ids: list[str]) -> None:
    runner.start()
    for bid in book_ids:
        _wait_until(lambda bid=bid: _status_of(runner, bid) == STATUS_NEEDS_INPUT)
        runner.confirm_metadata(bid)


def _status_of(runner: BatchRunner, book_id: str) -> str:
    for book in runner.snapshot():
        if book.book_id == book_id:
            return book.status
    raise KeyError(book_id)


def _data_of(runner: BatchRunner, book_id: str) -> dict[str, Any]:
    for book in runner.snapshot():
        if book.book_id == book_id:
            return book.data
    raise KeyError(book_id)


def _expected_folder_name(*, title: str, author_last: str | None = None) -> str:
    """The exact folder name build_filename() will produce -- with
    ai_provider="none", NullProvider never resolves an author, so the
    default fallback ("Unknown, Unknown") applies unless overridden."""
    return build_filename(
        {
            "title": title,
            "author_first": None,
            "author_last": author_last,
            "series": None,
            "series_number": None,
        }
    ).removesuffix(".epub")


# ---------------------------------------------------------------------------
# Screen 1: add / remove / capacity
# ---------------------------------------------------------------------------


def test_add_book_copies_into_incoming_and_returns_pending_book(tmp_path: Path) -> None:
    runner = _make_runner(tmp_path)

    book_id = _add_book(runner, tmp_path)

    books = runner.snapshot()
    assert len(books) == 1
    assert books[0].book_id == book_id
    assert books[0].status == "pending"
    incoming = tmp_path / "Library" / "00-Incoming" / "book.epub"
    assert incoming.exists()


def test_add_book_rejects_non_epub_file(tmp_path: Path) -> None:
    runner = _make_runner(tmp_path)
    bogus = tmp_path / "source" / "notes.txt"
    bogus.parent.mkdir(parents=True)
    bogus.write_text("hello")

    result = runner.add_book(bogus)

    assert result.ok is False
    assert result.reason is RejectionReason.NOT_EPUB
    assert runner.snapshot() == []


def test_add_book_enforces_max_files_cap(tmp_path: Path) -> None:
    runner = _make_runner(tmp_path, max_files=1)
    _add_book(runner, tmp_path, name="one.epub")

    second_src = _make_epub(tmp_path / "source" / "two.epub")
    result = runner.add_book(second_src)

    assert result.ok is False
    assert result.reason is RejectionReason.MAX_FILES_EXCEEDED


def test_add_book_dedupes_same_source_filename(tmp_path: Path) -> None:
    runner = _make_runner(tmp_path)
    src1 = _make_epub(tmp_path / "a" / "book.epub", title="One")
    src2 = _make_epub(tmp_path / "b" / "book.epub", title="Two")

    r1 = runner.add_book(src1)
    r2 = runner.add_book(src2)

    assert r1.ok and r2.ok
    assert r1.book.data["filename"] != r2.book.data["filename"]  # type: ignore[union-attr]


def test_remove_book_deletes_pending_book_and_its_incoming_copy(tmp_path: Path) -> None:
    runner = _make_runner(tmp_path)
    book_id = _add_book(runner, tmp_path)

    removed = runner.remove_book(book_id)

    assert removed is True
    assert runner.snapshot() == []
    assert not (tmp_path / "Library" / "00-Incoming" / "book.epub").exists()


def test_remove_book_refuses_once_processing_has_started(tmp_path: Path) -> None:
    runner = _make_runner(tmp_path)
    book_id = _add_book(runner, tmp_path)
    runner.start()
    _wait_until(lambda: _status_of(runner, book_id) == STATUS_NEEDS_INPUT)

    assert runner.remove_book(book_id) is False


# ---------------------------------------------------------------------------
# Identification loop -> needs_input
# ---------------------------------------------------------------------------


def test_identification_reaches_needs_input_confirm_metadata(tmp_path: Path) -> None:
    runner = _make_runner(tmp_path)
    book_id = _add_book(runner, tmp_path, title="Fated", author="Benedict Jacka")

    runner.start()
    _wait_until(lambda: _status_of(runner, book_id) == STATUS_NEEDS_INPUT)

    data = _data_of(runner, book_id)
    assert data["needs_input_type"] == NeedsInputType.CONFIRM_METADATA
    assert data["title"] == "Fated"


def test_start_called_again_while_thread_alive_still_picks_up_the_new_book(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression test: previously, start() was a full no-op while its
    background thread was still alive, so a book added (and start()
    called again) during that window stayed stuck at "pending" forever
    unless start() happened to be called a *third* time after the first
    thread had already exited. Now the newly-pending book is flipped to
    "identifying" immediately, and the already-running thread's own loop
    picks it up without needing a second thread."""
    import pipeline.batch_runner as batch_runner_module

    gate = threading.Event()

    class _SlowRenameStage(RenameStage):
        def run(self, book: BookState) -> BookState:
            gate.wait(timeout=5)
            return super().run(book)

    monkeypatch.setattr(batch_runner_module, "RenameStage", _SlowRenameStage)

    runner = _make_runner(
        tmp_path, settings={"ai_provider": "none", "clean_language": False}
    )
    first_id = _add_book(runner, tmp_path, name="first.epub")
    runner.start()  # spawns the identification thread; blocks on the gate
    _wait_until(lambda: _status_of(runner, first_id) == STATUS_IDENTIFYING)

    # The thread is provably still alive (blocked on the gate) at this
    # point -- add a second book and call start() again.
    second_id = _add_book(runner, tmp_path, name="second.epub")
    runner.start()
    assert _status_of(runner, second_id) == STATUS_IDENTIFYING  # flipped immediately

    gate.set()  # let both books actually process now

    _wait_until(lambda: _status_of(runner, first_id) == STATUS_NEEDS_INPUT)
    _wait_until(lambda: _status_of(runner, second_id) == STATUS_NEEDS_INPUT)


def test_confirm_metadata_applies_corrections_and_reaches_identified(
    tmp_path: Path,
) -> None:
    runner = _make_runner(
        tmp_path, settings={"ai_provider": "none", "clean_language": False}
    )
    _add_book(runner, tmp_path)
    other_id = _add_book(runner, tmp_path, name="other.epub", title="Other")
    runner.start()
    _wait_until(lambda: _status_of(runner, other_id) == STATUS_NEEDS_INPUT)

    updated = runner.confirm_metadata(
        other_id, corrections={"author_last": "Smith", "author_first": "Jane"}
    )

    assert updated.status == STATUS_IDENTIFIED
    assert updated.data["author_last"] == "Smith"


def test_confirm_metadata_rejects_a_book_not_awaiting_it(tmp_path: Path) -> None:
    runner = _make_runner(tmp_path)
    book_id = _add_book(runner, tmp_path)

    with pytest.raises(ValueError):
        runner.confirm_metadata(book_id)


def test_sanitize_toggle_off_passes_the_file_through_unchanged(tmp_path: Path) -> None:
    runner = _make_runner(
        tmp_path, settings={"ai_provider": "none", "clean_language": False}
    )
    book_id = _add_book(runner, tmp_path)

    runner.start()
    _wait_until(lambda: _status_of(runner, book_id) == STATUS_NEEDS_INPUT)

    data = _data_of(runner, book_id)
    sanitized_path = tmp_path / "Library" / "02-Sanitized" / data["filename"]
    assert sanitized_path.exists()
    # No sanitize suffix was applied since the stage never ran.
    assert not data["filename"].endswith("_cln.epub")


# ---------------------------------------------------------------------------
# Voice assignment
# ---------------------------------------------------------------------------


def test_all_books_reach_voice_pick_together_only_once_all_are_confirmed(
    tmp_path: Path,
) -> None:
    runner = _make_runner(
        tmp_path, settings={"ai_provider": "none", "clean_language": False}
    )
    id1 = _add_book(runner, tmp_path, name="one.epub", title="One")
    id2 = _add_book(runner, tmp_path, name="two.epub", title="Two")
    runner.start()
    _wait_until(lambda: _status_of(runner, id1) == STATUS_NEEDS_INPUT)
    _wait_until(lambda: _status_of(runner, id2) == STATUS_NEEDS_INPUT)

    runner.confirm_metadata(id1)
    assert _status_of(runner, id1) == STATUS_IDENTIFIED  # waiting on id2 still

    runner.confirm_metadata(id2)
    assert _status_of(runner, id1) == STATUS_VOICE_PICK
    assert _status_of(runner, id2) == STATUS_VOICE_PICK


def test_multi_book_batch_does_not_auto_start_generation(tmp_path: Path) -> None:
    runner = _make_runner(
        tmp_path, settings={"ai_provider": "none", "clean_language": False}
    )
    id1 = _add_book(runner, tmp_path, name="one.epub")
    id2 = _add_book(runner, tmp_path, name="two.epub")
    _run_identification_and_confirm(runner, [id1, id2])

    time.sleep(0.1)
    assert _status_of(runner, id1) == STATUS_VOICE_PICK
    assert _status_of(runner, id2) == STATUS_VOICE_PICK


def test_assign_voice_changes_one_row_without_affecting_others(tmp_path: Path) -> None:
    runner = _make_runner(
        tmp_path, settings={"ai_provider": "none", "clean_language": False}
    )
    id1 = _add_book(runner, tmp_path, name="one.epub")
    id2 = _add_book(runner, tmp_path, name="two.epub")
    _run_identification_and_confirm(runner, [id1, id2])

    runner.assign_voice(id1, "bf_alice")

    assert _data_of(runner, id1)["voice"] == "bf_alice"
    assert _data_of(runner, id2)["voice"] != "bf_alice"


# ---------------------------------------------------------------------------
# End-to-end generation -> review -> complete -> cleanup (ADR-0017)
# ---------------------------------------------------------------------------


def test_single_book_batch_auto_starts_generation_after_voice_assignment(
    tmp_path: Path,
) -> None:
    engine = _FakeTTSEngine()
    runner = _make_runner(
        tmp_path,
        tts_engine=engine,
        settings={"ai_provider": "none", "clean_language": False},
    )
    book_id = _add_book(runner, tmp_path)
    runner.start()
    _wait_until(lambda: _status_of(runner, book_id) == STATUS_NEEDS_INPUT)
    runner.confirm_metadata(book_id)  # -> voice_pick, auto-starts generation

    _wait_until(
        lambda: _status_of(runner, book_id) == STATUS_NEEDS_INPUT
        and _data_of(runner, book_id).get("needs_input_type")
        == NeedsInputType.REVIEW_RESULT
    )
    assert len(engine.calls) >= 1


def test_state_file_is_kept_current_as_each_stage_finishes(tmp_path: Path) -> None:
    """The "Welcome back" flow's data source
    (StateRepository.incomplete_book_ids()) must reflect real progress on
    disk as the batch runs, not only once fully complete -- reload a
    fresh StateRepository from the same path to prove this is real
    persisted state, not just in-memory bookkeeping."""
    runner = _make_runner(
        tmp_path, settings={"ai_provider": "none", "clean_language": False}
    )
    book_id = _add_book(runner, tmp_path)
    runner.start()
    _wait_until(lambda: _status_of(runner, book_id) == STATUS_NEEDS_INPUT)

    reloaded = StateRepository(tmp_path / "state.json")
    reloaded.load()
    assert reloaded.is_stage_complete(book_id, "rename") is True
    assert reloaded.is_stage_complete(book_id, "sanitize") is True
    assert book_id in reloaded.incomplete_book_ids()  # not "cleanup" yet

    runner.confirm_metadata(book_id)  # single book -> auto-generates -> completes
    _wait_until(
        lambda: _data_of(runner, book_id).get("needs_input_type")
        == NeedsInputType.REVIEW_RESULT
    )
    runner.review_result(book_id, looks_good=True)

    reloaded2 = StateRepository(tmp_path / "state.json")
    reloaded2.load()
    assert reloaded2.is_stage_complete(book_id, "audio") is True
    assert reloaded2.is_stage_complete(book_id, "cleanup") is True
    assert reloaded2.incomplete_book_ids() == []


def test_review_yes_marks_complete_and_cleans_up_library_copies(tmp_path: Path) -> None:
    runner = _make_runner(
        tmp_path, settings={"ai_provider": "none", "clean_language": False}
    )
    book_id = _add_book(runner, tmp_path)
    runner.start()
    _wait_until(lambda: _status_of(runner, book_id) == STATUS_NEEDS_INPUT)
    data = _data_of(runner, book_id)
    incoming_copy = tmp_path / "Library" / "00-Incoming" / data["_trace"]["incoming"]
    runner.confirm_metadata(book_id)  # single-book -> auto-generates

    _wait_until(
        lambda: _data_of(runner, book_id).get("needs_input_type")
        == NeedsInputType.REVIEW_RESULT
    )
    library_audio_folder = Path(_data_of(runner, book_id)["audio_folder"])
    output_audio_folder = Path(_data_of(runner, book_id)["output_audio_folder"])
    assert output_audio_folder.exists()
    assert any(output_audio_folder.glob("*.mp3"))

    updated = runner.review_result(book_id, looks_good=True)

    assert updated.status == STATUS_COMPLETE
    assert not incoming_copy.exists()
    assert not library_audio_folder.exists()
    assert output_audio_folder.exists()  # her copy survives cleanup


def test_review_no_then_retag_applies_overrides_to_the_output_copy_only(
    tmp_path: Path,
) -> None:
    runner = _make_runner(
        tmp_path, settings={"ai_provider": "none", "clean_language": False}
    )
    book_id = _add_book(
        runner, tmp_path, title="Original Title", author="Original Author"
    )
    runner.start()
    _wait_until(lambda: _status_of(runner, book_id) == STATUS_NEEDS_INPUT)
    runner.confirm_metadata(book_id)

    _wait_until(
        lambda: _data_of(runner, book_id).get("needs_input_type")
        == NeedsInputType.REVIEW_RESULT
    )
    library_audio_folder = Path(_data_of(runner, book_id)["audio_folder"])

    still_pending = runner.review_result(book_id, looks_good=False)
    assert (
        still_pending.status == STATUS_NEEDS_INPUT
    )  # unchanged, waiting for corrections

    updated = runner.retag_book(book_id, {"title": "Corrected Title"})

    assert updated.status == STATUS_COMPLETE
    assert updated.data["title"] == "Corrected Title"
    new_output_folder = Path(updated.data["output_audio_folder"])
    assert new_output_folder.exists()
    assert "Corrected Title" in new_output_folder.name
    # The internal Library copy (pre-retag name) was cleaned up, not the
    # freshly-retagged output copy.
    assert not library_audio_folder.exists()


# ---------------------------------------------------------------------------
# Output collision (docs/BACKLOG.md Epic 6's own addition)
# ---------------------------------------------------------------------------


def test_output_collision_pauses_for_her_decision_instead_of_overwriting(
    tmp_path: Path,
) -> None:
    runner = _make_runner(
        tmp_path, settings={"ai_provider": "none", "clean_language": False}
    )
    book_id = _add_book(runner, tmp_path)
    runner.start()
    _wait_until(lambda: _status_of(runner, book_id) == STATUS_NEEDS_INPUT)

    # Pre-create a colliding folder in output_folder before generation
    # would try to copy the finished audiobook out. NullProvider never
    # resolves an author (ai_provider="none"), so build_filename() falls
    # back to "Unknown, Unknown" for that component.
    colliding = tmp_path / "Output" / _expected_folder_name(title="Fated")
    colliding.mkdir(parents=True)
    (colliding / "sentinel.txt").write_text("pre-existing content")

    runner.confirm_metadata(book_id)

    _wait_until(
        lambda: _data_of(runner, book_id).get("needs_input_type")
        == NeedsInputType.OUTPUT_COLLISION
    )
    collision = _data_of(runner, book_id)["collision"]
    assert collision["artifact"] == "audiobook"
    assert (colliding / "sentinel.txt").exists()  # untouched until she decides


def test_resolve_collision_keep_both_preserves_the_original(tmp_path: Path) -> None:
    runner = _make_runner(
        tmp_path, settings={"ai_provider": "none", "clean_language": False}
    )
    book_id = _add_book(runner, tmp_path)
    runner.start()
    _wait_until(lambda: _status_of(runner, book_id) == STATUS_NEEDS_INPUT)
    colliding = tmp_path / "Output" / _expected_folder_name(title="Fated")
    colliding.mkdir(parents=True)
    (colliding / "sentinel.txt").write_text("pre-existing content")
    runner.confirm_metadata(book_id)
    _wait_until(
        lambda: _data_of(runner, book_id).get("needs_input_type")
        == NeedsInputType.OUTPUT_COLLISION
    )

    updated = runner.resolve_collision(book_id, "keep_both")

    assert updated.data["needs_input_type"] == NeedsInputType.REVIEW_RESULT
    assert (colliding / "sentinel.txt").exists()  # original untouched
    new_folder = Path(updated.data["output_audio_folder"])
    assert new_folder != colliding
    assert any(new_folder.glob("*.mp3"))


def test_resolve_collision_replace_overwrites_the_original(tmp_path: Path) -> None:
    runner = _make_runner(
        tmp_path, settings={"ai_provider": "none", "clean_language": False}
    )
    book_id = _add_book(runner, tmp_path)
    runner.start()
    _wait_until(lambda: _status_of(runner, book_id) == STATUS_NEEDS_INPUT)
    colliding = tmp_path / "Output" / _expected_folder_name(title="Fated")
    colliding.mkdir(parents=True)
    (colliding / "sentinel.txt").write_text("pre-existing content")
    runner.confirm_metadata(book_id)
    _wait_until(
        lambda: _data_of(runner, book_id).get("needs_input_type")
        == NeedsInputType.OUTPUT_COLLISION
    )

    updated = runner.resolve_collision(book_id, "replace")

    new_folder = Path(updated.data["output_audio_folder"])
    assert new_folder == colliding
    assert not (colliding / "sentinel.txt").exists()  # overwritten
    assert any(colliding.glob("*.mp3"))


# ---------------------------------------------------------------------------
# Pause / Cancel
# ---------------------------------------------------------------------------


def test_pause_mid_generation_stops_before_the_next_chunk(tmp_path: Path) -> None:
    engine = _FakeTTSEngine()
    engine.gate.clear()
    runner = _make_runner(
        tmp_path,
        tts_engine=engine,
        settings={"ai_provider": "none", "clean_language": False},
    )
    book_id = _add_book(runner, tmp_path, chapters=[("Chapter 1", _MULTI_CHUNK_TEXT)])
    runner.start()
    _wait_until(lambda: _status_of(runner, book_id) == STATUS_NEEDS_INPUT)
    runner.confirm_metadata(book_id)  # auto-starts generation; blocks on the gate

    # Wait until chunk 1's should_stop check has already run (and found no
    # pending pause) before requesting one -- otherwise request_pause()
    # could race ahead of thread.start() and land before that first check,
    # making "chunks_done" nondeterministic.
    engine.entered.wait(timeout=5)
    runner.request_pause(book_id)
    engine.gate.set()  # let exactly the in-flight chunk finish, then stop

    _wait_until(lambda: _status_of(runner, book_id) == STATUS_PAUSED)
    data = _data_of(runner, book_id)
    assert data["chunks_done"] == 1
    assert data["chunks_done"] < data["chunks_total"]
    assert len(engine.calls) == 1


def test_resuming_a_paused_book_continues_from_where_it_left_off(
    tmp_path: Path,
) -> None:
    engine = _FakeTTSEngine()
    engine.gate.clear()
    runner = _make_runner(
        tmp_path,
        tts_engine=engine,
        settings={"ai_provider": "none", "clean_language": False},
    )
    book_id = _add_book(runner, tmp_path, chapters=[("Chapter 1", _MULTI_CHUNK_TEXT)])
    runner.start()
    _wait_until(lambda: _status_of(runner, book_id) == STATUS_NEEDS_INPUT)
    runner.confirm_metadata(book_id)
    engine.entered.wait(timeout=5)
    runner.request_pause(book_id)
    engine.gate.set()
    _wait_until(lambda: _status_of(runner, book_id) == STATUS_PAUSED)
    calls_before_resume = len(engine.calls)
    assert calls_before_resume == 1
    chunks_total = _data_of(runner, book_id)["chunks_total"]
    assert chunks_total > 1  # otherwise this test proves nothing about resume

    runner.start_generation()  # she comes back and resumes

    _wait_until(
        lambda: _data_of(runner, book_id).get("needs_input_type")
        == NeedsInputType.REVIEW_RESULT
    )
    # Already-written chunk 1 was skipped on resume, not regenerated --
    # only the remaining chunks triggered a fresh generate() call.
    assert len(engine.calls) == calls_before_resume + (chunks_total - 1)


def test_start_generation_called_again_while_thread_alive_still_picks_up_new_book(
    tmp_path: Path,
) -> None:
    """Regression test for the same stuck-book class of bug on the
    generation side: a second book reaching voice_pick while generation
    is already running for a first book must not be stranded until the
    first thread happens to exit and start_generation() is called again."""
    engine = _FakeTTSEngine()
    runner = _make_runner(
        tmp_path,
        tts_engine=engine,
        settings={"ai_provider": "none", "clean_language": False},
    )
    id1 = _add_book(runner, tmp_path, name="one.epub", title="One")
    id2 = _add_book(runner, tmp_path, name="two.epub", title="Two")
    _run_identification_and_confirm(runner, [id1, id2])  # both now at voice_pick

    engine.gate.clear()
    runner.start_generation()
    engine.entered.wait(timeout=5)  # id1's generation has genuinely started

    # id2 is still queued and untouched -- prove it wasn't silently
    # skipped just because a thread was already running for id1.
    assert _status_of(runner, id2) == STATUS_VOICE_PICK
    engine.gate.set()

    _wait_until(
        lambda: _data_of(runner, id2).get("needs_input_type")
        == NeedsInputType.REVIEW_RESULT
    )
    assert _data_of(runner, id1).get("needs_input_type") == NeedsInputType.REVIEW_RESULT


def test_cancel_keep_partial_preserves_the_audio_folder(tmp_path: Path) -> None:
    engine = _FakeTTSEngine()
    engine.gate.clear()
    runner = _make_runner(
        tmp_path,
        tts_engine=engine,
        settings={"ai_provider": "none", "clean_language": False},
    )
    book_id = _add_book(runner, tmp_path, chapters=[("Chapter 1", _MULTI_CHUNK_TEXT)])
    runner.start()
    _wait_until(lambda: _status_of(runner, book_id) == STATUS_NEEDS_INPUT)
    runner.confirm_metadata(book_id)
    engine.entered.wait(timeout=5)  # generation has genuinely started

    runner.request_cancel(book_id, keep_partial=True)
    engine.gate.set()

    _wait_until(lambda: _status_of(runner, book_id) == STATUS_CANCELLED)
    audio_folder = Path(_data_of(runner, book_id)["audio_folder"])
    assert audio_folder.exists()
    assert any(audio_folder.glob("*.mp3"))


def test_cancel_discard_deletes_the_partial_audio_folder(tmp_path: Path) -> None:
    engine = _FakeTTSEngine()
    engine.gate.clear()
    runner = _make_runner(
        tmp_path,
        tts_engine=engine,
        settings={"ai_provider": "none", "clean_language": False},
    )
    book_id = _add_book(runner, tmp_path, chapters=[("Chapter 1", _MULTI_CHUNK_TEXT)])
    runner.start()
    _wait_until(lambda: _status_of(runner, book_id) == STATUS_NEEDS_INPUT)
    runner.confirm_metadata(book_id)
    audio_folder_hint = tmp_path / "Library" / "03-Audio"
    engine.entered.wait(timeout=5)  # generation has genuinely started

    runner.request_cancel(book_id, keep_partial=False)
    engine.gate.set()

    _wait_until(lambda: _status_of(runner, book_id) == STATUS_CANCELLED)
    assert "audio_folder" not in _data_of(runner, book_id)
    assert list(audio_folder_hint.glob("*")) == []


def test_cancel_a_book_that_has_not_started_generating_is_immediate(
    tmp_path: Path,
) -> None:
    runner = _make_runner(
        tmp_path, settings={"ai_provider": "none", "clean_language": False}
    )
    id1 = _add_book(runner, tmp_path, name="one.epub")
    id2 = _add_book(runner, tmp_path, name="two.epub")
    _run_identification_and_confirm(
        runner, [id1, id2]
    )  # both at voice_pick, no auto-start

    updated = runner.request_cancel(id1, keep_partial=True)

    assert updated.status == STATUS_CANCELLED


# ---------------------------------------------------------------------------
# Disk-space report composes correctly with real added books
# ---------------------------------------------------------------------------


def test_disk_space_report_reflects_added_books(tmp_path: Path) -> None:
    runner = _make_runner(tmp_path)
    _add_book(runner, tmp_path)

    report = runner.disk_space_report()

    assert report.estimated_total_bytes > 0
