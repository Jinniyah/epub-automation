"""Adapter: translates pipeline/ (`BatchRunner`) calls into HTTP
request/response + polling state for backend/app.py
(ADR-0001, docs/design/PATTERNS.md §1).

Zero business logic belongs here -- if this file ever makes a decision
beyond translation, that's a bug, not a style preference (the same rule
applies to main.py's CLI Adapter role). The one real piece of logic this
module owns, `derive_batch_state()`, is itself a pure State Machine
function (docs/design/PATTERNS.md §1 sketch) -- a projection/translation
of `BatchRunner`'s internal per-book statuses into the wire contract's
coarse `state` field, not a pipeline decision.

See docs/requirements/01-architecture.md §Status endpoint contract for
the full response shape this module builds.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from pipeline.audit_logger import AuditLogRepository
from pipeline.batch_runner import (
    STATUS_ERROR,
    STATUS_GENERATING,
    STATUS_IDENTIFIED,
    STATUS_IDENTIFYING,
    STATUS_NEEDS_INPUT,
    STATUS_PAUSED,
    STATUS_PENDING,
    STATUS_VOICE_PICK,
    NeedsInputType,
)
from pipeline.stage import BookState


class SnapshotSource(Protocol):
    """The only sliver of `BatchRunner`'s surface `build_status_response`
    actually needs -- typed narrowly so this module depends on a
    capability, not the concrete class, and so tests can supply a plain
    fake without it needing to *be* a `BatchRunner`."""

    def snapshot(self) -> list[BookState]: ...


# Top-level `state` values -- 01-architecture.md §Status endpoint contract.
BATCH_IDLE = "idle"
BATCH_ERROR = "error"
BATCH_IDENTIFYING = "identifying"
BATCH_VOICE_PICK = "voice_pick"
BATCH_WORKING = "working"
BATCH_REVIEW = "review"
BATCH_DONE = "done"

# needs_input types that belong to the identification loop (metadata
# review) rather than a later pipeline step -- see derive_batch_state()'s
# docstring for why this distinction matters.
_IDENTIFICATION_NEEDS_INPUT_TYPES = frozenset(
    {NeedsInputType.CONFIRM_METADATA, NeedsInputType.AI_ENRICHMENT_FAILED}
)


def _needs_input_type(book: BookState) -> str | None:
    if book.status != STATUS_NEEDS_INPUT:
        return None
    value = book.data.get("needs_input_type")
    return str(value) if value is not None else None


def derive_batch_state(books: list[BookState]) -> str:
    """Pure function: given the current per-book statuses, return the
    single top-level `state` value the polling contract exposes --
    implements the fixed precedence rule from 01-architecture.md §State
    derivation (State Machine pattern, docs/design/PATTERNS.md §1),
    independently unit-testable with no HTTP/BatchRunner involved
    (docs/BACKLOG.md Epic 6).

    **One documented resolution beyond the literal rule text:** the
    original precedence rule buckets *any* `needs_input` book under
    "identifying" ("any book is pending, identifying, or needs_input").
    That rule was written before `needs_input.type` grew to also cover
    `review_result` (post-generation) and this epic's own
    `output_collision` (mid-generation) -- taken completely literally, a
    book awaiting Review would incorrectly demote the whole batch back to
    the per-book identification screen. This implementation instead
    buckets a `needs_input` book by *which* step it's actually waiting
    on: `confirm_metadata`/`ai_enrichment_failed` -> `identifying` (the
    rule's original intent), `output_collision` -> `working` (it happens
    mid-generation, blocking only that one book), `review_result` ->
    `review`. Every other precedence boundary follows the rule exactly as
    written.
    """
    if not books:
        return BATCH_IDLE

    if any(b.status == STATUS_ERROR for b in books):
        return BATCH_ERROR

    identification_pending = any(
        b.status in (STATUS_PENDING, STATUS_IDENTIFYING, STATUS_IDENTIFIED)
        or _needs_input_type(b) in _IDENTIFICATION_NEEDS_INPUT_TYPES
        for b in books
    )
    if identification_pending:
        return BATCH_IDENTIFYING

    working_now = any(
        b.status in (STATUS_GENERATING, STATUS_PAUSED)
        or _needs_input_type(b) == NeedsInputType.OUTPUT_COLLISION
        for b in books
    )

    voice_pick_pending = any(b.status == STATUS_VOICE_PICK for b in books)
    if voice_pick_pending and not working_now:
        return BATCH_VOICE_PICK

    if working_now:
        return BATCH_WORKING

    unresolved_review = any(
        _needs_input_type(b) == NeedsInputType.REVIEW_RESULT for b in books
    )
    if unresolved_review:
        return BATCH_REVIEW

    return BATCH_DONE


# ---------------------------------------------------------------------------
# Her-facing status copy -- the backend owns this wording, not the
# frontend, so it stays centrally editable (01-architecture.md §message).
# Drafted, not final -- see 08-open-questions-and-assumptions.md's note
# that all her-facing copy needs a full read-through pass regardless.
# ---------------------------------------------------------------------------

_MESSAGES: dict[str, str] = {
    BATCH_IDLE: "Add some books to get started.",
    BATCH_IDENTIFYING: "Finding out about your books...",
    BATCH_VOICE_PICK: "Choose a voice for each book.",
    BATCH_WORKING: "Making the audiobook now...",
    BATCH_REVIEW: "Take a look and let us know if it's right.",
    BATCH_DONE: "All done!",
    BATCH_ERROR: "Something went wrong.",
}


def _active_book_id(state: str, books: list[BookState]) -> str | None:
    if state == BATCH_ERROR:
        for b in books:
            if b.status == STATUS_ERROR:
                return b.book_id
        return None
    if state == BATCH_IDENTIFYING:
        for b in books:
            if b.status in (STATUS_PENDING, STATUS_IDENTIFYING, STATUS_IDENTIFIED) or (
                _needs_input_type(b) in _IDENTIFICATION_NEEDS_INPUT_TYPES
            ):
                return b.book_id
        return None
    if state == BATCH_WORKING:
        for b in books:
            if b.status in (STATUS_GENERATING, STATUS_PAUSED) or (
                _needs_input_type(b) == NeedsInputType.OUTPUT_COLLISION
            ):
                return b.book_id
        return None
    if state == BATCH_REVIEW:
        for b in books:
            if _needs_input_type(b) == NeedsInputType.REVIEW_RESULT:
                return b.book_id
        return None
    return None


def _needs_input_payload(active_book: BookState | None) -> dict[str, Any] | None:
    if active_book is None:
        return None
    ntype = _needs_input_type(active_book)
    if ntype is None:
        return None
    payload: dict[str, Any] = {"book_id": active_book.book_id, "type": ntype}
    if ntype == NeedsInputType.OUTPUT_COLLISION:
        payload["collision"] = active_book.data.get("collision")
    return payload


def _book_summary(book: BookState) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "id": book.book_id,
        "original_filename": book.data.get("original_filename"),
        "status": book.status,
    }
    for key in (
        "title",
        "author_last",
        "author_first",
        "series",
        "series_number",
        "voice",
    ):
        if book.data.get(key) is not None:
            summary[key] = book.data[key]
    if book.status == STATUS_GENERATING or (
        book.status == STATUS_NEEDS_INPUT and book.data.get("chunks_total") is not None
    ):
        chunks_done = book.data.get("chunks_done")
        chunks_total = book.data.get("chunks_total")
        if chunks_total is not None:
            summary["progress"] = {
                "chunks_done": chunks_done or 0,
                "chunks_total": chunks_total,
            }
    return summary


def build_status_response(runner: SnapshotSource) -> dict[str, Any]:
    """The full polling contract response
    (01-architecture.md §Status endpoint contract), built entirely from
    `runner.snapshot()` -- reconstructable at any time, never a second
    source of truth."""
    books = runner.snapshot()
    state = derive_batch_state(books)
    active_id = _active_book_id(state, books)
    active_book = next((b for b in books if b.book_id == active_id), None)

    error_payload: dict[str, Any] | None = None
    if state == BATCH_ERROR:
        error_book = next((b for b in books if b.status == STATUS_ERROR), None)
        error_payload = {
            "book_id": error_book.book_id if error_book else None,
            "summary": "Something went wrong.",
            "support_bundle_available": True,
        }

    return {
        "state": state,
        "active_book_id": active_id,
        "message": _MESSAGES[state],
        "needs_input": _needs_input_payload(active_book),
        "books": [_book_summary(b) for b in books],
        "error": error_payload,
    }


# ---------------------------------------------------------------------------
# "What voice did I use before?" (03-gui-ux-design.md §Settings areas)
# ---------------------------------------------------------------------------


class VoiceHistoryUnavailable(Exception):
    """The audit log itself could not be read -- distinct from "no rows
    yet" (03-gui-ux-design.md's own explicit distinction between the two
    empty-looking states)."""


def voice_history(audit_log: AuditLogRepository) -> list[dict[str, str]]:
    """One row per series (or per standalone book), showing the most
    recently used voice for it -- derived from the audit log's `voice`
    column, never exposing the raw log to her.

    Raises `VoiceHistoryUnavailable` if the log itself can't be read (a
    real failure); returns `[]` for the legitimately-empty case (no
    audiobooks made yet) -- callers must render these two states with
    different copy, not conflate them (03-gui-ux-design.md).
    """
    try:
        rows = audit_log.read_all()
    except OSError as exc:
        raise VoiceHistoryUnavailable(str(exc)) from exc

    latest_by_label: dict[str, dict[str, str]] = {}
    for row in rows:
        if row.get("stage") != "audio" or not row.get("voice"):
            continue
        label = row.get("series") or row.get("title") or ""
        if not label:
            continue
        # CSV rows are appended in chronological order -- the last one
        # seen for a given label is the most recent.
        latest_by_label[label] = {"label": label, "voice": row["voice"]}
    return list(latest_by_label.values())


# ---------------------------------------------------------------------------
# "Copy details for support" (06-safety-error-handling.md §Error
# communication)
# ---------------------------------------------------------------------------

_SECRET_SETTINGS_KEYS = frozenset({"ai_api_key"})


def _strip_secrets(settings: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in settings.items() if k not in _SECRET_SETTINGS_KEYS}


def current_error_detail(books: list[BookState]) -> str:
    """The raw technical error text for whichever book is currently in
    `error` status, or `""` if none is.

    This is the *only* place that real text is ever pulled from --
    `build_status_response()` deliberately never includes it (its
    `error.summary` is always the fixed generic string, per
    01-architecture.md: "the real stack trace/technical detail is never
    in this response"). Without this function, nothing could ever supply
    `build_support_bundle()`'s `technical_error` with real content, since
    the client has no route that ever told it what the error actually
    was -- the support-bundle route calls this itself server-side rather
    than trusting the caller to already know something the API never
    exposed.
    """
    for book in books:
        if book.status == STATUS_ERROR:
            return str(book.data.get("error") or "")
    return ""


def build_support_bundle(
    *,
    settings: dict[str, Any],
    audit_log: AuditLogRepository,
    technical_error: str = "",
    recent_rows: int = 20,
) -> dict[str, Any]:
    """Assemble the "Copy details for support" bundle: the real technical
    error plus recent audit-log context, from a copy of settings with
    every secret stripped -- never the raw settings.json, never
    `ai_api_key` (06-safety-error-handling.md §Error communication).

    Degrades gracefully if the audit log itself can't be read: the bundle
    is still produced, with an explicit note instead of silently failing
    at exactly the moment the support flow is most needed.
    """
    bundle: dict[str, Any] = {
        "technical_error": technical_error,
        "settings": _strip_secrets(settings),
    }
    try:
        rows = audit_log.read_all()
        bundle["recent_audit_log_rows"] = rows[-recent_rows:]
    except OSError as exc:
        bundle["recent_audit_log_rows"] = []
        bundle["audit_log_error"] = f"Could not read the audit log: {exc}"
    return bundle


def write_support_bundle(path: Path, bundle: dict[str, Any]) -> Path:
    """Write a previously-built bundle (`build_support_bundle`) to a
    plain-text file she can attach/send -- no jargon, no raw CSV/JSON dump
    she'd need to parse herself."""
    lines = ["epub-automation support details", ""]
    if bundle.get("technical_error"):
        lines += ["Error:", bundle["technical_error"], ""]
    if bundle.get("audit_log_error"):
        lines += ["Note:", bundle["audit_log_error"], ""]
    lines.append("Settings (secrets removed):")
    for key, value in sorted(bundle["settings"].items()):
        lines.append(f"  {key}: {value}")
    lines.append("")
    lines.append("Recent activity:")
    for row in bundle.get("recent_audit_log_rows", []):
        lines.append(f"  {row}")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
