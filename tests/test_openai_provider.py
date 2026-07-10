"""Tests for OpenAIProvider -- JSON parsing, fallback, and response
handling. Ported from epub-renamer/tests/test_openai_provider.py
(ADR-0014), adjusted for the explicit `api_key` constructor argument
(ADR-0003) in place of the original's `.env`-backed `config.py` module.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from pipeline.ai_providers.openai_provider import OpenAIProvider


def _make_provider(mock_openai: MagicMock, response_content: str) -> OpenAIProvider:
    """Helper: set up a patched OpenAIProvider with a fixed response string."""
    mock_client = MagicMock()
    mock_openai.return_value = mock_client

    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content=response_content))]
    mock_client.chat.completions.create.return_value = mock_response

    return OpenAIProvider(api_key="test-key")


@patch("pipeline.ai_providers.openai_provider.OpenAI")
def test_parses_clean_json(mock_openai: MagicMock) -> None:
    provider = _make_provider(
        mock_openai,
        '{"title": "Trace", "author_first": "Patricia", "author_last": "Cornwell", '
        '"series": "Kay Scarpetta", "series_number": 13}',
    )
    result = provider.identify_book("Trace.epub", {}, "sample text")

    assert result["title"] == "Trace"
    assert result["author_last"] == "Cornwell"
    assert result["series_number"] == 13


@patch("pipeline.ai_providers.openai_provider.OpenAI")
def test_parses_json_wrapped_in_markdown(mock_openai: MagicMock) -> None:
    """Model sometimes wraps JSON in ```json fences -- parser must handle it."""
    provider = _make_provider(
        mock_openai,
        '```json\n{"title": "T", "author_first": null, "author_last": null, '
        '"series": null, "series_number": null}\n```',
    )
    result = provider.identify_book("T.epub", {}, "")
    assert result["title"] == "T"


@patch("pipeline.ai_providers.openai_provider.OpenAI")
def test_all_keys_present_on_partial_response(mock_openai: MagicMock) -> None:
    """Every required key must be present even if the model omits some."""
    provider = _make_provider(mock_openai, '{"title": "Only Title"}')
    result = provider.identify_book("book.epub", {}, "")

    for key in ["title", "author_first", "author_last", "series", "series_number"]:
        assert key in result


@patch("pipeline.ai_providers.openai_provider.OpenAI")
def test_returns_none_defaults_on_garbage_response(mock_openai: MagicMock) -> None:
    provider = _make_provider(mock_openai, "Sorry, I cannot help with that.")
    result = provider.identify_book("book.epub", {}, "")
    assert result.get("title") is None


def test_raises_on_missing_api_key() -> None:
    with pytest.raises(ValueError, match="OpenAI API key"):
        OpenAIProvider(api_key="")
