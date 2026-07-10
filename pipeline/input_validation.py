"""Screen-1 input validation (docs/requirements/06-safety-error-handling.md
§Input validation) -- extension check, real-zip-validity check, and DRM
detection, all run synchronously on drop/choose, before "Start" is even
reachable, per that section's explicit resolution.

Pure functions, no HTTP/Flask dependency -- backend/bridge.py calls these
directly, and pipeline/batch_runner.py's `add_book()` is the single call
site for the whole app (both front doors add books through the same
validation path).

Zip-bomb and path-traversal guards apply here too, not only in
sanitize_stage.py (`06-safety-error-handling.md` §Input validation) --
reuses the same `SafeZipOperation` Template Method base
(docs/design/PATTERNS.md §1) rather than re-implementing those guards a
second time.
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from pipeline.safe_zip import SafeZipOperation, ZipSafetyError

# Ported from epub-renamer's MAX_FILES=50 default (see
# pipeline/rename_stage.py::DEFAULT_MAX_FILES) -- kept as an independent
# constant here rather than importing rename_stage's, since this is a
# batch-level cap enforced at Screen 1, not a rename-stage concern
# (docs/BACKLOG.md Epic 3's own scope note defers exactly this to Epic 6).
DEFAULT_MAX_FILES = 50

# The standard marker Adobe-DRM-protected EPUBs use to declare which
# files are encrypted -- checking for its presence is cheap (a namelist
# membership check) and reliable, unlike inferring DRM after the fact
# from garbled text (06-safety-error-handling.md §Input validation).
DRM_MARKER = "META-INF/encryption.xml"


class RejectionReason(str, Enum):
    NOT_EPUB = "not_epub"
    DAMAGED = "damaged"
    DRM_PROTECTED = "drm_protected"
    MAX_FILES_EXCEEDED = "max_files_exceeded"


# Her-facing copy, verbatim from 06-safety-error-handling.md's own examples
# -- centralized here so bridge.py/app.py never invent their own wording.
MESSAGES: dict[RejectionReason, str] = {
    RejectionReason.NOT_EPUB: (
        "That doesn't look like a book file — only .epub files work here"
    ),
    RejectionReason.DAMAGED: "This file looks damaged",
    RejectionReason.DRM_PROTECTED: (
        "This book is protected and can't be opened here — try removing "
        "the protection first, or check if your library/store offers a "
        "DRM-free download"
    ),
    RejectionReason.MAX_FILES_EXCEEDED: (
        f"You can convert up to {DEFAULT_MAX_FILES} books at a time — "
        "try the rest in another batch."
    ),
}


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    reason: RejectionReason | None = None
    message: str = ""


def _reject(reason: RejectionReason) -> ValidationResult:
    return ValidationResult(ok=False, reason=reason, message=MESSAGES[reason])


class _ValidateEpub(SafeZipOperation):
    """Runs the shared zip-safety guard order, then just hands back the
    member list -- Screen 1 doesn't need to extract anything, only decide
    whether this zip is safe and EPUB-shaped enough to accept."""

    def _do_operation(self, zf: zipfile.ZipFile) -> list[str]:
        return zf.namelist()


def validate_epub_file(path: Path) -> ValidationResult:
    """Validate one candidate file for Screen 1's "Your books" list.

    Checks, in order: extension, real-zip validity (including the shared
    path-traversal/zip-bomb/XXE guards), EPUB-shaped internals (a
    `mimetype` member), then DRM. A file that fails any check is rejected
    with a specific, friendly `message` -- never a raw exception -- so the
    caller can show it immediately without inventing its own wording.
    """
    if path.suffix.lower() != ".epub":
        return _reject(RejectionReason.NOT_EPUB)

    if not zipfile.is_zipfile(path):
        return _reject(RejectionReason.DAMAGED)

    try:
        names = _ValidateEpub(zip_path=path).run()
    except (ZipSafetyError, zipfile.BadZipFile, OSError):
        # A crafted malicious zip and a genuinely corrupted download both
        # land here -- neither is a distinction worth surfacing to her
        # (06-safety-error-handling.md never asks for a security-specific
        # message), and not leaking "this tripped a security guard" is the
        # safer default for an adversarial input either way.
        return _reject(RejectionReason.DAMAGED)

    if "mimetype" not in names:
        return _reject(RejectionReason.DAMAGED)

    if DRM_MARKER in names:
        return _reject(RejectionReason.DRM_PROTECTED)

    return ValidationResult(ok=True)


def check_batch_capacity(
    current_count: int, max_files: int = DEFAULT_MAX_FILES
) -> ValidationResult:
    """Reject an *additional* book once the batch already holds
    `max_files` -- called before a new book is added, not after
    (06-safety-error-handling.md §Batches exceeding MAX_FILES: excess
    books are rejected individually at add-time, never a silent
    mid-batch truncation)."""
    if current_count >= max_files:
        return _reject(RejectionReason.MAX_FILES_EXCEEDED)
    return ValidationResult(ok=True)
