# epub-automation — Implementation Backlog

**Status:** Epics 0–8 complete. Epic 8.5 (real-user feedback pass) in progress — visual/whitespace redesign, header/landmark, Male/Female voice labels, stronger selected-state contrast, bigger Listen targets, and back/home navigation done (2026-07-12); auto-load-from-folder, AI-enrichment field merge, input format hints, and the Working-screen progress bar remain. Epic 9+ not started.

This is the source of truth for *build order*. `docs/requirements/` is
*what*, `docs/design/` is *why*, `docs/design/PATTERNS.md` is *how*,
this file is *in what order*.

**Sequencing:** scaffolding first, then the two highest-risk items
(sanitize port, Kokoro packaging spike) run in parallel, then the
remaining stages in reuse order, then the backend contract, frontend +
accessibility, then packaging/QA/docs close-out. New code and unverified
assumptions are front-loaded; ported/tested logic is back-loaded.

**Confirmed at kickoff:** Windows-only v1 scope; Gemini free-tier
data-use trade-off accepted. Gemini and OpenAI are equally first-class
provider choices (Epic 3).

**Usage:** work top to bottom within an epic unless noted otherwise.
Mark `[ ]` → `[x]` as completed; add new stories here if work surfaces
that isn't captured yet.

---

## Epic 0 — Scaffolding & Cross-Cutting Infrastructure ✅ Complete

- [x] Repo structure per `01-architecture.md` (`pipeline/`, `backend/`,
  `frontend/`, `main.py`, `launcher.py`, `tests/`); stage files deferred
  to their own epics
- [x] `Stage` protocol + `BookState` (Pipeline pattern) — `pipeline/stage.py`
- [x] `StateRepository` / `AuditLogRepository` with schema versioning —
  `pipeline/state_manager.py`, `pipeline/audit_logger.py`
- [x] Atomic write/read for settings + state (ADR-0005), TDD'd with a
  crash-mid-write test — `pipeline/atomic_write.py`
- [x] Single-instance lock with PID-based stale-lock detection (ADR-0007,
  uses `psutil`) — `pipeline/single_instance.py`
- [x] `SafeZipOperation` Template Method base — path-traversal →
  zip-bomb cap → XXE, with adversarial fixtures — `pipeline/safe_zip.py`
- [x] CI skeleton: `pytest`/`pytest-cov` (80% floor), `black`, `ruff`,
  `mypy --strict`, ported from `epub-renamer`'s toolchain
- [x] Profanity list bundling + first-run seed — `pipeline/config.py`
- [x] `.env.example` for CLI/advanced use
- [x] Exact dependency pinning in `requirements.txt`

---

## Epic 1 — Kokoro/PyInstaller Packaging Spike ✅ Complete (2026-07-08)

The highest-blast-radius open item, sequenced early. *(Ran in parallel
with Epic 2.)*

- [x] Espeak-ng confirmed required, shipped via `espeakng-loader==0.2.4`
  (DLL + data as a Python wheel, loaded via ctypes)
- [x] Spike script verifies import → model load → audio generation —
  `spike/kokoro_spike.py`
- [x] Full PyInstaller build + standalone `.exe` test, verified on
  Windows: `dist\kokoro_spike.exe` produces a real 153KB `spike_output.wav`

**Confirmed working build command** (full context in
`07-packaging-deployment.md` §Known packaging constraints):

```
pip install https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl

pyinstaller --onefile \
    --collect-data espeakng_loader \
    --collect-data language_tags \
    --collect-data misaki \
    --collect-all en_core_web_sm \
    --collect-all torch \
    --collect-all transformers \
    --collect-all kokoro \
    --collect-all soundfile \
    spike/kokoro_spike.py
```

**Notes:** three data-only packages needed explicit `--collect-*` flags
beyond the original spike (`language_tags`, `misaki`, `soundfile`) — all
the same root cause as espeak-ng (ctypes/`importlib.resources` data
invisible to static analysis). One genuinely new runtime dependency:
`en_core_web_sm` (spaCy model), since misaki's `pip`-based auto-download
fails inside a frozen exe. Both `en_core_web_sm` and `soundfile` are now
pinned in `requirements.txt`.

