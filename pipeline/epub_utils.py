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
        heading_el = soup.find(re.compile(r"^h[1-3]$"))
        raw_title = heading_el.get_text(strip=True) if heading_el else ""
        ch_title = normalise_heading(raw_title) if raw_title else ""

        text = soup.get_text(separator="\n")
        text = re.sub(r"\n\s*\n+", "\n\n", text).strip()

        if len(text) < 50:
            skipped.append(f"{name} (too short: {len(text)} chars)")
            continue

        # Headingless short documents are dedications / epigraphs
        if not ch_title and len(text) <= DEDICATION_MAX_CHARS:
            ch_title = "Dedication"

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
