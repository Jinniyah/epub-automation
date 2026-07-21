"""Shared filesystem-safe naming utility (ADR-0016), plus (Epic 4)
chapter extraction and text chunking ported verbatim from
`epub-to-audio\\epub_utils.py` (ADR-0014) -- see
docs/requirements/02-pipeline-stages.md §Stage 3 and
docs/requirements/04-tts-engine.md §What stays exactly the same.

`sanitize_filesystem_name()` is new code -- none of the three source repos
needed to solve this (they're developer-run CLI tools operating on
filenames the developer already controls, not a pipeline taking arbitrary
real-world book metadata from a non-technical persona). Used by the rename
stage (Epic 3), the audio stage (Epic 4), and the retag stage (Epic 5)
everywhere Title/Author/Series text becomes part of a filename or folder
name.
"""

from __future__ import annotations

import re

import ebooklib
from bs4 import BeautifulSoup
from bs4.element import NavigableString, Tag
from ebooklib import epub

MAX_COMPONENT_LENGTH = 100

# ---------------------------------------------------------------------------
# Chapter extraction / chunking tunables -- ported verbatim from
# epub-to-audio\epub_utils.py (ADR-0014).
# ---------------------------------------------------------------------------

# Max characters fed to the TTS engine per request. Tuned originally for
# what Perchance's API would accept, not for Kokoro specifically -- carried
# over unchanged for now (04-tts-engine.md §Open item for review), flagged
# for re-validation once real Kokoro output exists to compare against.
MAX_CHUNK_CHARS = 4_000

# Headingless documents at or below this length are labelled "Dedication"
# (covers dedications, epigraphs, etc. that have no <h1>/<h2>/<h3>).
DEDICATION_MAX_CHARS = 300

# Filename fragments that identify front/back-matter documents to skip entirely.
SKIP_FILENAMES = ("nav", "toc", "ncx", "copyright", "cover")

# Headings that signal the end of the main narrative. Processing stops
# AFTER the chapter whose normalised heading contains one of these
# substrings (case-insensitive). The matching chapter IS included.
DEFAULT_STOP_AFTER = [
    "author's note",
    "acknowledgment",
    "acknowledgement",
    "about the author",
    "also by",
    "excerpt",
    "preview",
]

_RESERVED_CHARS_RE = re.compile(r'[<>:"/\\|?*]')
_WHITESPACE_RE = re.compile(r"\s+")
_RESERVED_DEVICE_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)
_RESERVED_NAME_SUFFIX = "_"


def sanitize_filesystem_name(name: str, max_length: int = MAX_COMPONENT_LENGTH) -> str:
    """Make *name* safe to use as one component of a Windows filename or
    folder name.

    Deterministic and idempotent:
    ``sanitize_filesystem_name(sanitize_filesystem_name(x)) ==
    sanitize_filesystem_name(x)`` for any *x* -- this matters because
    `FILENAME_PATTERN` (pipeline/rename_stage.py)'s already-normalized
    check must keep recognizing a name this function already sanitized on
    a prior run.

    1. Replace each Windows-reserved character (``< > : " / \\ | ? *``)
       with a single space, then collapse repeated whitespace.
    2. Strip trailing dots and spaces (Windows silently disallows both;
       leading whitespace is left alone -- only trailing is illegal).
    3. If the name (case-insensitive, ignoring extension) matches a
       reserved device name (CON, PRN, AUX, NUL, COM1-9, LPT1-9), append
       a safe suffix rather than leaving it as-is.
    4. Truncate to a conservative max length (defense-in-depth for long
       paths, independent of whether long-path support is enabled on a
       given machine -- see ADR-0016 §Long-path handling), then re-strip
       any trailing dot/space truncation may have exposed.
    """
    sanitized = _RESERVED_CHARS_RE.sub(" ", name)
    sanitized = _WHITESPACE_RE.sub(" ", sanitized)
    sanitized = sanitized.rstrip(" .")

    stem = sanitized.rsplit(".", 1)[0] if "." in sanitized else sanitized
    if stem.upper() in _RESERVED_DEVICE_NAMES:
        sanitized = sanitized + _RESERVED_NAME_SUFFIX

    sanitized = sanitized[:max_length]
    sanitized = sanitized.rstrip(" .")
    return sanitized