---

## Epic 2 — Sanitize Stage Port (PowerShell → Python) ✅ Complete (2026-07-06)

Highest-risk stage: the only full language port, security-critical
(untrusted ZIPs). See ADR-0004.

- [x] All 10 security controls ported from `PS_Run-CleanUpEpub.ps1`:
  path-traversal guard, zip-bomb cap, XXE prevention, profanity size
  cap, whole-word matching, asterisk replacement, `.xhtml`/`.htm`/`.html`
  scope, mimetype-first repack, temp-dir cleanup — `pipeline/sanitize_stage.py`
- [x] `regex` package for Unicode whole-word matching + 5s ReDoS timeout
  (`regex==2026.6.28`, Apache-2.0)
- [x] Built on `SafeZipOperation` (`_ExtractEpub` subclass)
- [x] Sidecar CSV report + audit-log columns
- [x] 29-test adversarial suite (path-traversal, zip-bomb, XXE, ReDoS,
  profanity cap, Unicode boundaries) — all 82 project tests pass
- [x] Editable word list via `settings.json`

---

## Epic 3 — Rename Stage Port ✅ Complete (2026-07-08)

- [x] Port `ai_providers/` registry as-is: `base.py`, `registry.py`,
  `openai_provider.py`, `null_provider.py` (ADR-0003/0014) —
  `pipeline/ai_providers/`. Adapted to take `api_key` explicitly via
  constructor (settings.json-driven, not the original's `.env`-backed
  `config.py`); registry keys renamed `"null"` → `"none"` to match
  settings.json's `ai_provider` vocabulary.
- [x] Write `gemini_provider.py` — the one new provider (ADR-0003) —
  uses the `google-genai` SDK (the maintained successor to the
  deprecated `google-generativeai` package), mirrors `OpenAIProvider`'s
  prompt/JSON-parsing structure via a shared `parse_json_object()` helper
  in `ai_providers/base.py`.
- [x] Both providers equally selectable via `settings.json`; neither is
  default — `pipeline/ai_providers/registry.py`'s `PROVIDERS` dict.
- [x] Port `MAX_FILES` cap + `DRY_RUN=true` default — `dry_run` is a
  per-call `RenameStage` constructor flag (honored: writes no file,
  logs `skipped_reason="dry_run"`). `MAX_FILES` batch-level enforcement
  (stopping a batch, rejecting excess books at Screen 1) is deferred to
  Epic 6/Epic 8 — `Stage.run()` is per-book by design
  (`docs/design/PATTERNS.md`), so there's no batch loop in this stage to
  cap. `DEFAULT_MAX_FILES = 50` exported from `rename_stage.py` for
  those epics to wire up.
- [x] `FILENAME_PATTERN` reuse + already-normalized-skip logic — ported
  verbatim, ADR-0016 confirms it only matches shape, not characters.
- [x] Per-file silent fallback to `NullProvider` on AI failure — both at
  construction time (bad config) and per-`run()` call (runtime failure).
- **Deferred at the time:** MAX_FILES overflow (rejecting excess books
  individually at Screen 1) needed a Screen 1 that didn't exist yet.
  **Resolved in Epic 6:** the enforcement itself is now built —
  `pipeline/input_validation.py::check_batch_capacity()`, wired into
  `BatchRunner.add_book()` and exposed per-file via `POST /api/books`
  (`reason: "max_files_exceeded"`, a ready-to-display friendly message).
  Only the Screen 1 UI rendering of that per-file rejection is still
  open — moved to Epic 8's own checklist below, since that's genuinely
  the earliest point it can be finished.
- [x] **New this epic, not originally listed:** `pipeline/epub_utils.py`
  `sanitize_filesystem_name()` (ADR-0016) — shared by rename now, retag
  (Epic 5) later. `pipeline/epub_reader.py` ported verbatim
  (`extract_epub_metadata`/`extract_text_sample`).

---

## Epic 4 — Audio Stage (Kokoro TTS Integration) ✅ Complete (2026-07-10)

