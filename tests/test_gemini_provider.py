"""Tests for GeminiProvider -- the one new AI provider added by this
project (ADR-0003, ADR-0014). Mirrors test_openai_provider.py since both
providers share the same prompt intent and JSON-parsing fallback; only
the vendor SDK call differs.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from pipeline.ai_providers.gemini_provider import GeminiProvider


def _make_provider(mock_genai: MagicMock, response_text: str) -> GeminiProvider:
    mock_client = MagicMock()
    mock_genai.Client.return_value = mock_client

    mock_response = MagicMock()
    mock_response.text = response_text
    mock_client.models.generate_content.return_value = mock_response

    return GeminiProvider(api_key="test-key")


@patch("pipeline.ai_providers.gemini_provider.genai")
def test_parses_clean_json(mock_genai: MagicMock) -> None:
    provider = _make_provider(
        mock_genai,
        '{"title": "Trace", "author_first": "Patricia", "author_last": "Cornwell", '
        '"series": "Kay Scarpetta", "series_number": 13}',
    )
    result = provider.identify_book("Trace.epub", {}, "sample text")

    assert result["title"] == "Trace"
    assert result["author_last"] == "Cornwell"
    assert result["series_number"] == 13


@patch("pipeline.ai_providers.gemini_provider.genai")
def test_parses_json_wrapped_in_markdown(mock_genai: MagicMock) -> None:
    provider = _make_provider(
        mock_genai,
        '```json\n{"title": "T", "author_first": null, "author_last": null, '
        '"series": null, "series_number": null}\n```',
    )
    result = provider.identify_book("T.epub", {}, "")
    assert result["title"] == "T"


@patch("pipeline.ai_providers.gemini_provider.genai")
def test_all_keys_present_on_partial_response(mock_genai: MagicMock) -> None:
    provider = _make_provider(mock_genai, '{"title": "Only Title"}')
    result = provider.identify_book("book.epub", {}, "")

    for key in ["title", "author_first", "author_last", "series", "series_number"]:
        assert key in result


@patch("pipeline.ai_providers.gemini_provider.genai")
def test_returns_none_defaults_on_garbage_response(mock_genai: MagicMock) -> None:
    provider = _make_provider(mock_genai, "Sorry, I cannot help with that.")
    result = provider.identify_book("book.epub", {}, "")
    assert result.get("title") is None


def test_raises_on_missing_api_key() -> None:
    with pytest.raises(ValueError, match="Gemini API key"):
        GeminiProvider(api_key="")
