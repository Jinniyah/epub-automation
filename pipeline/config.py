"""Settings load/save (settings.json) -- env/default merging, and the
first-run-only profanity-list seeding mechanism.

See docs/requirements/05-data-settings-and-logging.md (§Settings schema,
§Schema versioning, §Profanity list) and ADR-0005.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from pipeline.atomic_write import atomic_read_json, atomic_write_json

CURRENT_SCHEMA_VERSION = 1

# Ships at pipeline/profanity.txt, ported directly from epub-sanitize's own
# profanity.txt (docs/requirements/05-data-settings-and-logging.md
# §Profanity list) -- the word list itself is the author's own editorial
# call and out of scope for this project to change; only the
# copy-once-then-independent mechanism below is new.
_BUNDLED_PROFANITY_PATH = Path(__file__).parent / "profanity.txt"


class SettingsSchemaVersionError(Exception):
    """Raised when settings.json's schema_version is newer than this app
    understands -- see pipeline/state_manager.py's identical policy and
    docs/requirements/05-data-settings-and-logging.md §Schema versioning.
    """


# One migration function per version step -- see
# pipeline/state_manager.py's identical mechanism. Empty for now.
_MIGRATIONS: dict[int, Callable[[dict[str, Any]], dict[str, Any]]] = {}


def load_bundled_profanity_words() -> list[str]:
    """Read the bundled default profanity list shipped at
    pipeline/profanity.txt (66 words as of this writing, ported verbatim
    from epub-sanitize)."""
    with open(_BUNDLED_PROFANITY_PATH, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def _default_settings() -> dict[str, Any]:
    return {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "books_folder": "",
        "output_folder": "",
        "fix_names": True,
        "clean_language": True,
        # "none" routes to NullProvider regardless of ai_api_key -- the
        # pre-selected default on the first-run AI Helper Setup screen
        # (Epic 8), not a preference for one real provider over the other.
        "ai_provider": "none",
        "ai_api_key": "",
        "last_voice": "",
        # First-run seeding only -- see SettingsRepository.load()'s "first
        # run only" comment below for why an *existing* file's
        # profanity_words is never touched here.
        "profanity_words": load_bundled_profanity_words(),
    }


def _migrate(data: dict[str, Any]) -> dict[str, Any]:
    """Apply the schema-version policy from 05-data-settings-and-
    logging.md §Schema versioning (identical policy to
    pipeline/state_manager.py's `_migrate`, applied to settings.json)."""
    version = data.get("schema_version", 1)
    if version > CURRENT_SCHEMA_VERSION:
        raise SettingsSchemaVersionError(
            f"settings.json schema_version {version} is newer than this "
            f"app understands ({CURRENT_SCHEMA_VERSION})"
        )
    while version < CURRENT_SCHEMA_VERSION:
        step = _MIGRATIONS.get(version)
        if step is None:
            raise SettingsSchemaVersionError(
                f"no migration registered from schema_version {version}"
            )
        data = step(data)
        version = data["schema_version"]
    data.setdefault("schema_version", CURRENT_SCHEMA_VERSION)
    return data


@dataclass
class SettingsRepository:
    """Repository over settings.json -- atomic writes, schema versioning,
    and the first-run-only profanity list seed."""

    path: Path
    _data: dict[str, Any] = field(default_factory=dict, repr=False)
    _loaded: bool = field(default=False, repr=False)

    def load(self) -> dict[str, Any]:
        """Load settings.json, seeding the bundled profanity list only if
        this is a brand-new settings file (no file existed yet -- true
        first run). An *existing* file's `profanity_words` is never
        touched here: once seeded, her personal edits must stay
        independent of the bundled list forever after (05-data-settings-
        and-logging.md §Profanity list) -- a future app update shipping an
        improved bundled list must not silently overwrite what she's
        customized.
        """
        raw = atomic_read_json(self.path)
        self._data = _default_settings() if raw is None else _migrate(raw)
        self._loaded = True
        return self._data

    def save(self) -> None:
        """Persist current settings atomically (ADR-0005)."""
        if not self._loaded:
            raise RuntimeError("load() must be called before save()")
        self._data["schema_version"] = CURRENT_SCHEMA_VERSION
        atomic_write_json(self.path, self._data)
