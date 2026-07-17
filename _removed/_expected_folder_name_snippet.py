def _expected_folder_name(
    *, title: str, author_first: str | None = "Benedict", author_last: str | None = "Jacka"
) -> str:
    """The exact folder name build_filename() will produce for a book
    added via `_add_book()`'s default author ("Benedict Jacka").
    NullProvider now parses the EPUB's own DC:creator field rather than
    always returning "Unknown, Unknown" (docs/BACKLOG.md Epic 8.5, fixed
    2026-07-14) -- these defaults match that real parse, not a fallback."""
    return build_filename(
        {
            "title": title,
            "author_first": author_first,
            "author_last": author_last,
            "series": None,
            "series_number": None,
        }
    ).removesuffix(".epub")
