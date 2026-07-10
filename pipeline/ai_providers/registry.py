"""Provider registry -- Registry pattern (docs/design/PATTERNS.md §1).
Ported from epub-renamer/ai_providers/registry.py (ADR-0003, ADR-0014).

To add a new provider:
1. Create ``pipeline/ai_providers/my_provider.py`` implementing ``AIProvider``.
2. Import it here and add an entry to ``PROVIDERS``.
3. Select ``ai_provider: "my_provider"`` in settings.json.

No changes to rename_stage.py or any other module are required.

Adapted from the original: provider keys match settings.json's
`ai_provider` values (ADR-0003, `"gemini"` / `"openai"` / `"none"`) rather
than the original's `"openai"` / `"null"` -- `"none"` is the settings-
schema term for "no provider selected"
(docs/requirements/05-data-settings-and-logging.md §Settings schema).
`get_provider` also now takes an explicit `api_key`, threaded through to
whichever provider needs it (NullProvider takes none).
"""

from __future__ import annotations

from typing import Type

from pipeline.ai_providers.base import AIProvider
from pipeline.ai_providers.gemini_provider import GeminiProvider
from pipeline.ai_providers.null_provider import NullProvider
from pipeline.ai_providers.openai_provider import OpenAIProvider

PROVIDERS: dict[str, Type[AIProvider]] = {
    "openai": OpenAIProvider,
    "gemini": GeminiProvider,
    "none": NullProvider,
}


def get_provider(name: str, api_key: str = "") -> AIProvider:
    """Instantiate and return the named provider.

    Raises ``ValueError`` with a helpful message listing valid choices if
    *name* is not registered, or if a keyed provider is selected without
    an `api_key`.
    """
    cls = PROVIDERS.get((name or "none").lower())
    if cls is None:
        valid = ", ".join(sorted(PROVIDERS))
        raise ValueError(f"Unknown AI provider: {name!r}. Valid choices: {valid}")
    if cls is NullProvider:
        return NullProvider()
    return cls(api_key=api_key)
