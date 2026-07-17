"""Offline fallback provider -- ported verbatim from epub-renamer/
ai_providers/null_provider.py (ADR-0003, ADR-0014). Used whenever
`ai_provider` is `"none"` in settings.json, and as the silent per-file
fallback when a real provider's API call fails
(docs/requirements/02-pipeline-stages.md §Stage 1 Failure handling).
"""

from __future__ import annotations

from typing import Any, Dict

from pipeline.ai_providers.base import AIProvider
from pipeline.epub_utils import (
    guess_author_from_filename,
    guess_series_from_filename,
    parse_author_name,
)


class NullProvider(AIProvider):
    """Fallback provider used when no API key is available.

    Returns whatever metadata was already embedded in the EPUB or already
    present in the filename, without making any external calls -- offline
    use, testing, or a per-file fallback when a real provider fails.

    **Fixed (docs/BACKLOG.md Epic 8.5):** this used to return the title
    only, always `None` for author/series/series_number even when a
    filename like "Sanderson, Brandon - Elantris.epub" or the EPUB's own
    DC:creator field made the author obvious -- a real gap against
    03-gui-ux-design.md's own promise that skipping AI still works "using
    EPUB's own built-in info." Filename is checked first (a filename that
    already looks like "Lastname, Firstname" is usually more deliberately
    curated than DC:creator), falling back to the EPUB's own author field.
    """

    def identify_book(
        self,
        filename: str,
        metadata: Dict[str, Any],
        text_sample: str,
    ) -> Dict[str, Any]:
        author_first, author_last = guess_author_from_filename(filename)
        if author_first is None and author_last is None:
            author_first, author_last = parse_author_name(metadata.get("author"))
        series, series_number = guess_series_from_filename(filename)

        return {
            "title": metadata.get("title"),
            "author_first": author_first,
            "author_last": author_last,
            "series": series,
            "series_number": series_number,
        }
