"""Tests for pipeline/epub_utils.py.

sanitize_filesystem_name() (ADR-0016) is new code (none of the three
source repos needed to solve this), so it gets a full test-first suite.
normalise_heading()/extract_chapters()/chunk_text() (Epic 4) are ported
verbatim from epub-to-audio\\epub_utils.py (ADR-0014); their tests are
adapted from that project's own test suite where one existed, otherwise
written fresh against the ported behavior. parse_author_name()/
guess_author_from_filename()/guess_series_from_filename() (docs/
BACKLOG.md Epic 8.5, fixed 2026-07-14) are new fallback-guess helpers for
the rename stage's per-field AI-enrichment merge.
"""

from __future__ import annotations

from pathlib import Path

from ebooklib import epub

from pipeline.epub_utils import (
    MAX_COMPONENT_LENGTH,
    chunk_text,
    extract_chapters,
    group_chunks_into_parts,
    guess_author_from_filename,
    guess_series_from_filename,
    normalise_heading,
    parse_author_name,
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
# parse_author_name / guess_author_from_filename / guess_series_from_filename
# (docs/BACKLOG.md Epic 8.5, fixed 2026-07-14)
# ---------------------------------------------------------------------------


def test_parse_author_name_first_last_shape() -> None:
    assert parse_author_name("Brandon Sanderson") == ("Brandon", "Sanderson")


def test_parse_author_name_last_comma_first_shape() -> None:
    assert parse_author_name("Sanderson, Brandon") == ("Brandon", "Sanderson")


def test_parse_author_name_single_word_is_last_name_only() -> None:
    assert parse_author_name("Cher") == (None, "Cher")


def test_parse_author_name_multi_word_first_name() -> None:
    assert parse_author_name("Mary Ann Shaffer") == ("Mary Ann", "Shaffer")


def test_parse_author_name_blank_or_none_returns_nones() -> None:
    assert parse_author_name(None) == (None, None)
    assert parse_author_name("") == (None, None)
    assert parse_author_name("   ") == (None, None)


def test_guess_author_from_filename_matches_lastname_comma_firstname() -> None:
    assert guess_author_from_filename("Sanderson, Brandon - Elantris.epub") == (
        "Brandon",
        "Sanderson",
    )


def test_guess_author_from_filename_matches_em_dash_too() -> None:
    assert guess_author_from_filename("Sanderson, Brandon — Elantris.epub") == (
        "Brandon",
        "Sanderson",
    )


def test_guess_author_from_filename_no_match_without_comma() -> None:
    assert guess_author_from_filename("Elantris.epub") == (None, None)


def test_guess_author_from_filename_no_match_without_dash() -> None:
    # A comma alone isn't enough -- e.g. a title that happens to contain
    # one shouldn't be misread as "Lastname, Firstname".
    assert guess_author_from_filename("A Tale, Retold.epub") == (None, None)


def test_guess_series_from_filename_matches_hyphen_shape() -> None:
    name = "Jordan, Robert - Wheel of Time #09 - Winter's Heart.epub"
    assert guess_series_from_filename(name) == ("Wheel of Time", 9)


def test_guess_series_from_filename_matches_em_dash_shape() -> None:
    name = "Cornwell, Patricia — Kay Scarpetta #13 — Trace.epub"
    assert guess_series_from_filename(name) == ("Kay Scarpetta", 13)


def test_guess_series_from_filename_no_match_for_standalone() -> None:
    assert guess_series_from_filename("Sanderson, Brandon - Elantris.epub") == (
        None,
        None,
    )


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


# ---------------------------------------------------------------------------
# Chapter title detection -- ADR-0019, added 2026-07-20 after two real
# books in the user's own library showed the original "first <h1>-<h3>"
# heuristic missing real titles entirely (see module docstring additions
# in epub_utils.py for the real examples).
# ---------------------------------------------------------------------------


def _make_single_chapter_epub(path: Path, body_html: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    book = epub.EpubBook()
    book.set_identifier("id-single")
    book.set_title("Single Chapter Book")
    book.set_language("en")
    book.add_author("Some Author")

    ch1 = _add_html_doc(book, "chap1.xhtml", "Chapter 1", body_html)

    book.toc = (ch1,)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", ch1]

    epub.write_epub(str(path), book)
    return path


def test_extract_chapters_joins_two_headings_split_across_tags(
    tmp_path: Path,
) -> None:
    """Real example: Wheel of Time EPUBs mark a chapter as a generic
    "<h3>Chapter 1</h3>" immediately followed by a separately-tagged
    named title, "<em><h4>Waiting</h4></em>" -- the original single-
    heading lookup only ever saw "Chapter 1" and dropped "Waiting"."""
    body = (
        "<h3>Chapter 1</h3>"
        "<em><h4>Waiting</h4></em>"
        "<p>" + ("Real narrative content, sentence by sentence. " * 20) + "</p>"
    )
    path = _make_single_chapter_epub(tmp_path / "book.epub", body)
    chapters, _, _ = extract_chapters(str(path))
    assert chapters[0]["title"] == "Chapter 1 — Waiting"


def test_extract_chapters_does_not_join_a_heading_after_real_narrative_text(
    tmp_path: Path,
) -> None:
    """A second heading separated from the first by substantial narrative
    text is a genuinely different, later heading (e.g. a mid-chapter
    section break) -- must not be folded into the chapter title."""
    body = (
        "<h1>Chapter 1</h1>"
        "<p>" + ("Real narrative content, sentence by sentence. " * 20) + "</p>"
        "<h2>A Later Section Break</h2>"
        "<p>" + ("More narrative content follows here. " * 20) + "</p>"
    )
    path = _make_single_chapter_epub(tmp_path / "book.epub", body)
    chapters, _, _ = extract_chapters(str(path))
    assert chapters[0]["title"] == "Chapter 1"


def test_extract_chapters_single_heading_behaves_as_before(tmp_path: Path) -> None:
    body = "<h1>Chapter 1</h1><p>" + ("Some real narrative content. " * 20) + "</p>"
    path = _make_single_chapter_epub(tmp_path / "book.epub", body)
    chapters, _, _ = extract_chapters(str(path))
    assert chapters[0]["title"] == "Chapter 1"


def test_extract_chapters_finds_de_facto_title_with_no_heading_tag(
    tmp_path: Path,
) -> None:
    """Real example: The Risen Empire's chapter names ("Pilot", "Senator")
    are plain bold-styled <p> tags, never a real <hN> heading."""
    body = (
        '<p class="bold-style">Pilot</p>'
        "<p>" + ("Real narrative content, sentence by sentence. " * 20) + "</p>"
    )
    path = _make_single_chapter_epub(tmp_path / "book.epub", body)
    chapters, _, _ = extract_chapters(str(path))
    assert chapters[0]["title"] == "Pilot"


def test_extract_chapters_de_facto_title_skipped_for_a_real_opening_sentence(
    tmp_path: Path,
) -> None:
    """A short first paragraph that's a genuine sentence (ends in
    terminal punctuation) must not be mistaken for a title."""
    body = (
        "<p>She awoke without sanity.</p>"
        "<p>" + ("Real narrative content, sentence by sentence. " * 20) + "</p>"
    )
    path = _make_single_chapter_epub(tmp_path / "book.epub", body)
    chapters, _, _ = extract_chapters(str(path))
    assert chapters[0]["title"] == ""


def test_extract_chapters_de_facto_title_skipped_when_little_text_remains(
    tmp_path: Path,
) -> None:
    """A short first paragraph followed by only a little more text isn't
    a title sitting in front of a chapter -- it's most of a short
    document's actual content (guards the "remaining text" floor,
    distinct from the separate short-headingless-doc "Dedication" path,
    which only applies at or under DEDICATION_MAX_CHARS)."""
    body = "<p>Short Label</p><p>" + ("A little more text. " * 16) + "</p>"
    path = _make_single_chapter_epub(tmp_path / "book.epub", body)
    chapters, _, _ = extract_chapters(str(path))
    assert len(chapters[0]["text"]) > 300  # not short enough for "Dedication"
    assert chapters[0]["title"] == ""


def test_extract_chapters_real_heading_takes_precedence_over_de_facto_title(
    tmp_path: Path,
) -> None:
    """A document with a real heading never falls through to the
    de-facto-title fallback, even if the first paragraph would otherwise
    look title-like."""
    body = (
        "<h1>Chapter 1</h1>"
        "<p>Pilot</p>"
        "<p>" + ("Real narrative content, sentence by sentence. " * 20) + "</p>"
    )
    path = _make_single_chapter_epub(tmp_path / "book.epub", body)
    chapters, _, _ = extract_chapters(str(path))
    assert chapters[0]["title"] == "Chapter 1"


# ---------------------------------------------------------------------------
# group_chunks_into_parts -- ADR-0020, added 2026-07-20. One level up from
# chunk_text(): groups already-chunked text into larger "parts" so
# AudioStage can write one merged MP3 per ~15 minutes of audio.
# ---------------------------------------------------------------------------


def test_group_chunks_into_parts_combines_small_chunks_up_to_the_limit() -> None:
    chunks = ["a" * 100, "b" * 100, "c" * 100]
    parts = group_chunks_into_parts(chunks, max_part_chars=1000)
    assert parts == [chunks]


def test_group_chunks_into_parts_starts_a_new_part_when_over_limit() -> None:
    chunks = ["a" * 100, "b" * 100, "c" * 100]
    parts = group_chunks_into_parts(chunks, max_part_chars=250)
    assert parts == [["a" * 100, "b" * 100], ["c" * 100]]


def test_group_chunks_into_parts_never_splits_a_single_oversized_chunk() -> None:
    chunks = ["a" * 5000]
    parts = group_chunks_into_parts(chunks, max_part_chars=1000)
    assert parts == [["a" * 5000]]


def test_group_chunks_into_parts_oversized_chunk_followed_by_more_chunks() -> None:
    chunks = ["a" * 5000, "b" * 100, "c" * 100]
    parts = group_chunks_into_parts(chunks, max_part_chars=1000)
    assert parts == [["a" * 5000], ["b" * 100, "c" * 100]]


def test_group_chunks_into_parts_empty_input_returns_no_parts() -> None:
    assert group_chunks_into_parts([], max_part_chars=1000) == []


def test_group_chunks_into_parts_no_part_exceeds_the_limit_except_a_lone_oversized_chunk() -> (  # noqa: E501
    None
):
    chunks = [f"sentence {i} " * 50 for i in range(20)]
    parts = group_chunks_into_parts(chunks, max_part_chars=4000)
    for part in parts:
        total = sum(len(c) for c in part)
        assert total <= 4000 or len(part) == 1


def test_group_chunks_into_parts_is_deterministic() -> None:
    chunks = [f"sentence {i} " * 50 for i in range(20)]
    first = group_chunks_into_parts(chunks, max_part_chars=4000)
    second = group_chunks_into_parts(chunks, max_part_chars=4000)
    assert first == second
