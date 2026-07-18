# CLAUDE.md — AI Development Rules for epub-automation
# Last updated: 2026-07-18 — Epics 0-8.6 complete. Epic 9's code-buildable items also complete (448 backend tests / 96% coverage, 216 frontend tests across 32 files, black/ruff/mypy --strict + eslint/tsc/build clean -- confirmed via real `pytest --cov` and `npm run build && npm run lint && npm test` passes, this session). Built: full "Welcome back" resume (`state.json` schema bumped to v2 to persist each book's full status/data as a `"snapshot"`, not just per-stage completion flags; `BatchRunner.restore_books()` rebuilds a live runner from those snapshots at process startup, before any request is served -- a `generating`/`paused` book coarse-grains to `voice_pick` since `AudioStage` already resumes via an existing per-chunk disk-file-size check, an `identifying` book coarse-grains to `pending` since rename/sanitize copy rather than delete their source; found and fixed a related pre-existing gap where a cancelled book never marked its `cleanup` stage complete and would have kept reappearing as "pending" forever); "clean up stuck in-progress state" (`POST /api/cleanup-in-progress`, a confirm-gated "🧹 Nuke everything in progress" button on the "More options" hub, a blanket best-effort sweep of the `Library/*` staging folders plus a full `state.json` reset, never touching `audit_log.csv`); the persistent step-progress indicator (`StepProgress`, a `<nav>`/`<ol>` wizard bar across the five main-flow screens, non-color-only current/completed state, wired into each screen's own notion of "active book" -- the multi-book voice table's needed state turned out to already exist as local component state, nothing new to add there); and confirming `axe-core`/`eslint-plugin-jsx-a11y` were already wired into CI (no code change, just a stale checkbox). **Epic 9's remaining items are all human-only** (manual keyboard-only pass, real NVDA/Narrator pass, screen-reader tester, her-facing copy dry-run, per-series voice memory second look) and cannot be completed by an AI agent -- see docs/BACKLOG.md Epic 9's own checklist. **The real dyslexic-reader test moved to docs/BACKLOG.md's new Wish List section the same day** -- the previously-lined-up tester is no longer available; see the "Dyslexic-reader tester" row in Flagged open items below. **Epic 10 Phase A built and live-verified the same day** (474 backend tests / 96% coverage, 235 frontend tests / 32 files): Flask now serves the built frontend (`backend/app.py::_frontend_dist_dir()` + a catch-all route registered last, real GET under `/api/` still 404s instead of silently serving HTML), a `run_gui.vbs` no-console launcher (live-tested via `cscript`, no console window, no lingering process after quit), and Epic 8.5's two leftover items -- Screen 1 auto-load-from-folder (`GET`/`POST /api/books/from-folder`, default-checked, reuses the upload route's own per-file result shape) and Field Correction Popup format hints (`hint` prop, `aria-describedby`-linked). All live-verified with real curl requests against an actually-running `python launcher.py` process, not just the Flask test client -- see docs/BACKLOG.md Epic 10 Phase A for the exact checks run. **Real bug found and fixed the same day, real user report:** "Change my folders" stopped opening its dialog at all -- a pre-existing threading bug (`tkinter` needs one consistent thread; every Flask route runs on a fresh `waitress` worker thread), never actually exercised against a real running server before Phase A made that this easy for the first time. Fixed via a persistent background thread owning all `tkinter` calls (`backend/dialogs.py::request_folder_pick()`, `ADR-0006`'s addendum), live-verified (not just unit-tested) with 474 backend tests total. **A third real gap found the same day, while diagnosing the two bugs above:** "Quit for now" only ever existed on the Working screen -- closing the tab never stops the background server (ADR-0001), and with no way to end the session anywhere else, a still-running pre-fix server got mistaken for "already closed," masking both fixes above behind stale code during diagnosis. Fixed: `AppHeader` gained a confirm-gated Quit button, shown on every screen except onboarding and the Working screen itself (which keeps its own, to avoid a duplicate) -- 235 frontend tests / 32 files, all clean. **A fourth real bug fixed the same day, real user report:** `RenameStage._pass_through_already_normalized()` skipped populating title/author/series for a book whose filename was already normalized, which `BatchRunner._run_identification()` couldn't tell apart from a genuine AI failure -- fixed via `_parse_normalized_filename()`, parsing those fields straight back out of the filename instead (474 backend tests). **A fifth item, real user feedback the same day** ("I need to be able to use the cookie crumb bar to go backwards. It is normal and intuitive to expect it to work that way"): `StepProgress` was a pure status indicator with no clickable steps at all. Fixed: completed steps become real buttons only where the current screen already has an existing, non-destructive way to act on them, reusing that exact action -- Choose Voice (single-book) and Review both wire their "Confirm Info" step to the edit-metadata/"No, let me fix it" flows already there. "Add Books" and "Choose Voice" (from Convert/Review) deliberately stay non-clickable -- going back there would mean reopening Screen 1 mid-batch or discarding already-generated audio, neither of which any existing action supports -- see `03-gui-ux-design.md` §Step progress indicator. 241 frontend tests / 32 files, all clean. **A sixth item, real user report the same day** ("Something went wrong" on a real failed audio-generation run): her own support bundle carried nothing but "Audio generation failed at chapter 1, chunk 1 (track 1/385)" -- `AudioStage._generate_with_retry()` discarded the real underlying exception on every attempt. Reproduced the exact failing chunk/voice live in the venv; it succeeded, pointing to a one-off transient failure (first-ever use of that voice, which fetches its assets from Hugging Face Hub on first use) rather than a reproducible bug. Fixed regardless: the last attempt's exception text now gets appended to the book's `error` field, the same field `current_error_detail()`/the support bundle already read as the "technical detail" channel -- it just had nothing real in it before now. 474 backend tests, clean `ruff`/`black`/`mypy`. Phase B (the real PyInstaller `.exe`) deliberately still not started. Full epic-by-epic history: CODEBASE_INDEX.md's Session notes.

