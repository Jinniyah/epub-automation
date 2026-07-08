# CODEBASE_INDEX.md

Created during the first build session (Epic 0), per `CLAUDE.md`
§Documentation & session close #2. File map + migration/schema table --
kept current as later epics land real stage/backend/frontend code.

## File map

| Path | Status | Owned by |
|---|---|---|
| `main.py` | Scaffold -- argument parsing, `--workers` seam, single-instance lock. No stage logic yet. | Epic 0 (scaffold) / Epics 2-5 (real stage calls) |
| `launcher.py` | Scaffold -- fixed `127.0.0.1` bind, single-instance lock, serves the placeholder Flask app. | Epic 0 (scaffold) / Epic 6 (real routes) / Epic 10 (free-port discovery, browser-fallback) |
| `backend/__init__.py` | Package marker. | Epic 0 |
| `backend/app.py` | Scaffold -- Flask app factory with a `/api/health` route only. | Epic 0 (scaffold) / Epic 6 (real routes) |
| `backend/dialogs.py` | Placeholder -- `pick_folder()` raises `NotImplementedError`. | Epic 6 |
| `backend/bridge.py` | Placeholder -- empty module, docstring only. Will hold `derive_batch_state()` and the Adapter logic. | Epic 6 |
| `pipeline/__init__.py` | Package marker. | Epic 0 |
| `pipeline/stage.py` | `Stage` Protocol + `BookState` (Pipeline pattern). Real. | Epic 0 |
| `pipeline/atomic_write.py` | `atomic_write_json` / `atomic_read_json` (ADR-0005). Real. | Epic 0 |
| `pipeline/state_manager.py` | `StateRepository` -- schema-versioned state file wrapper. Real. | Epic 0 |
| `pipeline/audit_logger.py` | `AuditLogRepository` -- CSV audit log wrapper. Real. | Epic 0 |
| `pipeline/single_instance.py` | `SingleInstanceLock` -- PID-based stale-lock detection (ADR-0007). Real. | Epic 0 |
| `pipeline/safe_zip.py` | `SafeZipOperation` Template Method base (path traversal -> zip-bomb -> XXE). Real, base only -- no concrete stage subclasses yet. | Epic 0 (base) / Epic 2 (sanitize_stage.py subclass) / Epic 8 (Screen-1 validation subclass) |
| `pipeline/config.py` | `SettingsRepository` -- settings.json load/save, first-run profanity seeding. Real. | Epic 0 |
| `pipeline/profanity.txt` | Bundled default word list (61 entries), ported verbatim from `epub-sanitize/profanity.txt`. | Epic 0 |
| `spike/kokoro_spike.py` | Epic 1 spike: verifies kokoro import, espeakng-loader DLL load, KPipeline init, and audio generation. Step 1 (venv run) confirmed working. Step 2 (PyInstaller build+exe test) still to-do. | Epic 1 |
| `pipeline/rename_stage.py` | Not yet created. | Epic 3 |
| `pipeline/sanitize_stage.py` | Real implementation (Epic 2, 2026-07-06). All 10 security controls from `PS_Run-CleanUpEpub.ps1`: path-traversal guard, zip-bomb cap, XXE prevention, profanity-list size cap, Unicode whole-word matching (`regex` package), asterisk replacement, `.xhtml`/`.html` scope, mimetype-first repack, ReDoS timeout (5s), temp-dir cleanup. `_ExtractEpub(SafeZipOperation)` subclass + `SanitizeStage` with sidecar CSV + audit-log columns. | Epic 2 |
| `pipeline/audio_stage.py` | Not yet created. | Epic 4 |
| `pipeline/retag_stage.py` | Not yet created. | Epic 5 |
| `pipeline/tts_engine.py` | Not yet created. | Epic 4 |
| `pipeline/epub_reader.py` | Not yet created. | Epic 3 |
| `pipeline/epub_utils.py` | Not yet created. | Epic 3/4 |
| `pipeline/ai_providers/` | Not yet created (ported from `epub-renamer` except `gemini_provider.py`, which is new). | Epic 3 |
| `frontend/` | Not yet scaffolded -- placeholder `README.md` only. | Epic 7 |
| `tests/test_sanitize_stage.py` | 29 adversarial tests for all 10 security controls in `SanitizeStage`, including path-traversal, zip-bomb, XXE, ReDoS, and profanity-list cap. | Epic 2 |
| `tests/test_stage.py` | Tests the `Stage` Protocol against a minimal fake implementation. | Epic 0 |
| `tests/test_atomic_write.py` | Includes a simulated crash-mid-write test. | Epic 0 |
| `tests/test_state_manager.py` | Includes schema-version mismatch/migration tests. | Epic 0 |
| `tests/test_audit_logger.py` | CSV wrapper tests, including the `ai_api_key` exclusion. | Epic 0 |
| `tests/test_single_instance.py` | Includes a simulated dead-PID stale-lock test. | Epic 0 |
| `tests/test_safe_zip.py` | Adversarial fixtures: path traversal, zip bomb (size + ratio), XXE. | Epic 0 |
| `tests/test_config.py` | Settings load/save, first-run profanity seeding, schema versioning. | Epic 0 |
| `pyproject.toml` | Toolchain config, ported from `epub-renamer` + coverage config added. | Epic 0 |
| `requirements.txt` | Exactly pinned dependencies (see §Migration/schema table note below). | Epic 0 |
| `Makefile` | Ported from `epub-renamer`, `coverage` target added (80% floor). | Epic 0 |
| `.github/workflows/ci.yml` | Backend CI job (lint/typecheck/test/coverage). `pip install` step includes `--extra-index-url` for PyTorch CPU wheels (fixed 2026-07-08, see notes below). Frontend job deferred to Epic 7. | Epic 0 |
| `.env.example` | CLI/advanced-use env vars. | Epic 0 |

