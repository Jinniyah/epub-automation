"""Rename stage — ports epub-renamer's renamer.py/main.py to the Stage
protocol (docs/design/PATTERNS.md §1).

See docs/design/adr/0003-pluggable-user-keyed-ai-provider.md,
docs/design/adr/0014-reuse-existing-implementations-by-default.md,
docs/design/adr/0016-windows-safe-filesystem-naming.md, and
docs/requirements/02-pipeline-stages.md §Stage 1.

Adapted from the original epub-renamer, for concrete, nameable reasons
(ADR-0014):
  - `FILENAME_PATTERN` reused verbatim -- it matches the *shape* of an
    already-normalized name, not which characters may appear inside it.
  - `build_filename()` now sanitizes each Title/Author/Series component
    individually via `pipeline.epub_utils.sanitize_filesystem_name()`
    before assembly (ADR-0016), replacing the original's blanket
    em-dash-replacement `safe_filename()`/`rename_file()` combo.
  - The original operates in-place on one folder (`os.rename`); this
    pipeline's stage folders are copy-based (`01-architecture.md` §Folder
    mapping / ADR-0017), so this stage copies into `output_folder` under
    the new name rather than renaming in place.
  - The AI provider is selected per-install via settings.json
    (`ai_provider`/`ai_api_key`), not a module-level `.env`-backed
    `config.py`, and a runtime AI failure falls back silently, per file,
    to `NullProvider` (`02-pipeline-stages.md` §Stage 1 Failure handling)
    -- the original only fell back to Null when the key was blank, never
    on a runtime failure, since it had no failure-handling story at all.

**Scope note:** `MAX_FILES`/`DRY_RUN` (docs/BACKLOG.md Epic 3) are batch-
level concerns; `Stage.run()` is deliberately per-book
(docs/design/PATTERNS.md's `Stage` sketch), so there is no batch loop
here to cap. `dry_run` is honored per call (this stage never writes a
file when `dry_run=True`, matching the original tool's exact "preview
only" semantics) for the CLI/advanced front door
(`docs/requirements/01-architecture.md`); the GUI front door never sets
it. Enforcing `MAX_FILES` itself -- stopping a batch after N books, and
rejecting excess books individually at Screen 1 -- is a batch-runner
concern that belongs to `main.py`/`backend/bridge.py` (Epic 6) and
Screen 1 validation (Epic 8), once a runner that iterates whole batches
exists. `DEFAULT_MAX_FILES` below is exported now so those epics have a
single constant to wire up rather than inventing their own number.

**Per-field AI-enrichment merge (docs/BACKLOG.md Epic 8.5, fixed
2026-07-14):** `final_meta` used to take the AI response's
author/series/series_number fields as-is, with no fallback for a field
the AI response left blank -- unlike `title`, which already fell back to
the EPUB's own metadata. A real filename like "Sanderson, Brandon —
Elantris.epub" already carries clean author info, and a real AI response
sometimes only fills in `title` and leaves the rest `null` (the model
genuinely doesn't know, or the prompt's series-only rules don't apply to
a standalone book) -- both cases used to silently discard information
that was sitting right there. `_merge_field_fallbacks()` below applies
the same fallback chain (AI response -> filename-derived guess -> EPUB
metadata) to every field, not just title.
"""

from __future__ import annotations

import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pipeline.ai_providers.null_provider import NullProvider
from pipeline.ai_providers.registry import get_provider
from pipeline.audit_logger import AuditLogRepository
from pipeline.epub_reader import extract_epub_metadata, extract_text_sample
from pipeline.epub_utils import (
    guess_author_from_filename,
    guess_series_from_filename,
    parse_author_name,
    sanitize_filesystem_name,
)
from pipeline.stage import BookState

# Matches both valid normalized formats:
#   Lastname, Firstname — Series #01 — Title.epub
#   Lastname, Firstname — Title.epub
# Ported verbatim from epub-renamer/renamer.py (ADR-0014) -- this matches
# the *shape* of an already-normalized name; sanitized Title/Author/Series
# text still matches correctly (ADR-0016).
FILENAME_PATTERN = re.compile(
    r"^[^,]+, [^—]+(— .+ #\d{2} — .+|— [^—]+)\.epub$",
    re.IGNORECASE,
)

