"""`SafeZipOperation` -- Template Method base for every zip-opening code
path (docs/design/PATTERNS.md §1).

The pre-code design review found that the same zip-safety guards (path
traversal, zip-bomb cap, XXE prevention) must apply everywhere a zip is
opened, not just in the sanitize stage (docs/requirements/02-pipeline-
stages.md §Stage 2, docs/requirements/06-safety-error-handling.md §Input
validation, ADR-0004/ADR-0013). Fixing the guard order here -- path
traversal, then zip-bomb cap, then XXE prevention -- means a new
zip-touching code path (e.g. Screen 1's validation pass, Epic 8) forgets a
guard by construction being harder, not something to catch in code review
every time.

Concrete stages (pipeline/sanitize_stage.py, Epic 2; Screen-1 validation,
Epic 8) subclass `SafeZipOperation` and implement only `_do_operation` --
the actual read/extract/repack work, given a zip that has already passed
every guard below.
"""

from __future__ import annotations

import zipfile
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Conservative defaults -- a real EPUB's uncompressed content is measured
# in single-digit MB. A zip claiming gigabytes of uncompressed content
# from a small compressed archive is a bomb, not a large book.
DEFAULT_MAX_UNCOMPRESSED_TOTAL_BYTES = 500 * 1024 * 1024  # 500 MB
DEFAULT_MAX_UNCOMPRESSED_ENTRY_BYTES = 200 * 1024 * 1024  # 200 MB
DEFAULT_MAX_COMPRESSION_RATIO = 100  # uncompressed / compressed, per entry


class ZipSafetyError(Exception):
    """Base class for every guard failure below.

    Callers can catch this one type to handle "this zip failed a safety
    check" generically (e.g. Screen 1's validation pass, which just needs
    to reject the file with a friendly message), or catch a specific
    subclass for a more precise message/log entry.
    """


class PathTraversalError(ZipSafetyError):
    """A zip entry's name would extract outside the target directory."""


class ZipBombError(ZipSafetyError):
    """A zip entry's (or the archive's total) uncompressed size, or an
    entry's compression ratio, exceeds the configured cap."""


class XXEError(ZipSafetyError):
    """An XML-ish member (e.g. content.opf) contains a DOCTYPE/ENTITY
    declaration -- the shape of a classic XXE payload."""


@dataclass
class SafeZipOperation(ABC):
    """Template Method: `run()` fixes the guard order and must not be
    overridden. Subclasses implement `_do_operation` only."""

    zip_path: Path
    max_uncompressed_total_bytes: int = DEFAULT_MAX_UNCOMPRESSED_TOTAL_BYTES
    max_uncompressed_entry_bytes: int = DEFAULT_MAX_UNCOMPRESSED_ENTRY_BYTES
    max_compression_ratio: int = DEFAULT_MAX_COMPRESSION_RATIO

    def run(self) -> Any:
        """Fixed guard order: path traversal -> zip-bomb cap -> XXE.

        Do not override this method -- override `_do_operation` instead.
        """
        with zipfile.ZipFile(self.zip_path) as zf:
            self._guard_path_traversal(zf)
            self._guard_zip_bomb(zf)
            self._guard_xxe(zf)
            return self._do_operation(zf)

    def _guard_path_traversal(self, zf: zipfile.ZipFile) -> None:
        target = Path(".").resolve()
        for name in zf.namelist():
            # Absolute paths and "../" segments are the two ways a crafted
            # zip entry can escape the extraction directory.
            if Path(name).is_absolute():
                raise PathTraversalError(f"absolute path entry: {name!r}")
            resolved = (target / name).resolve()
            if resolved != target and target not in resolved.parents:
                raise PathTraversalError(f"path-traversal entry: {name!r}")

    def _guard_zip_bomb(self, zf: zipfile.ZipFile) -> None:
        total_uncompressed = 0
        for info in zf.infolist():
            if info.is_dir():
                continue
            if info.file_size > self.max_uncompressed_entry_bytes:
                raise ZipBombError(
                    f"entry {info.filename!r} uncompressed size "
                    f"{info.file_size} exceeds the per-entry cap "
                    f"({self.max_uncompressed_entry_bytes})"
                )
            if info.compress_size > 0:
                ratio = info.file_size / info.compress_size
                if ratio > self.max_compression_ratio:
                    raise ZipBombError(
                        f"entry {info.filename!r} compression ratio "
                        f"{ratio:.0f}x exceeds the cap "
                        f"({self.max_compression_ratio}x)"
                    )
            total_uncompressed += info.file_size
            if total_uncompressed > self.max_uncompressed_total_bytes:
                raise ZipBombError(
                    "archive total uncompressed size exceeds the cap "
                    f"({self.max_uncompressed_total_bytes})"
                )

    def _guard_xxe(self, zf: zipfile.ZipFile) -> None:
        xml_suffixes = (".opf", ".xhtml", ".html", ".htm", ".ncx", ".xml")
        for info in zf.infolist():
            if info.is_dir() or not info.filename.lower().endswith(xml_suffixes):
                continue
            data = zf.read(info.filename)
            # A cheap, dependency-free ENTITY/DOCTYPE sniff before ever
            # handing these bytes to an XML parser -- the fastest way to
            # reject the classic XXE payload shape without requiring every
            # call site to remember to configure a hardened parser.
            if b"<!ENTITY" in data:
                raise XXEError(f"{info.filename!r} contains an ENTITY declaration")
            # A DOCTYPE is only a real XXE vector if it references an
            # external resource (SYSTEM/PUBLIC) or declares an internal
            # subset ("["  -- where an inline ENTITY would live, already
            # caught above regardless). A bare `<!DOCTYPE html>` with
            # neither is the standard, harmless HTML5 doctype every real
            # XHTML file uses (including ebooklib's own output) and must
            # not be flagged -- found via input_validation.py becoming
            # this guard's first caller against realistic EPUB content;
            # sanitize_stage.py's own hand-crafted fixtures never
            # happened to include a plain doctype, which is why this sat
            # latent.
            doctype_idx = data.upper().find(b"<!DOCTYPE")
            if doctype_idx != -1:
                end = data.find(b">", doctype_idx)
                declaration = data[doctype_idx : end if end != -1 else len(data)]
                upper_declaration = declaration.upper()
                if (
                    b"SYSTEM" in upper_declaration
                    or b"PUBLIC" in upper_declaration
                    or b"[" in declaration
                ):
                    raise XXEError(
                        f"{info.filename!r} contains a DOCTYPE with an external "
                        "reference or internal subset"
                    )

    @abstractmethod
    def _do_operation(self, zf: zipfile.ZipFile) -> Any:
        """Subclass hook: the actual read/extract/repack work, given a zip
        that has already passed every guard above."""
        raise NotImplementedError
