"""Repository wrapper for the unified cross-stage CSV audit log (Repository
pattern, docs/design/PATTERNS.md §1).

One CSV across all four pipeline stages, not a per-stage report file (see
docs/requirements/05-data-settings-and-logging.md §Audit log) -- the
human-readable history, distinct from the machine-readable state file
(pipeline/state_manager.py). Wrapping it behind a Repository interface
lets pipeline-stage tests use a fake/in-memory audit log instead of
hitting the real filesystem.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Fixed column order, per 05-data-settings-and-logging.md §Audit log. New
# columns get appended here (never inserted in the middle / reordered), so
# an existing audit_log.csv on a real install stays column-compatible with
# rows appended by a newer app version.
COLUMNS = [
    "timestamp",
    "stage",
    "original_filename",
    "new_filename",
    "title",
    "author",
    "series",
    "series_number",
    "ai_used",
    "renamed",
    "skipped_reason",
    "voice",
    "words_replaced",
    "sanitize_detail_report",
]


@dataclass
class AuditLogRepository:
    """Append-only Repository over audit_log.csv."""

    path: Path

    def _ensure_header(self) -> None:
        if not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "w", newline="", encoding="utf-8") as f:
                csv.DictWriter(f, fieldnames=COLUMNS).writeheader()

    def append(self, row: dict[str, Any]) -> None:
        """Append one audit row.

        `row` may omit any column that doesn't apply to this stage (e.g. a
        rename-stage row has no `voice`) -- missing columns are written
        blank. An unknown key raises `ValueError` rather than being
        silently dropped: a typo'd column name vanishing without a trace
        would be a bad debugging experience for exactly the tool this log
        exists to help debug.

        Never pass `ai_api_key` or any other settings.json secret into a
        row -- see 05-data-settings-and-logging.md's explicit exclusion of
        secrets from this log.
        """
        unknown = set(row) - set(COLUMNS)
        if unknown:
            raise ValueError(f"Unknown audit log column(s): {sorted(unknown)}")
        self._ensure_header()
        with open(self.path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=COLUMNS)
            writer.writerow({col: row.get(col, "") for col in COLUMNS})

    def read_all(self) -> list[dict[str, str]]:
        """Read every row back.

        Used by the "what voice did I use before?" read-only lookup screen
        (Epic 8) and by support-bundle generation
        (docs/requirements/06-safety-error-handling.md §Error
        communication) -- never by exposing this CSV to her directly.
        """
        if not self.path.exists():
            return []
        with open(self.path, "r", newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))
