# epub-automation — Implementation Backlog

**Status:** Epics 0–6 complete. Epic 7+ not started.

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
- [ ] MAX_FILES overflow: reject excess books individually at Screen 1 —
  genuinely Epic 8 scope (no Screen 1 exists yet); left unchecked here,
  tracked there.
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
- [ ] Session-local same-series voice default (no persisted memory) —
  genuinely Epic 8 scope, not this stage: it requires knowing which
  books in the *current batch* share a series, which `Stage.run()`'s
  per-book signature has no visibility into (same reasoning Epic 3 used
  to defer `MAX_FILES` batch-level enforcement). `AudioStage` takes
  whatever voice the caller already resolved via `book.data["voice"]`.
- [ ] **Open:** CPU vs. GPU benchmarking on real hardware — produces
  `SECONDS_PER_CHAR` and the Working-screen time estimate. Needs real
  hardware, not resolvable from this session.
- [ ] **Open:** Kokoro vs. Perchance parity QA pass before retiring the
  Selenium path. Needs a real side-by-side listen, not resolvable from
  this session.

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

---

## Epic 7 — Frontend Scaffolding

- [ ] Vite + React setup (build-time only, no runtime Node/npm in the
  packaged `.exe`)
- [ ] API-client facade wrapping all `fetch` calls
- [ ] `usePollingStatus()`, `useFocusTrap()`, `useAriaLiveThrottled()` hooks
- [ ] `useReducer`-based local UI state
- [ ] Container/Presentational split
- [ ] Frontend CI job (Vitest + coverage, `axe-core`, `eslint-plugin-jsx-a11y`)

---

## Epic 8 — GUI Screens

Build in encounter order per `03-gui-ux-design.md`. Every screen must
meet WCAG 2.1 AA alignment before being done.

- [ ] First-launch setup (folder pickers)
- [ ] AI Helper Setup (provider choice, key entry, masked display)
- [ ] "Welcome back" screen (state-file driven)
- [ ] Screen 1: Add Books (drag-and-drop + button, per-book Remove,
  stage toggles)
- [ ] Field Correction Popup (one shared component, reused everywhere)
- [ ] Per-book identification loop
- [ ] Voice assignment (single-book + multi-book table, shared
  view-model hook)
- [ ] Screen: Working (dynamic time estimate, Pause/Cancel, Quit for now)
- [ ] Screen: Review (per-book link + output-folder link)
- [ ] "No, let me fix it" flow (feeds `retag_stage.py`)
- [ ] Settings: folders, word list, voice history (read-only)

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

- [ ] Full PyInstaller build pipeline (`npm run build` → `dist/` → bundle)
- [ ] SmartScreen mitigation: installer runs it once first + fallback
  HTML file
- [ ] Browser-launch fallback: retry, then native `tkinter` dialog with
  clipboard-copied address
- [ ] First-run setup screen tied to the lazy trigger point
- [ ] Verify uninstall is genuinely two deletions

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
| Perchance vs. Kokoro output parity | 4 |
| CPU vs. GPU benchmarking (`SECONDS_PER_CHAR`) | 4 |
| Her-facing copy wording, unassisted dry-run test | 9 |
| Screen-reader tester confirmation | 9 |
| Per-series voice memory, second look | 9 |
| "Welcome back" full state-file-driven resume (rebuild a live `BatchRunner` after a backend restart) — `GET /api/welcome-back` detection-only endpoint already exists (Epic 6) | 8 |
