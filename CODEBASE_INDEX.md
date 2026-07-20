# CODEBASE_INDEX.md

File map + migration/schema table. Kept current as epics land real code.

## File map

| Path | Status | Owned by |
|---|---|---|
| `main.py` | Real (Epic 6). CLI `rename`/`sanitize`/`audio`/`all`/`retag` commands wired to real stages via `pipeline/cli_runner.py`, non-interactively, over `settings.json`'s `books_folder`/`output_folder`. `all` chains stages through ephemeral temp dirs. `retag` takes a positional folder + `--author-first`/`--author-last`/`--title`/`--series`/`--series-number` overrides (new args, absent from the Epic 0 scaffold). `--workers` still reserved/validated only (ADR-0009). | Epic 0 / Epics 2-6 |
| `launcher.py` | Real (Epic 6). `find_free_port()` (OS-assigned, ADR-0008's host stays fixed), `open_browser()` retry-then-native-tkinter-fallback (07-packaging-deployment.md), a port sidecar file next to the lock file so a second launch can still reopen a tab despite dynamic port selection. **Live-verified end to end 2026-07-18** (Epic 10 Phase A): a real `python launcher.py` run, curl-confirmed to serve the real built frontend + real API + correct SPA-fallback/404 behavior, then shut down cleanly via `/api/quit`. **Real bug found and fixed 2026-07-18, real user report:** `_ensure_stdio_streams()` — `pythonw.exe` (what `run_gui.vbs` runs) detaches stdio entirely, `sys.stdout`/`sys.stderr` are `None`, not just empty; `kokoro`'s own `__init__.py` does `logger.add(sys.stderr, ...)` at import time and crashed with `TypeError: Cannot log to objects of type 'NoneType'` the moment audio generation first tried to lazily import it. Called once at module level, replaces a `None` stream with a real `os.devnull` handle before Flask ever starts serving requests. | Epic 0 / Epic 6 / Epic 10 |
| `run_gui.vbs` | Real (Epic 10 Phase A). No-console `pythonw.exe` wrapper around `launcher.py` for real-person testing before the real packaged `.exe` (Phase B) exists — a testing-phase stand-in, explicitly not a replacement. Live-verified via `cscript` (2026-07-18): no console window, no lingering process after `/api/quit`. | Epic 10 |
| `backend/app.py` | Real (Epic 6, extended Epic 8/9/10). Full JSON API route set — status polling, settings, folder picker, add/remove books (multipart upload), auto-load-from-folder (Epic 10), disk-space, batch start/start-generation, per-book confirm/voice/pause/cancel/collision/review/retag, voice-history, support-bundle, welcome-back, cleanup-in-progress (Epic 9), quit, plus serving the built frontend (Epic 10). **Epic 8 additions**, all found genuinely missing while building the real frontend against this contract, not pre-planned: `GET /api/voices` + `GET /api/voice-samples/<voice>` (voice picker list + preview playback; the former is also this app's lazy voice-sample-cache trigger point), `POST /api/books/<id>/metadata` (multi-book voice table's clickable-title metadata edit, distinct from `confirm` and `retag`), `POST /api/books/<id>/open-folder` + `POST /api/open-output-folder` (Review screen's two "📂 See..." links — no raw filesystem path ever crosses the wire, both resolved server-side). **Epic 9 additions:** `_build_runner(restore=True)` seeds the one runner built at process startup from `state_repo.incomplete_book_snapshots()` — full "Welcome back" resume, not just detection (`AppState.new_runner()`'s "batch done -> fresh runner" reset stays `restore=False`, deliberately never resurrects a genuinely finished batch); `POST /api/cleanup-in-progress` (the "nuke everything in progress" escape hatch, replaces the in-memory runner afterward since it may hold now-deleted books/files). **Epic 10 Phase A additions:** `_frontend_dist_dir()` + a catch-all `GET /`/`GET /<path:path>` route (registered last, `static_folder=None` on the `Flask()` construction since this replaces its default static handling entirely) serving `frontend/dist/` — live-verified via curl against a real running server, not just the Flask test client; a mistyped `/api/*` GET still gets a real 404, never silently falls back to `index.html`. `GET`/`POST /api/books/from-folder` (auto-load-from-folder, moved from Epic 8.5) — the `POST` reuses `POST /api/books`'s exact per-file result shape, each filename re-validated server-side against `books_folder` before being read. **`_safe_folder_epub_path()` deliberately does NOT run the filename through `secure_filename()`** (fixed post-verification, real user report) — that's the right tool for `_safe_upload_path()` above (choosing a *new* destination filename, where mangling is harmless) but the wrong one for looking up an *existing* file by its exact, already-known name: `secure_filename()` collapses whitespace into `_`, so a real book like "The Dragon Reborn.epub" silently came back "couldn't be found." A plain path-separator-character check (no `/`/`\`) plus the existing resolve()-and-containment check block traversal just as well, without mangling anything. One `BatchRunner` per app instance; auto-replaced with a fresh one once `done` (`_current_runner()`). | Epic 0 / Epic 6 / Epic 8 / Epic 9 / Epic 10 |
| `backend/dialogs.py` | Real (Epic 6, extended Epic 8/10). `pick_folder()` via `tkinter.filedialog.askdirectory()`; `tk_factory`/`ask_directory` injectable seams so tests never open a real Tk window. Epic 8 added `open_folder()` (`os.startfile`, Windows-only) for the same two Review-screen links above — **`tests/test_app.py` monkeypatches this globally (autouse fixture)**, same as `pick_folder`, after an early Epic 8 session accidentally popped real Explorer windows during a full local test run before that fixture existed. **Epic 10 Phase A addition, real bug found and fixed via live testing (real user report, 2026-07-18):** `request_folder_pick()` — `pick_folder_route()` now calls this instead of `pick_folder()` directly. Every Flask route runs on a fresh `waitress` worker thread, never the process's actual main thread, and `tkinter` needs one *consistent* thread for its global interpreter state — calling `pick_folder()` straight from a route intermittently hung forever (reproduced live: the request never returned while every other route kept responding, meaning exactly one of `waitress`'s finite worker threads got stuck). `request_folder_pick()` hands the real `tkinter` work off to a single background thread, started lazily and reused for the process's whole lifetime, and blocks for the answer the same way the route already needed to. See `ADR-0006`'s addendum and Session notes below. | Epic 6 / Epic 8 / Epic 10 |
| `backend/bridge.py` | Real (Epic 6, extended Epic 8/9). `derive_batch_state()` — pure State Machine function, unit-tested independent of HTTP; one **documented deviation** from the literal precedence-rule text (see its own docstring) to correctly bucket the `review_result`/`output_collision` `needs_input` types this epic added. `build_status_response()`, `voice_history()`, `build_support_bundle()`/`write_support_bundle()` (secrets always stripped). Epic 8 added `voice_choices()` — strips `tts_engine.VOICES`' display strings down to plain first names for the picker. **Epic 9 added `reset_all_in_progress()`** — the "clean up stuck in-progress state" mechanism: a best-effort sweep of every `Library/*` stage folder plus a full `StateRepository.reset_all()`, deliberately never correlated with any live tracked `Book`. | Epic 6 / Epic 8 / Epic 9 |
| `pipeline/batch_runner.py` | Real (Epic 6, extended Epic 8). `BatchRunner` — the stateful, interactive engine behind the GUI's polling contract: add/remove books (reuses `input_validation.py`), rename→sanitize identification loop (needs_input pauses never block the background thread), per-book/per-batch voice assignment, serial audio generation (ADR-0009) with Pause/Cancel via `AudioStage`'s new Observer hooks, output-collision handling (`NeedsInputType.OUTPUT_COLLISION`), manually-triggered retag (operates on the **output-folder copy**, not the internal Library copy ADR-0017 deletes), ADR-0017 cleanup. Keeps `state.json` genuinely current stage-by-stage, specifically ordered so a fast client can never race ahead of a stage's own persistence (see `_finish_generation`'s comment). **Epic 8 additions:** `add_book()` gained an `original_filename` override (a real bug found via a live browser smoke test — the GUI upload route's collision-avoiding temp filename, e.g. `0_Fated.epub`, was leaking into what Screen 1 displayed; the safe temp name is still what the internal `00-Incoming/` copy uses, only the *display* value changed); `update_metadata()` (the voice table's clickable-title edit, restricted to `voice_pick`); and a real bug fix in `_maybe_enter_voice_pick()` — it used to also trigger the single-book auto-start-generation the instant a book reached `voice_pick`, before the picker screen could ever matter, contradicting `assign_voice()`'s own docstring ("picking a voice and pressing Next starts generating"). Both were found while building/live-testing the real Epic 8 voice-picker screen against this existing Epic 6 code, not by the pre-existing unit suite. **Note (2026-07-17, confirmed while investigating a Pause/Cancel feedback report):** this file's pause/cancel/resume logic itself was already correct — `request_pause()`/`request_cancel()` just set flags, `AudioStage`'s `should_stop` hook applies them at the next chunk boundary, and `start_generation()` already resumes any `paused` book by re-queueing it as `voice_pick` (see that method's own docstring). No backend change was needed; the real gap was frontend-only (see Session notes below). **Epic 9 additions:** a new `_set_book()` helper centralizes every status-changing mutation's state-file snapshot persistence (deliberately not used by the high-frequency `_on_audio_progress()` chunk callback); `restore_books()` seeds a freshly-constructed runner from persisted snapshots at process startup, coarse-graining `generating`/`paused` to `voice_pick` and `identifying` to `pending`; `_finalize_cancel()` now also marks the `cleanup` stage complete (a pre-existing gap — a cancelled book previously stayed "incomplete" forever). **2026-07-20 real bug fix:** `_copy_epub_to_output()` — the sanitized EPUB half of `01-architecture.md`'s "two things per book" output-folder rule, never actually wired up before now; called from `_run_identification()` right after sanitize/pass-through completes, always before ADR-0017 cleanup could ever delete its source. EPUB collisions auto-dedupe rather than raising a new `needs_input` pause — see Session notes below for why. | Epic 6 / Epic 8 / Epic 9 |
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
| `pipeline/rename_stage.py` | Real (Epic 3). `RenameStage` + `FILENAME_PATTERN`/`build_filename` ported from `epub-renamer`'s `renamer.py`/`main.py`; copy-based (not in-place rename) to fit this pipeline's stage-folder model; dry-run + name-conflict handling; silent per-file `NullProvider` fallback on AI failure. **Real bug found and fixed 2026-07-18, real user report:** `_pass_through_already_normalized()` skipped re-renaming/AI (correctly — an already-normalized filename needs neither) but also skipped populating `title`/`author`/`series` entirely, which `BatchRunner._run_identification()` can't distinguish from a genuine AI failure (both look like "no title set"). Fixed via new `_parse_normalized_filename()`, which parses those fields back out of the filename directly, since `FILENAME_PATTERN` match means the filename is already in `build_filename()`'s own output shape. | Epic 3 |
| `pipeline/audio_stage.py` | Real (Epic 4, extended Epic 6). `AudioStage` — per-book chapter/chunk TTS loop, ID3 tagging via mutagen, per-chunk resume, retry-then-error. Reuses `rename_stage.build_filename()` directly (minus `.epub`) for the output folder/file base name. Epic 6 added `on_progress`/`should_stop` Observer-pattern hooks (optional, default `None`, backward-compatible) — `pipeline/batch_runner.py`'s only way to report progress and implement Pause/Cancel without this stage ever knowing an HTTP server or batch runner exists. **Real bug found and fixed 2026-07-18, real user report:** `_generate_with_retry()` discarded the real exception on every attempt, leaving the book's `error` field (the only channel `current_error_detail()`/the support bundle ever reads) with a bare "chapter 1, chunk 1" sentence and nothing underneath it. Now returns `(bytes | None, detail)`; the last attempt's `TypeName: message` gets appended to `error` on final failure. | Epic 4/6 |
| `pipeline/retag_stage.py` | Real (Epic 5). `RetagStage` — fixes ID3 tags/filenames/**containing folder name** (bug fix over the original script) for an already-generated audiobook folder. Folder-name parsing (`parse_folder_metadata`/`parse_stem_metadata`) handles both the old standalone-tool shape and this pipeline's own `build_filename()` shape; reuses `rename_stage.build_filename()` directly for all naming (ADR-0016), same pattern `audio_stage.py` already uses. Always manually triggered (`applies_to()` always `False`). | Epic 5 |
| `pipeline/tts_engine.py` | Real (Epic 4, extended Epic 8). `TTSEngine` wraps `kokoro.KPipeline`, lazily imported/constructed (first real call only). `VOICES`/`DEFAULT_VOICE`, `estimate_audio_bytes()` (disk-space formula), `ensure_voice_samples()` (cache + version-tagging, now typed against `TTSEngineLike` rather than the concrete class — one less coupling point). MP3 encoding via `lameenc` at Kokoro's native 24kHz — see session notes below. Epic 8 added `installed_kokoro_version()` (package-metadata-only, never imports `kokoro` itself) to finally wire up `ensure_voice_samples()`'s cache-invalidation trigger, deferred since Epic 4/6. | Epic 4 / Epic 8 |
| `pipeline/epub_reader.py` | Real (Epic 3, extended Epic 4). `extract_epub_metadata`/`extract_text_sample` ported verbatim from `epub-renamer/epub_reader.py`; `extract_cover_bytes()` (Epic 4) ported verbatim from `epub-to-audio\epub_utils.py`, 3-strategy fallback, used for ID3 cover art. | Epic 3/4 |
| `pipeline/epub_utils.py` | Real (Epic 3, extended Epic 4). `sanitize_filesystem_name()` (ADR-0016) — new shared utility, used by rename, audio (Epic 4), and retag (Epic 5). `extract_chapters()`/`chunk_text()`/`normalise_heading()`/`MAX_CHUNK_CHARS` (Epic 4) ported verbatim from `epub-to-audio\epub_utils.py`. | Epic 3/4/5 |
| `pipeline/ai_providers/` | Real (Epic 3). `base.py`/`null_provider.py`/`openai_provider.py`/`registry.py` ported from `epub-renamer` (constructors adapted to take `api_key` explicitly, per ADR-0003); `gemini_provider.py` new, uses the `google-genai` SDK. | Epic 3 |
| `frontend/` | Real (Epic 7/8). Vite + React 19 + TypeScript, built with `npm create vite@latest -- --template react-ts` then reworked: **oxlint replaced with ESLint 9** (flat config, `eslint-plugin-jsx-a11y` + `eslint-plugin-react-hooks` — pinned to the classic 5.x line, not the newer React-Compiler-flavored 7.x, since this project doesn't use the Compiler and several of its rules assume it) so `eslint-plugin-jsx-a11y` could be wired in at all. `src/api/` (`client.ts`/`types.ts`) is the one module that knows the Flask JSON API's shapes; `src/hooks/` (`usePollingStatus`, `useFocusTrap`, `useAriaLiveThrottled`); `src/components/shared/` (`BigButton`, `RadioRow`, `ToggleSwitch`, `EditableFieldRow`, `Overlay`, `FieldCorrectionPopup`, `VoicePicker`, `LiveRegion`); `src/viewmodels/` (`useVoiceAssignmentView`, `useWorkingScreenView`); `src/screens/` (one file per screen in `03-gui-ux-design.md`'s encounter order); `src/App.tsx` (the one top-level container — owns onboarding-phase routing + the single `usePollingStatus()` every screen is built from). **241 tests across 32 files** (confirmed via a real `npm test` run 2026-07-18, after the `StepProgress` back-navigation follow-up below), coverage comfortably above the 80% floor. `vite.config.ts` implements the dev-proxy/Origin-rewrite this directory's own `README.md` already specified. `index.css`'s spacing-utility family (`main > * + *`, `.stack-sm`, and now `.stack`/`.stack-md`, 2026-07-17) is the one place vertical rhythm is controlled app-wide — see that file's own comments before adding a new one-off margin anywhere. **Recurring nesting-depth gotcha, worth checking for elsewhere:** any component that renders its own single wrapping element (rather than being a direct child of `main`/`.overlay`) loses that ancestor's `> * + *` spacing rule for its *own* children, one level too deep to be reached — this bit both `VoicePicker` (heading/list, `main`'s rule) and `ConfirmMetadataScreen`'s `asOverlay` mode (field-list/Save button, `.overlay`'s rule), fixed the same way both times with a `.stack`/`.stack-md` wrapper scoped to just the affected pair (2026-07-17, see Session notes below). Also gained `.progress-bar` (2026-07-17) -- a native `<progress>` element styled via vendor pseudo-elements rather than a `<div>` with inline `width`, since the latter would need the `style` prop this same stylesheet's own ESLint rule forbids. | Epic 7/8 |
| `frontend/src/screens/*.tsx` | Real (Epic 8, extended Epic 9/10). `FoldersScreen` (first-launch + "⚙️ Change my folders", same component), `AiHelperSetup` (intro→choice→key, one component covering all three steps), `WelcomeBack` (degrades honestly to a plain count only for the rare pre-Epic-9-migration/never-snapshotted case now — see its own module comment; the common "backend restarted" case is now genuinely resumed, not just detected, see Epic 9 Session notes below), `AddBooksScreen` (**Epic 10 Phase A addition:** an auto-load-from-folder checklist, see its own row below), `ConfirmMetadataScreen` (also reused inside an `Overlay` from the voice table, `asOverlay` prop — **overlay-mode spacing fixed 2026-07-17**, see that file's own docstring and Session notes below; **Epic 10 addition:** passes `hint` through to its Author/Series Number `FieldCorrectionPopup`s), `VoiceAssignmentScreen`, `WorkingScreen` (Pause/Cancel/Resume feedback and the chunk-progress readout both added and verified 2026-07-17, see Session notes), `CollisionPrompt`, `ReviewScreen`, `FixInfoFlow` (**Epic 10 addition:** same `hint` wiring as `ConfirmMetadataScreen`, via a `HINTS` record parallel to its existing `LABELS`), `WordsScreen`, `VoiceHistoryScreen`, `ErrorScreen`. **`MoreOptionsScreen` gained a fifth entry Epic 9** — "🧹 Nuke everything in progress," confirm-gated via `Overlay`, calls the new `cleanupInProgress()` API client function. **Epic 9 also wired `StepProgress`** (new shared component, see its own row below) into `AddBooksScreen`/`ConfirmMetadataScreen`/`VoiceAssignmentScreen`/`WorkingScreen`/`CollisionPrompt`/`ReviewScreen`/`FixInfoFlow` — the five main-flow screens plus `CollisionPrompt` (a pause within Convert). All wired together in `App.tsx` (unchanged by Epic 9/10 — neither the full-resume fix nor the frontend-serving fix needed any `App.tsx` change, see Session notes). | Epic 8/9/10 |
| `frontend/src/components/shared/VoicePicker.tsx` | Real (Epic 8). Full voice-picker list, used standalone (single-book) and inside an `Overlay` ("Change Voice"). **Spacing fixed 2026-07-17** (real screenshot + follow-up request) — heading-to-list and inter-row gaps were both zero; see that file's own docstring and Session notes below for the fix and the deliberate decision to leave the 70px row-height accessibility floor unchanged. | Epic 8 |
| `frontend/src/components/shared/StepProgress.tsx` | Real (Epic 9). The "you are here" wizard bar — `<nav>`/`<ol>` of five steps (Add Books/Confirm Info/Choose Voice/Convert/Review), `aria-current="step"`, non-color-only current/completed markers (checkmark glyph vs. filled/outlined circle, not color alone), an optional active-book-title line tied to the `<nav>` via `aria-describedby`. New `.step-progress*` CSS in `index.css`. See Session notes below for the multi-book "active book" state, which turned out to already exist. **Real bug found and fixed 2026-07-18, real user report:** it was pure display, no step ever clickable. New `clickableSteps`/`onStepClick` props render a completed step as a real `<button>` only where the calling screen already has a matching, non-destructive action — `VoiceAssignmentScreen` (single-book mode) and `ReviewScreen` both wire "Confirm Info" to their existing edit-metadata/"No, let me fix it" flows; every other completed step stays plain text since going back there has no existing non-destructive backend action to reuse. | Epic 9 |
| `frontend/src/components/shared/FieldCorrectionPopup.tsx` | Real (Epic 8, extended Epic 10). **Epic 10 Phase A addition (moved from Epic 8.5):** an optional `hint` prop — a short plain-language format example rendered under the input, tied to it via `aria-describedby`. Wired at both call sites (`ConfirmMetadataScreen`'s Author/Series Number popups; `FixInfoFlow`'s shared invocation via a new `HINTS` record parallel to its existing `LABELS`). Title/Series have no particular expected shape, so no hint for those. | Epic 8/10 |
| `frontend/src/components/shared/AppHeader.tsx` | Real (Epic 8.5, extended Epic 10 Phase A). **Epic 10 addition, a real gap found live while diagnosing the two bugs above:** an optional `onQuit` prop — a confirm-gated "Quit for now" button, alongside `onHome`. Originally `03-gui-ux-design.md` scoped "Quit for now" to the Working screen only (a persistent-header version was *allowed* as an alternative, never built) — real confusion diagnosing the dialog-hang and folder-lookup bugs above traced back to exactly this gap: closing the tab never stops the background server (ADR-0001), and with no way to end the session anywhere else, a still-running pre-fix server got mistaken for "already closed." `App.tsx` computes visibility by mirroring `renderScreen()`'s own `state`/`needs_input` branching, so the collision prompt (the *other* thing `state: "working"` can mean, with no Quit button of its own) still gets the header's, while the plain Working screen (which already has one) doesn't get a duplicate. | Epic 8.5/10 |
| `frontend/src/**/*.test.{ts,tsx}` | Real (Epic 7/8), co-located with the code they test. Vitest + React Testing Library + `vitest-axe` (axe-core assertions in nearly every component/screen test — needed a hand-written local `declare module "vitest"` augmentation in `src/test/vitest-axe.d.ts`, since `vitest-axe@0.1.0`'s own shipped types target an older `Vi.Assertion` global-namespace convention vitest 4.x no longer reads). | Epic 7/8 |
| `tests/test_sanitize_stage.py` | 29 adversarial tests, all 10 controls. | Epic 2 |
| `tests/test_rename_stage.py`, `test_ai_providers.py`, `test_openai_provider.py`, `test_gemini_provider.py`, `test_epub_reader.py`, `test_epub_utils.py` | Epic 3 test suite (`test_epub_reader.py`/`test_epub_utils.py` extended Epic 4 — see below): `build_filename`/`FILENAME_PATTERN`/`RenameStage` (happy path, already-normalized, dry-run, name-conflict, AI failure fallback, corrupted EPUB), provider base/registry/Null/OpenAI/Gemini, `sanitize_filesystem_name` (incl. idempotency). | Epic 3 |
| `tests/test_retag_stage.py` | Epic 5 test suite, 29 tests. Folder-name parsing (old + new shapes), chapter-title/track-number derivation from MP3 filename suffix, ID3 tag rewriting, override-vs-parsed precedence, dry-run, idempotency, and the folder-rename regression test (`test_run_renames_folder_not_just_files`). | Epic 5 |
| `tests/test_tts_engine.py`, `test_audio_stage.py` | Epic 4 test suite. Fake `pipeline_factory`/fake TTS engine throughout — never downloads or runs the real Kokoro model. Covers: MP3 bitrate/sample-rate/mono verification, per-lang-code pipeline caching, `estimate_audio_bytes()` formula, `ensure_voice_samples()` version-mismatch/offline-failure behavior; chunk/chapter naming conventions, per-chunk resume, retry-then-error (partial chunks left intact), ID3 tagging incl. cover art, unknown-voice/missing-file/corrupted-EPUB/no-chapters error paths. `test_epub_utils.py`/`test_epub_reader.py` extended with `extract_chapters()`/`chunk_text()`/`normalise_heading()`/`extract_cover_bytes()` coverage. | Epic 4 |
| `tests/test_*.py` (stage, atomic_write, state_manager, audit_logger, single_instance, safe_zip, config) | Epic 0 test suite, incl. crash-mid-write, dead-PID, adversarial zip fixtures. `test_state_manager.py`/`test_safe_zip.py` extended Epic 6 (`incomplete_book_ids()`, the XXE-guard regression test). `test_state_manager.py` extended again Epic 9 (schema v1→v2 migration, `save_book_snapshot()`/`incomplete_book_snapshots()`/`reset_all()`). | Epic 0/6/9 |
| `tests/test_input_validation.py`, `test_disk_space.py`, `test_cli_runner.py` | Epic 6, pure-function/pipeline-level tests — no Flask/HTTP. | Epic 6 |
| `tests/test_batch_runner.py` | Epic 6, extended Epic 9, 42 tests. Real `RenameStage`/`SanitizeStage`/`AudioStage`/`RetagStage`, only the TTS engine faked. Covers the full add→identify→confirm→voice→generate→review→complete→cleanup lifecycle, output-collision resolve (`keep_both`/`replace`), Pause/Cancel (keep-partial vs. discard), resume-after-pause, and `state.json` staying genuinely current stage-by-stage. Uses a gated fake TTS engine (`threading.Event`) to land Pause/Cancel requests deterministically instead of racing real background-thread timing. **Epic 9 additions:** `restore_books()` coarse-graining per status bucket, a real end-to-end round trip (pause a book, then build a brand-new `BatchRunner`/`StateRepository` pair from the same on-disk file, simulating a real process restart), the cancel/`cleanup`-stage fix. **2026-07-20 additions:** the EPUB output-copy fix — copy-on-sanitize-completion, copy still fires with the sanitize stage toggled off, collision auto-dedupe, copy surviving a later audio failure — plus two new assertions in the existing ADR-0017 cleanup test. | Epic 6/9 |
| `tests/test_bridge.py` | Epic 6, 24 tests. `derive_batch_state()` tested entirely against plain `BookState` objects (no HTTP, per docs/BACKLOG.md's own requirement) — every precedence boundary plus the two documented `needs_input`-type deviations; `build_status_response()`/`voice_history()`/`build_support_bundle()` shape and secret-stripping. | Epic 6 |
| `tests/test_app.py` | Epic 6, extended Epic 9/10, 73 tests. Flask test client throughout; `dialogs.pick_folder` always monkeypatched (never opens a real Tk window). Full single-book and multi-book HTTP flows, settings masking/persistence, every 400/409 error branch, the fresh-batch-after-`done` reset, and the `/api/quit` route verified without ever letting the real `os._exit` fire (would kill the test process). **Epic 9 additions:** a real two-separate-`create_app()`-instances-against-the-same-`appdata_dir` test proving full "Welcome back" resume (not just one app's in-memory runner), `/api/cleanup-in-progress` happy path + the no-live-runner-knowledge case + the audit-log-untouched guarantee. **Epic 10 Phase A additions:** `/api/books/from-folder` GET/POST (listing, exclusion-of-already-added, path-traversal/nonexistent-filename rejection); frontend-serving tests monkeypatching `_frontend_dist_dir()` (missing build → real 404, index.html at root, a real static asset, SPA fallback for an unknown path, a mistyped `/api/*` path still 404s, a `..`-traversal attempt never leaks a file outside `dist/`). | Epic 6/9/10 |
| `tests/test_dialogs.py`, `test_launcher.py`, `test_main.py` | Epic 6, extended Epic 8/10 (`test_dialogs.py`: `open_folder()` coverage, Epic 8; `request_folder_pick()` coverage, Epic 10 — the same-background-thread property and exception-survival, the two things that actually matter for the real bug it fixes, plus the usual return-value/argument-passing cases). `test_launcher.py` proves `open_browser()`'s retry-then-fallback and the port-sidecar-file second-launch behavior without ever creating a real Tk window or binding a real server. `test_main.py` exercises `main.py`'s CLI commands end-to-end against real stages (fake nothing except never touching real Kokoro, since `audio`/`all` aren't directly tested end-to-end — `rename`/`sanitize`/`retag` are). | Epic 6 / Epic 8 / Epic 10 |
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

**2026-07-20, real bug found via real-world testing: the sanitized EPUB
was never actually delivered to `output_folder`.**
`01-architecture.md` §Folder mapping has always said `output_folder`
receives *two* things per book, added incrementally: the cleaned/renamed
EPUB as soon as sanitize finishes, and the finished audiobook as soon as
audio finishes. Only the second half was ever wired up
(`_finish_generation()`/`_copy_tree_to_output()`) --
`_run_identification()` never copied the sanitized EPUB anywhere, and
ADR-0017's cleanup then deleted the internal `Library/02-Sanitized/`
working copy once the book reached `complete`, so the cleaned EPUB was
generated, used as TTS input, and permanently discarded -- confirmed by
the real user checking her own output folder and finding no `.epub`
file. **Fix:** `BatchRunner._copy_epub_to_output()`, called from
`_run_identification()`'s loop body right after the sanitize
stage/pass-through completes for that book_id -- always before that same
book_id could ever reach `_mark_complete`/`_cleanup_library_copies`
(confirming metadata, picking a voice, and a full audio pass all have to
happen first), so the copy is provably made before ADR-0017's cleanup
could ever delete the source it copies from. **Collision handling --
a real, deliberate scope decision, not an oversight:** unlike the
audiobook artifact, an EPUB output collision is auto-deduped via the
existing `_dedupe_path()` helper rather than raising a new
`needs_input`/`output_collision` pause. `06-safety-error-handling.md`
calls for a real "replace or keep both" prompt per artifact, and the
frontend's `CollisionDetail`/`CollisionPrompt` already type- and
component-support an `"epub"` artifact value -- but wiring that in for
real surfaced a genuine, separate gap: `backend/bridge.py::
derive_batch_state()`'s precedence rule buckets *any* other book still
mid-identification as `BATCH_IDENTIFYING`, which would leave a book
paused on an EPUB collision invisible to the frontend until every other
book in the batch finishes its own metadata confirmation -- a real,
confusing multi-book-batch delay, not a clean drop-in of the existing
audiobook-collision pattern. Fixing that means changing
`derive_batch_state()`'s bucketing rule itself, out of scope for this
fix; auto-dedupe (same helper `resolve_collision()`'s `"keep_both"`
branch already uses) is the safe interim default -- she still gets both
files under distinct names, never a silent overwrite. Flagged in
`docs/BACKLOG.md` for a proper follow-up. Four new tests in
`tests/test_batch_runner.py` (copy-on-sanitize-completion, copy still
fires when the sanitize stage is toggled off, collision auto-dedupe,
copy survives a later audio-generation failure), plus two new assertions
in the existing ADR-0017 cleanup test confirming the internal
`02-Sanitized` copy is deleted while the `output_folder` copy survives.
478 backend tests / 96.53% coverage, clean `black`/`ruff`/`mypy --strict`.

**Epic 4, a real bug found and fixed the same day (real user report,
"Something went wrong" on a real failed run):** her own support bundle
showed only "Audio generation failed at chapter 1, chunk 1 (track
1/385)" -- no exception type, no message, nothing to diagnose from.
**Root cause:** `AudioStage._generate_with_retry()` caught every
attempt's real exception and threw it away, returning a bare `None` on
final failure -- `run()`'s error message was then built from scratch
with zero knowledge of what had actually gone wrong underneath.
**Diagnosis:** read her real support bundle and `state.json` directly
(same pattern as the rename-stage bug earlier the same day), then
reproduced the exact chapter-1/chunk-1 text against the exact voice
(`bm_lewis`) live in the venv -- it generated successfully on the first
try, wrongly suggesting a one-off transient failure. **Fix:**
`_generate_with_retry()` now returns `(bytes | None, detail)`, and the
last attempt's `TypeName: message` gets appended to the book's `error`
field on final failure -- the exact same field `backend/bridge.py::
current_error_detail()` already documented as the *only* channel real
error text ever leaves the machine through (`build_support_bundle()`'s
`technical_error`), it just had nothing real in it for this failure
mode before now. No new logging infrastructure -- this reuses the
existing support-bundle channel. **This fix is exactly what caught the
real root cause minutes later, same day:** her next retry, now carrying
the real exception, showed `TypeError: Cannot log to objects of type
'NoneType'` -- not transient at all. See the `launcher.py` entry
immediately below.

**Epic 10 Phase A, a second real bug the same day, found via her actual
retry immediately after the fix above:** `TypeError: Cannot log to
objects of type 'NoneType'`, deterministic every time, not the
transient failure the first live repro wrongly suggested. **Root
cause:** the first repro ran under a normal console-attached `python`,
where `sys.stderr` is a real object; the real app runs via `run_gui.vbs`
(`pythonw.exe`), which detaches stdio entirely -- `sys.stdout`/
`sys.stderr` are `None`, not just empty. `kokoro`'s own `__init__.py`
(third-party, not this project's code) unconditionally does
`from loguru import logger; logger.add(sys.stderr, ...)` the instant
it's first imported -- `pipeline/tts_engine.py`'s lazy `_get_pipeline()`,
deep inside the first real audio-generation request, which is exactly
the first moment this ever ran under the new no-console launcher (every
earlier successful generation, back through 2026-07-17, predates
`run_gui.vbs`). loguru's `add()` raises exactly that `TypeError` for any
sink that isn't a real writable/callable/path/`logging.Handler` -- `None`
included. **Fix:** `launcher.py::_ensure_stdio_streams()`, called once
at module level right after `launcher.py`'s own imports, replaces a
`None` `sys.stdout`/`sys.stderr` with a real `os.devnull` handle before
Flask/waitress ever starts serving requests. Confirmed two ways: forcing
`sys.stdout`/`sys.stderr` to `None` reproduces the exact production
error on `import kokoro`, and the fix resolves it; the exact failing
chapter-1/chunk-1 text generates real audio end-to-end under simulated
`None` stdio once the fix is applied. Two new regression tests
(`tests/test_launcher.py`). 474 backend tests, clean
`ruff`/`black`/`mypy`.

**Epic 9, `StepProgress` follow-up fix, same day (real user feedback):**
"I need to be able to use the cookie crumb bar to go backwards. It is
normal and intuitive to expect it to work that way." The step bar as
originally built (see its own row above and the Epic 9 write-up below)
was pure display -- every step was plain text, none of it clickable, a
real gap against the standard breadcrumb pattern the user's own
expectation named directly. **Fix, deliberately scoped to what's
already safe rather than a blanket "make everything clickable":**
`StepProgress` gained `clickableSteps`/`onStepClick` props; a completed
step renders as a real `<button>` (visible underline, not color-only,
44px touch target, a screen-reader-only " (go back and fix this)"
suffix) only where the calling screen already has an existing,
non-destructive way to act on that step, reusing that exact action
rather than inventing a new one -- `VoiceAssignmentScreen`'s single-book
mode wires "Confirm Info" to the same edit-metadata overlay already
behind "✏️ Not quite right?", and `ReviewScreen` wires it to the same
`handleNo()` already behind "No, let me fix it" (submits
`looks_good: false`, then opens `FixInfoFlow` -- no audio regenerated).
**Everything else deliberately stays non-clickable:** "Add Books" has no
backend concept of reopening Screen 1 mid-batch without deciding what
happens to every other book already past that point; "Choose Voice" from
Convert/Review would mean discarding and regenerating already-baked
audio, which no existing action does. Both would need real backend
design work, not a click handler -- making them clickable now would
look safe and silently lose work, worse than the original all-static
bar. The multi-book voice table also stays non-clickable in the bar
itself, same reasoning as its "active book" note below: no single
unambiguous book for a bar click to act on when several sit in
`voice_pick` at once (the table's own per-row title click already
covers this unambiguously). Full rule and per-screen mapping:
`docs/requirements/03-gui-ux-design.md` §Step progress indicator. 241
frontend tests / 32 files, clean build/lint/test.

**Epic 3, a third post-Epic-10 bug fix, same day (real user report):**
a book whose filename already matched `FILENAME_PATTERN` -- re-imported
from an earlier run, or from one of the predecessor tools this project
merges -- landed on the "We couldn't quite figure out this book" screen
with no title, author, or series at all, and no AI provider was ever
called despite one being configured. Diagnosed directly from the user's
own real `audit_log.csv`/`state.json` (`skipped_reason:
already_normalized, ai_used: no`, every metadata field blank) rather
than asking for a screenshot. **Root cause:**
`RenameStage._pass_through_already_normalized()` correctly skipped
re-renaming and the AI call (an already-normalized filename needs
neither) but also skipped populating metadata entirely --
`BatchRunner._run_identification()` routes any book with no `title` to
`ai_enrichment_failed` regardless of *why* it's missing, so "nothing
more to do" was indistinguishable from a genuine AI failure. **Fix:**
new `_parse_normalized_filename()` -- since a `FILENAME_PATTERN` match
means the filename is already in `build_filename()`'s own output shape,
its title/author/series/series_number can be parsed back out reliably
(title via a new regex; author/series reuse the existing
`guess_author_from_filename()`/`guess_series_from_filename()` helpers,
which already work against arbitrary filenames). No AI call needed --
the filename already encodes everything. Verified directly against the
exact real filename that surfaced this ("Jordan, Robert -- The Wheel of
Time #03 -- The Dragon Reborn.epub") via a live script, plus two new
regression tests (standalone-book and series shapes). 472 backend tests
/ 96.42% coverage, clean `ruff`/`black`/`mypy`. **Needs a running server
restart to take effect** -- this is a code fix, not a state fix, so any
already-running `python launcher.py`/`run_gui.vbs` process still has the
old buggy code loaded in memory.

**Epic 10 Phase A, a real gap found live while diagnosing the two bug
fixes below (2026-07-18):** "Quit for now" only ever existed on the
Working screen -- every other screen (Screen 1, Voice Pick, Review,
Confirm Info, onboarding, error, "More options") had no way to end the
session at all except closing the browser tab, which by design
(ADR-0001) never stops the background server. This directly caused real
confusion diagnosing the dialog-hang and folder-lookup bugs documented
below: a still-running server from an earlier attempt got mistaken for
"already closed," its stale pre-fix code masking the real fix behind
what looked like a persistent bug. Not a regression -- `03-gui-ux-
design.md` always scoped Quit to the Working screen, with a persistent-
header version merely *allowed* as an alternative, never actually built.
**Fix:** `AppHeader` gained a confirm-gated `onQuit` prop ("Stop for
now? You can pick up right where you left off next time."), computed in
`App.tsx` by mirroring the exact same `state`/`needs_input` branching
`renderScreen()` already uses -- shown on every screen except first-
launch onboarding and the Working screen itself (which keeps its own,
to avoid a confusing duplicate). New tests cover every phase/state
boundary directly, including a check that exactly one "Quit for now"
button ever renders on the Working screen. 472 backend tests unchanged
(no backend code touched), 235 frontend tests / 32 files, both clean.

**Epic 10 Phase A, post-verification bug fix (2026-07-18, real user
report):** "Change my folders" stopped opening the native dialog at
all -- confirmed via her own report, then reproduced live: a real
`POST /api/dialogs/folder` call against a real running server never
returned (full timeout, empty response), while every other route on the
same server kept responding normally the whole time. **Root cause:**
`tkinter`'s `Tk()`/dialogs need one *consistent* thread for their global
interpreter state, but every Flask route runs on a fresh thread from
`waitress`'s worker-thread pool on each request, never the process's
actual main thread -- `backend/dialogs.py::pick_folder()` was being
called directly from the route handler, landing on a different thread
every time. Not a Phase A regression (`dialogs.py`/`FoldersScreen.tsx`
untouched since Epic 7/8, confirmed via `git log`) -- a pre-existing bug
that had simply never been exercised against a real running server
before, since every automated test mocks the dialog call out, and Phase
A's own single-process path is what made clicking through the real GUI
this easy for the first time. **Fix:** `request_folder_pick()` -- a
single background thread, started lazily and reused for the process's
whole lifetime, now owns every real `tkinter` call; a route submits a
request via a queue and blocks for the answer, same behavior as before,
just the right thread doing the work. `pick_folder()` itself (the
directly-testable dialog logic) is unchanged. **Live-verified, not just
unit-tested:** a real running server with the dialog's own deepest call
faked (driveable without a human clicking an OS dialog) handled 8
sequential and 6 concurrent real HTTP calls correctly and quickly
(~200ms each), staying fully healthy throughout -- the same real-server
test reproduced the original hang, every time, before the fix. Full
writeup: `docs/BACKLOG.md` Epic 10 Phase A, `ADR-0006`'s addendum.

**Epic 10 Phase A, a second post-verification bug fix, same day (real
user report):** auto-load-from-folder's "Add N books" button failed
every book whose filename had a space in it -- "The Dragon Reborn.epub,"
visibly listed on the same screen a moment earlier, came back "That file
couldn't be found in your books folder" the instant she tried to add
it. **Root cause:** `backend/app.py::_safe_folder_epub_path()` ran the
filename through `secure_filename()` before looking it up on disk --
copied from `_safe_upload_path()`'s own defense above it, which is the
right tool for choosing a *new* filename to write but the wrong one for
looking up an *existing* file by its exact, already-known name.
Confirmed directly: `secure_filename("The Dragon Reborn.epub")` ->
`"The_Dragon_Reborn.epub"`, which never existed. **Fix:** drop the
`secure_filename()` step; reject any filename containing a path-
separator character outright (sufficient on its own to block traversal
as a single path component), on top of the resolve()-and-containment
check that was already there as defense in depth. New regression test
adds a real file with a space in its name and confirms the full add
flow succeeds -- the same class of gap the traversal tests didn't catch,
since they only ever used filenames *without* spaces.

**Epic 10 Phase A (2026-07-18, same day as Epic 9's own pass below):**
built and live-verified everything needed to unblock real-person testing
without the full PyInstaller/SmartScreen/installer work. 472 backend
tests / 96% coverage, 235 frontend tests / 32 files, both clean via a
real `pytest --cov` and a real `npm run build && npm run lint && npm
test` pass.

- **Flask serves the built frontend:** `backend/app.py::
  _frontend_dist_dir()` resolves `frontend/dist/` both in dev (relative
  to `backend/app.py`) and under a frozen `.exe`'s `sys._MEIPASS` (built
  now, exercised once Phase B's PyInstaller work exists). A catch-all
  `GET /` / `GET /<path:path>` route, registered last in `create_app()`
  (Werkzeug sorts by specificity regardless of registration order, so
  this never actually shadows `/api/*` routes — registered last purely
  for readability), serves it — `App.tsx` has no client-side routing at
  all, so the fallback unconditionally serves `index.html` for any
  unmatched GET, except a GET under `/api/` specifically, which still
  gets a real 404 rather than silently looking like a frontend bug.
  `Flask(__name__, static_folder=None)` disables Flask's own unrelated
  default `/static/` convention entirely, avoiding any ambiguity with
  the catch-all. **Live-verified with curl against a real running
  server** (`python launcher.py`, not just the Flask test client): real
  `index.html`, a real static asset, real JSON from `/api/status`, SPA
  fallback for an unrelated path, and a real 404 for a mistyped
  `/api/*` path — all confirmed, then shut down cleanly via
  `/api/quit`.
- **`run_gui.vbs`** (repo root): a `pythonw.exe` wrapper around
  `launcher.py` for a no-console double-click launch, without any
  PyInstaller work — explicitly a testing-phase stand-in for the real
  `.exe` (Phase B). **Live-verified via `cscript`**, not just written:
  confirmed a real server actually starts (curl against the port
  sidecar file's port), no console window, and no lingering `pythonw`
  process after `/api/quit`.
- **Auto-load-from-folder** (moved from Epic 8.5): `GET`/
  `POST /api/books/from-folder`. The `POST` deliberately reuses
  `POST /api/books`'s exact per-file result shape, so the frontend's
  existing rejection-handling logic in `AddBooksScreen` needed zero
  changes to also handle this second source. Each filename is
  re-validated server-side (`secure_filename` + containment check, the
  same defensive pattern as `_safe_upload_path`) before being read from
  `books_folder` — never trusted blindly even though it's this app's own
  frontend sending it. **Default-checked-state decision:** everything
  found starts pre-checked (fewest required actions for the common
  case); the list re-fetches whenever the batch's book count changes
  (same dependency pattern as the existing disk-space effect), so an
  added item drops off automatically.
- **Field Correction Popup format hints** (moved from Epic 8.5): a new
  optional `hint` prop, tied to the input via `aria-describedby`. Reused
  identically at both call sites (`ConfirmMetadataScreen`'s standalone
  popups, `FixInfoFlow`'s shared step-through) — Author gets "Last name,
  first name -- like Jacka, Benedict," Series Number gets "Just the
  number -- like 1 or 2.5," Title/Series get no hint (no particular
  expected shape).
- **Phase B (the real PyInstaller `.exe`) deliberately not started** —
  see the reasoning already captured in `docs/BACKLOG.md` Epic 10's own
  intro: iterating against a packaged `.exe` costs a full rebuild plus a
  fresh SmartScreen click-through on every single fix, so it waits for
  an initial round of real-person feedback against the cheap
  single-process path above first.

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
