# CODEBASE_INDEX.md

File map + migration/schema table. Kept current as epics land real code.

## File map

| Path | Status | Owned by |
|---|---|---|
| `main.py` | Scaffold — arg parsing, `--workers` seam, single-instance lock. No stage logic yet. | Epic 0 / Epics 2-5 |
| `launcher.py` | Scaffold — fixed `127.0.0.1` bind, single-instance lock, placeholder Flask app. | Epic 0 / Epic 6 / Epic 10 |
| `backend/app.py` | Scaffold — `/api/health` only. | Epic 0 / Epic 6 |
| `backend/dialogs.py` | Placeholder — `pick_folder()` raises `NotImplementedError`. | Epic 6 |
| `backend/bridge.py` | Placeholder — empty, will hold `derive_batch_state()`. | Epic 6 |
| `pipeline/stage.py` | `Stage` Protocol + `BookState`. Real. | Epic 0 |
| `pipeline/atomic_write.py` | `atomic_write_json`/`atomic_read_json` (ADR-0005). Real. | Epic 0 |
| `pipeline/state_manager.py` | `StateRepository`, schema-versioned. Real. | Epic 0 |
| `pipeline/audit_logger.py` | `AuditLogRepository`, CSV wrapper. Real. | Epic 0 |
| `pipeline/single_instance.py` | `SingleInstanceLock`, PID stale-lock detection (ADR-0007, uses `psutil`). Real. | Epic 0 |
| `pipeline/safe_zip.py` | `SafeZipOperation` Template Method base. Real, base only. | Epic 0 (base) / Epic 2 / Epic 8 (subclasses) |
| `pipeline/config.py` | `SettingsRepository`, first-run profanity seeding. Real. | Epic 0 |
| `pipeline/profanity.txt` | 61-entry default list, ported from `epub-sanitize`. | Epic 0 |
| `spike/kokoro_spike.py` | **Complete.** Verifies kokoro import, espeak-ng DLL load, KPipeline init, audio gen — in venv and as built `.exe`. Confirmed working on Windows 2026-07-08. | Epic 1 (done) |
| `pipeline/sanitize_stage.py` | Real (Epic 2). All 10 security controls from `PS_Run-CleanUpEpub.ps1`. `_ExtractEpub(SafeZipOperation)` + `SanitizeStage` w/ sidecar CSV + audit columns. | Epic 2 |
| `pipeline/rename_stage.py` | Real (Epic 3). `RenameStage` + `FILENAME_PATTERN`/`build_filename` ported from `epub-renamer`'s `renamer.py`/`main.py`; copy-based (not in-place rename) to fit this pipeline's stage-folder model; dry-run + name-conflict handling; silent per-file `NullProvider` fallback on AI failure. | Epic 3 |
| `pipeline/audio_stage.py` | Real (Epic 4). `AudioStage` — per-book chapter/chunk TTS loop, ID3 tagging via mutagen, per-chunk resume, retry-then-error. Reuses `rename_stage.build_filename()` directly (minus `.epub`) for the output folder/file base name. | Epic 4 |
| `pipeline/retag_stage.py` | Not yet created. | Epic 5 |
| `pipeline/tts_engine.py` | Real (Epic 4). `TTSEngine` wraps `kokoro.KPipeline`, lazily imported/constructed (first real call only). `VOICES`/`DEFAULT_VOICE`, `estimate_audio_bytes()` (disk-space formula), `ensure_voice_samples()` (cache + version-tagging). MP3 encoding via `lameenc` at Kokoro's native 24kHz — see session notes below. | Epic 4 |
| `pipeline/epub_reader.py` | Real (Epic 3, extended Epic 4). `extract_epub_metadata`/`extract_text_sample` ported verbatim from `epub-renamer/epub_reader.py`; `extract_cover_bytes()` (Epic 4) ported verbatim from `epub-to-audio\epub_utils.py`, 3-strategy fallback, used for ID3 cover art. | Epic 3/4 |
| `pipeline/epub_utils.py` | Real (Epic 3, extended Epic 4). `sanitize_filesystem_name()` (ADR-0016) — new shared utility, used by rename, audio (Epic 4), and retag (Epic 5). `extract_chapters()`/`chunk_text()`/`normalise_heading()`/`MAX_CHUNK_CHARS` (Epic 4) ported verbatim from `epub-to-audio\epub_utils.py`. | Epic 3/4/5 |
| `pipeline/ai_providers/` | Real (Epic 3). `base.py`/`null_provider.py`/`openai_provider.py`/`registry.py` ported from `epub-renamer` (constructors adapted to take `api_key` explicitly, per ADR-0003); `gemini_provider.py` new, uses the `google-genai` SDK. | Epic 3 |
| `frontend/` | Placeholder `README.md` only. | Epic 7 |
| `tests/test_sanitize_stage.py` | 29 adversarial tests, all 10 controls. | Epic 2 |
| `tests/test_rename_stage.py`, `test_ai_providers.py`, `test_openai_provider.py`, `test_gemini_provider.py`, `test_epub_reader.py`, `test_epub_utils.py` | Epic 3 test suite (`test_epub_reader.py`/`test_epub_utils.py` extended Epic 4 — see below): `build_filename`/`FILENAME_PATTERN`/`RenameStage` (happy path, already-normalized, dry-run, name-conflict, AI failure fallback, corrupted EPUB), provider base/registry/Null/OpenAI/Gemini, `sanitize_filesystem_name` (incl. idempotency). | Epic 3 |
| `tests/test_tts_engine.py`, `test_audio_stage.py` | Epic 4 test suite. Fake `pipeline_factory`/fake TTS engine throughout — never downloads or runs the real Kokoro model. Covers: MP3 bitrate/sample-rate/mono verification, per-lang-code pipeline caching, `estimate_audio_bytes()` formula, `ensure_voice_samples()` version-mismatch/offline-failure behavior; chunk/chapter naming conventions, per-chunk resume, retry-then-error (partial chunks left intact), ID3 tagging incl. cover art, unknown-voice/missing-file/corrupted-EPUB/no-chapters error paths. `test_epub_utils.py`/`test_epub_reader.py` extended with `extract_chapters()`/`chunk_text()`/`normalise_heading()`/`extract_cover_bytes()` coverage. | Epic 4 |
| `tests/test_*.py` (stage, atomic_write, state_manager, audit_logger, single_instance, safe_zip, config) | Epic 0 test suite, incl. crash-mid-write, dead-PID, adversarial zip fixtures. | Epic 0 |
| `pyproject.toml` / `Makefile` | Toolchain, ported from `epub-renamer`, coverage config added. `[[tool.mypy.overrides]]` for `pipeline.audio_stage` (Epic 4, see session notes below). | Epic 0/4 |
| `requirements.txt` | Exactly pinned. `en_core_web_sm`/`soundfile` added Epic 1. `lameenc`/`numpy` added Epic 4 (MP3 encoding). | Epic 0/1/4 |
| `.github/workflows/ci.yml` | Backend CI job. `--extra-index-url` for PyTorch CPU wheels (fixed 2026-07-08). Frontend job deferred to Epic 7. | Epic 0 |
| `.env.example` | CLI/advanced-use env vars. | Epic 0 |

