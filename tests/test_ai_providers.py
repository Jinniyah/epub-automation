"""Tests for the AIProvider base class, JSON-parsing helper, NullProvider,
and the provider registry. Ported from epub-renamer/tests/
test_ai_provider_base.py (ADR-0014), adjusted for this project's registry
keys (`"none"` instead of `"null"`) and the explicit `api_key` constructor
argument (ADR-0003).
"""

from __future__ import annotations

import pytest

from pipeline.ai_providers.base import AIProvider, parse_json_object
from pipeline.ai_providers.gemini_provider import GeminiProvider
from pipeline.ai_providers.null_provider import NullProvider
from pipeline.ai_providers.openai_provider import OpenAIProvider
from pipeline.ai_providers.registry import PROVIDERS, get_provider

# ---------------------------------------------------------------------------
# Abstract base class enforcement
# ---------------------------------------------------------------------------


def test_cannot_instantiate_abstract_provider() -> None:
    with pytest.raises(TypeError):
        AIProvider()  # type: ignore[abstract]


def test_concrete_subclass_must_implement_identify_book() -> None:
    class Incomplete(AIProvider):
        pass  # missing identify_book

    with pytest.raises(TypeError):
        Incomplete()  # type: ignore[abstract]


# ---------------------------------------------------------------------------
# parse_json_object -- shared lenient JSON extraction
# ---------------------------------------------------------------------------


def test_parse_json_object_parses_clean_json() -> None:
    assert parse_json_object('{"title": "T"}') == {"title": "T"}


def test_parse_json_object_extracts_from_markdown_fence() -> None:
    content = '```json\n{"title": "T"}\n```'
    assert parse_json_object(content) == {"title": "T"}


def test_parse_json_object_returns_empty_dict_on_garbage() -> None:
    assert parse_json_object("Sorry, I cannot help with that.") == {}


def test_parse_json_object_returns_empty_dict_on_none() -> None:
    assert parse_json_object(None) == {}


# ---------------------------------------------------------------------------
# NullProvider -- smoke test the interface
# ---------------------------------------------------------------------------


def test_null_provider_returns_all_keys() -> None:
    provider = NullProvider()
    result = provider.identify_book("book.epub", {"title": "T"}, "sample")

    for key in ["title", "author_first", "author_last", "series", "series_number"]:
        assert key in result


def test_null_provider_passes_through_title() -> None:
    provider = NullProvider()
    result = provider.identify_book("book.epub", {"title": "My Book"}, "")
    assert result["title"] == "My Book"


def test_null_provider_returns_none_for_missing_metadata() -> None:
    provider = NullProvider()
    result = provider.identify_book("book.epub", {}, "")
    assert result["title"] is None


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_registry_contains_expected_providers() -> None:
    assert "openai" in PROVIDERS
    assert "gemini" in PROVIDERS
    assert "none" in PROVIDERS


def test_get_provider_none_returns_null_provider() -> None:
    provider = get_provider("none")
    assert isinstance(provider, NullProvider)


def test_get_provider_is_case_insensitive() -> None:
    provider = get_provider("NONE")
    assert isinstance(provider, NullProvider)


def test_get_provider_raises_on_unknown_name() -> None:
    with pytest.raises(ValueError, match="Unknown AI provider"):
        get_provider("nonexistent_provider")


def test_get_provider_openai_requires_api_key() -> None:
    with pytest.raises(ValueError, match="OpenAI API key"):
        get_provider("openai", "")


def test_get_provider_openai_constructs_with_key() -> None:
    provider = get_provider("openai", "sk-test")
    assert isinstance(provider, OpenAIProvider)


def test_get_provider_gemini_requires_api_key() -> None:
    with pytest.raises(ValueError, match="Gemini API key"):
        get_provider("gemini", "")


def test_get_provider_gemini_constructs_with_key() -> None:
    provider = get_provider("gemini", "test-key")
    assert isinstance(provider, GeminiProvider)