- [x] `tts_engine.py` wrapping `kokoro.KPipeline` — `pipeline/tts_engine.py`.
  `KPipeline` itself is imported lazily (inside `_get_pipeline()`, first
  real call only), matching the lazy-download requirement below;
  `pipeline_factory` constructor param is the testing seam (never
  downloads/runs the real model in tests).
- [x] Reuse `chunk_text()` / `MAX_CHUNK_CHARS = 4,000` — ported verbatim
  into `pipeline/epub_utils.py` alongside `extract_chapters()`,
  `normalise_heading()`, `DEFAULT_STOP_AFTER` (ADR-0014). Still flagged
  for re-validation against real Kokoro output once real side-by-side
  samples exist (04-tts-engine.md §Open item for review).
- [x] MP3 encoding: 128kbps CBR, mono — **resolved during implementation,
  not 48kHz as originally written**: encodes at Kokoro's native 24kHz
  (confirmed by the already-verified Epic 1 spike) via `lameenc`, a new
  pinned dependency. `soundfile`/libsndfile's MP3 writer (used for Epic
  1's WAV spike) turned out to only expose a `compression_level` quality
  knob, not a real bitrate control — measured ~21kbps at its highest
  setting during implementation, nowhere near 128kbps CBR. Full writeup:
  04-tts-engine.md §MP3 encoding parameters. `pipeline/tts_engine.py`'s
  `_encode_mp3()`.
- [x] Voice sample pre-generation + cache, versioned by installed
  `kokoro` version — `pipeline/tts_engine.py::ensure_voice_samples()`.
  On regeneration failure (e.g. offline), existing stale-tagged samples
  are left in place rather than deleted first, retried on a future call.
- [x] Lazy first-run trigger for model download + voice samples — the
  laziness itself lives in `TTSEngine`/`ensure_voice_samples()` (nothing
  imports `kokoro` or touches the model until a real call happens).
  *Deciding when* to make that first call (a real audio-stage run, or
  her opening the voice picker) is `bridge.py`/GUI wiring — genuinely
  Epic 6/8 scope, no batch runner or voice-picker screen exists yet.
  Same split Epic 3 used for `DEFAULT_MAX_FILES`.
- [x] Per-chunk resume (skip existing MP3 above size threshold) —
  `pipeline/audio_stage.py::MIN_VALID_MP3_BYTES`, ported verbatim
  (`> 1024` bytes) from `epub-to-audio`'s resume check.
- [x] Disk-space estimate formula (`SECONDS_PER_CHAR` placeholder,
  biased toward overestimating) — `pipeline/tts_engine.py::
  estimate_audio_bytes()`. Pure function, reusable by both CLI and GUI
  once a Screen 1 exists to call it (Epic 8).
- **Deferred at the time:** session-local same-series voice default (no
  persisted memory) — genuinely not this stage's job: it requires
  knowing which books in the *current batch* share a series, which
  `Stage.run()`'s per-book signature has no visibility into (same
  reasoning Epic 3 used to defer `MAX_FILES` batch-level enforcement).
  `AudioStage` takes whatever voice the caller already resolved via
  `book.data["voice"]`. **Partly resolved in Epic 6:**
  `pipeline/batch_runner.py::BatchRunner` now exists and *does* have
  full batch visibility (the blocking reason above no longer applies),
  but its `_maybe_enter_voice_pick()` only implements a single uniform
  global default (`settings.last_voice`) for every book — not the
  series-grouping default `03-gui-ux-design.md` describes. That page's
  own wording turned out to be ambiguous/effectively vacuous for the
  single-global-default case (see `CODEBASE_INDEX.md`'s Epic 6 session
  notes for the full reasoning). Whether a real series-grouping
  implementation is actually needed, once the multi-book voice table
  screen makes the question concrete, is moved to Epic 8's own
  checklist below.
- **Deferred at the time, needs real hardware/a real listen, not
  resolvable in any coding session:** CPU vs. GPU benchmarking
  (produces the real `SECONDS_PER_CHAR` the Working-screen time
  estimate needs) and a Kokoro vs. Perchance parity QA pass before
  retiring the Selenium path. Both moved to Epic 10's checklist below —
  the first point a packaged `.exe` gets run on real target hardware,
  not a dev machine.

