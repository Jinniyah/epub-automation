"""Tests for pipeline/cli_runner.py -- the non-interactive folder loop
shared by main.py's CLI commands."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ebooklib import epub

from pipeline.cli_runner import discover_books, run_stage_over_folder
from pipeline.stage import BookState


def _make_epub(path: Path, *, title: str = "Some Title") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    book = epub.EpubBook()
    book.set_identifier("id-cli-test")
    book.set_title(title)
    book.set_language("en")
    book.add_author("Some Author")
    chapter = epub.EpubHtml(title="Chapter 1", file_name="chap1.xhtml", lang="en")
    chapter.content = "<html><body><p>Some sample content.</p></body></html>"
    book.add_item(chapter)
    book.toc = (chapter,)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", chapter]
    epub.write_epub(str(path), book)
    return path


def test_discover_books_finds_every_epub_non_recursively(tmp_path: Path) -> None:
    _make_epub(tmp_path / "a.epub")
    _make_epub(tmp_path / "b.epub")
    _make_epub(tmp_path / "nested" / "c.epub")  # must not be found

    books = discover_books(tmp_path)

    assert {b.data["filename"] for b in books} == {"a.epub", "b.epub"}


def test_discover_books_ignores_non_epub_files(tmp_path: Path) -> None:
    _make_epub(tmp_path / "a.epub")
    (tmp_path / "notes.txt").write_text("hello")

    books = discover_books(tmp_path)

    assert len(books) == 1


def test_discover_books_caps_at_max_files(tmp_path: Path, capsys: Any) -> None:
    for i in range(5):
        _make_epub(tmp_path / f"book{i}.epub")

    books = discover_books(tmp_path, max_files=3)

    assert len(books) == 3
    assert "only processing the first 3" in capsys.readouterr().err


class _UppercaseTitleStage:
    """A minimal fake Stage -- proves the loop's toggle/pass-through
    behavior without depending on a real concrete stage."""

    name = "fake"

    def applies_to(self, book: BookState, settings: dict[str, Any]) -> bool:
        return bool(settings.get("enabled", True))

    def run(self, book: BookState) -> BookState:
        from dataclasses import replace

        return replace(book, status="processed")


def test_run_stage_over_folder_runs_the_stage_on_every_book(tmp_path: Path) -> None:
    _make_epub(tmp_path / "a.epub")
    _make_epub(tmp_path / "b.epub")

    results = run_stage_over_folder(_UppercaseTitleStage(), tmp_path, {"enabled": True})

    assert len(results) == 2
    assert all(b.status == "processed" for b in results)


def test_run_stage_over_folder_passes_through_when_disabled(tmp_path: Path) -> None:
    _make_epub(tmp_path / "a.epub")

    results = run_stage_over_folder(
        _UppercaseTitleStage(), tmp_path, {"enabled": False}
    )

    assert len(results) == 1
    assert results[0].status == "pending"  # unchanged, stage never ran
