"""EPUB metadata/text extraction -- ported verbatim from epub-renamer/
epub_reader.py (ADR-0014). Used by the rename stage to build the inputs
an AI provider enriches (docs/requirements/02-pipeline-stages.md §Stage 1).

`extract_cover_bytes()` (Epic 4) is ported verbatim from
epub-to-audio\\epub_utils.py (ADR-0014) instead -- landed here rather than
pipeline/epub_utils.py since it operates on the same already-opened
ebooklib `Book` object as the metadata extraction above, not on chunked
chapter text.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import ebooklib
from bs4 import BeautifulSoup
from ebooklib import ITEM_DOCUMENT, epub

TEXT_SAMPLE_LENGTH = 5000


def extract_epub_metadata(path: str | Path) -> Dict[str, Any]:
    """Extract basic metadata from an EPUB file."""
    book = epub.read_epub(str(path))

    title = book.get_metadata("DC", "title")
    author = book.get_metadata("DC", "creator")
    identifier = book.get_metadata("DC", "identifier")

    return {
        "title": title[0][0] if title else None,
        "author": author[0][0] if author else None,
        "identifier": identifier[0][0] if identifier else None,
    }


def extract_text_sample(path: str | Path, max_length: int = TEXT_SAMPLE_LENGTH) -> str:
    """Extract a text sample from the EPUB content."""
    book = epub.read_epub(str(path))
    text_chunks: list[str] = []
    total_len = 0

    for item in book.get_items():
        if item.get_type() == ITEM_DOCUMENT:
            soup = BeautifulSoup(item.get_body_content(), "html.parser")
            chunk = soup.get_text()
            if not chunk:
                continue

            remaining = max_length - total_len
            if remaining <= 0:
                break

            text_chunks.append(chunk[:remaining])
            total_len += len(chunk[:remaining])

            if total_len >= max_length:
                break

    return "".join(text_chunks)


def extract_cover_bytes(path: str | Path) -> bytes | None:
    """Return raw image bytes for the cover art embedded in the EPUB at
    *path*, or None if no cover image is found.

    Tries three strategies in order:
      1. Any ITEM_IMAGE whose filename contains 'cover'.
      2. The item referenced by the OPF <meta name="cover"> tag.
      3. The first <img src="..."> found inside any cover.xhtml document.
    """
    book = epub.read_epub(str(path))

    for item in book.get_items_of_type(ebooklib.ITEM_IMAGE):
        if "cover" in item.get_name().lower():
            return item.get_content()  # type: ignore[no-any-return]

    cover_meta = book.get_metadata("OPF", "cover")
    if cover_meta:
        cover_id = cover_meta[0][1].get("content", "")
        try:
            item = book.get_item_with_id(cover_id)
            if item:
                return item.get_content()  # type: ignore[no-any-return]
        except Exception:
            pass

    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        if "cover" in item.get_name().lower():
            soup = BeautifulSoup(item.get_content(), "html.parser")
            img = soup.find("img")
            if img and img.get("src"):
                img_name = str(img["src"]).lstrip("./")
                for img_item in book.get_items_of_type(ebooklib.ITEM_IMAGE):
                    if img_item.get_name().endswith(img_name):
                        return img_item.get_content()  # type: ignore[no-any-return]

    return None