---

## Startup protocol

1. **Epics 0-8.6 complete; Epic 9's code-buildable items complete, its
   human-only items still open.** Before writing new code,
   read: `docs/requirements/README.md` → numbered docs 00–10 →
   `docs/design/SYSTEM_DESIGN.md` → `docs/design/adr/README.md` →
   `docs/design/PATTERNS.md` → `docs/BACKLOG.md` → `CODEBASE_INDEX.md`.
   `docs/design_review.md` explains why several decisions look the way
   they do.
2. Check `docs/requirements/08-open-questions-and-assumptions.md` and
   this file's "Flagged open items" table before building against an
   open item.
3. Keep `docs/requirements/`, `docs/design/`, and `docs/BACKLOG.md`
   reconciled — update both sides of a change together.
4. Keep `CODEBASE_INDEX.md` current as placeholder files become real.
5. **Use the patterns in `docs/design/PATTERNS.md`** (`Stage` interface,
   `Strategy`/`Registry` for `ai_providers/`, `Repository` wrappers,
   state-machine derivation, React hook layer). Flag it if a pattern is
   the wrong fit rather than silently diverging.
6. **Work from `docs/BACKLOG.md`, in sequence** unless told otherwise.
   Check items off; add new ones if work surfaces that isn't captured.

## Project summary (full detail: `docs/requirements/00-overview-and-goals.md`)

Merges three existing tools into one batch pipeline with two front
doors: CLI/advanced mode, and an accessible local web GUI for a real
accessibility persona (RA: reduced fine-motor precision; FMS: difficulty
learning/holding multi-step new processes in mind), plus WCAG 2.1 AA
alignment (ADR-0015). Also a portfolio piece.