## Schema / migration table

| File | Current `schema_version` | Migration mechanism |
|---|---|---|
| `%APPDATA%\EpubAutomation\settings.json` | 1 | `pipeline/config.py::_MIGRATIONS` (empty -- nothing to migrate from yet) |
| `%APPDATA%\EpubAutomation\state.json` | 1 | `pipeline/state_manager.py::_MIGRATIONS` (empty -- nothing to migrate from yet) |
| `%APPDATA%\EpubAutomation\audit_log.csv` | N/A (CSV, not versioned) | New columns are appended to `pipeline/audit_logger.py::COLUMNS`, never inserted/reordered |

When a future change needs a new settings/state field: bump
`CURRENT_SCHEMA_VERSION` in the relevant module, add one function to that
module's `_MIGRATIONS` dict keyed by the *old* version number, and add a
row to this table.

## Notes carried from Epic 0's build session

- **Dependency pinning gap found and fixed:** `docs/requirements/08-open-
  questions-and-assumptions.md` says dependency pinning is "Tracked as a
  backlog item -- see docs/BACKLOG.md Epic 0," but Epic 0's story list in
  `docs/BACKLOG.md` didn't actually have a line item for it. Added one
  (see BACKLOG.md's changelog note at the top of Epic 0) and implemented
  it: `requirements.txt` pins exact versions for every dependency Epic 0
  actually introduces. `kokoro`/`torch` (Epic 1/4) and
  `google-generativeai` (Epic 3) are intentionally not yet listed --
  they'll be pinned when those epics introduce the import.
- **New dependency not called out elsewhere in the design docs:**
  `pipeline/single_instance.py` uses `psutil` for cross-platform PID
  liveness/process-name checks (ADR-0007 specifies *what* the stale-lock
  check must do, not *how* to check PID liveness). This is a small,
  well-established dependency chosen to keep the stale-lock policy
  readable rather than tangled with OS-specific `ctypes` calls. Not
  ADR-worthy on its own (no real alternative was seriously weighed against
  it), but flagged here since it's a dependency the design docs don't
  mention.
- All Epic 0 tests pass locally with `pytest -m "not slow"` at 89% combined
  `pipeline`/`backend` coverage (80% floor from
  `docs/requirements/09-testing-strategy.md`), and `black`/`ruff`/`mypy
  --strict` are all clean.

## Notes carried from Epic 1+2's build session (2026-07-06)

- **`regex.TimeoutError` does not exist** (regex==2026.6.28): the `regex`
  module raises Python's built-in `TimeoutError` (subclass of `OSError`)
  when a substitution times out, not a module-specific exception.
  `sanitize_stage.py` uses `except TimeoutError:` accordingly.
- **`_ExtractEpub` is not a `@dataclass`**: `SafeZipOperation` is a
  `@dataclass`; subclassing it with additional fields while also
  `@dataclass`-decorating the subclass causes MRO problems. Solved by
  writing an explicit `__init__` on `_ExtractEpub` that calls
  `super().__init__(...)` and sets `self.extract_to` separately.
- **`espeakng-loader==0.2.4`** ships `espeak-ng.dll` + `espeak-ng-data/`
  as a Python wheel. PyInstaller can't auto-detect the ctypes DLL load;
  `--collect-data espeakng_loader` is required. See
  `docs/requirements/07-packaging-deployment.md` §Known packaging constraints.
- **`torch==2.12.1+cpu`** must be installed from the PyTorch CPU-only
  index (`--index-url https://download.pytorch.org/whl/cpu`), not PyPI.
  The `+cpu` local version label is part of the version string.
- All 82 project tests pass after Epic 2; coverage and lint status
  confirmed before the session ended.

## Notes carried from 2026-07-08 CI fix session

- **CI broke on `torch==2.12.1+cpu`:** the note above (torch needs the
  PyTorch CPU index) was captured here during Epic 1+2 but never actually
  wired into `.github/workflows/ci.yml` -- the install step was still a
  plain `pip install -r requirements.txt`, which only checks PyPI and
  fails with "No matching distribution found for torch==2.12.1+cpu"
  (PyPI has no `+cpu` build for that version, only the plain-CUDA one and
  earlier releases). Fixed by adding
  `--extra-index-url https://download.pytorch.org/whl/cpu` to the install
  step. Used `--extra-index-url`, not `--index-url`, so the rest of
  `requirements.txt` still resolves from PyPI as normal -- only `torch`
  (and any future PyTorch-ecosystem pin) falls through to the CPU wheel
  index. Lesson: a note in this file describing a fix doesn't mean the
  fix shipped -- check the actual CI config, not just the documentation
  trail, when a dependency-resolution error recurs.
