"""CLI entry point -- Adapter into pipeline/ (ADR-0001,
docs/design/PATTERNS.md §1).

Zero business logic lives here: if this file makes a decision beyond
argument parsing and wiring, that's a bug, not a style preference.

Unlike `backend/bridge.py`'s `BatchRunner`, the CLI never pauses for
`needs_input` -- there's no UI here to answer one from. Each command runs
its stage(s) once, non-interactively, over a folder
(`pipeline/cli_runner.py`), matching how the three original standalone
tools already worked (docs/design/adr/0014-reuse-existing-
implementations-by-default.md) -- a single pass, not a resumable
multi-screen workflow.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Any

from pipeline.audio_stage import AudioStage
from pipeline.audit_logger import AuditLogRepository
from pipeline.cli_runner import run_stage_over_folder
from pipeline.config import SettingsRepository
from pipeline.rename_stage import RenameStage
from pipeline.retag_stage import RetagStage
from pipeline.sanitize_stage import SanitizeStage
from pipeline.single_instance import AlreadyRunningError, SingleInstanceLock
from pipeline.stage import BookState
from pipeline.tts_engine import DEFAULT_VOICE, TTSEngine

APPDATA_DIR = Path.home() / "AppData" / "Roaming" / "EpubAutomation"
LOCK_PATH = APPDATA_DIR / "epub-automation.lock"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="epub-automation")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("rename")
    subparsers.add_parser("sanitize")
    subparsers.add_parser("all")

    audio_parser = subparsers.add_parser("audio")
    audio_parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help=(
            "Reserved for future parallelism (ADR-0009). The GUI always "
            "runs serially; this version validates and defaults to 1 "
            "without implementing parallel execution."
        ),
    )

    retag_parser = subparsers.add_parser("retag")
    retag_parser.add_argument(
        "folder", type=Path, help="An already-generated audiobook output folder"
    )
    retag_parser.add_argument("--author-first")
    retag_parser.add_argument("--author-last")
    retag_parser.add_argument("--title")
    retag_parser.add_argument("--series")
    retag_parser.add_argument("--series-number")

    return parser


def _load_settings(appdata_dir: Path) -> dict[str, Any]:
    return SettingsRepository(appdata_dir / "settings.json").load()


def _pass_through(
    book: BookState, input_folder: Path, output_folder: Path
) -> BookState:
    """Copy a book's file forward unchanged when its stage's toggle is
    off -- only relevant to `all`'s chained folders (a standalone
    single-stage command has no downstream stage to feed, so this is
    never called for `rename`/`sanitize`/`audio` run alone)."""
    filename = book.data.get("filename") or (book.book_id + ".epub")
    src = input_folder / filename
    output_folder.mkdir(parents=True, exist_ok=True)
    dst = output_folder / filename
    if src.resolve() != dst.resolve():
        shutil.copy2(src, dst)
    return replace(
        book, data={**book.data, "filename": filename, "epub_path": str(dst)}
    )


def _run_rename(
    input_folder: Path,
    output_folder: Path,
    settings: dict[str, Any],
    audit_log: AuditLogRepository,
) -> None:
    stage = RenameStage(
        input_folder,
        output_folder,
        audit_log,
        ai_provider=settings.get("ai_provider", "none"),
        ai_api_key=settings.get("ai_api_key", ""),
    )
    if settings.get("fix_names", True):
        run_stage_over_folder(stage, input_folder, settings)
    else:
        for book in run_stage_over_folder(stage, input_folder, settings):
            _pass_through(book, input_folder, output_folder)


def _run_sanitize(
    input_folder: Path,
    output_folder: Path,
    settings: dict[str, Any],
    appdata_dir: Path,
) -> None:
    words = settings.get("profanity_words") or ["placeholder"]
    stage = SanitizeStage(input_folder, output_folder, appdata_dir / "logs", words)
    if settings.get("clean_language", True):
        run_stage_over_folder(stage, input_folder, settings)
        stage.write_report()
    else:
        for book in run_stage_over_folder(stage, input_folder, settings):
            _pass_through(book, input_folder, output_folder)


def _run_audio(
    input_folder: Path,
    output_folder: Path,
    settings: dict[str, Any],
    audit_log: AuditLogRepository,
) -> None:
    tts_engine = TTSEngine()
    default_voice = settings.get("last_voice") or DEFAULT_VOICE
    stage = AudioStage(
        input_folder, output_folder, audit_log, tts_engine, default_voice=default_voice
    )
    run_stage_over_folder(stage, input_folder, settings)


def _run_all(
    books_folder: Path,
    output_folder: Path,
    settings: dict[str, Any],
    audit_log: AuditLogRepository,
    appdata_dir: Path,
) -> None:
    with (
        tempfile.TemporaryDirectory(prefix="epub-automation-renamed-") as renamed_tmp,
        tempfile.TemporaryDirectory(
            prefix="epub-automation-sanitized-"
        ) as sanitized_tmp,
    ):
        renamed_dir = Path(renamed_tmp)
        sanitized_dir = Path(sanitized_tmp)
        _run_rename(books_folder, renamed_dir, settings, audit_log)
        _run_sanitize(renamed_dir, sanitized_dir, settings, appdata_dir)
        _run_audio(sanitized_dir, output_folder, settings, audit_log)


def _run_retag(
    folder: Path, args: argparse.Namespace, audit_log: AuditLogRepository
) -> int:
    if not folder.exists() or not folder.is_dir():
        print(f"Not a folder: {folder}", file=sys.stderr)
        return 2
    stage = RetagStage(audit_log)
    overrides = {
        "author_first": args.author_first,
        "author_last": args.author_last,
        "title": args.title,
        "series": args.series,
        "series_number": args.series_number,
    }
    overrides = {k: v for k, v in overrides.items() if v is not None}
    book = BookState(
        book_id=folder.name, data={"audio_folder": str(folder), **overrides}
    )
    result = stage.run(book)
    if result.status == "error":
        print(result.data.get("error", "Retag failed."), file=sys.stderr)
        return 1
    return 0


def main(
    argv: list[str] | None = None,
    *,
    lock_path: Path = LOCK_PATH,
    appdata_dir: Path = APPDATA_DIR,
) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "audio" and args.workers < 1:
        print("--workers must be >= 1", file=sys.stderr)
        return 2

    lock = SingleInstanceLock(lock_path)
    try:
        lock.acquire()
    except AlreadyRunningError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    try:
        settings = _load_settings(appdata_dir)
        audit_log = AuditLogRepository(appdata_dir / "audit_log.csv")
        books_folder = Path(settings.get("books_folder") or ".")
        output_folder = Path(settings.get("output_folder") or ".")

        if args.command == "rename":
            _run_rename(books_folder, output_folder, settings, audit_log)
        elif args.command == "sanitize":
            _run_sanitize(books_folder, output_folder, settings, appdata_dir)
        elif args.command == "audio":
            _run_audio(books_folder, output_folder, settings, audit_log)
        elif args.command == "all":
            _run_all(books_folder, output_folder, settings, audit_log, appdata_dir)
        elif args.command == "retag":
            return _run_retag(args.folder, args, audit_log)
        return 0
    finally:
        lock.release()


if __name__ == "__main__":
    sys.exit(main())
