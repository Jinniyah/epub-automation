"""Tests for pipeline/epub_utils.py.

sanitize_filesystem_name() (ADR-0016) is new code (none of the three
source repos needed to solve this), so it gets a full test-first suite.
normalise_heading()/extract_chapters()/chunk_text() (Epic 4) are ported
verbatim from epub-to-audio\\epub_utils.py (ADR-0014); their tests are
adapted from that project's own test suite where one existed, otherwise
written fresh against the ported behavior.
"""

from __future__ import annotations

from pathlib import Path

from ebooklib import epub

from pipeline.epub_utils import (
    MAX_COMPONENT_LENGTH,
    chunk_text,
    extract_chapters,
    normalise_heading,
    sanitize_filesystem_name,
)


def test_replaces_windows_illegal_characters_with_space() -> None:
    result = sanitize_filesystem_name('A:B*C?"D<>E|F\\G/H')
    for bad_char in '<>:"/\\|?*':
        assert bad_char not in result


def test_collapses_repeated_whitespace_from_adjacent_illegal_chars() -> None:
    result = sanitize_filesystem_name("A::B")
    assert result == "A B"


def test_colon_in_subtitle_becomes_space() -> None:
    result = sanitize_filesystem_name("Spider-Man: Homecoming")
    assert result == "Spider-Man Homecoming"


def test_question_mark_becomes_space() -> None:
    result = sanitize_filesystem_name("Who Framed Roger Rabbit?")
    assert result == "Who Framed Roger Rabbit"


def test_strips_trailing_dot_and_space() -> None:
    assert sanitize_filesystem_name("Book Title. ") == "Book Title"
    assert sanitize_filesystem_name("Book Title.") == "Book Title"
    assert sanitize_filesystem_name("Book Title ") == "Book Title"


def test_leading_space_is_preserved() -> None:
    # Only trailing whitespace is illegal on Windows -- leading is fine.
    assert sanitize_filesystem_name(" Book") == " Book"


def test_reserved_device_name_gets_suffixed() -> None:
    for name in ["CON", "con", "PRN", "AUX", "NUL", "COM1", "LPT9"]:
        result = sanitize_filesystem_name(name)
        assert result != name
        assert result.upper().startswith(name.upper())


def test_non_reserved_name_containing_device_name_untouched() -> None:
    # "CONsole" isn't itself a reserved name -- only an exact match is.
    assert sanitize_filesystem_name("Console") == "Console"


def test_truncates_to_max_length() -> None:
    long_name = "A" * (MAX_COMPONENT_LENGTH + 50)
    result = sanitize_filesystem_name(long_name)
    assert len(result) <= MAX_COMPONENT_LENGTH


def test_truncation_does_not_leave_trailing_space_or_dot() -> None:
    # Craft a string whose max_length-th character lands on a space.
    name = ("A" * 9 + " ") * 20  # repeating "AAAAAAAAA "
    result = sanitize_filesystem_name(name, max_length=10)
    assert not result.endswith(" ")
    assert not result.endswith(".")


def test_idempotent_on_illegal_characters() -> None:
    name = 'Spider-Man: "Homecoming"?'
    once = sanitize_filesystem_name(name)
    twice = sanitize_filesystem_name(once)
    assert once == twice


def test_idempotent_on_reserved_device_name() -> None:
    once = sanitize_filesystem_name("CON")
    twice = sanitize_filesystem_name(once)
    assert once == twice


def test_idempotent_after_truncation() -> None:
    long_name = "Word " * 40
    once = sanitize_filesystem_name(long_name, max_length=30)
    twice = sanitize_filesystem_name(once, max_length=30)
    assert once == twice


# ---------------------------------------------------------------------------
# normalise_heading
# ---------------------------------------------------------------------------


def test_normalise_heading_spaces_letter_and_digit() -> None:
    assert normalise_heading("CHAPTER1") == "Chapter 1"
    assert normalise_heading("chapter10") == "Chapter 10"


def test_normalise_heading_already_spaced() -> None:
    assert normalise_heading("CHAPTER 1") == "Chapter 1"


def test_normalise_heading_apostrophe_segment_left_unmodified() -> None:
    # Ported verbatim (ADR-0014): only the part *before* the apostrophe is
    # capitalize()'d -- the part after is passed through as-is, so an
    # all-caps input's trailing "S" stays uppercase ("Author'S", not
    # "Author's"). The source project's own docstring example claims
    # "Author's Note", but that's not what its code actually does --
    # documented here rather than silently "fixed", since changing this
    # ported function's actual behavior wasn't asked for.
    assert normalise_heading("AUTHOR'S NOTE") == "Author'S Note"


def test_normalise_heading_preserves_simple_word() -> None:
    assert normalise_heading("Prologue") == "Prologue"


# ---------------------------------------------------------------------------
# chunk_text
# ---------------------------------------------------------------------------


def test_chunk_text_single_short_paragraph_is_one_chunk() -> None:
    assert chunk_text("Just one short paragraph.") == ["Just one short paragraph."]


def test_chunk_text_splits_on_paragraph_boundary_when_over_limit() -> None:
    para_a = "A" * 30
    para_b = "B" * 30
    chunks = chunk_text(f"{para_a}\n\n{para_b}", max_chars=40)
    assert chunks == [para_a, para_b]


def test_chunk_text_keeps_paragraphs_together_when_under_limit() -> None:
    para_a = "A" * 10
    para_b = "B" * 10
    chunks = chunk_text(f"{para_a}\n\n{para_b}", max_chars=100)
    assert len(chunks) == 1
    assert para_a in chunks[0] and para_b in chunks[0]


