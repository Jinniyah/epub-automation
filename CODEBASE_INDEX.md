# CODEBASE_INDEX.md

File map + migration/schema table. Kept current as epics land real code.

## File map

| Path | Status | Owned by |
|---|---|---|
| `main.py` | Real (Epic 6). CLI `rename`/`sanitize`/`audio`/`all`/`retag` commands wired to real stages via `pipeline/cli_runner.py`, non-interactively, over `settings.json`'s `books_folder`/`output_folder`. `all` chains stages through ephemeral temp dirs. `retag` takes a positional folder + `--author-first`/`--author-last`/`--title`/`--series`/`--series-number` overrides (new args, absent from the Epic 0 scaffold). `--workers` still reserved/validated only (ADR-0009). | Epic 0 / Epics 2-6 |
| `launcher.py` | Real (Epic 6). `find_free_port()` (OS-assigned, ADR-0008's host stays fixed), `open_browser()` retry-then-native-tkinter-fallback (07-packaging-deployment.md), a port sidecar file next to the lock file so a second launch can still reopen a tab despite dynamic port selection. | Epic 0 / Epic 6 / Epic 10 |
| `backend/app.py` | Real (Epic 6). Full JSON API route set — status polling, settings, folder picker, add/remove books (multipart upload), disk-space, batch start/start-generation, per-book confirm/voice/pause/cancel/collision/review/retag, voice-history, support-bundle, welcome-back (detection only, see below), quit. One `BatchRunner` per app instance; auto-replaced with a fresh one once `done` (`_current_runner()`). `_origin_is_allowed()`'s docstring carries a dev note pointing to `frontend/README.md`'s Vite-proxy fix for Epic 7 (see Session notes). | Epic 0 / Epic 6 |
| `backend/dialogs.py` | Real (Epic 6). `pick_folder()` via `tkinter.filedialog.askdirectory()`; `tk_factory`/`ask_directory` injectable seams so tests never open a real Tk window. | Epic 6 |
| `backend/bridge.py` | Real (Epic 6). `derive_batch_state()` — pure State Machine function, unit-tested independent of HTTP; one **documented deviation** from the literal precedence-rule text (see its own docstring) to correctly bucket the `review_result`/`output_collision` `needs_input` types this epic added. `build_status_response()`, `voice_history()`, `build_support_bundle()`/`write_support_bundle()` (secrets always stripped). | Epic 6 |
| `pipeline/batch_runner.py` | Real (Epic 6). `BatchRunner` — the stateful, interactive engine behind the GUI's polling contract: add/remove books (reuses `input_validation.py`), rename→sanitize identification loop (needs_input pauses never block the background thread), per-book/per-batch voice assignment (single-book auto-starts generation), serial audio generation (ADR-0009) with Pause/Cancel via `AudioStage`'s new Observer hooks, output-collision handling (`NeedsInputType.OUTPUT_COLLISION`, this epic's own addition — "distinct prompts for EPUB vs. audiobook"), manually-triggered retag (operates on the **output-folder copy**, not the internal Library copy ADR-0017 deletes), ADR-0017 cleanup. Keeps `state.json` genuinely current stage-by-stage (not just at the end), specifically ordered so a fast client can never race ahead of a stage's own persistence (see `_finish_generation`'s comment). | Epic 6 |
| `pipeline/cli_runner.py` | Real (Epic 6). `discover_books()`/`run_stage_over_folder()` — the CLI's much simpler, non-interactive counterpart to `BatchRunner` (no `needs_input`, no UI to answer one). | Epic 6 |
| `pipeline/input_validation.py` | Real (Epic 6). Screen-1 file validation — extension, real-zip validity (reuses `SafeZipOperation`), DRM detection (`META-INF/encryption.xml`), `MAX_FILES` capacity check. | Epic 6 |
| `pipeline/disk_space.py` | Real (Epic 6). Pre-batch disk-space estimate/check — composes `tts_engine.estimate_audio_bytes()` with the copy-based-storage formula and a real `shutil.disk_usage()` check. | Epic 6 |
| `pipeline/stage.py` | `Stage` Protocol + `BookState`. Real. | Epic 0 |
| `pipeline/atomic_write.py` | `atomic_write_json`/`atomic_read_json` (ADR-0005). Real. | Epic 0 |
| `pipeline/state_manager.py` | `StateRepository`, schema-versioned. Real. Extended Epic 6: `incomplete_book_ids()` — the "Welcome back" screen's data source, based on whether a book reached the terminal `"cleanup"` stage (ADR-0017), not on enumerating every individual stage. | Epic 0/6 |
| `pipeline/audit_logger.py` | `AuditLogRepository`, CSV wrapper. Real. | Epic 0 |
| `pipeline/single_instance.py` | `SingleInstanceLock`, PID stale-lock detection (ADR-0007, uses `psutil`). Real. | Epic 0 |
| `pipeline/safe_zip.py` | `SafeZipOperation` Template Method base. Real, base only. `_guard_xxe()` refined in Epic 6 — a real bug: the original check flagged any bare `<!DOCTYPE html>`, which every real XHTML file has. | Epic 0 (base) / Epic 2 / Epic 6 (`input_validation.py` subclass) |
| `pipeline/config.py` | `SettingsRepository`, first-run profanity seeding. Real. | Epic 0 |
| `pipeline/profanity.txt` | 61-entry default list, ported from `epub-sanitize`. | Epic 0 |
| `spike/kokoro_spike.py` | **Complete.** Verifies kokoro import, espeak-ng DLL load, KPipeline init, audio gen — in venv and as built `.exe`. Confirmed working on Windows 2026-07-08. | Epic 1 (done) |
| `pipeline/sanitize_stage.py` | Real (Epic 2). All 10 security controls from `PS_Run-CleanUpEpub.ps1`. `_ExtractEpub(SafeZipOperation)` + `SanitizeStage` w/ sidecar CSV + audit columns. | Epic 2 |
| `pipeline/rename_stage.py` | Real (Epic 3). `RenameStage` + `FILENAME_PATTERN`/`build_filename` ported from `epub-renamer`'s `renamer.py`/`main.py`; copy-based (not in-place rename) to fit this pipeline's stage-folder model; dry-run + name-conflict handling; silent per-file `NullProvider` fallback on AI failure. | Epic 3 |
| `pipeline/audio_stage.py` | Real (Epic 4, extended Epic 6). `AudioStage` — per-book chapter/chunk TTS loop, ID3 tagging via mutagen, per-chunk resume, retry-then-error. Reuses `rename_stage.build_filename()` directly (minus `.epub`) for the output folder/file base name. Epic 6 added `on_progress`/`should_stop` Observer-pattern hooks (optional, default `None`, backward-compatible) — `pipeline/batch_runner.py`'s only way to report progress and implement Pause/Cancel without this stage ever knowing an HTTP server or batch runner exists. | Epic 4/6 |
| `pipeline/retag_stage.py` | Real (Epic 5). `RetagStage` — fixes ID3 tags/filenames/**containing folder name** (bug fix over the original script) for an already-generated audiobook folder. Folder-name parsing (`parse_folder_metadata`/`parse_stem_metadata`) handles both the old standalone-tool shape and this pipeline's own `build_filename()` shape; reuses `rename_stage.build_filename()` directly for all naming (ADR-0016), same pattern `audio_stage.py` already uses. Always manually triggered (`applies_to()` always `False`). | Epic 5 |
| `pipeline/tts_engine.py` | Real (Epic 4). `TTSEngine` wraps `kokoro.KPipeline`, lazily imported/constructed (first real call only). `VOICES`/`DEFAULT_VOICE`, `estimate_audio_bytes()` (disk-space formula), `ensure_voice_samples()` (cache + version-tagging). MP3 encoding via `lameenc` at Kokoro's native 24kHz — see session notes below. | Epic 4 |
| `pipeline/epub_reader.py` | Real (Epic 3, extended Epic 4). `extract_epub_metadata`/`extract_text_sample` ported verbatim from `epub-renamer/epub_reader.py`; `extract_cover_bytes()` (Epic 4) ported verbatim from `epub-to-audio\epub_utils.py`, 3-strategy fallback, used for ID3 cover art. | Epic 3/4 |
| `pipeline/epub_utils.py` | Real (Epic 3, extended Epic 4). `sanitize_filesystem_name()` (ADR-0016) — new shared utility, used by rename, audio (Epic 4), and retag (Epic 5). `extract_chapters()`/`chunk_text()`/`normalise_heading()`/`MAX_CHUNK_CHARS` (Epic 4) ported verbatim from `epub-to-audio\epub_utils.py`. | Epic 3/4/5 |
| `pipeline/ai_providers/` | Real (Epic 3). `base.py`/`null_provider.py`/`openai_provider.py`/`registry.py` ported from `epub-renamer` (constructors adapted to take `api_key` explicitly, per ADR-0003); `gemini_provider.py` new, uses the `google-genai` SDK. | Epic 3 |
| `frontend/` | Placeholder `README.md` only, now including the Epic 7 dev-proxy/Origin-header decision (see Session notes). | Epic 7 |
| `tests/test_sanitize_stage.py` | 29 adversarial tests, all 10 controls. | Epic 2 |
| `tests/test_rename_stage.py`, `test_ai_providers.py`, `test_openai_provider.py`, `test_gemini_provider.py`, `test_epub_reader.py`, `test_epub_utils.py` | Epic 3 test suite (`test_epub_reader.py`/`test_epub_utils.py` extended Epic 4 — see below): `build_filename`/`FILENAME_PATTERN`/`RenameStage` (happy path, already-normalized, dry-run, name-conflict, AI failure fallback, corrupted EPUB), provider base/registry/Null/OpenAI/Gemini, `sanitize_filesystem_name` (incl. idempotency). | Epic 3 |
| `tests/test_retag_stage.py` | Epic 5 test suite, 29 tests. Folder-name parsing (old + new shapes), chapter-title/track-number derivation from MP3 filename suffix, ID3 tag rewriting, override-vs-parsed precedence, dry-run, idempotency, and the folder-rename regression test (`test_run_renames_folder_not_just_files`). | Epic 5 |
| `tests/test_tts_engine.py`, `test_audio_stage.py` | Epic 4 test suite. Fake `pipeline_factory`/fake TTS engine throughout — never downloads or runs the real Kokoro model. Covers: MP3 bitrate/sample-rate/mono verification, per-lang-code pipeline caching, `estimate_audio_bytes()` formula, `ensure_voice_samples()` version-mismatch/offline-failure behavior; chunk/chapter naming conventions, per-chunk resume, retry-then-error (partial chunks left intact), ID3 tagging incl. cover art, unknown-voice/missing-file/corrupted-EPUB/no-chapters error paths. `test_epub_utils.py`/`test_epub_reader.py` extended with `extract_chapters()`/`chunk_text()`/`normalise_heading()`/`extract_cover_bytes()` coverage. | Epic 4 |
| `tests/test_*.py` (stage, atomic_write, state_manager, audit_logger, single_instance, safe_zip, config) | Epic 0 test suite, incl. crash-mid-write, dead-PID, adversarial zip fixtures. `test_state_manager.py`/`test_safe_zip.py` extended Epic 6 (`incomplete_book_ids()`, the XXE-guard regression test). | Epic 0/6 |
| `tests/test_input_validation.py`, `test_disk_space.py`, `test_cli_runner.py` | Epic 6, pure-function/pipeline-level tests — no Flask/HTTP. | Epic 6 |
| `tests/test_batch_runner.py` | Epic 6, 25 tests. Real `RenameStage`/`SanitizeStage`/`AudioStage`/`RetagStage`, only the TTS engine faked. Covers the full add→identify→confirm→voice→generate→review→complete→cleanup lifecycle, output-collision resolve (`keep_both`/`replace`), Pause/Cancel (keep-partial vs. discard), resume-after-pause, and `state.json` staying genuinely current stage-by-stage. Uses a gated fake TTS engine (`threading.Event`) to land Pause/Cancel requests deterministically instead of racing real background-thread timing. | Epic 6 |
| `tests/test_bridge.py` | Epic 6, 24 tests. `derive_batch_state()` tested entirely against plain `BookState` objects (no HTTP, per docs/BACKLOG.md's own requirement) — every precedence boundary plus the two documented `needs_input`-type deviations; `build_status_response()`/`voice_history()`/`build_support_bundle()` shape and secret-stripping. | Epic 6 |
| `tests/test_app.py` | Epic 6, 29 tests. Flask test client throughout; `dialogs.pick_folder` always monkeypatched (never opens a real Tk window). Full single-book and multi-book HTTP flows, settings masking/persistence, every 400/409 error branch, the fresh-batch-after-`done` reset, and the `/api/quit` route verified without ever letting the real `os._exit` fire (would kill the test process). | Epic 6 |
| `tests/test_dialogs.py`, `test_launcher.py`, `test_main.py` | Epic 6. `test_launcher.py` proves `open_browser()`'s retry-then-fallback and the port-sidecar-file second-launch behavior without ever creating a real Tk window or binding a real server. `test_main.py` exercises `main.py`'s CLI commands end-to-end against real stages (fake nothing except never touching real Kokoro, since `audio`/`all` aren't directly tested end-to-end — `rename`/`sanitize`/`retag` are). | Epic 6 |
| `pyproject.toml` / `Makefile` | Toolchain, ported from `epub-renamer`, coverage config added. `[[tool.mypy.overrides]]` for `pipeline.audio_stage`/`pipeline.retag_stage` (Epic 4/5) and their test modules, `tests.test_main` (Epic 6, same mutagen partial-typing issue). | Epic 0/4/5/6 |
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

*Compacted 2026-07-10 — Epics 0-6 are closed and this history is an
archive, not active guidance; entries below are condensed to the
decisions/gotchas with lasting relevance. Full narrative detail from
before this pass is recoverable from git history if ever needed.*

**Pre-Epic-7 decision (2026-07-10):** the Origin/CSRF check added below
(Epic 6 post-review) will reject the Vite dev server's cross-origin
traffic once Epic 7 starts (different port than Flask's dynamic one).
Resolved as a frontend-side fix — Vite proxy + Origin-header rewrite,
documented in `frontend/README.md` and `01-architecture.md`'s API
reference — not a backend relaxation; `_origin_is_allowed()` itself is
unchanged. See `docs/BACKLOG.md` Epic 7's first checklist item.

**Epic 6 post-review fixes (2026-07-10):** post-commit security/
correctness review, all fixed same session. (1) HIGH — upload path
traversal in `/api/books` (attacker-controlled filename used to build a
save path); fixed via `secure_filename()` + a fail-closed resolved-path
check (`_safe_upload_path`). (2) HIGH — no CSRF/Origin protection on
mutating routes, letting another browser tab silently trigger them;
fixed via `_origin_is_allowed()` requiring `Origin` (when sent) to match
`request.host`, wired via `@app.before_request`. (3) support-bundle's
`technical_error` was unfillable client-side by design (no route ever
exposes raw error text); fixed to look it up server-side
(`bridge.py::current_error_detail()`). (4) `retag_route` always returned
`ok:true` on failure; fixed to return `422` on a real failure. (5)
`BatchRunner.start()`/`start_generation()` were a no-op if the thread was
already alive, stranding books added mid-run; fixed by re-scanning live
state each pass instead of a list captured once at thread-start. Also:
a `TTSEngineLike` Protocol closed a pre-existing CI `mypy` gap, and a
flaky `/api/quit` test (real `os._exit` firing during a later, unrelated
test after `monkeypatch` teardown) was fixed by switching to a harmless
route. 390 tests pass, 95.9% coverage, all linters clean.

**Epic 6 (2026-07-10):** backend/Flask bridge. `needs_input.type`
extended with `output_collision` (the original four-type list was
explicitly illustrative, not exhaustive). `derive_batch_state()`
deviates from the literal precedence-rule text in one documented way —
buckets a `needs_input` book by *which* step it's waiting on rather than
always `identifying` (own docstring has the full reasoning). Retag must
operate on the `output_folder` copy, not the internal `Library/03-Audio`
copy, since ADR-0017 deletes the latter on completion. A genuine TOCTOU
race was found by a test, not inspection: status flips were happening
before `state.json` persistence in two places; fixed to persist-then-
flip. `StateRepository.incomplete_book_ids()` checks only for the
terminal `"cleanup"` stage. `AudioStage` gained two optional Observer
hooks (`on_progress`/`should_stop`) for Pause/Cancel/progress, keeping
the stage itself HTTP-agnostic. "Welcome back" is detection-only this
epic (full resume deferred to Epic 8). CLI doesn't use `BatchRunner` (no
UI to answer a `needs_input` pause with); `pipeline/cli_runner.py` is a
simpler non-interactive folder loop instead. `/api/quit` uses
`os._exit(0)` from a short-delayed thread — accepted tradeoff, since
ADR-0007's stale-lock detection already treats an abrupt kill as
expected. Also fixed a stray `</content>` editing-tool artifact across
`requirements.txt` and five docs files (was breaking CI's `pip install`),
and a real XXE-guard false positive in `pipeline/safe_zip.py` (flagged
every bare `<!DOCTYPE html>`, not just a dangerous one — every real
XHTML file has one). 371 tests pass, 95%+ coverage.

**Epic 5 (2026-07-10):** retag stage port. The original `retag.py`'s
author-name handling is manual, not automatic — its docstring's "human
corrects this in the prompt" example was mistakenly read as code
behavior in an earlier pass; confirmed by reading the actual source, not
just the docstring. Filename/folder construction reuses
`rename_stage.build_filename()` rather than porting the original's own
builder. Missing-metadata handling deliberately does *not* use the
"Unknown, Unknown" fallback other stages use — retag operates on an
already-named folder, so that would be destructive, not just unhelpful.
Found + fixed a stray `</content>` artifact in `spike/kokoro_spike.py`
(broke `mypy .` repo-wide) while verifying. 233 tests pass.

**Epic 4 (2026-07-10):** audio stage. Two spec corrections made and
confirmed with the user before building on them: MP3 encoding needed
`lameenc` instead of `soundfile` (tops out ~21kbps, nowhere near the
required 128kbps CBR); sample rate is Kokoro's native 24kHz, not the
spec's originally-stated 48kHz (`04-tts-engine.md` corrected in place).
`kokoro.KPipeline`'s output is a `torch.FloatTensor`, converted without
importing `torch` directly in `tts_engine.py`. mutagen's partial typing
needs a scoped `disallow_untyped_calls = false` override at the *call
site's* module — mypy evaluates that flag there, not at the callee's.
`normalise_heading()`'s apostrophe-capitalization quirk preserved as a
verbatim-port artifact, not silently fixed. 204 tests pass.

**Epic 3 (2026-07-08):** rename stage + AI providers. Source repos read
directly from local sibling clones, not GitHub. Provider constructors
adapted to take `api_key` explicitly (settings.json-driven, not
`.env`-driven); registry key renamed `"null"` → `"none"`. `GeminiProvider`
uses `google-genai` (not the deprecated `google-generativeai`).
`build_filename()` sanitizes each component individually (ADR-0016)
rather than the original's blanket em-dash replacement. Rename copies
into `output_folder` under the new name rather than renaming in place
(stage folders are copy-based, ADR-0017). 147 tests pass.

**Epic 1+2 (2026-07-06) / CI fix + build-verification (2026-07-08):**
`regex` raises the built-in `TimeoutError`, not a module-specific one.
`SafeZipOperation` is a dataclass; `_ExtractEpub` needs an explicit
`__init__` (dataclass MRO conflict otherwise). `torch==2.12.1+cpu` needs
`--extra-index-url https://download.pytorch.org/whl/cpu` — documented
early but not actually wired into `ci.yml` until the 2026-07-08 fix. The
full `.exe` build needed three more `--collect-data`/`--collect-all`
flags beyond the original spike (`language_tags`, `misaki`, `soundfile`),
plus pre-installing `en_core_web_sm` via wheel URL (misaki's runtime
`pip`-download fails inside a frozen exe — no `pip` available there).
Verified: `dist\kokoro_spike.exe` produced a real 153KB `spike_output.wav`
standalone. 82→204 tests across this stretch.

**Epic 0:** `psutil` for PID liveness (small, well-established dep, not
ADR-worthy). 89% coverage, all linters clean.