## Schema / migration table

| File | `schema_version` | Migration mechanism |
|---|---|---|
| `settings.json` | 1 | `pipeline/config.py::_MIGRATIONS` (empty) |
| `state.json` | 1 | `pipeline/state_manager.py::_MIGRATIONS` (empty) |
| `audit_log.csv` | N/A | New columns appended to `COLUMNS`, never reordered |

Future field: bump `CURRENT_SCHEMA_VERSION`, add a `_MIGRATIONS` entry
keyed by old version, add a row here.

## Session notes

**Epic 0:** `psutil` used for PID liveness (not in design docs, small
well-established dep, not ADR-worthy). 89% coverage, `black`/`ruff`/`mypy
--strict` clean.

**Epic 1+2 (2026-07-06):** `regex` module raises built-in `TimeoutError`,
not a module-specific exception. `SafeZipOperation` is a `@dataclass`;
`_ExtractEpub` uses an explicit `__init__` + `super().__init__()` rather
than also being `@dataclass` (MRO conflict). `torch==2.12.1+cpu` needs
`--index-url https://download.pytorch.org/whl/cpu`. 82 tests pass.

**CI fix (2026-07-08):** `torch==2.12.1+cpu` isn't on plain PyPI; CI
needed `--extra-index-url https://download.pytorch.org/whl/cpu` added to
the install step (the fix was documented earlier but never actually
wired into `ci.yml`).

**Epic 1 build+exe verification (2026-07-08):** the 2026-07-06 spike
only ran inside an activated venv; the full PyInstaller build surfaced
gaps invisible until running the actual `.exe`. Three data-only packages
needed explicit collect flags (same root cause as espeak-ng — ctypes/
`importlib.resources` data invisible to static analysis): `language_tags`
(`--collect-data`), `misaki` (`--collect-data`), `soundfile`
(`--collect-all`). One genuinely new runtime dependency: `en_core_web_sm`
— misaki auto-downloads this spaCy model via `pip` on first use if
absent, which works in a venv but fails inside a frozen exe (no `pip`
available). Fixed by pre-installing the wheel before building. Full
command in `spike/kokoro_spike.py` and `07-packaging-deployment.md`.
Verified: `dist\kokoro_spike.exe` run standalone on Windows produced a
real 153KB `spike_output.wav`. PyInstaller's `warn-*.txt` output (~1000
"missing module" lines from `--collect-all torch`) reviewed and
dismissed as noise — all optional GPU/distributed-training/POSIX-only
paths not exercised by this project. `spike/kokoro_spike.py`'s docstring
also had a `^`/backtick (cmd.exe vs. PowerShell) inconsistency, fixed in
the same session.