# ---------------------------------------------------------------------------
# Best-effort metadata guesses -- fallback sources for the rename stage's
# AI-enrichment merge (docs/BACKLOG.md Epic 8.5 "AI-enrichment sanity
# check / per-field merge"), and for `NullProvider` when no AI is
# configured at all. Real, already-available signals (the EPUB's own
# DC:creator field, and a filename that already starts "Lastname,
# Firstname") were previously being discarded whenever an AI response (or
# the no-AI NullProvider path) didn't independently reproduce them -- a
# real bug, not a design choice: 03-gui-ux-design.md's own AI Helper Setup
# copy promises "Fix messy file names... still works using EPUB's own
# built-in info" when AI is skipped, which wasn't actually true for the
# author field before this.
# ---------------------------------------------------------------------------

# A filename that already starts "Lastname, Firstname" ahead of a dash --
# covers the very common real-world case of a filename that's already
# mostly right (e.g. "Sanderson, Brandon - Elantris.epub") even when it
# doesn't exactly match this project's own normalized shape
# (`rename_stage.FILENAME_PATTERN`), for example because it uses a plain
# hyphen instead of an em dash.
_FILENAME_AUTHOR_RE = re.compile(r"^([^,]+),\s*([^—\-]+?)\s*[—\-]")

# A "— Series #NN —" segment anywhere in the filename, independent of
# whether the filename as a whole matches the normalized shape.
_FILENAME_SERIES_RE = re.compile(
    r"[—\-]\s*(?P<series>.+?)\s*#(?P<number>\d{1,3})\s*[—\-]", re.IGNORECASE
)


def parse_author_name(raw: str | None) -> tuple[str | None, str | None]:
    """Best-effort split of a single combined author string -- typically
    an EPUB's own DC:creator field (e.g. "Brandon Sanderson") -- into
    ``(first, last)``. Handles both "First Last" and "Last, First" shapes.

    Returns ``(None, None)`` for anything blank -- a wrong guess is worse
    than no guess here, since Screen 1's Confirm step is always the real
    backstop (03-gui-ux-design.md §Per-book identification loop), and
    `build_filename()` already has its own "Unknown" fallback for a
    genuinely missing author.
    """
    if not raw or not raw.strip():
        return None, None
    text = raw.strip()
    if "," in text:
        last, _, first = text.partition(",")
        last = last.strip()
        first = first.strip()
        return (first or None), (last or None)
    parts = text.split()
    if len(parts) == 1:
        return None, parts[0]
    return " ".join(parts[:-1]), parts[-1]


def guess_author_from_filename(filename: str) -> tuple[str | None, str | None]:
    """Best-effort ``(first, last)`` author guess from a filename that
    already starts "Lastname, Firstname" ahead of a dash. Returns
    ``(None, None)`` if the filename doesn't start with that shape."""
    match = _FILENAME_AUTHOR_RE.match(filename)
    if not match:
        return None, None
    last = match.group(1).strip()
    first = match.group(2).strip()
    return (first or None), (last or None)


def guess_series_from_filename(filename: str) -> tuple[str | None, int | None]:
    """Best-effort ``(series, series_number)`` guess from a filename that
    already contains a "— Series #NN —" segment. Returns ``(None, None)``
    if no such segment is present."""
    match = _FILENAME_SERIES_RE.search(filename)
    if not match:
        return None, None
    series = match.group("series").strip()
    try:
        number = int(match.group("number"))
    except ValueError:
        return (series or None), None
    return (series or None), number


# ---------------------------------------------------------------------------
# Heading normalisation -- ported verbatim from epub-to-audio\epub_utils.py.
# ---------------------------------------------------------------------------


def normalise_heading(raw: str) -> str:
    """Normalise an EPUB heading string for display and ID3 tagging.

    Examples
    --------
    'CHAPTER1'      -> 'Chapter 1'
    'CHAPTER 1'     -> 'Chapter 1'
    'chapter10'     -> 'Chapter 10'
    "AUTHOR'S NOTE" -> "Author's Note"   (letter after apostrophe NOT uppercased)
    'Prologue'      -> 'Prologue'

    Uses word-by-word capitalisation rather than str.title() to avoid the
    well-known Python behaviour where title() uppercases every letter that
    follows a non-alphanumeric character, including apostrophes
    (e.g. "it's" -> "It'S").
    """
    # Insert a space between a letter run and an immediately following digit
    spaced = re.sub(r"([A-Za-z])(\d)", r"\1 \2", raw.strip())

    def _cap_word(word: str) -> str:
        # Split on apostrophe; capitalise only the part before it
        parts = word.split("'")
        parts[0] = parts[0].capitalize()
        return "'".join(parts)

    return " ".join(_cap_word(w) for w in spaced.split())


