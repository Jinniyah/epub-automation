"""Tests for main.py -- CLI Adapter wiring real pipeline stages
(ADR-0001, docs/BACKLOG.md Epic 6)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from ebooklib import epub
from mutagen.id3 import ID3

import main as main_module


def _make_epub(
    path: Path, *, title: str = "Fated", author: str = "Benedict Jacka"
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    book = epub.EpubBook()
    book.set_identifier("id-main-test")
    book.set_title(title)
    book.set_language("en")
    book.add_author(author)
    chapter = epub.EpubHtml(title="Chapter 1", file_name="chap1.xhtml", lang="en")
    chapter.content = "<html><body><p>Some sample narrative content.</p></body></html>"
    book.add_item(chapter)
    book.toc = (chapter,)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", chapter]
    epub.write_epub(str(path), book)
    return path


def _write_settings(appdata_dir: Path, **overrides: Any) -> None:
    appdata_dir.mkdir(parents=True, exist_ok=True)
    defaults = {
        "schema_version": 1,
        "books_folder": "",
        "output_folder": "",
        "fix_names": True,
        "clean_language": True,
        "ai_provider": "none",
        "ai_api_key": "",
        "last_voice": "",
        "profanity_words": ["damn"],
    }
    defaults.update(overrides)
    (appdata_dir / "settings.json").write_text(json.dumps(defaults))


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


def test_workers_defaults_to_1() -> None:
    args = main_module.build_parser().parse_args(["audio"])
    assert args.workers == 1


def test_workers_can_be_set() -> None:
    args = main_module.build_parser().parse_args(["audio", "--workers", "4"])
    assert args.workers == 4


def test_retag_requires_a_folder_argument() -> None:
    with pytest.raises(SystemExit):
        main_module.build_parser().parse_args(["retag"])


def test_retag_accepts_override_flags() -> None:
    args = main_module.build_parser().parse_args(
        ["retag", "C:\\Books\\Fated", "--title", "Fated", "--author-last", "Jacka"]
    )
    assert args.folder == Path("C:\\Books\\Fated")
    assert args.title == "Fated"
    assert args.author_last == "Jacka"
    assert args.author_first is None


def test_unknown_command_exits() -> None:
    with pytest.raises(SystemExit):
        main_module.build_parser().parse_args(["not-a-real-command"])


# ---------------------------------------------------------------------------
# main() -- single-instance lock
# ---------------------------------------------------------------------------


def test_main_fails_fast_when_lock_already_held(tmp_path: Path) -> None:
    appdata_dir = tmp_path / "appdata"
    _write_settings(appdata_dir)
    lock_path = tmp_path / "epub-automation.lock"

    from pipeline.single_instance import SingleInstanceLock

    holder = SingleInstanceLock(lock_path)
    holder.acquire()
    try:
        result = main_module.main(
            ["rename"], lock_path=lock_path, appdata_dir=appdata_dir
        )
    finally:
        holder.release()

    assert result == 1


def test_main_releases_the_lock_after_running(tmp_path: Path) -> None:
    appdata_dir = tmp_path / "appdata"
    _write_settings(appdata_dir, books_folder=str(tmp_path / "books"))
    (tmp_path / "books").mkdir()
    lock_path = tmp_path / "epub-automation.lock"

    result = main_module.main(["rename"], lock_path=lock_path, appdata_dir=appdata_dir)

    assert result == 0
    assert not lock_path.exists()


# ---------------------------------------------------------------------------
# main() -- rename command
# ---------------------------------------------------------------------------


def test_rename_command_renames_books_using_null_provider(tmp_path: Path) -> None:
    appdata_dir = tmp_path / "appdata"
    books_folder = tmp_path / "books"
    output_folder = tmp_path / "output"
    _make_epub(books_folder / "messy.epub", title="Fated", author="Benedict Jacka")
    _write_settings(
        appdata_dir,
        books_folder=str(books_folder),
        output_folder=str(output_folder),
    )

    result = main_module.main(
        ["rename"],
        lock_path=tmp_path / "lock",
        appdata_dir=appdata_dir,
    )

    assert result == 0
    renamed = list(output_folder.glob("*.epub"))
    assert len(renamed) == 1
    assert "Fated" in renamed[0].name


def test_rename_command_skipped_when_fix_names_off_but_original_untouched(
    tmp_path: Path,
) -> None:
    appdata_dir = tmp_path / "appdata"
    books_folder = tmp_path / "books"
    output_folder = tmp_path / "output"
    _make_epub(books_folder / "book.epub")
    _write_settings(
        appdata_dir,
        books_folder=str(books_folder),
        output_folder=str(output_folder),
        fix_names=False,
    )

    result = main_module.main(
        ["rename"], lock_path=tmp_path / "lock", appdata_dir=appdata_dir
    )

    assert result == 0
    assert (books_folder / "book.epub").exists()  # original never touched


# ---------------------------------------------------------------------------
# main() -- sanitize command
# ---------------------------------------------------------------------------


def test_sanitize_command_writes_cleaned_epub(tmp_path: Path) -> None:
    appdata_dir = tmp_path / "appdata"
    books_folder = tmp_path / "books"
    output_folder = tmp_path / "output"
    _make_epub(books_folder / "book.epub")
    _write_settings(
        appdata_dir,
        books_folder=str(books_folder),
        output_folder=str(output_folder),
    )

    result = main_module.main(
        ["sanitize"], lock_path=tmp_path / "lock", appdata_dir=appdata_dir
    )

    assert result == 0
    cleaned = list(output_folder.glob("*_cln.epub"))
    assert len(cleaned) == 1


# ---------------------------------------------------------------------------
# main() -- retag command
# ---------------------------------------------------------------------------


def test_retag_command_reports_error_for_missing_folder(tmp_path: Path) -> None:
    appdata_dir = tmp_path / "appdata"
    _write_settings(appdata_dir)

    result = main_module.main(
        ["retag", str(tmp_path / "does-not-exist")],
        lock_path=tmp_path / "lock",
        appdata_dir=appdata_dir,
    )

    assert result == 2


def test_retag_command_applies_overrides(tmp_path: Path) -> None:
    appdata_dir = tmp_path / "appdata"
    _write_settings(appdata_dir)
    audio_folder = tmp_path / "Unknown, Unknown — Some Book"
    audio_folder.mkdir(parents=True)
    mp3_path = audio_folder / "Unknown, Unknown — Some Book - 001.mp3"
    mp3_path.write_bytes(b"FAKE-MP3-CONTENT-" + b"-" * 2000)
    ID3().save(mp3_path, v2_version=3)

    result = main_module.main(
        [
            "retag",
            str(audio_folder),
            "--author-last",
            "Jacka",
            "--author-first",
            "Benedict",
            "--title",
            "Fated",
        ],
        lock_path=tmp_path / "lock",
        appdata_dir=appdata_dir,
    )

    assert result == 0
    renamed_folders = list(tmp_path.glob("Jacka, Benedict*"))
    assert len(renamed_folders) == 1
