"""Retag stage — ports epub-to-audio's retag.py to the Stage protocol
(docs/design/PATTERNS.md §1).

See docs/design/adr/0014-reuse-existing-implementations-by-default.md,
docs/design/adr/0016-windows-safe-filesystem-naming.md, and
docs/requirements/02-pipeline-stages.md §Stage 4.

Adapted from the original `retag.py`, for concrete, nameable reasons
(ADR-0014):
  - **New behavior, not in the original script:** also renames the
    containing output folder to match corrected metadata, not just the
    MP3 files inside it -- the original leaves the folder name stale,
    which would cause a future retag run (without repeating the same
    overrides) to silently revert to the old values, since
    `parse_folder_metadata()` reads that same folder name to auto-detect
    metadata. Fixing this is the whole point of this epic
    (docs/BACKLOG.md Epic 5, `02-pipeline-stages.md` §Stage 4).
  - Filename/folder construction reuses `rename_stage.build_filename()`
    directly (same reason `audio_stage.py` already does this) instead of
    the original's own bespoke `build_new_filename()` -- one sanitized
    (ADR-0016), tested naming function for the whole pipeline rather than
    a second copy that could drift from it. Cross-checked against the
    original script's own docstring example ("Jacka, Benedict — Alex
    Verus #01 — Fated") -- `build_filename()`'s zero-padded `#NN` shape
    matches exactly.
  - Metadata is represented as `author_first`/`author_last` (this
    pipeline's shape, produced by `RenameStage`/AI providers and reused by
    `AudioStage`), not the original's single opaque `author` string. The
    original never actually reasons about first/last order itself --
    `parse_filename_metadata()` stores whatever text sits before/after the
    separator verbatim, and any real first/last correction only ever
    happened via a human retyping the field in the interactive prompt.
    Splitting on the first comma reproduces that same structural handling
    for both the current pipeline's own folder shape (`Last, First — ...`,
    unambiguous since this pipeline is the one writing it) and legacy
    folders from the original standalone tool (order is whatever it was,
    exactly as before -- not a fix, just not a regression either).
  - The original's interactive `confirm_metadata()` CLI prompt has no
    place in a pipeline `Stage` -- corrections instead arrive as
    already-resolved `book.data` fields, exactly like the GUI's shared
    Field Correction Popup already supplies them to `RenameStage`
    upstream (`03-gui-ux-design.md` §"No, let me fix it" flow).
  - **Override precedence, adapted:** the original always parses the
    folder name first, then layers explicit CLI flags on top. Here,
    `book.data`'s existing title/author/series fields (set by
    `RenameStage`/`AudioStage` earlier in the same batch, or corrected via
    "No, let me fix it") are tried *first* -- they're ground truth when
    available -- falling back to folder-name parsing only when a field is
    genuinely unset, which is the real-world case of retagging a folder
    with no associated `book.data` at all ("manually later, any time, on
    any folder in `03-Audio/`," `02-pipeline-stages.md` §Stage 4).
  - **Missing-metadata handling, deliberately NOT matching
    `RenameStage`/`AudioStage`'s "Unknown, Unknown — Unknown" fallback:**
    unlike those stages (which are naming a brand-new file/folder, where
    "Unknown" is merely unhelpful), retag operates on an *already*
    correctly-named folder -- silently renaming it to "Unknown, Unknown —
    Unknown" on a parse failure would be actively destructive, not just
    unhelpful. This keeps the original script's own fail-closed behavior
    (error out, ask for explicit correction) rather than reusing the
    sibling stages' graceful-degradation convention.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mutagen.id3 import ID3, TALB, TIT2, TPE1, ID3NoHeaderError

from pipeline.audit_logger import AuditLogRepository
from pipeline.rename_stage import build_filename
from pipeline.stage import BookState

_OVERRIDE_KEYS = ("author_first", "author_last", "title", "series", "series_number")

# ---------------------------------------------------------------------------
# Folder-name parsing -- ported from epub-to-audio/retag.py's
# parse_folder_metadata() / epub_utils.py's parse_filename_metadata()
# (ADR-0014).
# ---------------------------------------------------------------------------

_NUM_PATTERN = re.compile(r"(?:#\s*(\d+)|[Bb]ook\s*(\d+))\s*$")
_BARE_TRAILING_NUM = re.compile(r"^(.*?)\s+(\d+)$")


def _parse_series_number(series_raw: str) -> tuple[str, str | None]:
    """Extract a series number from the raw series string.

    Priority: explicit marker ("Alex Verus #12" / "Alex Verus Book 12"),
    then a bare trailing number ("Alex Verus 12") as a best-effort guess.
    """
    m = _NUM_PATTERN.search(series_raw)
    if m:
        number = m.group(1) or m.group(2)
        clean = series_raw[: m.start()].strip()
        return clean, number

    m2 = _BARE_TRAILING_NUM.match(series_raw.strip())
    if m2:
        return m2.group(1).strip(), m2.group(2)

    return series_raw.strip(), None


def _split_author(raw: str) -> tuple[str, str]:
    """Split a folder-name author segment into (last, first).

    Splits on the first comma if present (this pipeline's own folders are
    always `Last, First`, written by `build_filename()`); a legacy folder
    from the original standalone tool carries forward whatever order it
    already had -- see module docstring.
    """
    if "," in raw:
        last, _, first = raw.partition(",")
        return last.strip(), first.strip()
    parts = raw.split()
    if len(parts) >= 2:
        return parts[-1], " ".join(parts[:-1])
    return raw.strip(), ""


def parse_stem_metadata(stem: str) -> dict[str, Any] | None:
    """Parse author_last/author_first/title/series/series_number from a
    folder-name stem shaped like `build_filename()`'s output (minus
    `.epub`): ``Last, First — Title`` or
    ``Last, First — Series #NN — Title``.
    """
    stem = re.sub(r"^[A-Za-z]+\d+\s*[—–-]\s*", "", stem).strip()
    stem = re.sub(r"(?:_[a-zA-Z0-9]+)+$", "", stem).strip()

    parts = [p.strip() for p in re.split(r"\s*[—–]\s*|\s+-\s+", stem) if p.strip()]

    if len(parts) == 2:
        author_raw, title = parts
        last, first = _split_author(author_raw)
        return {
            "author_last": last,
            "author_first": first,
            "title": title,
            "series": None,
            "series_number": None,
        }

    if len(parts) == 3:
        author_raw, series_raw, title = parts
        last, first = _split_author(author_raw)
        series_clean, series_number = _parse_series_number(series_raw)
        return {
            "author_last": last,
            "author_first": first,
            "title": title,
            "series": series_clean or None,
            "series_number": series_number,
        }

    return None


def parse_folder_metadata(folder_name: str) -> dict[str, Any] | None:
    """Parse author/title/series/series_number from an audiobook output
    folder name.

    Handles both this pipeline's own `build_filename()` shape and the
    older standalone-tool shape (optional leading code like ``AV01 - ``,
    series described parenthetically in the title, e.g.
    ``Fated (Alex Verus Book 1)``), ported from `epub-to-audio/retag.py`'s
    `parse_folder_metadata()` (ADR-0014).
    """
    name = re.sub(r"^[A-Za-z]+\d+\s*[—–-]\s*", "", folder_name).strip()

    paren_match = re.search(
        r"^(.*?)\s*\((?:An?\s+)?(.+?)\s+(?:Book|Novel)\s*(\d+)?\s*\)$",
        name,
        re.IGNORECASE,
    )
    if paren_match:
        before_paren = paren_match.group(1).strip()
        series_name = paren_match.group(2).strip()
        series_num = paren_match.group(3)

        parts = re.split(r"\s*[—–]\s*|\s+-\s+", before_paren, maxsplit=1)
        if len(parts) == 2:
            author_raw, title = parts[0].strip(), parts[1].strip()
            num_str = f" #{series_num}" if series_num else ""
            synthetic = f"{author_raw} — {series_name}{num_str} — {title}"
            return parse_stem_metadata(synthetic)

    return parse_stem_metadata(name)


# ---------------------------------------------------------------------------
# MP3 filename suffix -> chapter title / track number -- ported verbatim
# (structurally) from epub-to-audio/retag.py.
# ---------------------------------------------------------------------------

_SUFFIX_RE = re.compile(r"-\s*(\d+)(?:_(\d+))?$")
_TRACK_NUM_RE = re.compile(r"^(\d+)\s+")


def chapter_title_from_stem(stem: str) -> str:
    """Derive a human-readable chapter title from an MP3 filename stem.

    "... - 013_10" -> "Chapter 13, Part 10"; "... - 003" -> "Chapter 3".
    """
    m = _SUFFIX_RE.search(stem)
    if not m:
        return "Chapter ?"
    chapter = int(m.group(1))
    part = int(m.group(2)) if m.group(2) else None
    if part is not None:
        return f"Chapter {chapter}, Part {part}"
    return f"Chapter {chapter}"


def track_number_from_tag(title_text: str) -> str | None:
    """Extract the zero-padded track number string from an existing Title
    tag, e.g. "100 Fated (Alex Verus #01) — Chapter 100" -> "100"."""
    m = _TRACK_NUM_RE.match(title_text.strip())
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# Tag builders -- ID3 tag values are raw Unicode text, not sanitized
# (only filenames/folder names go through sanitize_filesystem_name(),
# same rule audio_stage.py's _apply_tags() already follows).
# ---------------------------------------------------------------------------


def build_album_tag(title: str, series: str | None, series_number: Any) -> str:
    """Build the Album tag: ``Title (Series #NN)``."""
    if series and series_number:
        try:
            num = f"{int(series_number):02}"
        except (ValueError, TypeError):
            num = series_number
        return f"{title} ({series} #{num})"
    if series:
        return f"{title} ({series})"
    return title


def build_title_tag(
    track_str: str,
    title: str,
    series: str | None,
    series_number: Any,
    chapter_title: str,
) -> str:
    """Build the Title tag: ``NNN Title (Series #NN) — ChapterTitle``."""
    return (
        f"{track_str} {build_album_tag(title, series, series_number)} — {chapter_title}"
    )


def _new_mp3_stem(meta: dict[str, Any], old_stem: str) -> str:
    """New MP3 filename stem, preserving the trailing track/chunk suffix."""
    suffix_match = _SUFFIX_RE.search(old_stem)
    if suffix_match:
        raw = suffix_match.group(0).strip()
        suffix = " - " + raw.lstrip("- ").strip()
    else:
        suffix = ""
    base = build_filename(meta).removesuffix(".epub")
    return base + suffix


class RetagStage:
    """Stage 4: retag -- fix ID3 tags/filenames/folder name for an
    already-generated audiobook folder. Always manually triggered
    (`02-pipeline-stages.md` §Stage 4), never part of the automatic
    rename -> sanitize -> audio sequence.
    """

    name = "retag"

    def __init__(self, audit_log: AuditLogRepository, *, dry_run: bool = False) -> None:
        self._audit_log = audit_log
        self._dry_run = dry_run

    def applies_to(self, book: BookState, settings: dict[str, Any]) -> bool:
        # Never auto-run -- see class docstring / 02-pipeline-stages.md
        # §Stage 4. No settings toggle turns this stage on; it's only ever
        # invoked directly (her "Does it look right?" answer, or manually
        # later on any folder in 03-Audio/).
        return False

    def run(self, book: BookState) -> BookState:
        folder_str = book.data.get("audio_folder")
        if not folder_str:
            return BookState(
                book.book_id,
                "error",
                {**book.data, "error": "No audio_folder to retag."},
            )

        folder = Path(folder_str)
        if not folder.exists() or not folder.is_dir():
            return BookState(
                book.book_id,
                "error",
                {**book.data, "error": f"Audio folder not found: {folder}"},
            )

        parsed = parse_folder_metadata(folder.name) or {}
        meta: dict[str, Any] = dict(parsed)
        for key in _OVERRIDE_KEYS:
            override = book.data.get(key)
            if override:
                meta[key] = override

        if not meta.get("author_last") or not meta.get("title"):
            self._audit_log.append(
                self._audit_row(
                    folder.name,
                    "",
                    meta,
                    renamed="no",
                    skipped_reason="metadata_unresolved",
                )
            )
            return BookState(
                book.book_id,
                "error",
                {
                    **book.data,
                    "error": (
                        "Could not determine author and title for retag -- "
                        "supply author/title overrides."
                    ),
                },
            )

        mp3_files = sorted(folder.glob("*.mp3"))
        if not mp3_files:
            self._audit_log.append(
                self._audit_row(
                    folder.name, "", meta, renamed="no", skipped_reason="no_mp3_files"
                )
            )
            return BookState(
                book.book_id,
                "error",
                {**book.data, "error": f"No MP3 files found in: {folder}"},
            )

        processed = self._retag_files(mp3_files, meta)
        new_folder, folder_renamed = self._retag_folder_name(folder, meta)

        skipped_reason = "dry_run" if self._dry_run else ""
        renamed = "yes" if (folder_renamed or processed["files_renamed"]) else "no"
        self._audit_log.append(
            self._audit_row(
                folder.name,
                new_folder.name,
                meta,
                renamed=renamed,
                skipped_reason=skipped_reason,
            )
        )

        return BookState(
            book.book_id,
            "retagged",
            {
                **book.data,
                **meta,
                "audio_folder": str(new_folder),
                "retag_files_processed": processed["count"],
            },
        )

    def _retag_files(
        self, mp3_files: list[Path], meta: dict[str, Any]
    ) -> dict[str, int]:
        title = meta.get("title") or "Unknown"
        author_last = meta.get("author_last") or "Unknown"
        author_first = meta.get("author_first") or ""
        author = f"{author_last}, {author_first}" if author_first else author_last
        series = meta.get("series")
        series_number = meta.get("series_number")
        album = build_album_tag(title, series, series_number)

        count = 0
        files_renamed = 0
        for mp3_path in mp3_files:
            try:
                tags = ID3(str(mp3_path))
            except ID3NoHeaderError:
                tags = ID3()

            existing_title = tags.get("TIT2")
            title_text = existing_title.text[0] if existing_title else ""
            track_str = track_number_from_tag(title_text) or f"{count + 1:03}"

            chapter_title = chapter_title_from_stem(mp3_path.stem)
            new_title = build_title_tag(
                track_str, title, series, series_number, chapter_title
            )
            new_stem = _new_mp3_stem(meta, mp3_path.stem)
            new_path = mp3_path.parent / f"{new_stem}.mp3"

            if not self._dry_run:
                existing_apic = tags.get("APIC:")
                tags.delall("TIT2")
                tags.delall("TPE1")
                tags.delall("TALB")
                tags.add(TIT2(encoding=3, text=new_title))
                tags.add(TPE1(encoding=3, text=author))
                tags.add(TALB(encoding=3, text=album))
                if existing_apic:
                    tags.add(existing_apic)
                tags.save(str(mp3_path), v2_version=3)

                if mp3_path != new_path and not new_path.exists():
                    mp3_path.rename(new_path)
                    files_renamed += 1

            count += 1

        return {"count": count, "files_renamed": files_renamed}

    def _retag_folder_name(
        self, folder: Path, meta: dict[str, Any]
    ) -> tuple[Path, bool]:
        """Rename the containing folder to match corrected metadata.

        This is the fix over the original script (module docstring) --
        without it, a future retag run reading the (still-stale) folder
        name via `parse_folder_metadata()` would silently revert to the
        old values.
        """
        new_name = build_filename(meta).removesuffix(".epub")
        new_folder = folder.parent / new_name

        if new_folder == folder:
            return folder, False
        if self._dry_run or new_folder.exists():
            return folder, False

        folder.rename(new_folder)
        return new_folder, True

    def _audit_row(
        self,
        original_folder_name: str,
        new_folder_name: str,
        meta: dict[str, Any],
        *,
        renamed: str,
        skipped_reason: str,
    ) -> dict[str, Any]:
        author = " ".join(
            part for part in (meta.get("author_first"), meta.get("author_last")) if part
        )
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "stage": self.name,
            "original_filename": original_folder_name,
            "new_filename": new_folder_name,
            "title": meta.get("title") or "",
            "author": author,
            "series": meta.get("series") or "",
            "series_number": meta.get("series_number") or "",
            "renamed": renamed,
            "skipped_reason": skipped_reason,
        }