def test_chunk_text_splits_oversized_paragraph_on_sentences() -> None:
    sentence = "This is one sentence. "
    oversized_para = sentence * 20  # one paragraph, way over max_chars
    chunks = chunk_text(oversized_para, max_chars=100)
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) <= 100


def test_chunk_text_no_chunk_exceeds_max_chars() -> None:
    text = ("Paragraph number filler text here. " * 10 + "\n\n") * 5
    chunks = chunk_text(text, max_chars=200)
    assert all(len(c) <= 200 for c in chunks)


def test_chunk_text_empty_string_returns_no_chunks() -> None:
    assert chunk_text("") == []


def test_chunk_text_ignores_blank_paragraphs() -> None:
    assert chunk_text("Real text.\n\n\n\nMore text.", max_chars=100) == [
        "Real text.\n\nMore text."
    ]


# ---------------------------------------------------------------------------
# extract_chapters
# ---------------------------------------------------------------------------


def _add_html_doc(
    book: epub.EpubBook, file_name: str, title: str, body_html: str
) -> epub.EpubHtml:
    doc = epub.EpubHtml(title=title, file_name=file_name, lang="en")
    doc.content = f"<html><body>{body_html}</body></html>"
    book.add_item(doc)
    return doc


def _make_multi_chapter_epub(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    book = epub.EpubBook()
    book.set_identifier("id-multi")
    book.set_title("Multi Chapter Book")
    book.set_language("en")
    book.add_author("Some Author")

    toc_skip = _add_html_doc(
        book, "toc.xhtml", "Table of Contents", "<p>table of contents</p>"
    )
    ch1 = _add_html_doc(
        book,
        "chap1.xhtml",
        "Chapter 1",
        "<h1>CHAPTER1</h1>" + "<p>" + ("Some real narrative content. " * 20) + "</p>",
    )
    ch2 = _add_html_doc(
        book,
        "chap2.xhtml",
        "Chapter 2",
        "<h1>Chapter 2</h1>" + "<p>" + ("More narrative content here. " * 20) + "</p>",
    )
    dedication = _add_html_doc(
        book,
        "dedication.xhtml",
        "Dedication",
        "<p>For my family, who always believed in me and supported this book.</p>",
    )
    afterword = _add_html_doc(
        book,
        "afterword.xhtml",
        "Author's Note",
        "<h1>AUTHOR'S NOTE</h1>" + "<p>" + ("Thanks for reading. " * 20) + "</p>",
    )
    excerpt = _add_html_doc(
        book,
        "excerpt.xhtml",
        "Excerpt",
        "<h1>Excerpt From The Next Book</h1>"
        + "<p>"
        + ("Preview text. " * 20)
        + "</p>",
    )

    book.toc = (ch1, ch2, dedication, afterword, excerpt)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", toc_skip, ch1, dedication, ch2, afterword, excerpt]

    epub.write_epub(str(path), book)
    return path


def test_extract_chapters_skips_nav_and_toc_documents(tmp_path: Path) -> None:
    path = _make_multi_chapter_epub(tmp_path / "multi.epub")
    chapters, skipped, _ = extract_chapters(str(path))
    titles = [c["title"] for c in chapters]
    assert "Table of Contents" not in titles
    assert any("nav" in s for s in skipped)
    assert any("toc" in s for s in skipped)


def test_extract_chapters_normalises_headings(tmp_path: Path) -> None:
    path = _make_multi_chapter_epub(tmp_path / "multi.epub")
    chapters, _, _ = extract_chapters(str(path))
    titles = [c["title"] for c in chapters]
    assert "Chapter 1" in titles
    assert "Chapter 2" in titles


def test_extract_chapters_labels_short_headingless_doc_as_dedication(
    tmp_path: Path,
) -> None:
    path = _make_multi_chapter_epub(tmp_path / "multi.epub")
    chapters, _, _ = extract_chapters(str(path))
    titles = [c["title"] for c in chapters]
    assert "Dedication" in titles


def test_extract_chapters_stops_after_stop_marker_but_includes_it(
    tmp_path: Path,
) -> None:
    path = _make_multi_chapter_epub(tmp_path / "multi.epub")
    chapters, _, stopped_at = extract_chapters(str(path))
    titles = [c["title"] for c in chapters]
    assert "Author'S Note" in titles  # see the normalise_heading quirk noted above
    assert "Excerpt From The Next Book" not in titles  # after the stop marker
    assert stopped_at == "Author'S Note"


def test_extract_chapters_custom_stop_after_list(tmp_path: Path) -> None:
    path = _make_multi_chapter_epub(tmp_path / "multi.epub")
    chapters, _, stopped_at = extract_chapters(str(path), stop_after=["chapter 2"])
    titles = [c["title"] for c in chapters]
    assert "Chapter 2" in titles
    assert "Dedication" in titles  # comes before Chapter 2 in spine order
    assert "Author's Note" not in titles
    assert stopped_at == "Chapter 2"


def test_extract_chapters_no_stop_markers_returns_all_chapters(tmp_path: Path) -> None:
    path = _make_multi_chapter_epub(tmp_path / "multi.epub")
    chapters, _, stopped_at = extract_chapters(str(path), stop_after=[])
    titles = [c["title"] for c in chapters]
    assert "Excerpt From The Next Book" in titles
    assert stopped_at is None
