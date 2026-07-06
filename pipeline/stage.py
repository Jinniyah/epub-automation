"""The `Stage` protocol -- Pipeline pattern (docs/design/PATTERNS.md §1).

Every pipeline stage (rename: Epic 3, sanitize: Epic 2, audio: Epic 4,
retag: Epic 5) implements this Protocol so both main.py's `all` command and
the GUI's per-book loop can iterate an ordered list of stage objects instead
of hand-wiring stage-specific calls. This also cleanly expresses the
per-run skip toggles (`fix_names` / `clean_language`) as "this stage isn't
in this run's pipeline" via `applies_to`, rather than an `if` scattered
through the runner.

See docs/requirements/01-architecture.md §Project structure and
docs/design/SYSTEM_DESIGN.md §5 for how this fits into the overall pipeline
data flow.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class BookState:
    """Minimal per-book state a Stage operates on and returns.

    Deliberately minimal for Epic 0 -- this is the one real type the Stage
    protocol and its tests reference, rather than a bare dict, so the
    interface itself is provably sufficient before any concrete stage
    exists. Later epics (rename/sanitize/audio/retag) will extend the real
    shape that flows through pipeline/state_manager.py; if that turns out
    to need a different shape than this, update this class rather than
    letting concrete stages quietly diverge from it.
    """

    book_id: str
    status: str = "pending"
    data: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class Stage(Protocol):
    """Common seam every pipeline stage implements.

    If a concrete Stage's `run()` needs to do something `applies_to()`
    can't express via the toggle it's given, that's a sign the toggle
    plumbing needs to grow -- not a reason to special-case that stage in
    the runner.
    """

    name: str  # "rename" | "sanitize" | "audio" | "retag"

    def applies_to(self, book: BookState, settings: dict[str, Any]) -> bool:
        """Return False if this run's toggles skip this stage for this book."""
        ...

    def run(self, book: BookState) -> BookState:
        """Process one book, returning its updated state.

        Must be resumable: safe to call again on a book already partially
        processed by this stage (see
        docs/requirements/06-safety-error-handling.md §Long-run resilience).
        """
        ...
