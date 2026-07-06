"""CLI entry point -- Adapter into pipeline/ (ADR-0001,
docs/design/PATTERNS.md §1).

Zero business logic lives here: if this file makes a decision beyond
argument parsing and wiring, that's a bug, not a style preference.

Stage implementations land in later epics (rename: Epic 3, sanitize:
Epic 2, audio: Epic 4, retag: Epic 5) -- this scaffold exists so the
single-instance lock (ADR-0007) and the reserved `--workers` flag
(docs/requirements/01-architecture.md §CLI: reserved --workers flag,
ADR-0009) are real and testable before any stage logic exists.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pipeline.single_instance import AlreadyRunningError, SingleInstanceLock

APPDATA_DIR = Path.home() / "AppData" / "Roaming" / "EpubAutomation"
LOCK_PATH = APPDATA_DIR / "epub-automation.lock"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="epub-automation")
    subparsers = parser.add_subparsers(dest="command", required=True)

    for name in ("rename", "sanitize", "retag", "all"):
        subparsers.add_parser(name)

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

    return parser


def main(argv: list[str] | None = None, *, lock_path: Path = LOCK_PATH) -> int:
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
        # No stage is implemented yet (Epics 2-5) -- this scaffold proves
        # argument parsing, the --workers seam, and the single-instance
        # lock all work correctly ahead of any real pipeline logic.
        print(f"'{args.command}' is not yet implemented -- see docs/BACKLOG.md.")
        return 0
    finally:
        lock.release()


if __name__ == "__main__":
    sys.exit(main())