- [`epub-renamer`](https://github.com/Jinniyah/epub-renamer) (MIT, Python)
- [`epub-sanitize`](https://github.com/Jinniyah/epub-sanitize) (no license, PowerShell)
- [`epub-to-audio`](https://github.com/Jinniyah/epub-to-audio) (MIT, Python)

**Design principle:** reuse each source project's implementation by
default; new code only for a changed constraint, real gap, or bug fix
(ADR-0014). Exception: the WCAG layer (ADR-0015) — none of the three
source tools had a GUI at all.

## Environment

- Windows, PowerShell. Backslash paths. `;` not `&&` for chaining.
- Python 3.11+ for pipeline/backend. Node/Vite for React — build-time
  only, never a runtime dependency on the target machine.
- Ships as a single PyInstaller `.exe` — nothing at build time should
  assume Python/Node/a terminal exist on the target machine.

## Filesystem rules (this environment's known quirks)

- **Never use `filesystem:edit_file`** — silently fails (reports
  success, file unchanged) on this Windows/CRLF setup. Always: full
  `read_text_file` → edit in memory → full `write_file` back.
- **No delete operation** — only `move_file`. Stage removals in a
  `_removed/` folder for the user to `git rm` later.
- New files: `filesystem:write_file` only — sandbox file-creation tools
  write to a container, not this repo.

## Paths

| Root | Path |
|---|---|
| Repo root | `C:\Users\jinni\source\repos\epub-automation\` |
| Requirements (*what*) | `...\docs\requirements\` |
| Design + ADRs (*why*) | `...\docs\design\` |
| Patterns (*how*) | `...\docs\design\PATTERNS.md` |
| Backlog (*what order*) | `...\docs\BACKLOG.md` |
| Codebase file map | `...\CODEBASE_INDEX.md` |
| Pipeline/backend/frontend | `...\pipeline\`, `...\backend\`, `...\frontend\` |
| Library staging | `...\Library\00-Incoming → 01-Renamed → 02-Sanitized → 03-Audio` |

## Key architectural decisions

| Decision | Rule | Doc |
|---|---|---|
| GUI transport | Flask/waitress + React (Vite, static build) | ADR-0001 |
| GUI process model | Background launcher opens browser to Flask; tab close ≠ job death | ADR-0001 |
| Status contract | One polling endpoint; `state` derived from `books[]` via fixed precedence rule; frontend reads via view-model hooks. **Implemented Epic 6** (`backend/bridge.py::derive_batch_state()`) with one documented deviation for the `review_result`/`output_collision` `needs_input` types — see that function's docstring. | `01-architecture.md` |
| Output collision | Distinct "replace" vs. "keep both" prompt per artifact (EPUB vs. audiobook); `needs_input.type: "output_collision"` — new type, not in the original four-type list | `06-safety-error-handling.md`, `pipeline/batch_runner.py` |
| TTS engine | Local `kokoro` (Kokoro-82M) — no browser/Selenium | ADR-0002 |
| Kokoro download timing | Lazy — first real need, never eager at launch | `04-tts-engine.md` |
| MP3 encoding | `lameenc` (not `soundfile`, which can't hit real CBR bitrates), 128kbps CBR mono at Kokoro's native 24kHz (not 48kHz) | ADR-0018 |
| AI provider | Pluggable: Gemini / OpenAI / none, user-keyed, neither default. `ai_providers/` ported verbatim except `gemini_provider.py` | ADR-0003, ADR-0014 |
| AI failure handling | Falls back to `NullProvider` per-file, never blocks batch | `02-pipeline-stages.md` |
| MAX_FILES overflow | Excess books rejected individually at Screen 1 | `06-safety-error-handling.md` |
| Sanitize | PowerShell→Python port, all 10 original security controls incl. Unicode whole-word regex + ReDoS timeout (`regex` package) | ADR-0004 |
| Folder pickers | `tkinter.filedialog` via Flask backend. **Must run on one persistent, dedicated background thread, not the calling Flask/`waitress` request thread** — a real bug found and fixed 2026-07-18 (Epic 10 Phase A), see `backend/dialogs.py::request_folder_pick()`. | ADR-0006 |
| Voice selection | Per book, post-metadata; global default + session-local same-series default; no persisted per-series memory | ADR-0010 |
| Settings | `%APPDATA%\EpubAutomation\settings.json`; atomic writes; `schema_version` migration policy | ADR-0005 |
| Profanity list | Bundled default → personal copy on first run, independent thereafter | `05-data-settings-and-logging.md` |
| Input format | `.epub` only, content-validated | ADR-0013 |
| Cancel vs. Pause | Pause = resume later. Cancel = confirm, keep-partial (default) or discard. **Frontend feedback fixed and verified 2026-07-17** — see `03-gui-ux-design.md` §Screen: Working and `CODEBASE_INDEX.md`'s Session notes; backend logic (`request_pause`/`request_cancel`/`start_generation`'s resume behavior) was already correct, only `WorkingScreen`'s UI was missing. **Working screen also gained a chunk-progress readout + `<progress>` bar the same day, build/test-verified in a second pass** ("Working on file N of M..."). | `06-safety-error-handling.md` |
| Retag | Always manual, never auto-run | `02-pipeline-stages.md` |
| Audit log | One CSV, all stages, `stage` + `voice` columns | `05-data-settings-and-logging.md` |
| Batch concurrency | Audio generation serial only; CLI reserves unused `--workers N` | ADR-0009 |
| Single-instance | Lock file, PID-based stale-lock detection (`psutil`) | ADR-0007 |
| Network binding | `127.0.0.1` only, fixed constant | ADR-0008 |
| Progress reporting | Polling, not WebSockets | `03-gui-ux-design.md` |
| Target platform | Windows-only v1 — confirmed | `00-overview-and-goals.md` |
| Packaging | PyInstaller single `.exe`, no code signing | ADR-0011 |
| Packaging risk | **Resolved (Epic 1, verified 2026-07-08):** full build+`.exe` test passed on Windows. Flags: `--collect-data espeakng_loader/language_tags/misaki`, `--collect-all en_core_web_sm/torch/transformers/kokoro/soundfile`. New dep: `en_core_web_sm`, pre-installed via wheel URL (misaki's runtime `pip`-download fails in a frozen exe). Full command: `spike/kokoro_spike.py` docstring, `07-packaging-deployment.md`. | `docs/BACKLOG.md` Epic 1 |
| Copyleft deps | `mutagen` (GPL) + `ebooklib` (AGPL) retained, documented | ADR-0012 |
| Reuse principle | Port existing implementations by default | ADR-0014 |
| Accessibility | WCAG 2.1 AA alignment (not certified) via shared hooks; automated tests are the CI floor, manual passes best-effort. **Row-height floor confirmed 2026-07-17:** `.clickable-row`'s 70px `min-height` is deliberately never shrunk to reclaim vertical space (e.g. when spacing is added between rows) — see the Frontend styling row below. | ADR-0015 |
| Dependency pinning | Exact versions, not ranges, in `requirements.txt` | `08-open-questions-and-assumptions.md` |
| CSRF/Origin check | Mutating routes reject a mismatched `Origin` header (ADR-0008 addendum, Epic 6 post-review). **Dev-time (Epic 7, done):** fixed via Vite proxy + Origin-header rewrite so dev traffic looks same-origin, matching prod — the check itself was never relaxed, since dev and prod share the same backend code path. | `backend/app.py::_origin_is_allowed()`, `frontend/README.md` |
| Frontend toolchain | React 19 + TypeScript + Vite; ESLint 9 (flat config), not oxlint (`create-vite`'s current default) — needed for `eslint-plugin-jsx-a11y`. `eslint-plugin-react-hooks` pinned to the classic 5.x line, not 7.x's React-Compiler-flavored rules (this project doesn't use the Compiler). | `frontend/README.md`, `frontend/eslint.config.js` |
| Frontend styling | Single global stylesheet (`frontend/src/index.css`) — no CSS modules, CSS-in-JS, per-component stylesheets, or inline `style` props. Already true of the codebase as of Epic 8.5; Epic 8.6 enforces it in CI via core ESLint's `no-restricted-syntax` targeting `JSXAttribute[name.name='style']` in `frontend/eslint.config.js` — not `eslint-plugin-react`'s `forbid-dom-props`, since that plugin isn't otherwise a dependency of this project and adding it just for one rule wasn't worth a new `npm install`. **Verified 2026-07-16, and twice more on 2026-07-17** (once for the first four fixes below, once more for the chunk-progress readout that followed): `npm run build && npm run lint && npm test` all pass, every time — the second of those two passes also confirmed the real frontend test count (199 tests, 31 files), correcting a long-carried "331" figure. **Layout gotcha (2026-07-17):** the `.screen-actions` sticky bottom bar bleeds to `main`'s edges and rounds its bottom corners, so it must stay the *last* DOM child of `main` — a real bug (VoiceAssignmentScreen's `RemoveBookButton` rendered after it) put a button outside the visual card. **New utility classes (2026-07-17):** `.status-badge`/`.status-badge--amber` (a visible, non-color-only state indicator, first used for the Working screen's "Paused" badge, reusing the amber tokens already tied to the Pause button); `.stack` (space-5 rhythm, same as `main`'s own top-level spacing but usable on any container -- `main > * + *` only reaches `main`'s *direct* children, so a component rendering its own wrapping `<div>` doesn't get that spacing for free); `.stack-md` (space-3, a deliberate middle weight between `.stack-sm`'s 8px and `.stack`'s 24px); `.progress-bar` (a native `<progress>` element styled via `::-webkit-progress-bar`/`::-webkit-progress-value`/`::-moz-progress-bar` vendor pseudo-elements, chosen specifically because a hand-rolled `<div>` fill bar would need a dynamic inline `width` this same ESLint rule forbids -- the Working screen's chunk-progress bar). **Recurring gotcha found twice the same day:** any component that renders its own single wrapping element loses its ancestor's `> * + *` rule for its own children -- bit `VoicePicker` (`main`'s rule) and `ConfirmMetadataScreen`'s `asOverlay` mode (`.overlay`'s rule) the same way, fixed the same way both times. See `CODEBASE_INDEX.md`'s Session notes. | `03-gui-ux-design.md` §Visual design system, `docs/BACKLOG.md` Epic 8.6 |
| Voice picker / folder-link backend routes | `GET /api/voices`, `GET /api/voice-samples/<voice>`, `POST /api/books/<id>/metadata`, `POST /api/books/<id>/open-folder`, `POST /api/open-output-folder` — all added in Epic 8, found genuinely missing while building the real frontend against the Epic 6 contract, not pre-planned. Folder-link routes never pass a raw filesystem path over the wire, resolved server-side both ways. | `01-architecture.md` §Full API route reference, `CODEBASE_INDEX.md`'s Epic 7+8 session notes |
| Auto-load-from-folder backend routes | `GET`/`POST /api/books/from-folder` — Epic 10 Phase A (moved from Epic 8.5). `POST` reuses `POST /api/books`'s exact per-file result shape; each filename is re-validated server-side (`secure_filename` + containment check, same defensive pattern as `_safe_upload_path`) before being read, never trusted blindly even though it's this app's own frontend sending it. | `01-architecture.md` §Full API route reference, `docs/BACKLOG.md` Epic 10 Phase A |
| Full resume / cleanup backend routes | `POST /api/cleanup-in-progress` — new in Epic 9. `GET /api/welcome-back` and `GET /api/status` unchanged (no new route needed for full resume itself — the fix is entirely in what `_build_app_state()` seeds the runner with at startup, not in any route surface). | `01-architecture.md` §Full API route reference, `docs/BACKLOG.md` Epic 9 |

## Flagged open items

| Item | Status |
|---|---|
| Kokoro vs. Perchance output parity | Side-by-side listen needed — Epic 10 (moved from 4, needs a real packaged `.exe` on real hardware) |
| CPU vs. GPU inference speed | Needs benchmarking — Epic 10 (moved from 4, same reason) |
| No per-series voice memory | Decided against at both the backend (Epic 4/6) and frontend (Epic 8) layers — the frontend's `useVoiceAssignmentView` deliberately doesn't reproduce it client-side either, to avoid a second, possibly-disagreeing notion of "current default." Revisit only if real use surfaces a real annoyance — Epic 9 |
| Her-facing copy wording | Drafted, not final — real dry-run needed — Epic 9 |
| Screen-reader tester | Being pursued, not confirmed — never claim "validated by a blind user" until it happens — Epic 9 |
| Dyslexic-reader tester | **No longer available (2026-07-18)** — the tester previously lined up (ADR-0015, `00-overview-and-goals.md`) fell through. Moved to `docs/BACKLOG.md`'s new Wish List, not dropped. Same rule as the screen-reader row above: never claim "validated by a dyslexic reader" until a new tester is found and it actually happens. |
| "Welcome back" full resume | **Fixed and build/test-verified 2026-07-18.** `state.json` schema bumped to v2 to persist each book's full status/data as a `"snapshot"`, not just per-stage completion flags (`pipeline/state_manager.py`); `backend/app.py::_build_app_state()` rebuilds a live `BatchRunner` from those snapshots at process startup (`BatchRunner.restore_books()`), before any request is served. A `generating`/`paused` book coarse-grains to `voice_pick` (audio resumes via the existing per-chunk disk-file-size check); an `identifying` book coarse-grains to `pending` (rename/sanitize copy, never delete, their source). Also fixed a related pre-existing gap: a cancelled book never marked its `cleanup` stage complete and would have kept reappearing as "pending" forever. See `docs/BACKLOG.md` Epic 9's own checklist item for the full writeup. |
| "More options": clean up stuck in-progress book state | **Fixed and build/test-verified 2026-07-18.** `POST /api/cleanup-in-progress` (`backend/bridge.py::reset_all_in_progress()`) does a best-effort, catch-and-continue sweep of every `Library/*` stage folder plus a full `state.json` reset (`StateRepository.reset_all()`), never touching `audit_log.csv`; a confirm-gated "🧹 Nuke everything in progress" button on `MoreOptionsScreen` reuses the existing `Overlay` confirm-dialog pattern. See `docs/BACKLOG.md` Epic 9's own checklist item. |
| Flask doesn't serve the built frontend | **Fixed and live-verified 2026-07-18** (Epic 10 Phase A) — `backend/app.py::_frontend_dist_dir()` + a catch-all route serve `frontend/dist/`, real-curl-confirmed against a running `python launcher.py`. `sys._MEIPASS` handling for a frozen `.exe` is already built, not yet exercised (Phase B). See `docs/BACKLOG.md` Epic 10 Phase A. |
| No-console GUI launch for real-person testing | **Built and live-verified 2026-07-18** (Epic 10 Phase A) — `run_gui.vbs` (repo root), a `pythonw.exe` wrapper around `launcher.py`. Confirmed via `cscript`: no console window, no lingering process after `/api/quit`. Explicitly a testing-phase stand-in for the real `.exe` (Phase B), not a replacement. |
| Icon system (real inline SVG icons vs. emoji) | Deferred, not scheduled to any epic — reviewed alongside a mobile-app UI reference and judged not worth its real cost (a fresh `aria-label` pass + a full app-wide axe re-run) against the benefit, since the existing emoji already carry text alternatives per Epic 8/8.5's WCAG work. Revisit only if it becomes a real complaint — Epic 8.6 notes, `03-gui-ux-design.md` §Visual design system. |
| Step/progress indicator across the main batch flow | **Built and verified 2026-07-18** (`frontend/src/components/shared/StepProgress.tsx`), real user feedback (no orientation cue for a first-time/FMS-persona user). Wired into the five main-flow screens; the multi-book table's "active book" state turned out to already exist as `VoiceAssignmentScreen`'s own local state, nothing new needed. See `docs/BACKLOG.md` Epic 9's own checklist item. |
| Working-screen Pause/Cancel/Resume feedback | **Fixed and build/test-verified 2026-07-17**, real user report — see the "Cancel vs. Pause" row above and `CODEBASE_INDEX.md`'s Session notes. |
| VoicePicker heading/row spacing | **Fixed and build/test-verified 2026-07-17**, real screenshot + follow-up request — see the "Frontend styling" and "Accessibility" rows above and `CODEBASE_INDEX.md`'s Session notes. |
| "Fix info" overlay field-list-to-Save spacing | **Fixed and build/test-verified 2026-07-17**, real screenshot — same underlying nesting-depth bug class as the VoicePicker item above, one level deeper (`.overlay`'s spacing rule instead of `main`'s). See the "Frontend styling" row above and `CODEBASE_INDEX.md`'s Session notes. |
| Working-screen chunk-progress readout + `<progress>` bar | **Built and build/test-verified 2026-07-17**, real follow-up request — a second, separate `npm run build`/`npm run lint`/`npm test` pass, run right after the other three items above were already confirmed clean, also came back clean. See the "Cancel vs. Pause" and "Frontend styling" rows above and `CODEBASE_INDEX.md`'s Session notes. |
| Frontend test-count correction (331 → 199 tests, 31 files) | **Confirmed 2026-07-17** via a real `npm test` run. The "331" figure had been carried since Epic 7/8 and was simply wrong -- no tests were ever removed since then, so the true count was always lower. Fixed in README.md and this file's header; not tracked as its own backlog item since it's a documentation correction, not a code change. |

## Documentation & session close

1. Keep `docs/requirements/`, `docs/design/`, `docs/BACKLOG.md`
   reconciled — update both sides together, don't diverge silently.
2. Keep `CODEBASE_INDEX.md` current as placeholders become real.
3. Add new binding decisions to the table above; add an ADR if it
   clears the bar (real alternatives, real tradeoffs).
4. Keep this file's header line current.
5. **Every new frontend screen must satisfy WCAG 2.1 AA alignment**
   before being done (ADR-0015).
6. Use `docs/design/PATTERNS.md` patterns rather than ad hoc structures.
7. **Mark items complete in `docs/BACKLOG.md`**, add stories for
   uncaptured work.
