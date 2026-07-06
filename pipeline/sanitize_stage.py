"""Sanitize stage — ports PS_Run-CleanUpEpub.ps1 to Python (ADR-0004).

Preserves all ten security controls from the original PowerShell script:
  1. Path-traversal guard on ZIP extraction      (SafeZipOperation base)
  2. Path-traversal / symlink guard on repack    (_repack_epub)
  3. Zip-bomb guard                              (SafeZipOperation base)
  4. XXE prevention                (SafeZipOperation base + lxml parser flags)
  5. Profanity-list size cap                     (MAX_PROFANITY_WORDS check in __init__)
  6. Unicode whole-word matching + 5 s ReDoS timeout  (regex package)
  7. Asterisk replacement, same length as matched word
  8. .xhtml / .htm / .html content files only
  9. mimetype written first, uncompressed, on repack   (EPUB spec compliance)
 10. Temp-dir atomic cleanup on any failure

See docs/design/adr/0004-sanitize-ported-powershell-to-python.md and
docs/requirements/02-pipeline-stages.md §Stage 2.
"""

from __future__ import annotations

import csv
import os
import shutil
import tempfile
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

import regex
from lxml import etree

from pipeline.safe_zip import (
    DEFAULT_MAX_COMPRESSION_RATIO,
    DEFAULT_MAX_UNCOMPRESSED_ENTRY_BYTES,
    DEFAULT_MAX_UNCOMPRESSED_TOTAL_BYTES,
    SafeZipOperation,
)
from pipeline.stage import BookState

MAX_PROFANITY_WORDS = 2000
_CONTENT_SUFFIXES = frozenset({".xhtml", ".htm", ".html"})
_REDOS_TIMEOUT = 5.0  # seconds — mirrors the PowerShell original's 5-second timeout


class _ExtractEpub(SafeZipOperation):
    """Extracts a validated EPUB into a temp directory (controls 1, 3, 4)."""

    extract_to: Path

    def __init__(
        self,
        zip_path: Path,
        extract_to: Path,
        max_uncompressed_total_bytes: int = DEFAULT_MAX_UNCOMPRESSED_TOTAL_BYTES,
        max_uncompressed_entry_bytes: int = DEFAULT_MAX_UNCOMPRESSED_ENTRY_BYTES,
        max_compression_ratio: int = DEFAULT_MAX_COMPRESSION_RATIO,
    ) -> None:
        super().__init__(
            zip_path,
            max_uncompressed_total_bytes,
            max_uncompressed_entry_bytes,
            max_compression_ratio,
        )
        self.extract_to = extract_to

    def _do_operation(self, zf: zipfile.ZipFile) -> None:
        zf.extractall(self.extract_to)