**Epic 4 (2026-07-10):** two implementation decisions the requirements
doc left unresolved (or got wrong) before a real spike existed to check
against, both confirmed with the user before building on them:
- **MP3 encoding library:** `soundfile`/libsndfile (already pinned from
  Epic 1's WAV-writing spike) can technically write MP3, but only via a
  `compression_level` quality knob (0.0-0.9), not a real bitrate control
  — measured ~21kbps at its highest setting, nowhere near the 128kbps
  CBR this app's disk-space formula requires. `lameenc` (compiled LAME
  binding, prebuilt Windows wheels, no subprocess/external binary) hits
  exact CBR bitrates and is now pinned instead.
- **Sample rate:** 04-tts-engine.md said 48kHz; Kokoro-82M's real output
  is 24kHz (the Epic 1 spike itself already hardcodes `samplerate=24000`
  when writing its WAV). Encoding now uses the native rate — upsampling
  can't add real fidelity and would need a new resampling dependency for
  no benefit. 04-tts-engine.md corrected in place rather than left
  silently diverging from the code.

`kokoro.KPipeline`'s `Result.audio` is a `torch.FloatTensor`, not a plain
numpy array — `pipeline/tts_engine.py::_audio_to_numpy()` handles the
`.detach().cpu().numpy()` conversion without importing `torch` directly
in this module.

mutagen ships a `py.typed` marker, but its ID3 frame classes (`TIT2`/
`TPE1`/...) aren't fully annotated — unlike `ebooklib`/`bs4` (no
`py.typed` at all, so `ignore_missing_imports` already makes them `Any`
with no strict-mode complaints), a *partially* typed dependency still
trips `disallow_untyped_calls`. mypy evaluates that flag at the **call
site's** module, not the callee's, so the `pyproject.toml` override
targets `pipeline.audio_stage` itself, not `mutagen.*` — a `mutagen.*`
override would have had no effect. `pipeline/retag_stage.py` (Epic 5)
will need the same override added when it lands.

Building a test EPUB with a cover image needs `ebooklib.epub.EpubImage`
(→ `ITEM_IMAGE`) — `EpubBook.set_cover()`'s own authoring helper produces
an `EpubCover` item (→ `ITEM_COVER`, a different constant), which
`extract_cover_bytes()`'s real-world-EPUB-shaped strategy 1 correctly
doesn't match. Found by a fixture returning `None` unexpectedly; not a
bug in the ported function, since real EPUBs (Calibre etc.) use the
`EpubImage`-equivalent shape, not ebooklib's own round-trip helper.

`normalise_heading()` (ported verbatim, ADR-0014) has a small pre-existing
quirk: its own docstring in the source project claims
`"AUTHOR'S NOTE" -> "Author's Note"`, but the code only `capitalize()`s
the part *before* an apostrophe, leaving `"Author'S Note"` for an
all-caps input. Preserved as-is (a verbatim port, not a fix that was
asked for) and documented in `tests/test_epub_utils.py` rather than
silently corrected.

204 total tests pass (up from 147), 95%+ coverage, `black`/`ruff`/
`mypy --strict` clean.

**Epic 3 (2026-07-08):** the three source repos (`epub-renamer`,
`epub-sanitize`, `epub-to-audio`) are cloned locally as sibling
directories under `C:\Users\jinni\source\repos\` — read directly from
there rather than fetched from GitHub. `epub-renamer`'s `ai_providers/`
constructors originally read `OPENAI_API_KEY` from a module-level
`.env`-backed `config.py`; adapted to take `api_key` explicitly via the
constructor since this project's key is per-install/settings.json-driven
(ADR-0003), not `.env`-driven. Registry provider keys renamed `"null"` →
`"none"` to match settings.json's `ai_provider` vocabulary. `GeminiProvider`
uses `google-genai` (the actively maintained unified SDK), not the
deprecated `google-generativeai` package — added to `requirements.txt`.
`build_filename()` now sanitizes each Title/Author/Series component
individually via `epub_utils.sanitize_filesystem_name()` before assembly
(ADR-0016), replacing the original's blanket em-dash character
replacement. The rename stage copies into `output_folder` under the new
name (this pipeline's stage folders are copy-based, ADR-0017) rather than
renaming in place, unlike the original standalone CLI tool. `MAX_FILES`
batch-level enforcement is deliberately not in this stage — `Stage.run()`
is per-book by design (`docs/design/PATTERNS.md`); `DEFAULT_MAX_FILES`
is exported for Epic 6/8 to wire up when a real batch runner exists. 147
total tests pass, 94% coverage, `black`/`ruff`/`mypy --strict` clean.
</content>