# Ported from epub-renamer's .env.example `MAX_FILES=50` default
# (ADR-0003, ADR-0014) -- see the module docstring's Scope note above for
# why enforcement isn't in this stage.
DEFAULT_MAX_FILES = 50

_RESULT_KEYS = ("title", "author_first", "author_last", "series", "series_number")


def build_filename(meta: dict[str, Any]) -> str:
    """Construct a normalized EPUB filename from metadata fields.

    Output formats:
        ``Lastname, Firstname — Series #01 — Title.epub``
        ``Lastname, Firstname — Title.epub``

    Every Title/Author/Series component is sanitized individually before
    assembly (ADR-0016) -- the `—` separators and `#NN` numbering are
    structural, added here, not part of any sanitized component.
    """
    last = sanitize_filesystem_name(meta.get("author_last") or "Unknown")
    first = sanitize_filesystem_name(meta.get("author_first") or "Unknown")
    title = sanitize_filesystem_name(meta.get("title") or "Unknown")

    series = meta.get("series")
    number = meta.get("series_number")

    middle: str | None
    if series and number:
        middle = f"{sanitize_filesystem_name(str(series))} #{int(number):02d}"
    elif series:
        middle = f"{sanitize_filesystem_name(str(series))} #ZZ"
    else:
        middle = None

    if middle:
        return f"{last}, {first} — {middle} — {title}.epub"
    return f"{last}, {first} — {title}.epub"


def _merge_field_fallbacks(
    ai_meta: dict[str, Any], filename: str, metadata: dict[str, Any]
) -> dict[str, Any]:
    """Apply the AI-response -> filename-guess -> EPUB-metadata fallback
    chain to every field, not just title -- see the module docstring's
    "Per-field AI-enrichment merge" note above.

    `metadata` (from `extract_epub_metadata()`) has no series field at
    all -- EPUBs have no standard place to put one -- so series/
    series_number only ever fall back to a filename guess, never to
    `metadata`.
    """
    fname_author_first, fname_author_last = guess_author_from_filename(filename)
    meta_author_first, meta_author_last = parse_author_name(metadata.get("author"))
    fname_series, fname_series_number = guess_series_from_filename(filename)

    return {
        "title": ai_meta.get("title") or metadata.get("title"),
        "author_first": (
            ai_meta.get("author_first") or fname_author_first or meta_author_first
        ),
        "author_last": (
            ai_meta.get("author_last") or fname_author_last or meta_author_last
        ),
        "series": ai_meta.get("series") or fname_series,
        "series_number": ai_meta.get("series_number") or fname_series_number,
    }


