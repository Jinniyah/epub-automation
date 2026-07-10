"""Offline fallback provider -- ported verbatim from epub-renamer/
ai_providers/null_provider.py (ADR-0003, ADR-0014). Used whenever
`ai_provider` is `"none"` in settings.json, and as the silent per-file
fallback when a real provider's API call fails
(docs/requirements/02-pipeline-stages.md §Stage 1 Failure handling).
"""

from __future__ import annotations

from typing import Any, Dict

from pipeline.ai_providers.base import AIProvider


class NullProvider(AIProvider):
    """Fallback provider used when no API key is available.

    Returns whatever metadata was already embedded in the EPUB without
    making any external calls -- offline use, testing, or a per-file
    fallback when a real provider fails.
    """

    def identify_book(
        self,
        filename: str,
        metadata: Dict[str, Any],
        text_sample: str,
    ) -> Dict[str, Any]:
        return {
            "title": metadata.get("title"),
            "author_first": None,
            "author_last": None,
            "series": None,
            "series_number": None,
        }
