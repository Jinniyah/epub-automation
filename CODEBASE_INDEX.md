# CODEBASE_INDEX.md

File map + migration/schema table. Kept current as epics land real code.

## File map

| Path | Status | Owned by |
|---|---|---|
| `main.py` | Real (Epic 6). CLI `rename`/`sanitize`/`audio`/`all`/`retag` commands wired to real stages via `pipeline/cli_runner.py`, non-interactively, over `settings.json`'s `books_folder`/`output_folder`. `all` chains stages through ephemeral temp dirs. `retag` takes a positional folder + `--author-first`/`--author-last`/`--title`/`--series`/`--series-number` overrides (new args, absent from the Epic 0 scaffold). `--workers` still reserved/validated only (ADR-0009). | Epic 0 / Epics 2-6 |
| `launcher.py` | Real (Epic 6). `find_free_port()` (OS-assigned, ADR-0008's host stays fixed), `open_browser()` retry-then-native-tkinter-fallback (07-packaging-deployment.md), a port sidecar file next to the lock file so a second launch can still reopen a tab despite dynamic port selection. | Epic 0 / Epic 6 / Epic 10 |
| `backend/app.py` | Real (Epic 6). Full JSON API route set — status polling, settings, folder picker, add/remove books (multipart upload), disk-space, batch start/start-generation, per-book confirm/voice/pause/cancel/collision/review/retag, voice-history, support-bundle, welcome-back (detection only, see below), quit. One `BatchRunner` per app instance; auto-replaced with a fresh one once `done` (`_current_runner()`). | Epic 0 / Epic 6 |
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
| `pipeline/safe_zip.py` | `SafeZipOperation` Template Method base. Real, base only. `_guard_xxe()` refined in Epic 6 — see session notes below (a real bug: the original check flagged any bare `<!DOCTYPE html>`, which every real XHTML file has). | Epic 0 (base) / Epic 2 / Epic 6 (`input_validation.py` subclass) |
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
| `frontend/` | Placeholder `README.md` only. | Epic 7 |
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

**Epic 6 post-review fixes (2026-07-10):** a full security + correctness
review of the whole backend, requested after Epic 6 was committed and
pushed. Five real findings, all fixed same session, plus the CI-blocking
`mypy .` failure the user hit on GitHub Actions:

- **HIGH, security:** `/api/books`' upload handler (`backend/app.py`)
  built the on-disk save path directly from the client-supplied upload
  filename, with no sanitization — a crafted filename (`..\..\evil.epub`,
  or a full absolute path, which `pathlib` lets silently replace the
  temp-dir prefix entirely) could write anywhere the process has write
  access, including her Windows Startup folder, *before* any EPUB
  validation ran. Fixed with `werkzeug.utils.secure_filename()` plus a
  fail-closed resolved-path check (`backend/app.py::_safe_upload_path`).
- **HIGH, security:** no CSRF/Origin protection anywhere in `backend/`.
  Since several routes (`/api/quit`, `/api/batch/start`,
  `/api/batch/start-generation`, and the upload route itself) accept a
  body-less or non-JSON POST, a malicious webpage open in *another
  browser tab* while the app is running could trigger them via a simple
  cross-origin `fetch`/form POST that never triggers a CORS preflight —
  silently killing the server or (combined with the finding above)
  writing an arbitrary file, with zero interaction from her. Fixed with
  an `Origin`-header check (`backend/app.py::_origin_is_allowed`,
  wired via `@app.before_request`) requiring `Origin` to match
  `request.host` whenever it's present at all (non-browser clients that
  never send `Origin` are unaffected).
- **Correctness:** the "Copy details for support" bundle
  (06-safety-error-handling.md) could never actually work as specified —
  `build_status_response()` deliberately never exposes a book's raw
  error text (by design, so the polling endpoint never leaks a stack
  trace), but nothing else exposed it either, so the client had no way to
  supply `/api/support-bundle`'s `technical_error` field. Fixed by having
  that route look the current error up itself, server-side
  (`backend/bridge.py::current_error_detail()`), rather than trusting a
  client that was never told the answer.