class RenameStage:
    """Stage 1: rename — AI-enriched metadata, normalized filenames.

    Implements the Stage protocol (pipeline/stage.py). Configuration is
    injected at construction; run() processes one book at a time.
    """

    name = "rename"

    def __init__(
        self,
        input_folder: Path,
        output_folder: Path,
        audit_log: AuditLogRepository,
        ai_provider: str = "none",
        ai_api_key: str = "",
        *,
        dry_run: bool = False,
    ) -> None:
        self._input_folder = input_folder
        self._output_folder = output_folder
        self._audit_log = audit_log
        self._dry_run = dry_run
        self._null_provider = get_provider("none")
        try:
            self._provider = get_provider(ai_provider, ai_api_key)
        except Exception:
            # Missing/invalid key at construction time -- fall back to
            # NullProvider for the whole run, the same silent-fallback
            # principle as a per-file runtime failure below
            # (02-pipeline-stages.md §Stage 1 Failure handling).
            self._provider = self._null_provider

    def applies_to(self, book: BookState, settings: dict[str, Any]) -> bool:
        return bool(settings.get("fix_names", True))

    def run(self, book: BookState) -> BookState:
        filename = book.data.get("filename") or (book.book_id + ".epub")
        epub_path = self._input_folder / filename

        if not epub_path.exists():
            return BookState(
                book.book_id,
                "error",
                {**book.data, "error": f"Input EPUB not found: {epub_path}"},
            )

        if FILENAME_PATTERN.match(filename):
            return self._pass_through_already_normalized(book, epub_path, filename)

        try:
            metadata = extract_epub_metadata(epub_path)
            text_sample = extract_text_sample(epub_path)
        except Exception as exc:
            self._audit_log.append(
                self._audit_row(
                    filename,
                    filename,
                    {},
                    ai_used="no",
                    renamed="no",
                    skipped_reason="epub_read_error",
                )
            )
            return BookState(
                book.book_id,
                "error",
                {**book.data, "error": f"Could not read EPUB: {exc}"},
            )

        # "Was AI enrichment invoked" (05-data-settings-and-logging.md
        # §Audit log) means a real, non-Null provider -- an install with
        # ai_provider="none" never "used AI" even though the same
        # NullProvider.identify_book() call path runs either way.
        ai_used = not isinstance(self._provider, NullProvider)
        try:
            ai_meta = self._provider.identify_book(filename, metadata, text_sample)
        except Exception:
            # Silent per-file fallback -- never blocks the batch on one
            # file's AI call (02-pipeline-stages.md §Stage 1 Failure
            # handling).
            ai_meta = self._null_provider.identify_book(filename, metadata, text_sample)
            ai_used = False

        for key in _RESULT_KEYS:
            ai_meta.setdefault(key, None)

        final_meta = _merge_field_fallbacks(ai_meta, filename, metadata)
        new_name = build_filename(final_meta)
        ai_used_flag = "yes" if ai_used else "no"

        if self._dry_run:
            self._audit_log.append(
                self._audit_row(
                    filename,
                    new_name,
                    final_meta,
                    ai_used=ai_used_flag,
                    renamed="no",
                    skipped_reason="dry_run",
                )
            )
            return BookState(
                book.book_id,
                "renamed",
                {
                    **book.data,
                    **final_meta,
                    "filename": filename,
                    "epub_path": str(epub_path),
                },
            )

        self._output_folder.mkdir(parents=True, exist_ok=True)
        out_path = self._output_folder / new_name

        if out_path.exists() and out_path.name != filename:
            # Name conflict -- keep the file under its original name
            # rather than overwriting or losing it (mirrors the original
            # script's no-overwrite `rename_file()` behavior), so the
            # batch keeps moving instead of failing this book outright.
            fallback_path = self._output_folder / filename
            shutil.copy2(epub_path, fallback_path)
            self._audit_log.append(
                self._audit_row(
                    filename,
                    new_name,
                    final_meta,
                    ai_used=ai_used_flag,
                    renamed="no",
                    skipped_reason="name_conflict",
                )
            )
            return BookState(
                book.book_id,
                "renamed",
                {
                    **book.data,
                    **final_meta,
                    "filename": filename,
                    "epub_path": str(fallback_path),
                },
            )

        shutil.copy2(epub_path, out_path)
        self._audit_log.append(
            self._audit_row(
                filename,
                new_name,
                final_meta,
                ai_used=ai_used_flag,
                renamed="yes",
                skipped_reason="",
            )
        )
        return BookState(
            book.book_id,
            "renamed",
            {
                **book.data,
                **final_meta,
                "filename": new_name,
                "epub_path": str(out_path),
            },
        )

    def _pass_through_already_normalized(
        self, book: BookState, epub_path: Path, filename: str
    ) -> BookState:
        self._output_folder.mkdir(parents=True, exist_ok=True)
        out_path = self._output_folder / filename
        if out_path.resolve() != epub_path.resolve():
            shutil.copy2(epub_path, out_path)

        self._audit_log.append(
            self._audit_row(
                filename,
                filename,
                {},
                ai_used="no",
                renamed="no",
                skipped_reason="already_normalized",
            )
        )
        return BookState(
            book.book_id,
            "renamed",
            {**book.data, "filename": filename, "epub_path": str(out_path)},
        )

    def _audit_row(
        self,
        original_filename: str,
        new_filename: str,
        meta: dict[str, Any],
        *,
        ai_used: str,
        renamed: str,
        skipped_reason: str,
    ) -> dict[str, Any]:
        author = " ".join(
            part for part in (meta.get("author_first"), meta.get("author_last")) if part
        )
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "stage": self.name,
            "original_filename": original_filename,
            "new_filename": new_filename,
            "title": meta.get("title") or "",
            "author": author,
            "series": meta.get("series") or "",
            "series_number": meta.get("series_number") or "",
            "ai_used": ai_used,
            "renamed": renamed,
            "skipped_reason": skipped_reason,
        }
