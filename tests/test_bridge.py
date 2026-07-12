"""Tests for backend/bridge.py.

`derive_batch_state()` is tested entirely against plain `BookState`
objects -- no Flask, no HTTP, no BatchRunner -- per docs/BACKLOG.md
Epic 6's explicit requirement ("state-machine derivation ... unit-tested
independent of HTTP").
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.bridge import (
    BATCH_DONE,
    BATCH_ERROR,
    BATCH_IDENTIFYING,
    BATCH_IDLE,
    BATCH_REVIEW,
    BATCH_VOICE_PICK,
    BATCH_WORKING,
    VoiceHistoryUnavailable,
    build_status_response,
    build_support_bundle,
    current_error_detail,
    derive_batch_state,
    voice_history,
    write_support_bundle,
)
from pipeline.audit_logger import AuditLogRepository
from pipeline.batch_runner import NeedsInputType
from pipeline.stage import BookState

# ---------------------------------------------------------------------------
# derive_batch_state -- pure function, no HTTP
# ---------------------------------------------------------------------------


def _book(book_id: str, status: str, **data: object) -> BookState:
    return BookState(book_id, status, dict(data))


def test_empty_batch_is_idle() -> None:
    assert derive_batch_state([]) == BATCH_IDLE


def test_any_error_wins_over_everything_else() -> None:
    books = [
        _book("b1", "complete"),
        _book("b2", "error"),
        _book("b3", "generating"),
    ]
    assert derive_batch_state(books) == BATCH_ERROR


def test_pending_book_means_identifying() -> None:
    assert derive_batch_state([_book("b1", "pending")]) == BATCH_IDENTIFYING


def test_confirm_metadata_needs_input_means_identifying() -> None:
    books = [
        _book(
            "b1",
            "needs_input",
            needs_input_type=NeedsInputType.CONFIRM_METADATA,
        )
    ]
    assert derive_batch_state(books) == BATCH_IDENTIFYING


def test_ai_enrichment_failed_needs_input_means_identifying() -> None:
    books = [
        _book(
            "b1",
            "needs_input",
            needs_input_type=NeedsInputType.AI_ENRICHMENT_FAILED,
        )
    ]
    assert derive_batch_state(books) == BATCH_IDENTIFYING


def test_identifying_wins_even_if_another_book_is_further_along() -> None:
    books = [
        _book("b1", "needs_input", needs_input_type="confirm_metadata"),
        _book("b2", "voice_pick"),
    ]
    assert derive_batch_state(books) == BATCH_IDENTIFYING


def test_all_past_identification_and_one_at_voice_pick_none_generating() -> None:
    books = [_book("b1", "voice_pick"), _book("b2", "voice_pick")]
    assert derive_batch_state(books) == BATCH_VOICE_PICK


def test_generating_wins_over_voice_pick() -> None:
    books = [_book("b1", "voice_pick"), _book("b2", "generating")]
    assert derive_batch_state(books) == BATCH_WORKING


def test_paused_counts_as_working() -> None:
    assert derive_batch_state([_book("b1", "paused")]) == BATCH_WORKING


def test_output_collision_counts_as_working_not_identifying() -> None:
    """Documented deviation from the literal precedence-rule text -- see
    derive_batch_state()'s own docstring: an output collision happens
    mid-generation and must not demote the batch back to the per-book
    identification screen."""
    books = [
        _book(
            "b1",
            "needs_input",
            needs_input_type=NeedsInputType.OUTPUT_COLLISION,
            collision={"artifact": "audiobook", "path": "C:\\x"},
        )
    ]
    assert derive_batch_state(books) == BATCH_WORKING


def test_review_result_needs_input_means_review_not_identifying() -> None:
    """Same documented deviation -- a book awaiting her Yes/No must not
    fall back into the identification bucket."""
    books = [_book("b1", "needs_input", needs_input_type=NeedsInputType.REVIEW_RESULT)]
    assert derive_batch_state(books) == BATCH_REVIEW


def test_review_wins_over_a_completed_sibling_book() -> None:
    books = [
        _book("b1", "complete"),
        _book("b2", "needs_input", needs_input_type=NeedsInputType.REVIEW_RESULT),
    ]
    assert derive_batch_state(books) == BATCH_REVIEW


def test_all_complete_or_cancelled_means_done() -> None:
    books = [_book("b1", "complete"), _book("b2", "cancelled")]
    assert derive_batch_state(books) == BATCH_DONE


# ---------------------------------------------------------------------------
# build_status_response -- shape and field wiring
# ---------------------------------------------------------------------------


class _FakeRunner:
    def __init__(self, books: list[BookState]) -> None:
        self._books = books

    def snapshot(self) -> list[BookState]:
        return self._books


def test_status_response_shape_for_idle_batch() -> None:
    response = build_status_response(_FakeRunner([]))

    assert response["state"] == BATCH_IDLE
    assert response["active_book_id"] is None
    assert response["books"] == []
    assert response["needs_input"] is None
    assert response["error"] is None
    assert isinstance(response["message"], str) and response["message"]


def test_status_response_surfaces_needs_input_for_the_active_book() -> None:
    books = [
        _book(
            "b1",
            "needs_input",
            needs_input_type=NeedsInputType.CONFIRM_METADATA,
            title="Fated",
        )
    ]
    response = build_status_response(_FakeRunner(books))

    assert response["state"] == BATCH_IDENTIFYING
    assert response["active_book_id"] == "b1"
    assert response["needs_input"] == {"book_id": "b1", "type": "confirm_metadata"}
    assert response["books"][0]["title"] == "Fated"


def test_status_response_error_never_includes_raw_technical_detail() -> None:
    books = [_book("b1", "error", error="Traceback (most recent call last): ...")]
    response = build_status_response(_FakeRunner(books))

    assert response["state"] == BATCH_ERROR
    assert response["error"]["book_id"] == "b1"
    assert response["error"]["summary"] == "Something went wrong."
    assert "Traceback" not in response["error"]["summary"]
    assert response["error"]["support_bundle_available"] is True


def test_status_response_includes_progress_only_for_the_generating_book() -> None:
    books = [
        _book("b1", "complete"),
        _book("b2", "generating", chunks_done=3, chunks_total=10),
    ]
    response = build_status_response(_FakeRunner(books))

    b1_summary = next(b for b in response["books"] if b["id"] == "b1")
    b2_summary = next(b for b in response["books"] if b["id"] == "b2")
    assert "progress" not in b1_summary
    assert b2_summary["progress"] == {"chunks_done": 3, "chunks_total": 10}


# ---------------------------------------------------------------------------
# voice_choices
# ---------------------------------------------------------------------------


def test_voice_choices_strips_gender_and_accent_detail() -> None:
    from backend.bridge import voice_choices

    choices = voice_choices()

    assert {"key": "bm_george", "name": "George"} in choices
    assert all("(" not in c["name"] and ")" not in c["name"] for c in choices)


def test_voice_choices_covers_every_voice_key() -> None:
    from backend.bridge import voice_choices
    from pipeline.tts_engine import VOICES

    assert {c["key"] for c in voice_choices()} == set(VOICES)


# ---------------------------------------------------------------------------
# voice_history
# ---------------------------------------------------------------------------


def test_voice_history_is_empty_list_when_no_audiobooks_made_yet(
    tmp_path: Path,
) -> None:
    audit_log = AuditLogRepository(tmp_path / "audit_log.csv")

    assert voice_history(audit_log) == []


def test_voice_history_groups_by_series_keeping_the_most_recent_voice(
    tmp_path: Path,
) -> None:
    audit_log = AuditLogRepository(tmp_path / "audit_log.csv")
    audit_log.append(
        {
            "timestamp": "2026-01-01T00:00:00Z",
            "stage": "audio",
            "series": "Alex Verus",
            "voice": "am_george",
        }
    )
    audit_log.append(
        {
            "timestamp": "2026-02-01T00:00:00Z",
            "stage": "audio",
            "series": "Alex Verus",
            "voice": "bf_alice",
        }
    )
    audit_log.append(
        {
            "timestamp": "2026-01-15T00:00:00Z",
            "stage": "audio",
            "title": "The Hating Game",
            "voice": "af_bella",
        }
    )

    history = voice_history(audit_log)

    by_label = {row["label"]: row["voice"] for row in history}
    assert by_label["Alex Verus"] == "bf_alice"  # most recent wins
    assert by_label["The Hating Game"] == "af_bella"


def test_voice_history_ignores_non_audio_rows(tmp_path: Path) -> None:
    audit_log = AuditLogRepository(tmp_path / "audit_log.csv")
    audit_log.append({"timestamp": "t", "stage": "rename", "title": "Fated"})

    assert voice_history(audit_log) == []


def test_voice_history_raises_distinctly_when_the_log_is_unreadable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audit_log = AuditLogRepository(tmp_path / "audit_log.csv")

    def _boom() -> list[dict[str, str]]:
        raise OSError("disk error")

    monkeypatch.setattr(audit_log, "read_all", _boom)

    with pytest.raises(VoiceHistoryUnavailable):
        voice_history(audit_log)


# ---------------------------------------------------------------------------
# current_error_detail -- the fix for the support bundle never getting
# the real error text, since build_status_response() deliberately never
# exposes it
# ---------------------------------------------------------------------------


def test_current_error_detail_finds_the_erroring_book() -> None:
    books = [
        _book("b1", "complete"),
        _book("b2", "error", error="Could not read EPUB: bad zip"),
    ]

    assert current_error_detail(books) == "Could not read EPUB: bad zip"


def test_current_error_detail_is_empty_when_nothing_is_erroring() -> None:
    books = [_book("b1", "complete"), _book("b2", "voice_pick")]

    assert current_error_detail(books) == ""


def test_current_error_detail_is_empty_string_not_none_for_a_missing_error_field() -> (
    None
):
    books = [_book("b1", "error")]  # no "error" key in data at all

    assert current_error_detail(books) == ""


# ---------------------------------------------------------------------------
# Support bundle
# ---------------------------------------------------------------------------


def test_support_bundle_strips_the_ai_api_key(tmp_path: Path) -> None:
    audit_log = AuditLogRepository(tmp_path / "audit_log.csv")
    settings = {"ai_api_key": "sk-super-secret", "books_folder": "C:\\Books"}

    bundle = build_support_bundle(
        settings=settings, audit_log=audit_log, technical_error="boom"
    )

    assert "ai_api_key" not in bundle["settings"]
    assert bundle["settings"]["books_folder"] == "C:\\Books"
    assert bundle["technical_error"] == "boom"


def test_support_bundle_degrades_gracefully_when_log_is_unreadable(
    tmp_path: Path,
) -> None:
    # Simulate a real unreadable-file failure directly, since a merely
    # missing file already returns [] (not an error) per read_all()'s own
    # contract.
    import pipeline.audit_logger as audit_logger_module

    class _BrokenRepo(audit_logger_module.AuditLogRepository):
        def read_all(self) -> list[dict[str, str]]:
            raise OSError("permission denied")

    broken = _BrokenRepo(tmp_path / "audit_log.csv")

    bundle = build_support_bundle(
        settings={"ai_api_key": "secret"}, audit_log=broken, technical_error="boom"
    )

    assert bundle["recent_audit_log_rows"] == []
    assert "permission denied" in bundle["audit_log_error"]
    assert "ai_api_key" not in bundle["settings"]


def test_write_support_bundle_produces_a_readable_plain_text_file(
    tmp_path: Path,
) -> None:
    audit_log = AuditLogRepository(tmp_path / "audit_log.csv")
    bundle = build_support_bundle(
        settings={"books_folder": "C:\\Books"},
        audit_log=audit_log,
        technical_error="Something broke",
    )

    out_path = write_support_bundle(tmp_path / "support" / "details.txt", bundle)

    content = out_path.read_text(encoding="utf-8")
    assert "Something broke" in content
    assert "books_folder" in content
    assert "ai_api_key" not in content