- **Correctness:** `retag_route` always returned `ok: true` even when
  `RetagStage` genuinely failed, unlike every other mutating route. Fixed
  to check `updated.status` and return `422` with the real message.
- **Correctness:** `BatchRunner.start()`/`start_generation()` were a
  total no-op if their background thread was already alive — a book
  added (or reaching `voice_pick`) during that window was silently
  stranded until someone happened to call `start()`/`start_generation()`
  again *after* the thread had already exited, with no error surfaced
  anywhere. Fixed by making `_run_identification`/`_run_generation` loop
  against live book state each pass instead of a fixed list captured
  once at thread-start — genuinely self-healing now, proven by two new
  regression tests that gate a stage mid-run and add/queue more work
  while the thread is provably still alive. Resuming a paused book is
  now implemented as flipping it back to `voice_pick` (the same queue
  the self-healing loop already watches) rather than a separate case.
- **CI fix:** the `mypy .` failure the user hit on GitHub Actions
  (`tests/test_tts_engine.py`, `tests/test_audio_stage.py`) was the
  *same* pre-existing gap flagged-but-never-fixed in Epic 4/5's own
  session notes — fixed for real this time instead of continuing to
  document it as a known gap. Root cause for the `_FakeTTSEngine`
  vs. `TTSEngine` mismatches: added a `TTSEngineLike` Protocol
  (`pipeline/tts_engine.py`, just `generate()`) and typed
  `AudioStage`/`BatchRunner`/`create_app`'s `tts_engine` parameters
  against it instead of the concrete class — a real `TTSEngine` still
  satisfies it structurally, so no production call site changed, but
  test fakes no longer need a `# type: ignore`. The remaining untyped
  `ID3`/`MP3` mutagen calls got the same scoped
  `disallow_untyped_calls = false` override already used for
  `test_retag_stage`/`test_main`; one genuine `Optional` narrowing
  (`MP3(...).info` can be `None` per mutagen's own types) got a real
  `assert info is not None` instead of being silenced.
- Found and fixed one flaky test of its own making along the way: a new
  Origin-check test called `/api/quit` and monkeypatched `os._exit`
  without waiting for the route's delayed background thread to actually
  fire before returning — `monkeypatch` reverted the patch at teardown
  while that thread was still sleeping, so the thread's *real* `os._exit`
  call landed during a later, unrelated test and silently killed the
  whole pytest process. Switched that test to a harmless route instead of
  fixing it with more waiting, since it never needed `/api/quit`
  specifically.
- 390 total tests pass (up from 371), 95.9% coverage, `black`/`ruff`/
  `mypy --strict` (`mypy .`, matching CI exactly) all clean with zero
  remaining known gaps.

**Epic 6 (2026-07-10):** the backend/Flask bridge. Several real design
decisions and one class of bug surfaced during implementation, not just
routine wiring:

- **CI-blocking bug fixed first, unrelated to this epic:** `requirements.txt`
  had a stray literal `</content>` line appended at EOF — the exact same
  editing-tool artifact class Epic 5 found and fixed in
  `spike/kokoro_spike.py`, this time breaking `pip install -r
  requirements.txt` in CI outright (not just `mypy`). Grepped the whole
  repo for the same pattern and found four more docs files silently
  carrying it (`CLAUDE.md`, `CODEBASE_INDEX.md` itself, `docs/BACKLOG.md`,
  `docs/requirements/07-packaging-deployment.md`,
  `docs/design/SYSTEM_DESIGN.md`) — all stripped.
- **Real pre-existing bug found and fixed in `pipeline/safe_zip.py`'s XXE
  guard:** the original sniff flagged *any* `<!DOCTYPE` declaration, not
  just a dangerous one (external `SYSTEM`/`PUBLIC` reference or an
  internal subset). A bare `<!DOCTYPE html>` — what every real XHTML file
  has, including ebooklib's own generated output — was being rejected as
  an XXE payload. `sanitize_stage.py`'s own hand-crafted adversarial
  fixtures never happened to include a plain doctype, so this sat latent
  until `pipeline/input_validation.py` became this guard's first caller
  against realistic EPUB content. Fixed to only flag a DOCTYPE containing
  `SYSTEM`, `PUBLIC`, or an internal subset (`[`); a bare `<!ENTITY`
  anywhere is still caught independently either way. Two new regression
  tests in `tests/test_safe_zip.py`.
- **`needs_input.type` extended with `output_collision`** (not one of the
  four types 01-architecture.md's own example lists) — that list is
  explicitly illustrative ("an object *like*"), and docs/BACKLOG.md's own
  Epic 6 checklist requires "distinct prompts for EPUB vs. audiobook"
  collision handling, which the original four types have no room for.
- **`derive_batch_state()` deviates from the literal precedence-rule
  text in one documented way:** the rule as written buckets *any*
  `needs_input` book under `identifying`, written before `needs_input.type`
  grew to cover `review_result` (post-generation) and `output_collision`
  (mid-generation) — taken completely literally, a book awaiting Review
  would incorrectly demote the whole batch back to the per-book
  identification screen. Resolved by bucketing a `needs_input` book by
  *which* step it's actually waiting on instead. Full reasoning in
  `derive_batch_state()`'s own docstring.
- **Retag must operate on the `output_folder` copy, not the internal
  `Library/03-Audio` copy** — a real bug caught by design review before
  it shipped: ADR-0017 deletes the internal copy the moment a book
  reaches `complete`, so retagging it instead of the persistent copy
  would have silently discarded her corrections the instant cleanup ran.
  `BatchRunner.retag_book()` swaps to `output_audio_folder` before
  invoking `RetagStage`, then restores the internal-copy bookkeeping
  field afterward so ADR-0017 cleanup still finds the right (now
  superseded) internal folder.
- **A genuine TOCTOU race, found by a test, not by inspection:** the
  audio-generation background thread was updating a book's visible
  `needs_input: review_result` status *before* persisting `"audio"`
  complete to `state.json`. A sufficiently fast client answering the
  review immediately could race ahead of that write. Fixed by persisting
  first, then flipping the visible status — same ordering fix applied to
  the collision-resolution path. Two more pre-existing gaps found the
  same way: `_cleanup_library_copies()` and `_finalize_cancel()` were
  calling `state_repo.mark_stage_complete()`/`reset_stage()` without ever
  calling `.save()` afterward, meaning `state.json` — the documented data
  source for "Welcome back" — was silently never being written for those
  two paths. All three fixed; `test_batch_runner.py::
  test_state_file_is_kept_current_as_each_stage_finishes` is the
  regression test.
- **`StateRepository.incomplete_book_ids()`** (new) — deliberately checks
  only for the terminal `"cleanup"` stage (ADR-0017), not for every
  individual stage being present, since `state.json` has no field
  recording which stages a given run's toggles even included; checking
  for every stage by name would have required threading that context
  through just for this one query.
- **`AudioStage` gained two optional, backward-compatible Observer hooks**
  (`on_progress`, `should_stop`, both default `None`) — the only way
  `BatchRunner` gets progress numbers and implements Pause/Cancel without
  this stage ever knowing an HTTP server or batch runner exists
  (docs/design/PATTERNS.md's Observer pattern). `should_stop` is checked
  before each chunk, so a paused book's already-written chunks stay
  intact — the existing resume-by-file-size mechanism just works.
- **"Welcome back" is detection-only this epic**, not full state-file-driven
  resume (rebuilding a live `BatchRunner` from `state.json` after a
  backend restart) — `GET /api/welcome-back` answers "is anything
  pending," which is genuinely useful and newly reliable now that
  `state.json` is kept current (see above), but actually reconstructing
  a resumed batch is real, separate work deferred to Epic 8, once the
  "Welcome back" screen exists to drive it.
- **CLI (`main.py`) does not use `BatchRunner`** — it has no UI to answer
  a `needs_input` pause with, so `pipeline/cli_runner.py` is a much
  simpler, non-interactive folder loop shared by `rename`/`sanitize`/
  `audio`/`all`. `all` chains the three stages through ephemeral
  `tempfile.TemporaryDirectory` folders, respecting each stage's toggle
  (a skipped stage still copies files forward unchanged, or the next
  stage would find nothing to read). `retag`'s CLI surface (a positional
  folder + override flags) didn't exist in the Epic 0 scaffold at all —
  added new this epic, mirroring `RetagStage`'s existing overrides.
- **`/api/quit` uses `os._exit(0)` from a short-delayed background
  thread**, not a graceful waitress shutdown — waitress's `serve()` call
  has no clean in-process stop hook reachable from a request handler
  without deeper restructuring. Accepted as a pragmatic tradeoff: the
  already-built stale-lock detection (ADR-0007) already treats an
  abruptly-killed process as an expected, recoverable case, so this
  doesn't introduce a new failure mode, just relies on one already
  designed for.
- Dynamic free-port selection (`launcher.py::find_free_port()`) broke the
  Epic 0 scaffold's assumption of a fixed, well-known port for a second
  launch to reopen a tab to — fixed with a small port-sidecar file next
  to the lock file, written/cleaned up by `launcher.py` only (not
  `pipeline/single_instance.py`, keeping that module scoped to liveness
  only, per ADR-0007).
- 371 total tests pass (up from 233), 95%+ coverage, `black`/`ruff`
  clean. `mypy .` clean except the pre-existing, already-documented Epic 4
  gap (`tests/test_tts_engine.py`/`test_audio_stage.py`'s own untyped
  mutagen calls and `_FakeTTSEngine`/`TTSEngine` structural mismatch,
  unchanged this session, still out of scope) — every file this epic
  touched or added is itself clean, including a new `SnapshotSource`
  Protocol in `backend/bridge.py` so `build_status_response()` depends on
  a capability (`.snapshot()`) rather than the concrete `BatchRunner`
  class, letting tests supply a plain fake.

**Epic 5 (2026-07-10):** the original `retag.py` has no real author
first/last semantics -- `parse_filename_metadata()` stores whatever text
sits before/after a separator verbatim, and the module docstring's
"Benedict, Jacka -> Jacka, Benedict" example is a human correcting the
field in the interactive prompt, not something the code does
automatically (confirmed by reading the actual source, not just the
docstring -- the same "verify, don't just trust" discipline
`docs/design_review.md` credits this project with elsewhere). The port
splits parsed author text on the first comma into `author_last`/
`author_first` (this pipeline's shape everywhere else), which is
unambiguous for this pipeline's own folders and structurally equivalent
(same ambiguity, not a regression) for legacy folders from the old
standalone tool. Filename/folder construction reuses
`rename_stage.build_filename()` directly rather than porting the
original's own `build_new_filename()` -- cross-checked against the
original docstring's own example shape (`Jacka, Benedict — Alex Verus
#01 — Fated`), which matches `build_filename()`'s zero-padded `#NN`
output exactly. Missing-metadata handling deliberately does *not* match
`RenameStage`/`AudioStage`'s "Unknown, Unknown — Unknown" fallback --
retag operates on an *already*-named folder, so silently renaming it to
"Unknown" on a parse failure would be destructive, not just unhelpful;
kept the original script's fail-closed behavior instead. Found and fixed
a pre-existing, unrelated bug while verifying: `spike/kokoro_spike.py`
had a stray literal `</content>` line appended at EOF (an old
editing-tool artifact), which broke `mypy .` for the entire repo with a
syntax error -- removed. Also found that `tests/test_audio_stage.py` and
`tests/test_tts_engine.py` (Epic 4) currently fail `mypy --strict` on
their own (untyped `mutagen`/`ID3`/`MP3` calls, plus one real
`_FakeTTSEngine` vs. `TTSEngine` arg-type mismatch) despite Epic 4's
session notes claiming a clean run -- left as-is (pre-existing, not
introduced this session, out of scope for Epic 5) but flagged here
rather than silently ignored; `tests/test_retag_stage.py` got its own
scoped mypy override to stay genuinely clean. 233 total tests pass (up
from 204), `black`/`ruff` clean.

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
