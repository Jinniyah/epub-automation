"""Tests for pipeline/epub_reader.py.

extract_epub_metadata()/extract_text_sample() are ported from epub-renamer/
tests/test_epub_reader.py (ADR-0014), import paths updated only.
extract_cover_bytes() (Epic 4) is new test coverage for the function
ported from epub-to-audio\\epub_utils.py -- mocked the same way as the
tests above, one per fallback strategy.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from pipeline.epub_reader import (
    extract_cover_bytes,
    extract_epub_metadata,
    extract_text_sample,
)


@patch("pipeline.epub_reader.epub.read_epub")
def test_extract_epub_metadata(mock_read: MagicMock) -> None:
    mock_book = MagicMock()
    mock_book.get_metadata.side_effect = [
        [("Title", {})],
        [("Author", {})],
        [("ID", {})],
    ]
    mock_read.return_value = mock_book

    result = extract_epub_metadata("file.epub")
    assert result["title"] == "Title"
    assert result["author"] == "Author"
    assert result["identifier"] == "ID"


@patch("pipeline.epub_reader.epub.read_epub")
def test_extract_epub_metadata_handles_missing_fields(mock_read: MagicMock) -> None:
    mock_book = MagicMock()
    mock_book.get_metadata.side_effect = [[], [], []]
    mock_read.return_value = mock_book

    result = extract_epub_metadata("file.epub")
    assert result["title"] is None
    assert result["author"] is None
    assert result["identifier"] is None


@patch("pipeline.epub_reader.epub.read_epub")
def test_extract_text_sample(mock_read: MagicMock) -> None:
    mock_item = MagicMock()
    mock_item.get_type.return_value = 9  # ITEM_DOCUMENT
    mock_item.get_body_content.return_value = b"<p>Hello World</p>"

    mock_book = MagicMock()
    mock_book.get_items.return_value = [mock_item]
    mock_read.return_value = mock_book

    result = extract_text_sample("file.epub")
    assert "Hello World" in result


@patch("pipeline.epub_reader.epub.read_epub")
def test_extract_text_sample_respects_max_length(mock_read: MagicMock) -> None:
    mock_item = MagicMock()
    mock_item.get_type.return_value = 9  # ITEM_DOCUMENT
    mock_item.get_body_content.return_value = b"<p>" + b"x" * 100 + b"</p>"

    mock_book = MagicMock()
    mock_book.get_items.return_value = [mock_item]
    mock_read.return_value = mock_book

    result = extract_text_sample("file.epub", max_length=10)
    assert len(result) == 10


# ---------------------------------------------------------------------------
# extract_cover_bytes
# ---------------------------------------------------------------------------


@patch("pipeline.epub_reader.epub.read_epub")
def test_extract_cover_bytes_strategy1_image_item_named_cover(
    mock_read: MagicMock,
) -> None:
    cover_item = MagicMock()
    cover_item.get_name.return_value = "images/cover.jpg"
    cover_item.get_content.return_value = b"COVERBYTES"

    mock_book = MagicMock()
    mock_book.get_items_of_type.return_value = [cover_item]
    mock_read.return_value = mock_book

    assert extract_cover_bytes("file.epub") == b"COVERBYTES"


@patch("pipeline.epub_reader.epub.read_epub")
def test_extract_cover_bytes_strategy2_opf_meta_pointer(mock_read: MagicMock) -> None:
    cover_item = MagicMock()
    cover_item.get_content.return_value = b"OPF-COVER-BYTES"

    mock_book = MagicMock()
    mock_book.get_items_of_type.return_value = []  # strategy 1: nothing
    mock_book.get_metadata.return_value = [(None, {"content": "cover-id"})]
    mock_book.get_item_with_id.return_value = cover_item
    mock_read.return_value = mock_book

    assert extract_cover_bytes("file.epub") == b"OPF-COVER-BYTES"


@patch("pipeline.epub_reader.epub.read_epub")
def test_extract_cover_bytes_strategy2_falls_through_on_lookup_error(
    mock_read: MagicMock,
) -> None:
    mock_book = MagicMock()
    mock_book.get_items_of_type.return_value = []
    mock_book.get_metadata.return_value = [(None, {"content": "cover-id"})]
    mock_book.get_item_with_id.side_effect = RuntimeError("bad id")
    mock_read.return_value = mock_book

    assert extract_cover_bytes("file.epub") is None


@patch("pipeline.epub_reader.epub.read_epub")
def test_extract_cover_bytes_strategy3_img_tag_in_cover_document(
    mock_read: MagicMock,
) -> None:
    cover_doc = MagicMock()
    cover_doc.get_name.return_value = "cover.xhtml"
    cover_doc.get_content.return_value = (
        b'<html><body><img src="./images/cover.jpg"/></body></html>'
    )

    image_item = MagicMock()
    image_item.get_name.return_value = "images/cover.jpg"
    image_item.get_content.return_value = b"XHTML-COVER-BYTES"

    mock_book = MagicMock()
    # Called three times: strategy 1 (ITEM_IMAGE, empty), strategy 3's
    # ITEM_DOCUMENT scan, then strategy 3's own ITEM_IMAGE lookup.
    mock_book.get_items_of_type.side_effect = [[], [cover_doc], [image_item]]
    mock_book.get_metadata.return_value = []  # strategy 2: nothing
    mock_read.return_value = mock_book

    assert extract_cover_bytes("file.epub") == b"XHTML-COVER-BYTES"


@patch("pipeline.epub_reader.epub.read_epub")
def test_extract_cover_bytes_returns_none_when_nothing_found(
    mock_read: MagicMock,
) -> None:
    mock_book = MagicMock()
    mock_book.get_items_of_type.return_value = []
    mock_book.get_metadata.return_value = []
    mock_read.return_value = mock_book

    assert extract_cover_bytes("file.epub") is None