class SanitizeStage:
    """Stage 2: sanitize — clean profanity from EPUBs.

    Implements the Stage protocol (pipeline/stage.py). Configuration is
    injected at construction; run() processes one book at a time.
    Call write_report() after all books in the batch to flush the
    per-run sidecar CSV (02-pipeline-stages.md §Stage 2).
    """

    name = "sanitize"

    def __init__(
        self,
        input_folder: Path,
        output_folder: Path,
        report_dir: Path,
        profanity_words: list[str],
        output_suffix: str = "_cln",
        max_extracted_mb: int = 500,
        *,
        _run_timestamp: datetime | None = None,
    ) -> None:
        if not profanity_words:
            raise ValueError("Profanity list is empty.")
        if len(profanity_words) > MAX_PROFANITY_WORDS:
            raise ValueError(
                f"Profanity list has {len(profanity_words)} words, "
                f"exceeding the cap of {MAX_PROFANITY_WORDS}."
            )

        self._input_folder = input_folder
        self._output_folder = output_folder
        self._report_dir = report_dir
        self._output_suffix = output_suffix
        self._max_extracted_bytes = max_extracted_mb * 1024 * 1024

        ts = _run_timestamp or datetime.now()
        self._report_path = (
            report_dir
            / f"CleanReport{output_suffix}_{ts.strftime('%Y%m%d_%H%M%S')}.csv"
        )
        self._report_rows: list[dict[str, Any]] = []

        # Control 6: Unicode-aware whole-word boundaries + ReDoS timeout.
        # (?<![\p{L}\p{N}_]) / (?![\p{L}\p{N}_]) mirrors the .NET original's
        # lookbehind/lookahead exactly; plain \b would behave differently on
        # non-ASCII alphabetic text (ADR-0004).
        escaped = [regex.escape(w) for w in profanity_words]
        pattern = r"(?<![\p{L}\p{N}_])(" + "|".join(escaped) + r")(?![\p{L}\p{N}_])"
        self._rx = regex.compile(pattern, regex.IGNORECASE)

    def applies_to(self, book: BookState, settings: dict[str, Any]) -> bool:
        return bool(settings.get("clean_language", True))

    def run(self, book: BookState) -> BookState:
        filename = book.data.get("filename") or (book.book_id + ".epub")
        epub_path = self._input_folder / filename

        if not epub_path.exists():
            return BookState(
                book.book_id,
                "error",
                {**book.data, "error": f"Input EPUB not found: {epub_path}"},
            )

        out_stem = epub_path.stem + self._output_suffix
        out_path = self._output_folder / f"{out_stem}.epub"
        if out_path.resolve() == epub_path.resolve():
            return BookState(
                book.book_id,
                "error",
                {**book.data, "error": "Output path equals source path."},
            )

        # Control 10: all work in a temp dir; cleaned up in the finally block.
        work_dir = Path(tempfile.mkdtemp(prefix=f"epub_sanitize_{uuid.uuid4().hex}_"))
        try:
            # Controls 1, 3, 4: safe extraction via SafeZipOperation guards.
            _ExtractEpub(
                zip_path=epub_path,
                extract_to=work_dir,
                max_uncompressed_total_bytes=self._max_extracted_bytes,
            ).run()

            # Controls 6, 7, 8: text replacement in content files.
            words_replaced, rows = self._process_content(epub_path.name, work_dir)

            # Controls 2, 9: safe repack with mimetype first, uncompressed.
            _repack_epub(work_dir, out_path)

            self._report_rows.extend(rows)

            return BookState(
                book.book_id,
                "sanitized",
                {
                    **book.data,
                    "filename": out_path.name,
                    "epub_path": str(out_path),
                    "words_replaced": words_replaced,
                    "sanitize_detail_report": str(self._report_path),
                },
            )

        except Exception as exc:
            return BookState(book.book_id, "error", {**book.data, "error": str(exc)})

        finally:
            # Control 10: always remove temp dir regardless of success/failure.
            shutil.rmtree(work_dir, ignore_errors=True)

    def write_report(self) -> Path | None:
        """Write the per-run sidecar CSV; call after all books are processed.

        Returns the path written, or None if no replacements occurred.
        Matches the original script's CleanReport_<timestamp>.csv pattern.
        """
        if not self._report_rows:
            return None
        sorted_rows = sorted(
            self._report_rows, key=lambda r: (r["Epub"], r["File"], r["Word"])
        )
        self._report_dir.mkdir(parents=True, exist_ok=True)
        with open(self._report_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=["Epub", "File", "Word", "Count"])
            writer.writeheader()
            writer.writerows(sorted_rows)
        return self._report_path

    def _process_content(
        self, epub_name: str, work_dir: Path
    ) -> tuple[int, list[dict[str, Any]]]:
        total = 0
        rows: list[dict[str, Any]] = []
        work_root = str(work_dir.resolve()) + os.sep

        for content_file in work_dir.rglob("*"):
            if not content_file.is_file():
                continue
            if content_file.suffix.lower() not in _CONTENT_SUFFIXES:
                continue
            # Control 2: symlink guard — skip files resolving outside work_dir.
            if not str(content_file.resolve()).startswith(work_root):
                continue
            n, file_rows = self._process_file(epub_name, work_dir, content_file)
            total += n
            rows.extend(file_rows)

        return total, rows

    def _process_file(
        self, epub_name: str, work_dir: Path, file_path: Path
    ) -> tuple[int, list[dict[str, Any]]]:
        # Control 4: parse with entity/DTD resolution fully disabled.
        parser = etree.XMLParser(
            resolve_entities=False,
            no_network=True,
            dtd_validation=False,
            load_dtd=False,
        )
        try:
            tree = etree.parse(str(file_path), parser)
        except etree.XMLSyntaxError:
            return 0, []

        root = tree.getroot()
        counts: dict[str, int] = {}
        changed = False

        for elem in root.iter():
            # XPath //text() includes both elem.text (text before first child)
            # and elem.tail (text between closing tag and next sibling).
            if elem.text:
                new_val, c = self._replace_in_text(elem.text)
                if new_val != elem.text:
                    elem.text = new_val
                    changed = True
                    for w, n in c.items():
                        counts[w] = counts.get(w, 0) + n
            if elem.tail:
                new_val, c = self._replace_in_text(elem.tail)
                if new_val != elem.tail:
                    elem.tail = new_val
                    changed = True
                    for w, n in c.items():
                        counts[w] = counts.get(w, 0) + n

        if not changed:
            return 0, []

        tree.write(str(file_path), encoding="UTF-8", xml_declaration=True)

        relative = file_path.relative_to(work_dir).as_posix()
        total = sum(counts.values())
        file_rows = [
            {"Epub": epub_name, "File": relative, "Word": w, "Count": c}
            for w, c in counts.items()
            if c > 0
        ]
        return total, file_rows

    def _replace_in_text(self, text: str) -> tuple[str, dict[str, int]]:
        counts: dict[str, int] = {}

        def _repl(m: Any) -> str:
            key = m.group().lower()
            counts[key] = counts.get(key, 0) + 1
            # Control 7: asterisk replacement, same length as the matched word.
            return "*" * len(m.group())

        try:
            new_text = self._rx.sub(_repl, text, timeout=_REDOS_TIMEOUT)
        except TimeoutError:
            # Control 6: timeout fires — skip this text node gracefully,
            # exactly as the PowerShell original does on RegexMatchTimeoutException.
            # The regex package (2026+) raises the built-in TimeoutError, not
            # a regex-namespaced variant.
            return text, {}

        return new_text, counts


def _repack_epub(work_dir: Path, out_path: Path) -> None:
    """Repack work_dir as a spec-compliant EPUB ZIP.

    Control 9: mimetype written first, uncompressed (ZIP_STORED).
    Control 2: files resolving outside work_dir (symlinks) are skipped.
    """
    mimetype_path = work_dir / "mimetype"
    if not mimetype_path.exists():
        raise ValueError("EPUB is missing required 'mimetype' file.")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        out_path.unlink()

    work_root = str(work_dir.resolve()) + os.sep

    with zipfile.ZipFile(out_path, "w") as zf:
        # Control 9: mimetype first, stored (uncompressed) per EPUB spec.
        zf.write(mimetype_path, "mimetype", compress_type=zipfile.ZIP_STORED)

        for file in sorted(work_dir.rglob("*")):
            if not file.is_file() or file == mimetype_path:
                continue
            # Control 2: skip anything resolving outside work_dir (symlinks).
            if not str(file.resolve()).startswith(work_root):
                continue
            arc_name = file.relative_to(work_dir).as_posix()
            zf.write(file, arc_name, compress_type=zipfile.ZIP_DEFLATED)
