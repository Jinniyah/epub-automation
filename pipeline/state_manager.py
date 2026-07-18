"""Repository wrapper for the resume-tracking state file (Repository
pattern, docs/design/PATTERNS.md §1).

The state file is the machine-readable "what's already done" tracker the
pipeline reads to decide what to (re)process -- distinct from the
human-readable audit log (pipeline/audit_logger.py). See
docs/requirements/05-data-settings-and-logging.md §State file.

Wrapping reads/writes behind this Repository interface (rather than
pipeline code touching `state.json` paths directly) means pipeline-stage
tests can use an in-memory fake instead of hitting the real filesystem
(docs/requirements/09-testing-strategy.md), and centralizes the
`schema_version` migration/mismatch policy from
docs/requirements/05-data-settings-and-logging.md §Schema versioning in
one place.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from pipeline.atomic_write import atomic_read_json, atomic_write_json

CURRENT_SCHEMA_VERSION = 2


class StateSchemaVersionError(Exception):
    """Raised when the state file's schema_version is newer than this app
    understands.

    Per ADR-0005 / 05-data-settings-and-logging.md §Schema versioning: a
    newer schema_version than the running app expects (e.g. a downgrade,
    or drift between two family members' installs) is not guessed at --
    it's treated the same as an unparseable/corrupted file, not a third,
    bespoke failure mode.
    """


def _migrate_v1_to_v2(data: dict[str, Any]) -> dict[str, Any]:
    """v2 adds an optional per-book `"snapshot"` key (full `status`/`data`,
    written by `save_book_snapshot()`) alongside the stage-completion flags
    a v1 file already had -- needed for full "Welcome back" resume
    (docs/requirements/06-safety-error-handling.md §Long-run resilience),
    not just detection. No shape change to existing v1 data: an old book
    entry simply has no `"snapshot"` yet, which `incomplete_book_snapshots()`
    already treats as "nothing to restore" rather than an error."""
    data["schema_version"] = 2
    return data


# One migration function per version step: _MIGRATIONS[N] moves a dict from
# schema_version N to N+1, returning it with schema_version bumped to N+1.
_MIGRATIONS: dict[int, Callable[[dict[str, Any]], dict[str, Any]]] = {
    1: _migrate_v1_to_v2,
}


def _default_state() -> dict[str, Any]:
    return {"schema_version": CURRENT_SCHEMA_VERSION, "books": {}}


def _migrate(data: dict[str, Any]) -> dict[str, Any]:
    """Apply the schema-version policy documented in
    docs/requirements/05-data-settings-and-logging.md §Schema versioning:

    - No `schema_version` field at all: treated as version 1 (forward-
      compatible with any file written before this field existed).
    - Older than current: run each registered migration step in order.
    - Newer than current: raise (treated the same as corrupted).
    - Equal to current: returned as-is.
    """
    version = data.get("schema_version", 1)
    if version > CURRENT_SCHEMA_VERSION:
        raise StateSchemaVersionError(
            f"state file schema_version {version} is newer than this app "
            f"understands ({CURRENT_SCHEMA_VERSION})"
        )
    while version < CURRENT_SCHEMA_VERSION:
        migrate_step = _MIGRATIONS.get(version)
        if migrate_step is None:
            raise StateSchemaVersionError(
                f"no migration registered from schema_version {version}"
            )
        data = migrate_step(data)
        version = data["schema_version"]
    data.setdefault("schema_version", CURRENT_SCHEMA_VERSION)
    return data


@dataclass
class StateRepository:
    """Repository over the resume-tracking state file at `path`.

    Usage::

        repo = StateRepository(state_path)
        repo.load()
        repo.mark_stage_complete("b1", "sanitize")
        repo.save()
    """

    path: Path
    _data: dict[str, Any] = field(default_factory=dict, repr=False)
    _loaded: bool = field(default=False, repr=False)

    def load(self) -> dict[str, Any]:
        """Load state from disk, applying the schema-version policy.

        A missing file means a fresh install with no prior run -- not an
        error -- and returns the default empty state.
        """
        raw = atomic_read_json(self.path)
        self._data = _default_state() if raw is None else _migrate(raw)
        self._loaded = True
        return self._data

    def save(self) -> None:
        """Persist current state atomically (ADR-0005)."""
        if not self._loaded:
            raise RuntimeError("load() must be called before save()")
        self._data["schema_version"] = CURRENT_SCHEMA_VERSION
        atomic_write_json(self.path, self._data)

    def is_stage_complete(self, book_id: str, stage: str) -> bool:
        book = self._data.get("books", {}).get(book_id, {})
        status: Any = book.get(stage, {}).get("status")
        return bool(status == "complete")

    def mark_stage_complete(self, book_id: str, stage: str) -> None:
        books = self._data.setdefault("books", {})
        book = books.setdefault(book_id, {})
        book[stage] = {"status": "complete"}

    def incomplete_book_ids(self) -> list[str]:
        """Book IDs known to the state file that have not reached the
        terminal `"cleanup"` stage -- the data source behind the "Welcome
        back" screen (docs/requirements/06-safety-error-handling.md
        §Long-run resilience): on every launch, check the state file for
        any book not yet marked complete through every stage it needs,
        and offer to continue it.

        `"cleanup"` (ADR-0017) is the one stage a book only ever reaches
        after every stage its run actually needed has finished and its
        output has already been copied to `output_folder`
        (`pipeline/batch_runner.py::_mark_complete`) -- checking for it
        specifically, rather than requiring every *individual* stage key
        to be present, sidesteps needing this file to also know which
        stages a given run's toggles even included.
        """
        books = self._data.get("books", {})
        return [
            book_id
            for book_id, stages in books.items()
            if stages.get("cleanup", {}).get("status") != "complete"
        ]

    def reset_stage(self, book_id: str, stage: str) -> None:
        """Reset a stage back to incomplete.

        Used by the Cancel flow's cleanup behavior (see
        docs/requirements/06-safety-error-handling.md §Cancel Design) so a
        cancelled book is correctly re-attempted rather than assumed done,
        or assumed further along than it actually is.
        """
        books = self._data.setdefault("books", {})
        book = books.setdefault(book_id, {})
        book[stage] = {"status": "incomplete"}

    def save_book_snapshot(
        self, book_id: str, status: str, data: dict[str, Any]
    ) -> None:
        """Persist a book's full `status`/`data` (not just per-stage
        completion flags) -- what full "Welcome back" resume rebuilds a
        live `BatchRunner` from on the next launch
        (`pipeline/batch_runner.py::BatchRunner.restore_books()`). Called
        by `BatchRunner._set_book()` on every status change, the same way
        `mark_stage_complete()` already keeps stage flags current."""
        books = self._data.setdefault("books", {})
        book = books.setdefault(book_id, {})
        book["snapshot"] = {"status": status, "data": data}

    def incomplete_book_snapshots(self) -> list[dict[str, Any]]:
        """The full-resume counterpart to `incomplete_book_ids()`: the same
        "not yet through `cleanup`" filter, but returning each book's
        persisted `{"book_id", "status", "data"}` snapshot instead of just
        its id -- what `BatchRunner.restore_books()` needs to actually
        rebuild the book, not just know it exists. A book with no snapshot
        yet (a v1 file migrated to v2, or one that died before its first
        status change ever got persisted) is skipped -- there is nothing
        to restore it *from*, so it is silently dropped from resume rather
        than reconstructed with invented data. It stays in `state.json`
        and is picked up by "clean up stuck in-progress state"'s blanket
        sweep if she uses that instead."""
        books = self._data.get("books", {})
        result: list[dict[str, Any]] = []
        for book_id, stages in books.items():
            if stages.get("cleanup", {}).get("status") == "complete":
                continue
            snapshot = stages.get("snapshot")
            if not snapshot:
                continue
            result.append(
                {
                    "book_id": book_id,
                    "status": snapshot["status"],
                    "data": snapshot["data"],
                }
            )
        return result

    def reset_all(self) -> None:
        """Wipe all book tracking -- the state-file half of "clean up
        stuck in-progress state" (docs/BACKLOG.md Epic 9): a blunt full
        reset, not a per-book operation, so it never needs to correlate
        with any live tracked `Book` (the case that motivated it: files
        deleted outside the app, with no live book behind them anymore).
        Leaves `schema_version` untouched."""
        self._data["books"] = {}
