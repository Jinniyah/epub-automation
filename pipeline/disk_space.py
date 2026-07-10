"""Pre-batch disk-space estimate and check
(docs/requirements/06-safety-error-handling.md §Resource & cost safety).

Must account for copy-based storage, not just final audio size: per
`01-architecture.md` §Folder mapping, a book's source is copied into
`Library/00-Incoming/`, then copied again into `output_folder` at two
points (the sanitized EPUB, then the finished audiobook) -- meaning a
given book's content can exist in more than one place on disk at once.
The estimate below sums all of that, not audio size alone.

`SECONDS_PER_CHAR`'s placeholder status (and the exact 16,000 bytes/sec
constant it multiplies against) lives in `pipeline/tts_engine.py` -- this
module composes that existing formula with the "copy multiplies storage"
piece and a real `shutil.disk_usage()` check; it does not duplicate the
per-character estimate itself.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from pipeline.tts_engine import estimate_audio_bytes


@dataclass(frozen=True)
class BookSpaceEstimate:
    """One book's contribution to a batch's disk-space estimate."""

    book_id: str
    source_bytes: int
    remaining_chars: int


@dataclass(frozen=True)
class PathSpaceCheck:
    path: Path
    free_bytes: int
    sufficient: bool


@dataclass(frozen=True)
class DiskSpaceReport:
    """Everything Screen 1's pre-Start disk-space check needs to decide
    whether to warn her, and about which location specifically."""

    estimated_total_bytes: int
    checked_paths: dict[str, PathSpaceCheck]

    @property
    def any_insufficient(self) -> bool:
        return any(not check.sufficient for check in self.checked_paths.values())


def estimate_batch_bytes(books: list[BookSpaceEstimate]) -> int:
    """Sum, per book: the incoming copy + the sanitized-EPUB copy (both
    source-file-sized, existing on disk simultaneously at different pipeline
    points) + the estimated audio output -- the full formula from
    06-safety-error-handling.md §Resource & cost safety, not audio size
    alone. Deliberately biased toward overestimating, same as
    `estimate_audio_bytes()` itself.
    """
    total = 0
    for book in books:
        total += book.source_bytes * 2  # incoming copy + sanitized copy
        total += estimate_audio_bytes(book.remaining_chars)
    return total


def check_free_space(paths: list[Path], required_bytes: int) -> DiskSpaceReport:
    """Check free space on the drive(s) backing each of `paths` --
    typically the internal `Library/` root and her chosen `output_folder`,
    which may be on different drives -- against `required_bytes`.

    Deliberately per-location, not a single combined check: either
    location running out independently (e.g. a small system drive hosting
    `%APPDATA%\\EpubAutomation\\Library`, a nearly-full external drive as
    `output_folder`) is a real, distinct failure mode worth naming, not
    just a single pass/fail bit.
    """
    checked: dict[str, PathSpaceCheck] = {}
    for path in paths:
        probe = path
        while not probe.exists() and probe.parent != probe:
            probe = probe.parent
        usage = shutil.disk_usage(probe)
        checked[str(path)] = PathSpaceCheck(
            path=path,
            free_bytes=usage.free,
            sufficient=usage.free >= required_bytes,
        )
    return DiskSpaceReport(estimated_total_bytes=required_bytes, checked_paths=checked)
