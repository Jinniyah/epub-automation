"""Non-interactive CLI batch loop -- iterates every `.epub` in a folder,
running one pipeline `Stage` over each one, with none of
`pipeline/batch_runner.py`'s interactive pause points (`needs_input`,
voice picking, Review) -- the CLI has no UI to answer any of those from,
so it doesn't try. Shared by `main.py`'s `rename`/`sanitize`/`audio`/
`retag`/`all` commands.

This is deliberately much simpler than `BatchRunner`: a technical user
invoking the CLI expects a single pass over a folder, not a resumable,
multi-screen workflow -- matching how the original standalone tools
(`epub-renamer`, `epub-sanitize`, `epub-to-audio`) already worked
(docs/design/adr/0014-reuse-existing-implementations-by-default.md).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from pipeline.input_validation import DEFAULT_MAX_FILES
from pipeline.stage import BookState, Stage


def discover_books(
    input_folder: Path, max_files: int = DEFAULT_MAX_FILES
) -> list[BookState]:
    """Scan `input_folder` (non-recursive -- 02-pipeline-stages.md §Stage
    1: "folder structure is now controlled by the pipeline itself") for
    `.epub` files, one `BookState` per file.

    Caps at `max_files`, printing a friendly warning about the excess to
    stderr rather than silently processing an unbounded batch
    (06-safety-error-handling.md §Resource & cost safety's `MAX_FILES`
    cap applies regardless of provider/front door).
    """
    paths = sorted(input_folder.glob("*.epub"))
    if len(paths) > max_files:
        print(
            f"Found {len(paths)} .epub files, only processing the first "
            f"{max_files} (see MAX_FILES). Re-run for the rest.",
            file=sys.stderr,
        )
        paths = paths[:max_files]
    return [BookState(book_id=p.stem, data={"filename": p.name}) for p in paths]


def run_stage_over_folder(
    stage: Stage,
    input_folder: Path,
    settings: dict[str, Any],
    *,
    max_files: int = DEFAULT_MAX_FILES,
) -> list[BookState]:
    """Run `stage` over every EPUB in `input_folder`. A book whose
    `applies_to()` is False (its toggle is off) passes through unchanged
    -- not silently dropped -- so a caller chaining stages can feed the
    result straight into the next one regardless of which stages a given
    run actually enabled.
    """
    results = []
    for book in discover_books(input_folder, max_files=max_files):
        if stage.applies_to(book, settings):
            results.append(stage.run(book))
        else:
            results.append(book)
    return results