# ---------------------------------------------------------------------------
# Chapter title detection -- broadened 2026-07-20 (ADR-0019) beyond the
# original epub-to-audio behavior (a single "first <h1>-<h3>" lookup),
# after real books in the user's own library showed two distinct failure
# modes the original heuristic missed entirely: a heading split across
# multiple tags (Wheel of Time: "<h3>Chapter 1</h3>" then a separately
# nested "<h4>Waiting</h4>"), and a title with no heading tag at all
# (The Risen Empire: chapter names are plain bold-styled <p> tags, e.g.
# "Pilot"/"Senator"). Both fixes are deliberately best-effort, same "a
# wrong guess is worse than no guess" philosophy as
# guess_author_from_filename()/guess_series_from_filename() above -- see
# ADR-0019 for the real examples and why a universal solution isn't
# attempted ("not all books are the same").
# ---------------------------------------------------------------------------

_HEADING_TAG_RE = re.compile(r"^h[1-6]$")
# Chars of non-heading text allowed before a subsequent heading no longer
# counts as part of the same title cluster (e.g. a "Chapter N" heading
# immediately followed by a separately-tagged named title, with nothing
# but a stray image/whitespace paragraph between them).
_HEADING_CLUSTER_TEXT_BUDGET = 100

_TITLE_LIKE_MAX_CHARS = 60
_SENTENCE_END_RE = re.compile(r"[.!?]$")
# The de-facto-title fallback only fires when there's clearly substantial
# narrative content left after the candidate title -- guards against
# mistaking a short document's own content for a "title" sitting in front
# of it.
_DE_FACTO_TITLE_MIN_REMAINING_CHARS = 500


def _extract_heading_title(soup: BeautifulSoup) -> str:
    """Collect heading tags (h1-h6, not just h1-h3) that appear before
    real narrative text starts, in document order, and join them --
    covers documents that split a chapter's heading across multiple tags
    (real example: Wheel of Time EPUBs, "<h3>Chapter 1</h3>" then
    "<em><h4>Waiting</h4></em>"). A document with a single heading
    behaves exactly as before (one heading in, one heading out).

    Walks `.descendants` (every Tag *and* NavigableString leaf, in
    document order) rather than `.find_all(True)` -- a `Tag`'s own
    `get_text()` aggregates its *entire* subtree, so summing it across
    every tag in a document (including outer wrappers like `<html>`/
    `<body>`) would blow the budget on the very first container tag,
    before ever reaching a real heading. Only `NavigableString` leaves
    contribute to the budget, each real character counted exactly once
    regardless of nesting depth; text belonging to a heading itself is
    excluded from the budget (already captured via the heading branch).
    """
    titles: list[str] = []
    text_seen = 0
    body = soup.body or soup
    for node in body.descendants:
        if isinstance(node, Tag):
            if _HEADING_TAG_RE.match(node.name or ""):
                heading_text = node.get_text(strip=True)
                if heading_text:
                    titles.append(heading_text)
            continue
        if not isinstance(node, NavigableString):
            continue
        if node.find_parent(_HEADING_TAG_RE) is not None:
            continue  # part of a heading's own text -- already counted
        if text_seen > _HEADING_CLUSTER_TEXT_BUDGET:
            break
        text_seen += len(str(node).strip())
    return " — ".join(titles)


def _find_de_facto_title(soup: BeautifulSoup) -> str:
    """Fallback for documents with zero heading tags: if the first
    text-bearing paragraph is short, has no terminal sentence
    punctuation, and is followed by substantially longer prose, treat it
    as a de facto chapter title (real example: The Risen Empire's
    "Pilot"/"Senator", styled bold via a CSS class, never a real <hN>
    tag). Only ever consulted by extract_chapters() when
    _extract_heading_title() found nothing -- never overrides a real
    heading."""
    first_el = soup.find(lambda t: t.name == "p" and t.get_text(strip=True))
    if first_el is None:
        return ""
    candidate = first_el.get_text(strip=True)
    if not candidate or len(candidate) > _TITLE_LIKE_MAX_CHARS:
        return ""
    if _SENTENCE_END_RE.search(candidate):
        return ""
    remaining_text = soup.get_text()
    if len(remaining_text) - len(candidate) < _DE_FACTO_TITLE_MIN_REMAINING_CHARS:
        return ""
    return candidate


# ---------------------------------------------------------------------------
# Chapter extraction -- ported verbatim from epub-to-audio\epub_utils.py.
# ---------------------------------------------------------------------------