**New this epic, not originally listed:** `pipeline/epub_reader.py::
extract_cover_bytes()` (3-strategy fallback, ported verbatim from
`epub-to-audio\epub_utils.py`) — needed for ID3 cover art, landed
alongside `extract_epub_metadata()`/`extract_text_sample()` since it
operates on the same already-opened `ebooklib` `Book` object, not
chunked chapter text. `pyproject.toml` gained a scoped
`disallow_untyped_calls = false` override for `pipeline.audio_stage`
only — mutagen ships `py.typed` but its ID3 frame classes aren't fully
annotated, and mypy evaluates that strict flag at the call site's
module, not the callee's.

---

## Epic 5 — Retag Stage ✅ Complete (2026-07-10)

- [x] Port `retag.py` into `retag_stage.py` — folder-name parsing (old
  standalone-tool shape + this pipeline's own `build_filename()` shape),
  MP3-filename-suffix chapter-title/track derivation, ID3 tag rewriting
  — `pipeline/retag_stage.py`
- [x] Fix folder-rename bug: rename the containing folder, not just the
  MP3s (real gap in the original script) — `RetagStage._retag_folder_name()`
- [x] Regression test for the folder-rename fix —
  `test_run_renames_folder_not_just_files` in `tests/test_retag_stage.py`
- [x] Dry-run support — constructor-level `dry_run` flag, same convention
  as `RenameStage`
- [x] Author/title/series/series-number override plumbing — `book.data`'s
  existing fields (set by `RenameStage`/`AudioStage`, or corrected via
  "No, let me fix it") take precedence over folder-name parsing; parsing
  is the fallback for retagging an arbitrary folder with no known
  `book.data` (see `pipeline/retag_stage.py` module docstring for the
  full adaptation rationale)

---

## Epic 6 — Backend / Flask Bridge ✅ Complete (2026-07-10)

- [x] `launcher.py`: free-port discovery (`find_free_port()`), browser-launch
  retry + native-dialog fallback (`open_browser()`) (Epic 0 already had
  fixed bind + lock). Dynamic port selection needed a small port-sidecar
  file next to the lock file so a second launch can still reopen a tab
  to the running instance — new this epic, owned by `launcher.py` only.
- [x] `backend/app.py` full route set + `backend/dialogs.py`
  (`tkinter.filedialog`, injectable `tk_factory`/`ask_directory` seams)
- [x] `backend/bridge.py` — thin Adapter into `pipeline/`, zero business
  logic (`derive_batch_state()` itself is the one real function, a pure
  State Machine translation, not a pipeline decision)
- [x] Status endpoint: state-machine derivation per the fixed precedence
  rule, unit-tested independent of HTTP (`tests/test_bridge.py`) — one
  documented deviation for the `review_result`/`output_collision`
  `needs_input` types this epic added (see `derive_batch_state()`'s
  docstring and `CODEBASE_INDEX.md`'s Epic 6 session notes)
- [x] Progress via Observer-style event stream from stages —
  `AudioStage`'s new `on_progress`/`should_stop` hooks, consumed by
  `pipeline/batch_runner.py::BatchRunner`
- [x] `main.py` CLI wired to real stage calls via the new
  `pipeline/cli_runner.py` (non-interactive, no `BatchRunner`); `--workers
  N` still reserved, unimplemented (ADR-0009). `retag`'s CLI surface
  (folder + override flags) added new this epic.
- [x] Error communication: generic message + "Copy details" bundle
  (`backend/bridge.py::build_support_bundle`/`write_support_bundle`,
  never includes `ai_api_key`)
- [x] Output-collision handling: distinct prompts for EPUB vs. audiobook
  — `NeedsInputType.OUTPUT_COLLISION`, resolved via
  `BatchRunner.resolve_collision()` / `POST /api/books/<id>/collision`

**New this epic, not originally listed:** `pipeline/batch_runner.py`
(`BatchRunner`, the stateful interactive engine the GUI polling contract
is actually built on — not called out by name anywhere in the original
backlog bullet list above, but required to implement all of them
together), `pipeline/input_validation.py` (Screen-1 file validation —
extension/zip-validity/DRM/`MAX_FILES`, wired up per Epic 3's own
deferred scope note), `pipeline/disk_space.py` (pre-batch estimate/check,
composing `tts_engine.estimate_audio_bytes()` with a real
`shutil.disk_usage()` call), `StateRepository.incomplete_book_ids()`
(the "Welcome back" screen's data source — detection only this epic, full
resume reconstruction deferred to Epic 8). Also fixed two pre-existing
bugs found during implementation: a stray `</content>` artifact in
`requirements.txt` (breaking CI's `pip install`) and five docs files with
the same artifact, and a real false-positive in `pipeline/safe_zip.py`'s
XXE guard (flagged every plain `<!DOCTYPE html>`, not just a dangerous
one) — full detail in `CODEBASE_INDEX.md`'s Epic 6 session notes.

**Also decided post-Epic-6 (2026-07-10, before Epic 7 started):** the
Origin/CSRF check added in the post-review fixes above will reject the
Vite dev server's cross-origin traffic during Epic 7/8 development
(different port than Flask's dynamically-assigned one). Resolved as a
frontend-side fix, not a backend relaxation — see Epic 7's first
checklist item and `frontend/README.md`.

---

## Epic 7 — Frontend Scaffolding ✅ Complete (2026-07-11, combined with Epic 8)

- [x] Vite + React setup (build-time only, no runtime Node/npm in the
  packaged `.exe`) — React 19 + TypeScript, ESLint 9 (flat config,
  swapped in for `create-vite`'s default oxlint so
  `eslint-plugin-jsx-a11y` could be wired in), Vitest 4
- [x] **Dev-server proxy + Origin-header rewrite** so Vite's dev origin
  doesn't trip `backend/app.py::_origin_is_allowed()`'s CSRF/Origin
  check (added in the Epic 6 post-review fixes) — implemented exactly
  as drafted in `frontend/README.md`. Backend check itself unchanged.
- [x] API-client facade wrapping all `fetch` calls — `frontend/src/api/
  client.ts` + `types.ts`
- [x] `usePollingStatus()`, `useFocusTrap()`, `useAriaLiveThrottled()` hooks
- [x] `useReducer`-based local UI state — realized as `App.tsx`'s
  phase/sub-view state (folders → AI helper → welcome-back → main,
  plus which settings sub-screen or fix-it flow is open)
- [x] Container/Presentational split — `App.tsx` owns
  `usePollingStatus()`; every screen component receives plain props
- [x] Frontend CI job (Vitest + coverage, `axe-core` via `vitest-axe`,
  `eslint-plugin-jsx-a11y`) — `.github/workflows/ci.yml`

**New this epic, not originally listed:** two new backend routes
turned out to be required just to make the API-client facade complete
against what Epic 8's screens would actually need —
`GET /api/voices` (no route ever told the frontend what voice keys
exist) and the voice-sample-playback endpoint. See Epic 8's own "New
this epic" note for the rest; full reasoning in
`CODEBASE_INDEX.md`'s Epic 7+8 session notes.

---

## Epic 8 — GUI Screens ✅ Complete (2026-07-11, combined with Epic 7)

Built in encounter order per `03-gui-ux-design.md`. Every screen meets
WCAG 2.1 AA alignment (axe-core assertions in each screen's own test
file, plus manual review) before being marked done here — the
**manual** keyboard-only/NVDA/dyslexic-reader passes remain Epic 9's
own separate, not-yet-done checklist, per `09-testing-strategy.md`'s
explicit split between automated (done, CI-enforced) and manual
(best-effort, not yet scheduled) verification.

- [x] First-launch setup (folder pickers) — `FoldersScreen`, reused
  identically for the later "⚙️ Change my folders" entry point
- [x] AI Helper Setup (provider choice, key entry, masked display) —
  `AiHelperSetup`, one component covering intro → choice → key
- [x] "Welcome back" screen (state-file driven) — degrades honestly to
  a plain count when the backend can't identify a pending book by
  title (see its own module comment: full crash-resume `BatchRunner`
  reconstruction is still separate, open work, unchanged from what
  `CLAUDE.md` already flagged)
- [x] Screen 1: Add Books (drag-and-drop + button, per-book Remove,
  stage toggles, `MAX_FILES`-exceeded rejection message per file)
- [x] Field Correction Popup (one shared component, reused by the
  identification loop's confirm step, the voice table's title-edit
  overlay, and the "No, let me fix it" step-through alike)
- [x] Per-book identification loop — `ConfirmMetadataScreen`
- [x] Voice assignment (single-book + multi-book table, shared
  `useVoiceAssignmentView` hook). **Decided:** the session-local
  same-series default is *not* reproduced client-side — the backend
  only ever hands out one global default
  (`_maybe_enter_voice_pick()`), and a second client-only notion of
  "current default" that could silently disagree with the server was
  judged worse than the marginal convenience. "Change Voice" already
  covers giving specific books a different voice either way.
- [x] Screen: Working (dynamic time estimate derived client-side from
  observed chunks-per-second throughput this job, since the polling
  contract carries no timestamps; Pause/Cancel with a confirmation +
  keep-partial/discard choice; Quit for now)
- [x] Screen: Review (per-book link + output-folder link, both via new
  backend routes that resolve the path server-side — no raw filesystem
  path ever crosses the wire)
- [x] "No, let me fix it" flow (feeds `retag_stage.py` via `retagBook()`)
- [x] Settings: folders, word list, voice history (read-only)

**New this epic, not originally listed — all found by building the
real frontend against the real backend, not pre-planned:**
`POST /api/books/<id>/metadata` (the voice table's clickable-title
edit needed its own mutation, since a book there has already passed
`confirm_metadata` and `retag` only applies post-generation),
`POST /api/books/<id>/open-folder` + `POST /api/open-output-folder`
(browsers can't open a native Explorer window any more than a native
folder-picker dialog — same ADR-0006 reasoning, `backend/dialogs.py::
open_folder()`). **Two real pre-existing bugs found and fixed** (not
new-code bugs): the GUI upload route's collision-avoiding temp
filename was leaking into Screen 1's displayed filename
(`BatchRunner.add_book()` gained a display-only `original_filename`
override); `_maybe_enter_voice_pick()` was auto-starting single-book
generation before the voice picker could ever matter, contradicting
`assign_voice()`'s own docstring — both regression-tested. Full
writeup: `CODEBASE_INDEX.md`'s Epic 7+8 session notes.

---

## Epic 8.5 — First real-user feedback pass

Epic 8 was complete as originally scoped; this epic captures what a
real hands-on run through the GUI surfaced (2026-07-12), before Epic 9's
own (separately-scoped) manual accessibility passes. Numbered `8.5`
rather than renumbering Epic 9/10/11, which are referenced by number
throughout `CLAUDE.md` and `CODEBASE_INDEX.md`.

- [x] **Persistent `<header>` landmark, plain-language app name** (e.g.
  "📚 Audiobook Maker") on every screen. Two birds: makes it obvious
  which app/screen she's looking at (her own feedback), and closes a
  WCAG landmark requirement `03-gui-ux-design.md` §Robust already
  specifies ("a page `<header>`... so a screen-reader user can jump
  between sections") that never actually got built — every screen
  today is a bare `<main>` with a heading, no separate header region.
- [ ] **Screen 1: auto-load books already in the configured
  `books_folder`** as a checklist she can select from, *alongside*
  (not instead of) the existing drag-and-drop/"Choose Books..." for
  files elsewhere — asking her to drag-and-drop files that are already
  sitting in the folder she just picked is redundant. Needs: a backend
  route to list `.epub` files in `books_folder` without uploading them
  first, a decision on default-checked state, and an update to
  `03-gui-ux-design.md`'s Screen 1 spec (currently describes
  drag-and-drop/Choose-Books as the only entry path, list starting
  empty) so the doc and the code don't quietly diverge.
- [x] **General spacing/whitespace pass across every screen** — buttons
  and inputs sit too close together right now (real "oops-click" risk
  on a laptop/desktop, which has screen space to spare). No design
  conflict, just execution; treat as a full visual pass, not a
  one-line tweak.
- [ ] **Rename stage: AI-enrichment sanity check / per-field merge.**
  Real bug: a fully-parseable filename ("Sanderson, Brandon — The
  Stormlight Archive #01 — The Way of Kings.epub") round-tripped
  through AI enrichment as just `title: "The Way of Kings"`, losing
  author/series/series-number the filename plainly had. Fix: merge
  AI's response with what filename-parsing/EPUB-metadata already
  found, per field — a blank/missing AI field should fall back to the
  already-available value instead of the whole result being trusted
  wholesale. Lives in `pipeline/rename_stage.py`.
- [ ] **Format hint text on Field Correction Popup inputs.** Author
  gets a "Last Name, First Name" hint; Series Number gets a
  numeric-format hint. Applies everywhere the popup is used (Confirm
  metadata, the voice table's title-edit, "No, let me fix it") since
  it's the same shared component.
- [x] **Voice picker: Male/Female label per voice.** Reverses
  `03-gui-ux-design.md`'s current explicit "no gender/accent/
  quality-grade labels" rule — update that doc's Voice assignment
  section alongside the code, with a short note on why (real user
  feedback: helpful for choosing, not just decorative detail).
- [x] **Voice picker: bigger Listen button.** Never got the same
  big-click-target (~70px) treatment the rest of the app's controls
  have — `RadioRow`'s nested action button needs its own sizing, not
  just inherited row padding.
- [x] **Clickable-row selected/checked state: stronger, non-color-only
  contrast.** The current light-blue tint (`.clickable-row--checked`)
  likely fails the 3:1 UI-component contrast minimum this project
  already commits to elsewhere; add a checkmark icon alongside a
  darker background so the selected state isn't color-dependent either.
- [x] **Back buttons on multi-step flows, Home button from settings
  sub-views.** Not one of the original 8 feedback items — a separate
  mid-review ask. `FieldCorrectionPopup` gained an optional `onBack`
  prop (used by `AiHelperSetup`'s steps and `FixInfoFlow`'s field
  sequence); `AppHeader`'s Home button appears only when
  `subView !== null` (Folders/Words/AI Helper/Voice History), never
  mid-onboarding or mid-batch, since those screens already *are* her
  true current state.
- [x] **Remove-this-book generalized past Screen 1, to every screen a
  book can get stuck on.** Real bug hit live (2026-07-12): a file that
  passed Screen 1's shallow zip/mimetype check but failed real EPUB
  parsing later landed the whole batch on `ErrorScreen` with no way to
  identify or remove the offending book — "Back to Add Books" just
  re-polled into the same error forever, since `derive_batch_state()`
  stays `"error"` for as long as any book is in `error` status. Fixed
  via a shared `RemoveBookButton` (calls the existing
  `POST /books/<id>/cancel`, which already accepted a book in any
  status, not just `generating` — no backend change needed) added to
  `ErrorScreen` (now also names which book is at fault), the
  identification loop's `ConfirmMetadataScreen`, and both
  `VoiceAssignmentScreen` modes (single + table). Screen 1's original
  Remove got the same ✕-icon treatment for visual consistency.
- [ ] **Working screen: visible chunk-progress readout + a real
  progress bar.** E.g. "Part 45 of 120" plus a `<progress>`/styled bar
  — uses `progress.chunks_done`/`chunks_total` the backend already
  sends every poll (no backend change needed), just never surfaced
  visibly. Still paired with the existing friendly text + dynamic time
  estimate, not a replacement for it (`03-gui-ux-design.md`'s "never a
  bare percentage or spinner alone" still holds — this is a bar *with*
  context, not instead of it).

---

## Epic 9 — Accessibility Verification

- [ ] `axe-core` + `eslint-plugin-jsx-a11y` wired into CI
- [ ] Manual keyboard-only pass, all screens
- [ ] Real NVDA pass + Narrator sanity check
- [ ] Real dyslexic-reader test (unassisted)
- [ ] **Open:** screen-reader tester — confirm, or document the honest
  fallback framing if none materializes
- [ ] **Open:** her-facing copy read-through — real unassisted dry run
- [ ] **Open:** per-series voice memory, second look after real
  multi-book use

---

## Epic 10 — Packaging & First-Run Experience

- [ ] **Flask must gain a route serving `frontend/dist/`** (static files +
  an `index.html` fallback for client-side routing) — confirmed missing
  while closing out Epic 7/8: `backend/app.py` currently only registers
  `/api/*` JSON routes, so `python launcher.py` alone opens a browser to
  a `404`. Dev mode works today because Vite serves the frontend
  directly on its own port and proxies `/api` through
  (`frontend/vite.config.ts`) — that path never needed Flask to serve
  anything but JSON. This is genuinely packaging-shaped work (locating
  the bundled `dist/` at a frozen `.exe`'s runtime path, e.g.
  `sys._MEIPASS`, is PyInstaller-specific), which is why it was left
  here rather than pulled into Epic 7/8, but it blocks *any* single-
  process/single-command way to see the GUI, not just the final `.exe`
  — worth doing early in this epic, not saved for last.
- [ ] Full PyInstaller build pipeline (`npm run build` → `dist/` → bundle)
- [ ] SmartScreen mitigation: installer runs it once first + fallback
  HTML file
- [ ] Browser-launch fallback: retry, then native `tkinter` dialog with
  clipboard-copied address
- [ ] First-run setup screen tied to the lazy trigger point
- [ ] Verify uninstall is genuinely two deletions
- [ ] **Moved from Epic 4:** CPU vs. GPU benchmarking on real target
  hardware — produces the real `SECONDS_PER_CHAR` constant
  (`pipeline/tts_engine.py`) the Working-screen time estimate needs,
  replacing the current placeholder. Needs a real packaged `.exe` on
  real hardware, which this epic is the first point that exists.
- [ ] **Moved from Epic 4:** Kokoro vs. Perchance output parity QA pass
  — a real side-by-side listen before fully retiring the old
  Selenium/Perchance path as a fallback option.

---

## Epic 11 — Documentation & Release Wrap-Up

- [x] `CODEBASE_INDEX.md` created (Epic 0), kept current since
- [ ] `NOTICE` file from `10-licensing-and-notices.md`'s dependency
  table (include `en_core_web_sm`, `soundfile`)
- [ ] Coverage badge in README
- [ ] Privacy note in shipped README
- [ ] Final `CLAUDE.md`/ADR/`SYSTEM_DESIGN.md` consistency pass

---

## Open Items

| Item | Epic |
|---|---|
| Kokoro/PyInstaller packaging risk | 1 — done |
| Dependency version pinning | 0 — done |
| Perchance vs. Kokoro output parity | 10 (moved from 4 — needs a real packaged `.exe` on real hardware) |
| CPU vs. GPU benchmarking (`SECONDS_PER_CHAR`) | 10 (moved from 4, same reason) |
| MAX_FILES-exceeded rejection message, Screen 1 UI | 8 — done |
| Session-local same-series voice default | 8 — **decided against** (moved from 4): the backend only ever hands out one global default; a second, client-only notion of "current default" risked silently disagreeing with the server for marginal convenience. "Change Voice" already covers the real need. See Epic 8's own checklist note. |
| Her-facing copy wording, unassisted dry-run test | 9 |
| Screen-reader tester confirmation | 9 |
| Per-series voice memory, second look | 9 (same decision as the session-local default above, revisit together if ever) |
| "Welcome back" full state-file-driven resume (rebuild a live `BatchRunner` after a backend restart) | Still open — `GET /api/welcome-back` (Epic 6) plus the Epic 8 screen built against it both remain detection-only; `WelcomeBack.tsx` degrades honestly to a plain count rather than fabricating detail when this hasn't happened. No epic currently owns doing the reconstruction itself — flag before Epic 9's manual passes rely on a real multi-launch scenario. |
| Vite dev-server Origin/CSRF proxy config | 7 — done |
