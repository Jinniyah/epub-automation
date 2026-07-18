# CODEBASE_INDEX.md

File map + migration/schema table. Kept current as epics land real code.

## File map

| Path | Status | Owned by |
|---|---|---|
| `main.py` | Real (Epic 6). CLI `rename`/`sanitize`/`audio`/`all`/`retag` commands wired to real stages via `pipeline/cli_runner.py`, non-interactively, over `settings.json`'s `books_folder`/`output_folder`. `all` chains stages through ephemeral temp dirs. `retag` takes a positional folder + `--author-first`/`--author-last`/`--title`/`--series`/`--series-number` overrides (new args, absent from the Epic 0 scaffold). `--workers` still reserved/validated only (ADR-0009). | Epic 0 / Epics 2-6 |
| `launcher.py` | Real (Epic 6). `find_free_port()` (OS-assigned, ADR-0008's host stays fixed), `open_browser()` retry-then-native-tkinter-fallback (07-packaging-deployment.md), a port sidecar file next to the lock file so a second launch can still reopen a tab despite dynamic port selection. | Epic 0 / Epic 6 / Epic 10 |
| `backend/app.py` | Real (Epic 6, extended Epic 8/9). Full JSON API route set — status polling, settings, folder picker, add/remove books (multipart upload), disk-space, batch start/start-generation, per-book confirm/voice/pause/cancel/collision/review/retag, voice-history, support-bundle, welcome-back, cleanup-in-progress (Epic 9), quit. **Epic 8 additions**, all found genuinely missing while building the real frontend against this contract, not pre-planned: `GET /api/voices` + `GET /api/voice-samples/<voice>` (voice picker list + preview playback; the former is also this app's lazy voice-sample-cache trigger point), `POST /api/books/<id>/metadata` (multi-book voice table's clickable-title metadata edit, distinct from `confirm` and `retag`), `POST /api/books/<id>/open-folder` + `POST /api/open-output-folder` (Review screen's two "📂 See..." links — no raw filesystem path ever crosses the wire, both resolved server-side). **Epic 9 additions:** `_build_runner(restore=True)` seeds the one runner built at process startup from `state_repo.incomplete_book_snapshots()` — full "Welcome back" resume, not just detection (`AppState.new_runner()`'s "batch done -> fresh runner" reset stays `restore=False`, deliberately never resurrects a genuinely finished batch); `POST /api/cleanup-in-progress` (the "nuke everything in progress" escape hatch, replaces the in-memory runner afterward since it may hold now-deleted books/files). One `BatchRunner` per app instance; auto-replaced with a fresh one once `done` (`_current_runner()`). | Epic 0 / Epic 6 / Epic 8 / Epic 9 |
| `backend/dialogs.py` | Real (Epic 6, extended Epic 8). `pick_folder()` via `tkinter.filedialog.askdirectory()`; `tk_factory`/`ask_directory` injectable seams so tests never open a real Tk window. Epic 8 added `open_folder()` (`os.startfile`, Windows-only) for the same two Review-screen links above — **`tests/test_app.py` monkeypatches this globally (autouse fixture)**, same as `pick_folder`, after an early Epic 8 session accidentally popped real Explorer windows during a full local test run before that fixture existed. | Epic 6 / Epic 8 |
| `backend/bridge.py` | Real (Epic 6, extended Epic 8/9). `derive_batch_state()` — pure State Machine function, unit-tested independent of HTTP; one **documented deviation** from the literal precedence-rule text (see its own docstring) to correctly bucket the `review_result`/`output_collision` `needs_input` types this epic added. `build_status_response()`, `voice_history()`, `build_support_bundle()`/`write_support_bundle()` (secrets always stripped). Epic 8 added `voice_choices()` — strips `tts_engine.VOICES`' display strings down to plain first names for the picker. **Epic 9 added `reset_all_in_progress()`** — the "clean up stuck in-progress state" mechanism: a best-effort sweep of every `Library/*` stage folder plus a full `StateRepository.reset_all()`, deliberately never correlated with any live tracked `Book`. | Epic 6 / Epic 8 / Epic 9 |
| `pipeline/batch_runner.py` | Real (Epic 6, extended Epic 8). `BatchRunner` — the stateful, interactive engine behind the GUI's polling contract: add/remove books (reuses `input_validation.py`), rename→sanitize identification loop (needs_input pauses never block the background thread), per-book/per-batch voice assignment, serial audio generation (ADR-0009) with Pause/Cancel via `AudioStage`'s new Observer hooks, output-collision handling (`NeedsInputType.OUTPUT_COLLISION`), manually-triggered retag (operates on the **output-folder copy**, not the internal Library copy ADR-0017 deletes), ADR-0017 cleanup. Keeps `state.json` genuinely current stage-by-stage, specifically ordered so a fast client can never race ahead of a stage's own persistence (see `_finish_generation`'s comment). **Epic 8 additions:** `add_book()` gained an `original_filename` override (a real bug found via a live browser smoke test — the GUI upload route's collision-avoiding temp filename, e.g. `0_Fated.epub`, was leaking into what Screen 1 displayed; the safe temp name is still what the internal `00-Incoming/` copy uses, only the *display* value changed); `update_metadata()` (the voice table's clickable-title edit, restricted to `voice_pick`); and a real bug fix in `_maybe_enter_voice_pick()` — it used to also trigger the single-book auto-start-generation the instant a book reached `voice_pick`, before the picker screen could ever matter, contradicting `assign_voice()`'s own docstring ("picking a voice and pressing Next starts generating"). Both were found while building/live-testing the real Epic 8 voice-picker screen against this existing Epic 6 code, not by the pre-existing unit suite. **Note (2026-07-17, confirmed while investigating a Pause/Cancel feedback report):** this file's pause/cancel/resume logic itself was already correct — `request_pause()`/`request_cancel()` just set flags, `AudioStage`'s `should_stop` hook applies them at the next chunk boundary, and `start_generation()` already resumes any `paused` book by re-queueing it as `voice_pick` (see that method's own docstring). No backend change was needed; the real gap was frontend-only (see Session notes below). **Epic 9 additions:** a new `_set_book()` helper centralizes every status-changing mutation's state-file snapshot persistence (deliberately not used by the high-frequency `_on_audio_progress()` chunk callback); `restore_books()` seeds a freshly-constructed runner from persisted snapshots at process startup, coarse-graining `generating`/`paused` to `voice_pick` and `identifying` to `pending`; `_finalize_cancel()` now also marks the `cleanup` stage complete (a pre-existing gap — a cancelled book previously stayed "incomplete" forever). | Epic 6 / Epic 8 / Epic 9 |
| `pipeline/cli_runner.py` | Real (Epic 6). `discover_books()`/`run_stage_over_folder()` — the CLI's much simpler, non-interactive counterpart to `BatchRunner` (no `needs_input`, no UI to answer one). | Epic 6 |
| `pipeline/input_validation.py` | Real (Epic 6). Screen-1 file validation — extension, real-zip validity (reuses `SafeZipOperation`), DRM detection (`META-INF/encryption.xml`), `MAX_FILES` capacity check. | Epic 6 |
| `pipeline/disk_space.py` | Real (Epic 6). Pre-batch disk-space estimate/check — composes `tts_engine.estimate_audio_bytes()` with the copy-based-storage formula and a real `shutil.disk_usage()` check. | Epic 6 |
| `pipeline/stage.py` | `Stage` Protocol + `BookState`. Real. | Epic 0 |
| `pipeline/atomic_write.py` | `atomic_write_json`/`atomic_read_json` (ADR-0005). Real. | Epic 0 |
| `pipeline/state_manager.py` | `StateRepository`, schema-versioned. Real. Extended Epic 6: `incomplete_book_ids()` — the "Welcome back" screen's data source, based on whether a book reached the terminal `"cleanup"` stage (ADR-0017), not on enumerating every individual stage. **Extended Epic 9:** schema bumped to v2 — `save_book_snapshot()`/`incomplete_book_snapshots()` persist each book's full `status`/`data`, not just stage flags (full "Welcome back" resume); `reset_all()` (the "clean up stuck in-progress state" escape hatch). | Epic 0/6/9 |
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
| `pipeline/tts_engine.py` | Real (Epic 4, extended Epic 8). `TTSEngine` wraps `kokoro.KPipeline`, lazily imported/constructed (first real call only). `VOICES`/`DEFAULT_VOICE`, `estimate_audio_bytes()` (disk-space formula), `ensure_voice_samples()` (cache + version-tagging, now typed against `TTSEngineLike` rather than the concrete class — one less coupling point). MP3 encoding via `lameenc` at Kokoro's native 24kHz — see session notes below. Epic 8 added `installed_kokoro_version()` (package-metadata-only, never imports `kokoro` itself) to finally wire up `ensure_voice_samples()`'s cache-invalidation trigger, deferred since Epic 4/6. | Epic 4 / Epic 8 |
| `pipeline/epub_reader.py` | Real (Epic 3, extended Epic 4). `extract_epub_metadata`/`extract_text_sample` ported verbatim from `epub-renamer/epub_reader.py`; `extract_cover_bytes()` (Epic 4) ported verbatim from `epub-to-audio\epub_utils.py`, 3-strategy fallback, used for ID3 cover art. | Epic 3/4 |
| `pipeline/epub_utils.py` | Real (Epic 3, extended Epic 4). `sanitize_filesystem_name()` (ADR-0016) — new shared utility, used by rename, audio (Epic 4), and retag (Epic 5). `extract_chapters()`/`chunk_text()`/`normalise_heading()`/`MAX_CHUNK_CHARS` (Epic 4) ported verbatim from `epub-to-audio\epub_utils.py`. | Epic 3/4/5 |
| `pipeline/ai_providers/` | Real (Epic 3). `base.py`/`null_provider.py`/`openai_provider.py`/`registry.py` ported from `epub-renamer` (constructors adapted to take `api_key` explicitly, per ADR-0003); `gemini_provider.py` new, uses the `google-genai` SDK. | Epic 3 |
| `frontend/` | Real (Epic 7/8). Vite + React 19 + TypeScript, built with `npm create vite@latest -- --template react-ts` then reworked: **oxlint replaced with ESLint 9** (flat config, `eslint-plugin-jsx-a11y` + `eslint-plugin-react-hooks` — pinned to the classic 5.x line, not the newer React-Compiler-flavored 7.x, since this project doesn't use the Compiler and several of its rules assume it) so `eslint-plugin-jsx-a11y` could be wired in at all. `src/api/` (`client.ts`/`types.ts`) is the one module that knows the Flask JSON API's shapes; `src/hooks/` (`usePollingStatus`, `useFocusTrap`, `useAriaLiveThrottled`); `src/components/shared/` (`BigButton`, `RadioRow`, `ToggleSwitch`, `EditableFieldRow`, `Overlay`, `FieldCorrectionPopup`, `VoicePicker`, `LiveRegion`); `src/viewmodels/` (`useVoiceAssignmentView`, `useWorkingScreenView`); `src/screens/` (one file per screen in `03-gui-ux-design.md`'s encounter order); `src/App.tsx` (the one top-level container — owns onboarding-phase routing + the single `usePollingStatus()` every screen is built from). **216 tests across 32 files** (confirmed via a real `npm test` run 2026-07-18, after Epic 9's `StepProgress` component + wiring), coverage comfortably above the 80% floor. `vite.config.ts` implements the dev-proxy/Origin-rewrite this directory's own `README.md` already specified. `index.css`'s spacing-utility family (`main > * + *`, `.stack-sm`, and now `.stack`/`.stack-md`, 2026-07-17) is the one place vertical rhythm is controlled app-wide — see that file's own comments before adding a new one-off margin anywhere. **Recurring nesting-depth gotcha, worth checking for elsewhere:** any component that renders its own single wrapping element (rather than being a direct child of `main`/`.overlay`) loses that ancestor's `> * + *` spacing rule for its *own* children, one level too deep to be reached — this bit both `VoicePicker` (heading/list, `main`'s rule) and `ConfirmMetadataScreen`'s `asOverlay` mode (field-list/Save button, `.overlay`'s rule), fixed the same way both times with a `.stack`/`.stack-md` wrapper scoped to just the affected pair (2026-07-17, see Session notes below). Also gained `.progress-bar` (2026-07-17) -- a native `<progress>` element styled via vendor pseudo-elements rather than a `<div>` with inline `width`, since the latter would need the `style` prop this same stylesheet's own ESLint rule forbids. | Epic 7/8 |
| `frontend/src/screens/*.tsx` | Real (Epic 8, extended Epic 9). `FoldersScreen` (first-launch + "⚙️ Change my folders", same component), `AiHelperSetup` (intro→choice→key, one component covering all three steps), `WelcomeBack` (degrades honestly to a plain count only for the rare pre-Epic-9-migration/never-snapshotted case now — see its own module comment; the common "backend restarted" case is now genuinely resumed, not just detected, see Epic 9 Session notes below), `AddBooksScreen`, `ConfirmMetadataScreen` (also reused inside an `Overlay` from the voice table, `asOverlay` prop — **overlay-mode spacing fixed 2026-07-17**, see that file's own docstring and Session notes below), `VoiceAssignmentScreen`, `WorkingScreen` (Pause/Cancel/Resume feedback and the chunk-progress readout both added and verified 2026-07-17, see Session notes), `CollisionPrompt`, `ReviewScreen`, `FixInfoFlow`, `WordsScreen`, `VoiceHistoryScreen`, `ErrorScreen`. **`MoreOptionsScreen` gained a fifth entry Epic 9** — "🧹 Nuke everything in progress," confirm-gated via `Overlay`, calls the new `cleanupInProgress()` API client function. **Epic 9 also wired `StepProgress`** (new shared component, see its own row below) into `AddBooksScreen`/`ConfirmMetadataScreen`/`VoiceAssignmentScreen`/`WorkingScreen`/`CollisionPrompt`/`ReviewScreen`/`FixInfoFlow` — the five main-flow screens plus `CollisionPrompt` (a pause within Convert). All wired together in `App.tsx` (unchanged by Epic 9 — the full-resume fix needed no frontend change at all, see Session notes). | Epic 8/9 |
| `frontend/src/components/shared/VoicePicker.tsx` | Real (Epic 8). Full voice-picker list, used standalone (single-book) and inside an `Overlay` ("Change Voice"). **Spacing fixed 2026-07-17** (real screenshot + follow-up request) — heading-to-list and inter-row gaps were both zero; see that file's own docstring and Session notes below for the fix and the deliberate decision to leave the 70px row-height accessibility floor unchanged. | Epic 8 |
| `frontend/src/components/shared/StepProgress.tsx` | Real (Epic 9). The "you are here" wizard bar — `<nav>`/`<ol>` of five steps (Add Books/Confirm Info/Choose Voice/Convert/Review), `aria-current="step"`, non-color-only current/completed markers (checkmark glyph vs. filled/outlined circle, not color alone), an optional active-book-title line tied to the `<nav>` via `aria-describedby`. New `.step-progress*` CSS in `index.css`. See Session notes below for the multi-book "active book" state, which turned out to already exist. | Epic 9 |
| `frontend/src/**/*.test.{ts,tsx}` | Real (Epic 7/8), co-located with the code they test. Vitest + React Testing Library + `vitest-axe` (axe-core assertions in nearly every component/screen test — needed a hand-written local `declare module "vitest"` augmentation in `src/test/vitest-axe.d.ts`, since `vitest-axe@0.1.0`'s own shipped types target an older `Vi.Assertion` global-namespace convention vitest 4.x no longer reads). | Epic 7/8 |
| `tests/test_sanitize_stage.py` | 29 adversarial tests, all 10 controls. | Epic 2 |
| `tests/test_rename_stage.py`, `test_ai_providers.py`, `test_openai_provider.py`, `test_gemini_provider.py`, `test_epub_reader.py`, `test_epub_utils.py` | Epic 3 test suite (`test_epub_reader.py`/`test_epub_utils.py` extended Epic 4 — see below): `build_filename`/`FILENAME_PATTERN`/`RenameStage` (happy path, already-normalized, dry-run, name-conflict, AI failure fallback, corrupted EPUB), provider base/registry/Null/OpenAI/Gemini, `sanitize_filesystem_name` (incl. idempotency). | Epic 3 |
| `tests/test_retag_stage.py` | Epic 5 test suite, 29 tests. Folder-name parsing (old + new shapes), chapter-title/track-number derivation from MP3 filename suffix, ID3 tag rewriting, override-vs-parsed precedence, dry-run, idempotency, and the folder-rename regression test (`test_run_renames_folder_not_just_files`). | Epic 5 |
| `tests/test_tts_engine.py`, `test_audio_stage.py` | Epic 4 test suite. Fake `pipeline_factory`/fake TTS engine throughout — never downloads or runs the real Kokoro model. Covers: MP3 bitrate/sample-rate/mono verification, per-lang-code pipeline caching, `estimate_audio_bytes()` formula, `ensure_voice_samples()` version-mismatch/offline-failure behavior; chunk/chapter naming conventions, per-chunk resume, retry-then-error (partial chunks left intact), ID3 tagging incl. cover art, unknown-voice/missing-file/corrupted-EPUB/no-chapters error paths. `test_epub_utils.py`/`test_epub_reader.py` extended with `extract_chapters()`/`chunk_text()`/`normalise_heading()`/`extract_cover_bytes()` coverage. | Epic 4 |
| `tests/test_*.py` (stage, atomic_write, state_manager, audit_logger, single_instance, safe_zip, config) | Epic 0 test suite, incl. crash-mid-write, dead-PID, adversarial zip fixtures. `test_state_manager.py`/`test_safe_zip.py` extended Epic 6 (`incomplete_book_ids()`, the XXE-guard regression test). `test_state_manager.py` extended again Epic 9 (schema v1→v2 migration, `save_book_snapshot()`/`incomplete_book_snapshots()`/`reset_all()`). | Epic 0/6/9 |
| `tests/test_input_validation.py`, `test_disk_space.py`, `test_cli_runner.py` | Epic 6, pure-function/pipeline-level tests — no Flask/HTTP. | Epic 6 |
| `tests/test_batch_runner.py` | Epic 6, extended Epic 9, 38 tests. Real `RenameStage`/`SanitizeStage`/`AudioStage`/`RetagStage`, only the TTS engine faked. Covers the full add→identify→confirm→voice→generate→review→complete→cleanup lifecycle, output-collision resolve (`keep_both`/`replace`), Pause/Cancel (keep-partial vs. discard), resume-after-pause, and `state.json` staying genuinely current stage-by-stage. Uses a gated fake TTS engine (`threading.Event`) to land Pause/Cancel requests deterministically instead of racing real background-thread timing. **Epic 9 additions:** `restore_books()` coarse-graining per status bucket, a real end-to-end round trip (pause a book, then build a brand-new `BatchRunner`/`StateRepository` pair from the same on-disk file, simulating a real process restart), the cancel/`cleanup`-stage fix. | Epic 6/9 |
| `tests/test_bridge.py` | Epic 6, 24 tests. `derive_batch_state()` tested entirely against plain `BookState` objects (no HTTP, per docs/BACKLOG.md's own requirement) — every precedence boundary plus the two documented `needs_input`-type deviations; `build_status_response()`/`voice_history()`/`build_support_bundle()` shape and secret-stripping. | Epic 6 |
| `tests/test_app.py` | Epic 6, extended Epic 9, 59 tests. Flask test client throughout; `dialogs.pick_folder` always monkeypatched (never opens a real Tk window). Full single-book and multi-book HTTP flows, settings masking/persistence, every 400/409 error branch, the fresh-batch-after-`done` reset, and the `/api/quit` route verified without ever letting the real `os._exit` fire (would kill the test process). **Epic 9 additions:** a real two-separate-`create_app()`-instances-against-the-same-`appdata_dir` test proving full "Welcome back" resume (not just one app's in-memory runner), `/api/cleanup-in-progress` happy path + the no-live-runner-knowledge case + the audit-log-untouched guarantee. | Epic 6/9 |
| `tests/test_dialogs.py`, `test_launcher.py`, `test_main.py` | Epic 6, extended Epic 8 (`test_dialogs.py`: `open_folder()` coverage). `test_launcher.py` proves `open_browser()`'s retry-then-fallback and the port-sidecar-file second-launch behavior without ever creating a real Tk window or binding a real server. `test_main.py` exercises `main.py`'s CLI commands end-to-end against real stages (fake nothing except never touching real Kokoro, since `audio`/`all` aren't directly tested end-to-end — `rename`/`sanitize`/`retag` are). | Epic 6 / Epic 8 |
| `pyproject.toml` / `Makefile` | Toolchain, ported from `epub-renamer`, coverage config added. `[[tool.mypy.overrides]]` for `pipeline.audio_stage`/`pipeline.retag_stage` (Epic 4/5) and their test modules, `tests.test_main` (Epic 6, same mutagen partial-typing issue). | Epic 0/4/5/6 |
| `requirements.txt` | Exactly pinned. `en_core_web_sm`/`soundfile` added Epic 1. `lameenc`/`numpy` added Epic 4 (MP3 encoding). | Epic 0/1/4 |
| `frontend/package.json` | Exactly pinned (no `^`/`~`), matching `requirements.txt`'s convention. React 19, Vite 8, TypeScript 6.0.2 (deliberately not the newer 7.x `create-vite` itself declined to default to), ESLint 9 + `typescript-eslint` + `eslint-plugin-jsx-a11y` + `eslint-plugin-react-hooks@5` (classic line, see `frontend/` row above), Vitest 4 + `@testing-library/react` + `vitest-axe` + `@vitest/coverage-v8`. | Epic 7 |
| `.github/workflows/ci.yml` | Backend + **frontend** CI jobs. Backend: `--extra-index-url` for PyTorch CPU wheels (fixed 2026-07-08). Frontend (Epic 7): lint (eslint incl. jsx-a11y) → typecheck (tsc) → test+coverage (80% floor, incl. the axe-core assertions already embedded in component tests, `npm ci`/Node 24). | Epic 0 / Epic 7 |
| `.env.example` | CLI/advanced-use env vars. | Epic 0 |

## Schema / migration table

| File | `schema_version` | Migration mechanism |
|---|---|---|
| `settings.json` | 1 | `pipeline/config.py::_MIGRATIONS` (empty) |
| `state.json` | 2 (Epic 9) | `pipeline/state_manager.py::_MIGRATIONS` — `1 -> 2` (`_migrate_v1_to_v2`, no shape change; v2 adds an optional per-book `"snapshot"` key for full "Welcome back" resume, absent on migrated v1 data until a book's status next changes) |
| `audit_log.csv` | N/A | New columns appended to `COLUMNS`, never reordered |

Future field: bump `CURRENT_SCHEMA_VERSION`, add a `_MIGRATIONS` entry
keyed by old version, add a row here.

## Session notes

**Epic 9 code-buildable items (2026-07-18):** four items closed in one
session — full "Welcome back" resume, "clean up stuck in-progress
state," the step-progress indicator, and confirming the axe-core/
jsx-a11y CI item was already true. 448 backend tests / 96% coverage, 216
frontend tests / 32 files, both clean via a real `pytest --cov` and a
real `npm run build && npm run lint && npm test` pass, this session.

- **Full "Welcome back" resume — the real architectural finding:**
  `state.json` only ever stored per-stage completion flags
  (`book_id -> {stage: {status}}`), never the book's actual data
  (filename, title, voice, etc.), and `backend/app.py::_build_app_state()`
  builds a brand-new, empty `BatchRunner` every time the Flask process
  starts. So even though `state.json` always knew *which* book ids were
  incomplete, there was never enough persisted data to rebuild them —
  "Continue" landing on an empty Screen 1 was a direct consequence of
  that gap, not a frontend bug. Fix: `state.json` schema bumped to v2 to
  also persist a full `{"status", "data"}` snapshot per book
  (`StateRepository.save_book_snapshot()`/`incomplete_book_snapshots()`),
  written by a new `BatchRunner._set_book()` helper that centralizes
  every status-changing mutation's persistence (replacing ~20 scattered
  `self._books[book_id] = ...` call sites) — deliberately **not** used by
  `_on_audio_progress()`, which fires once per audio chunk, since
  `AudioStage.run()` already resumes a book by checking existing MP3 file
  sizes on disk per chunk (the exact mechanism a *paused* book's resume
  already relied on), so persisting exact chunk progress was never
  actually necessary. `BatchRunner.restore_books()` seeds a fresh runner
  from persisted snapshots at startup, coarse-graining `generating`/
  `paused` -> `voice_pick` (free resume via that same disk-check) and
  `identifying` -> `pending` (confirmed by reading `rename_stage.py`:
  it copies its source, never deletes it, so redoing identification from
  scratch is always safe). Verified end-to-end with a real two-separate-
  `create_app()`-instances test (`tests/test_app.py`) and a real
  pause-then-rebuild-from-disk test (`tests/test_batch_runner.py`), not
  just unit tests of the coarse-graining logic in isolation.
- **Pre-existing bug found in the same pass:** `_finalize_cancel()` never
  marked the `cleanup` stage complete, so a cancelled book stayed
  "incomplete" forever and would have kept reappearing as "pending" on
  every future launch. Fixed alongside the resume work since it shares
  the exact same code path.
- **"Clean up stuck in-progress state":** `POST /api/cleanup-in-progress`
  (`backend/bridge.py::reset_all_in_progress()`) does a best-effort sweep
  of all four `Library/*` stage folders plus `StateRepository.reset_all()`
  — deliberately never correlated with any live tracked `Book`, since the
  case that prompted this (files deleted outside the app) means there's
  nothing left to correlate with. Frontend: a confirm-gated "🧹 Nuke
  everything in progress" button on `MoreOptionsScreen`, reusing the
  exact same `Overlay` confirm-dialog pattern `WorkingScreen`'s Cancel
  flow already established.
- **Step-progress indicator:** built as `StepProgress.tsx` and rendered
  by each of the five main-flow screens themselves (plus `CollisionPrompt`)
  right after their own `<h1>`, rather than lifted into `App.tsx` — every
  screen already had (or could trivially compute) its own "active book"
  without needing that state threaded through a parent. The multi-book
  voice table's "most recently opened row" requirement turned out to
  already exist as `VoiceAssignmentScreen`'s own `changingVoiceFor`/
  `editingMetadataFor` local state — confirmed by reading the current
  implementation before assuming new state was needed.
- **`axe-core`/`eslint-plugin-jsx-a11y` CI item:** already true. Reading
  `.github/workflows/ci.yml` confirmed the frontend `lint` job already
  runs `eslint-plugin-jsx-a11y` and the `coverage` job already runs the
  axe-core assertions already present in every screen's test file — just
  a stale checkbox, no code change.
- **Left open, as human-only:** manual keyboard-only pass, real NVDA/
  Narrator pass, screen-reader tester, her-facing copy dry-run,
  per-series voice memory second look — none of these can be completed
  by an AI agent.
- **The real dyslexic-reader test moved to `docs/BACKLOG.md`'s new Wish
  List section, same day:** the tester previously lined up for it
  (ADR-0015, `00-overview-and-goals.md`) is no longer available. Not
  dropped, just blocked on finding a new tester — the app's dyslexic-
  reader-facing design work itself (typography, plain language) is
  already built and unaffected, only the real-person verification step
  is on hold.
- **Real concurrency bug found and fixed during this same pass, not a
  separate session:** the `_set_book()` refactor above raised how often
  `StateRepository.save()` gets called from multiple threads at once (the
  identification/generation background threads and the HTTP request
  thread) by a lot — and `StateRepository`/`atomic_write_json` had no
  locking of their own. This was already a latent, pre-existing gap (the
  same unprotected pattern existed before Epic 9, just triggered far less
  often), but the higher write frequency made it a real, reproducible
  Windows `PermissionError` (`os.replace()` failing with "Access is
  denied" when two threads' writes overlapped) — caught by running the
  full suite with `--cov` (which slows things down enough to widen the
  race window) three times in a row and seeing two different, unrelated
  tests fail intermittently. Fixed by widening every `with self._lock:`
  block in `batch_runner.py` to cover the `self._state_repo` calls
  themselves, not just the in-memory `self._books` dict update — verified
  clean across three consecutive full-suite-with-coverage runs afterward
  (each run had shown at least one flake before the fix; none did after).

**Frontend test-count correction (2026-07-17):** a real `npm test` run
reported **199 tests across 31 files**, all passing. This corrects the
"331 frontend tests" figure that had been carried in this file (and in
`README.md`/`CLAUDE.md`) since the original Epic 7+8 session note
below -- since no tests were ever removed between then and now, only
added, the true count was always lower than 331; that original figure
was simply wrong, not stale. Fixed at every mention across the three
docs.

**2026-07-17 second verification pass:** a real `npm run build`,
`npm run lint`, and `npm test` all passed clean against the
Working-screen chunk-progress readout (below), reported directly by
the user in a second, separate pass run right after the four-fix
batch further below was already confirmed. Not run in this session
(filesystem-only MCP access throughout).

**Working-screen chunk-progress readout (2026-07-17, real follow-up
request, verified in the second pass above):** closes
docs/BACKLOG.md Epic 8.5's own "visible chunk-progress readout" item,
specifically asking for "Working on file N of M..." updating live in
the blank space between the friendly status line and the Pause/Cancel
buttons -- `progress.chunks_done`/`chunks_total` were already in every
poll response, just never surfaced. Added the text line (N =
`chunks_done + 1` capped at the total -- the chunk currently in
flight) plus a real progress bar underneath, inside the existing
`.card`. **Used a native `<progress>` element, not a styled `<div>`:**
a hand-rolled fill bar needs a dynamic inline `width`, which the
app-wide `style`-prop ban (Epic 8.6, `frontend/eslint.config.js`)
forbids -- `<progress value max>` lets the browser own the fill
percentage and ships with `role="progressbar"`/`aria-valuenow`
semantics for free, styled via `::-webkit-progress-bar`/
`::-webkit-progress-value`/`::-moz-progress-bar` in `index.css` (new
`.progress-bar` class) instead. Shown regardless of pause state -- a
paused book's last-known chunk position is still useful context.
`WorkingScreen.test.tsx` extended with readout-text, bar value/max,
cap-at-total, no-progress-yet, and paused-still-shows-progress
coverage. Full writeup: `docs/BACKLOG.md` Epic 8.5's own checklist
item.

**2026-07-17 frontend-fix batch, verified:** a real `npm run build`,
`npm run lint`, and `npm test` all passed clean against the four
2026-07-17 frontend fixes together (Working-screen Pause/Cancel/
Resume feedback, VoicePicker heading/row spacing, the "Fix info"
overlay spacing fix, and the earlier `.screen-actions` DOM-ordering
fix) -- reported directly by the user, not run in this session
(filesystem-only MCP access throughout). The four session notes below
retain their original "not yet verified" wording as written at the
time; this note is the confirmation that landed after.

**"Fix info" overlay spacing fix (2026-07-17, real screenshot):**
same underlying bug class as the VoicePicker spacing fix immediately
below, one level deeper. `ConfirmMetadataScreen`'s `asOverlay` mode
renders as a single wrapping `<div>` -- the sole `children` `Overlay`
receives -- so `.overlay`'s own `> * + *` rhythm (index.css, space-4)
correctly spaces `Overlay`'s `<h2>` title against that div, but the
field list and Save button are *that div's own* two children, one
level too deep for the same selector to reach: zero gap, "Series
Number" touching "Save." Fixed by wrapping the field list + Save
button in `.stack` for `asOverlay` mode only (the same utility the
VoicePicker fix introduced). **Deliberately not fixed by flattening
this component's wrapper into a `Fragment`** (letting `.overlay`'s own
rule reach the two elements directly, the more obvious-looking fix):
the conditionally-rendered `FieldCorrectionPopup` blocks further down
in the same component are themselves full `Overlay`s
(`position: fixed` backdrop) -- flattening would make one a DOM
sibling of the field list/button at the same level, and
`.overlay > * + *` would then apply an unwanted `margin-top` to that
fixed-position backdrop, visibly shifting the popup-on-a-popup down
from the screen edge it needs to fully cover. `ConfirmMetadataScreen.
test.tsx` needed no changes (queries by role/text). Full writeup:
`docs/BACKLOG.md` Epic 8.5's own checklist item.

**VoicePicker spacing fix (2026-07-17, real screenshot + follow-up
request):** the heading and the voice list sat directly adjacent with
zero gap -- `VoicePicker` renders its own wrapping `<div>`, which is
`main`'s single child in the single-book screen, so the app-wide
`main > * + *` section rhythm (space-5) never reached the heading/list
inside it (that selector only matches *direct* children of `main`).
Fixed with a new `.stack` utility (index.css, same space-5 rhythm as
`main`'s own rule, usable on any container) applied narrowly to just
the heading+list group -- not the whole component -- so the
already-correct list-to-Next-button spacing (`.screen-actions`' own
margin) doesn't get doubled. Follow-up request the same session: gaps
between individual voice rows too (they read as one crowded block).
Added a second new utility, `.stack-md` (space-3, deliberately between
`.stack-sm`'s 8px and `.stack`'s 24px), to the radiogroup. **Row height
deliberately left unchanged** despite the added scroll -- `.clickable-
row`'s 70px `min-height` is the same accessibility floor shared by
every clickable row app-wide (RA persona, `03-gui-ux-design.md`
§General principles: Screen 1's toggles, AI Helper's choices, the
voice picker), not incidental sizing; shrinking it to reclaim scroll
space would trade away exactly the property this app is built around,
for the same real-user population that asked for the spacing fix.
Also worth noting for future reference: padding reduction wasn't a
real lever here regardless -- `min-height` pads a short row back out to
70px no matter its own padding, so a padding cut alone would not have
reclaimed any vertical space even if shrinking height had been the
right call. `VoicePicker.test.tsx` needed no changes (queries by role/
text, not DOM structure or class names). Full writeup: `docs/
BACKLOG.md` Epic 8.5's own checklist item.

**Working-screen Pause/Cancel/Resume feedback (2026-07-17, real user
report):** clicking Pause or Cancel appeared to do nothing. Investigated
backend first (`pipeline/batch_runner.py`, `backend/app.py`) and
confirmed the logic itself was already correct: `request_pause()`/
`request_cancel()` just set flags, `AudioStage`'s `should_stop` hook
applies them at the *next chunk boundary* (not instantly), and
`start_generation()` already resumes a `paused` book by re-queueing it
as `voice_pick` -- no new backend route needed for Resume. The entire
gap was frontend: `WorkingScreen` never reflected a paused book's real
status (no distinct UI, no Resume control, nothing disabled while a
request was in flight), so a correctly-working action looked broken.
Fixed entirely in `frontend/src/screens/WorkingScreen.tsx` +
`frontend/src/index.css`'s new `.status-badge`/`.status-badge--amber` --
a `paused` book now shows a "⏸️ Paused" badge and swaps Pause for a real
"▶ Resume" button (calls the existing `startGeneration()`); Pause/
Resume/Cancel each disable + relabel themselves ("Pausing…"/
"Resuming…"/"Stopping…") from click until the book's real status
confirms the change; confirming Cancel closes the popup immediately
instead of waiting for the delayed actual cancellation. Deliberately
did **not** add special-cased "go home after Cancel" logic -- once the
cancelled book is the batch's last one, `derive_batch_state()` already
flips to `done`, which `App.tsx` already routes back to Screen 1, so
that's the existing state machine working as designed, not a new
redirect; a multi-book batch correctly stays on Working, moving to the
next active book instead. `WorkingScreen.test.tsx` extended with
paused-state, in-flight-disabled-state (via a manually-resolved
deferred promise per assertion), and axe-while-paused coverage. Full
writeup: `docs/BACKLOG.md` Epic 8.5's own checklist item.

**Post-Epic-8.6 bugfix (2026-07-17):** real screenshot showed
`VoiceAssignmentScreen`'s single-book "✕ Remove this book" floating
below the white card, on the page background. Root cause: Epic 8.6's
`.screen-actions` sticky bar (index.css) bleeds to `main`'s edges and
rounds its bottom corners so it reads as the card's own footer — it
must stay the last DOM child of `main`, or later siblings render below
the visually-closed-off card. `RemoveBookButton` was rendered *after*
`VoicePicker` (whose own last child is that sticky bar) in single-book
mode; fixed by moving it above the picker, grouped with the existing
"Fix info" link. No CSS change, no test change (tests query by role/
name). Full writeup: `docs/BACKLOG.md` Epic 8.6's own checklist.

**Epic 7 + Epic 8 (2026-07-11, combined in one session on the user's
explicit direction):** frontend scaffolding straight through every
Epic 8 screen, rather than stopping at a placeholder — real screens
gave the hooks/facade/patterns something genuine to prove themselves
against instead of throwaway stand-ins. Backend grew from 390 to 413
tests; the frontend test count originally logged here ("331 tests")
was corrected 2026-07-17 -- see the note at the top of this section,
real count as of that date was 199 across 31 files. Full detail in
git history; the durable parts:

- **Tooling friction, not design friction:** `create-vite`'s current
  template ships oxlint, not ESLint — swapped for ESLint 9 (flat
  config) to get `eslint-plugin-jsx-a11y` at all. Both
  `eslint-plugin-react-hooks` and `vitest-axe`'s newest majors target
  React-Compiler-era / different vitest internals than this project
  actually uses; pinned to the versions that actually work
  (`react-hooks@5`, and a hand-written local `declare module "vitest"`
  augmentation for `vitest-axe`'s matcher — see `frontend/` row above).
- **Real backend gaps surfaced by building the frontend for real, not
  invented ahead of need:** `GET /api/voices`/`GET /api/voice-samples/
  <voice>` (no route ever told the frontend what voice keys exist),
  `POST /api/books/<id>/metadata` (the voice table's clickable-title
  edit needed a mutation `confirm`/`retag` don't cover), `POST /api/
  books/<id>/open-folder` + `POST /api/open-output-folder` (browsers
  can't open a native Explorer window any more than they can a native
  folder-picker dialog — same ADR-0006 reasoning, one more bridge
  route). All documented at their call sites and in
  `01-architecture.md`'s route reference.
- **Two real bugs found only by driving the actual app in a real
  browser against the real backend (Playwright + Edge, unit tests with
  mocks never would have caught either):** (1) the GUI upload route's
  collision-avoiding temp filename (`0_Fated.epub`) was leaking into
  what Screen 1 displayed her — `BatchRunner.add_book()` gained an
  `original_filename` override, display-only, never used for the
  actual `00-Incoming/` copy's path (kept path-traversal-safe). (2)
  `_maybe_enter_voice_pick()` was triggering single-book auto-start
  generation the instant a book reached `voice_pick`, before the
  picker screen could ever matter — contradicted `assign_voice()`'s
  own docstring and the GUI spec's "picking a voice... starts
  generating." Both fixed, both got regression tests, backend tests
  updated where they'd relied on the old (buggy) shortcut.
- **One test-hygiene incident, fixed the same session:** the new
  `open_folder()` backend tests weren't mocked in `test_app.py`
  (`test_dialogs.py`'s own tests were fine), so a full local test run
  popped real File Explorer windows. Fixed with an autouse
  monkeypatch fixture, same pattern `dialogs.pick_folder` already used.
- **Scope decisions made and documented, not left implicit:** the
  spec's per-batch same-series voice default is *not* reproduced
  client-side (`useVoiceAssignmentView`'s own docstring) — the backend
  only ever hands out one global default, and a second client-only
  notion of "current default" that can silently disagree with the
  server was judged worse than the marginal convenience; "Welcome
  back"'s full crash-resume reconstruction remains genuinely open
  (`WelcomeBack.tsx` degrades honestly to a plain count when the
  backend can't identify a pending book, rather than fabricating
  detail) — this was already flagged in `CLAUDE.md` as separate,
  not-yet-built backend work, confirmed still true.
- Live-tested end to end against the real Kokoro engine (not mocked):
  full 28-voice sample cache generation genuinely takes ~48s on CPU on
  first run per install, cached thereafter — matches the "lazy,
  opening the picker is the trigger" design already on record.

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