def extract_chapters(
    epub_path: str,
    stop_after: list[str] | None = None,
) -> tuple[list[dict[str, str]], list[str], str | None]:
    """Extract readable chapters from an EPUB in spine order.

    Parameters
    ----------
    epub_path  : Path to the .epub file.
    stop_after : List of lowercase substrings. Processing stops AFTER the
                 first chapter whose normalised heading contains any of them.
                 Defaults to DEFAULT_STOP_AFTER.

    Returns
    -------
    chapters   : list of {"title": str, "text": str}
    skipped    : list of human-readable skip reason strings (for diagnostics)
    stopped_at : heading string that triggered the stop, or None
    """
    if stop_after is None:
        stop_after = DEFAULT_STOP_AFTER

    book = epub.read_epub(str(epub_path))
    spine_ids = [item_id for item_id, _ in book.spine]

    chapters: list[dict[str, str]] = []
    skipped: list[str] = []
    stopped_at: str | None = None

    for item_id in spine_ids:
        item = book.get_item_with_id(item_id)
        if item is None or item.get_type() != ebooklib.ITEM_DOCUMENT:
            continue

        name = item.get_name().lower()
        if any(frag in name for frag in SKIP_FILENAMES):
            skipped.append(name)
            continue

        soup = BeautifulSoup(item.get_content(), "html.parser")
        heading_title = _extract_heading_title(soup)
        ch_title = normalise_heading(heading_title) if heading_title else ""

        text = soup.get_text(separator="\n")
        text = re.sub(r"\n\s*\n+", "\n\n", text).strip()

        if len(text) < 50:
            skipped.append(f"{name} (too short: {len(text)} chars)")
            continue

        # Headingless short documents are dedications / epigraphs
        if not ch_title and len(text) <= DEDICATION_MAX_CHARS:
            ch_title = "Dedication"
        elif not ch_title:
            de_facto = _find_de_facto_title(soup)
            ch_title = normalise_heading(de_facto) if de_facto else ""

        chapters.append({"title": ch_title, "text": text})

        # Stop AFTER including this chapter if its heading hits a stop marker
        if ch_title and any(marker in ch_title.lower() for marker in stop_after):
            stopped_at = ch_title
            break

    return chapters, skipped, stopped_at


# ---------------------------------------------------------------------------
# Text chunking -- ported verbatim from epub-to-audio\epub_utils.py.
# ---------------------------------------------------------------------------


def chunk_text(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    """Split *text* into chunks of at most *max_chars* characters.

    Breaks preferentially on paragraph boundaries (double newline), falling
    back to sentence boundaries (after .  !  ?) when a single paragraph
    exceeds *max_chars*.
    """
    paragraphs = text.split("\n\n")
    chunks: list[str] = []
    current: str = ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        # Oversized paragraph -- split on sentence boundaries
        if len(para) > max_chars:
            for sentence in re.split(r"(?<=[.!?])\s+", para):
                if len(current) + len(sentence) + 2 > max_chars:
                    if current:
                        chunks.append(current.strip())
                    current = sentence
                else:
                    current = (current + " " + sentence).strip()
            continue

        if len(current) + len(para) + 2 > max_chars:
            if current:
                chunks.append(current.strip())
            current = para
        else:
            current = (current + "\n\n" + para).strip()

    if current:
        chunks.append(current.strip())

    return chunks


# ---------------------------------------------------------------------------
# Part grouping -- new 2026-07-20 (ADR-0020). One level up from
# chunk_text(): groups already-chunked text into larger "parts" so
# AudioStage can write one merged MP3 per ~15 minutes of audio instead of
# one file per ~4,000-char chunk. See ADR-0020 for why this is pure text
# math (never based on actual generated audio duration) and why parts
# must never span a chapter boundary (callers call this once per chapter).
# ---------------------------------------------------------------------------


def group_chunks_into_parts(chunks: list[str], max_part_chars: int) -> list[list[str]]:
    """Group already-chunked text strings (chunk_text()'s output) into
    larger "part" groups by cumulative character count -- same
    greedy-accumulate shape chunk_text() already uses one level up
    (paragraphs/sentences into chunks). Pure text function, computed
    before any TTS/audio work from already-known chapter text, so it is
    exactly reproducible on a resumed run (same input -> same grouping,
    every time) -- deliberately NOT based on actual generated audio
    duration, which risks a different boundary on resume if TTS output
    length isn't bit-for-bit deterministic (ADR-0020).

    Never splits a chunk -- a chunk is the atomic TTS-generation unit.
    A single chunk already exceeding max_part_chars becomes its own
    one-chunk part rather than being split or dropped.

    Callers must call this once per chapter -- parts must never span a
    chapter boundary.
    """
    parts: list[list[str]] = []
    current: list[str] = []
    current_len = 0
    for chunk in chunks:
        if current and current_len + len(chunk) > max_part_chars:
            parts.append(current)
            current = []
            current_len = 0
        current.append(chunk)
        current_len += len(chunk)
    if current:
        parts.append(current)
    return parts
