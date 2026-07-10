"""`AIProvider` abstract base -- Strategy pattern (docs/design/PATTERNS.md
§1). Ported verbatim from epub-renamer/ai_providers/base.py (ADR-0003,
ADR-0014); the interface itself needed no adaptation for this project.
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from typing import Any, Dict

_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


class AIProvider(ABC):
    """Abstract base class for AI providers used to identify book metadata.

    All concrete providers must implement :meth:`identify_book` with this
    exact signature so they are interchangeable inside the pipeline
    (selected at runtime via settings.json's `ai_provider` field, see
    pipeline/ai_providers/registry.py).
    """

    def __init__(self, api_key: str = "") -> None:
        """Base constructor accepting an optional api_key so
        `registry.get_provider()` can construct any registered provider
        uniformly via ``cls(api_key=api_key)`` -- concrete providers that
        need a key (OpenAIProvider, GeminiProvider) override this and
        require one; NullProvider ignores it entirely.
        """
        self.api_key = api_key

    @abstractmethod
    def identify_book(
        self,
        filename: str,
        metadata: Dict[str, Any],
        text_sample: str,
    ) -> Dict[str, Any]:
        """Return enriched metadata inferred from the supplied inputs.

        Args:
            filename:    The original filename of the EPUB (useful for
                         inferring series / series number from messy names).
            metadata:    DC metadata extracted directly from the EPUB file.
            text_sample: A truncated plain-text sample of the book content.

        Returns:
            A dict with exactly these keys (values may be ``None``):

            .. code-block:: python

                {
                    "title":         str | None,
                    "author_first":  str | None,
                    "author_last":   str | None,
                    "series":        str | None,
                    "series_number": int | str | None,
                }
        """
        raise NotImplementedError


def parse_json_object(content: str | None) -> Dict[str, Any]:
    """Extract and parse the first JSON object from LLM output.

    Shared between OpenAIProvider and GeminiProvider (both models
    sometimes wrap their JSON reply in prose or ```json fences) -- one
    tested implementation of "be lenient about how the model formatted its
    JSON" rather than each provider reimplementing the same fallback
    parsing. Ported from epub-renamer's OpenAIProvider._safe_parse_json,
    lifted here so GeminiProvider (new, ADR-0003) can reuse it too.
    """
    if not content:
        return {}

    try:
        return dict(json.loads(content))
    except Exception:
        pass

    match = _JSON_OBJECT_RE.search(content)
    if match:
        try:
            return dict(json.loads(match.group(0)))
        except Exception:
            pass

    return {}
