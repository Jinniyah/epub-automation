# epub-automation — Implementation Backlog

**Status:** Epics 0–8.6 complete (2026-07-06 to 2026-07-17). Epic 8.5's two remaining UI-polish items (auto-load-from-folder, Field Correction Popup format hints) moved to Epic 10 Phase A 2026-07-18 rather than left open against a closed epic, and built the same day as part of that phase. **Epics 0–8.6's narrative detail was properly compacted 2026-07-18** — decisions/gotchas kept, blow-by-blow session narration dropped; an earlier claim that this happened 2026-07-17 was itself inaccurate for 8.5/8.6 specifically (they'd stayed in full checklist form until this pass), now corrected. Full history recoverable from git and from `CODEBASE_INDEX.md`'s own (separately-compacted) session notes. **Epic 9's code-buildable items done 2026-07-18** (full "Welcome back" resume, "clean up stuck in-progress state," the step-progress indicator, and confirming the axe-core/jsx-a11y CI item was already true) — 448 backend tests / 96% coverage, 216 frontend tests / 32 files, both clean via real `pytest --cov` and `npm run build && npm run lint && npm test` passes. **Epic 9's remaining items are all human-only** (manual keyboard-only pass, real NVDA/Narrator pass, screen-reader tester, her-facing copy dry-run, per-series voice memory second look) and cannot be completed by an AI agent — see that epic's own checklist for what's left. **The real dyslexic-reader test moved to the new Wish List section (bottom of this file) 2026-07-18** — the previously-lined-up tester is no longer available; not dropped, just blocked on finding a new one. **Epic 10 resequenced into Phase A/Phase B 2026-07-18, and Phase A built the same day**: Flask serves `frontend/dist/`, a no-console `run_gui.vbs` launch shortcut, and a real live smoke test against the actual running single-process server (curl-verified, not just unit-tested) — real-person testing can now start without the full PyInstaller/SmartScreen/installer work. Also moved and built Epic 8.5's two leftover UI-polish items here in the same pass (auto-load-from-folder, Field Correction Popup format hints). Phase B (the rest of Epic 10) stays deliberately deferred until after an initial round of real-person feedback, since iterating against a packaged `.exe` costs a full rebuild plus a fresh SmartScreen click-through on every fix — see Epic 10's own section.

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
that isn't captured yet. Closed epics get compacted periodically (see
the note above) — condense to decisions/gotchas, not narrative, and
trust git history for the rest.

---

## Epic 0 — Scaffolding & Cross-Cutting Infrastructure ✅ Complete

Repo structure, `Stage` protocol + `BookState`, `StateRepository`/
`AuditLogRepository` with schema versioning, atomic settings/state
writes (ADR-0005), single-instance lock with PID stale-lock detection
(ADR-0007, `psutil`), `SafeZipOperation` Template Method base
(path-traversal → zip-bomb cap → XXE), CI skeleton (pytest/black/ruff/
mypy --strict), profanity-list bundling + first-run seed, exact
dependency pinning.

---

## Epic 1 — Kokoro/PyInstaller Packaging Spike ✅ Complete (2026-07-08)

Verified the project's highest-blast-radius unknown early: a full
PyInstaller build + real standalone `.exe` producing real audio on
Windows (`dist\kokoro_spike.exe`, 153KB `spike_output.wav`). Needed
explicit `--collect-data`/`--collect-all` flags for espeak-ng,
`language_tags`, `misaki`, `soundfile`, `torch`, `transformers`,
`kokoro` (ctypes/`importlib.resources` data invisible to static
analysis), plus a pre-installed `en_core_web_sm` wheel (misaki's
runtime `pip`-download fails inside a frozen exe). Full working build
command preserved in `07-packaging-deployment.md`.

---

## Epic 2 — Sanitize Stage Port (PowerShell → Python) ✅ Complete (2026-07-06)

All 10 security controls from the original `PS_Run-CleanUpEpub.ps1`
ported (path-traversal guard, zip-bomb cap, XXE prevention, profanity
cap, Unicode whole-word regex + 5s ReDoS timeout, mimetype-first
repack). 29-test adversarial suite. Built on `SafeZipOperation`. See
ADR-0004.

---

## Epic 3 — Rename Stage Port ✅ Complete (2026-07-08)

`ai_providers/` registry ported (`Null`/`OpenAI` verbatim, `Gemini`
new via the `google-genai` SDK). `FILENAME_PATTERN`/`build_filename()`
ported verbatim (ADR-0016: matches shape only, not characters). Silent
per-file `NullProvider` fallback on AI failure. `MAX_FILES`
batch-level enforcement deferred to Epic 6 (needed a Screen 1 that
didn't exist yet — resolved there via `check_batch_capacity()`).

**Real bug found and fixed 2026-07-18, real user report:** a book whose
filename already matched `FILENAME_PATTERN` (e.g. re-imported from an
earlier run of this tool, or a predecessor tool that already normalized
it) landed on the "We couldn't quite figure out this book" screen with
no title, author, or series set at all — and no AI provider was ever
called, despite one being configured (OpenAI). **Root cause:**
`RenameStage._pass_through_already_normalized()` correctly skipped
re-renaming and the AI call (an already-normalized filename needs
neither), but *also* skipped populating the metadata fields entirely —
`BatchRunner._run_identification()` routes any book with no `title` to
`ai_enrichment_failed`, regardless of *why* it's missing, so "already
normalized, nothing more to do" looked identical to a genuine AI
failure. **Fix:** `_parse_normalized_filename()` — since a filename
already matching `FILENAME_PATTERN` is, by definition, already in
`build_filename()`'s own output shape, its title/author/series/
series_number can be parsed back out *reliably*, not guessed the way
`guess_author_from_filename()`/`guess_series_from_filename()` do
against an arbitrary unnormalized filename (both still reused here for
author/series; only title-extraction is new). No AI call needed for
this path — the filename already encodes everything. New regression
tests cover both the standalone-book and series shapes, using the exact
real filename that surfaced this (`"Jordan, Robert — The Wheel of Time
#03 — The Dragon Reborn.epub"`).

---

## Epic 4 — Audio Stage (Kokoro TTS Integration) ✅ Complete (2026-07-10)

`TTSEngine` wraps `kokoro.KPipeline`, lazily imported (nothing touches
the model until a real call happens). **Two spec corrections made
during implementation, confirmed with the user:** MP3 encoding needed
`lameenc` instead of `soundfile` (soundfile tops out ~21kbps, nowhere
near the required 128kbps CBR); sample rate is Kokoro's native 24kHz,
not the originally-spec'd 48kHz. Voice-sample cache versioned by
installed `kokoro` version; per-chunk resume; disk-space estimate
formula. Session-local same-series voice default deferred (needed
batch-wide visibility no single stage has — later decided against
entirely at the frontend layer too, see Epic 8's own note). CPU/GPU
benchmarking and Kokoro-vs-Perchance parity moved to Epic 10 (need
real hardware, a real packaged `.exe`).

**Real bug found and fixed 2026-07-18, real user report ("Something
went wrong," a real failed run):** `AudioStage._generate_with_retry()`
caught and discarded the actual Kokoro/pipeline exception on every
attempt, so a genuine failure surfaced only as "Audio generation failed
at chapter 1, chunk 1 (track 1/385)" — no exception type, no message,
nothing for "Copy details for support" to actually carry. Diagnosed by
reading her real support bundle directly (same pattern as the rename
bug above), then reproducing the exact chapter-1/chunk-1 text against
the exact voice (`bm_lewis`) live in the venv — it generated
successfully, meaning this was very likely a one-off transient failure
(this book's first-ever use of that particular voice, which downloads
its assets from Hugging Face Hub on first use — see the "unauthenticated
requests" warning `TTSEngine` already emits) rather than a reproducible
bug in this codebase. **Fix, regardless of root cause:** the last
attempt's exception (`TypeName: message`) is now appended to the `error`
text stored on the book — the same field `backend/bridge.py::
current_error_detail()` already reads as the "technical detail" for
"Copy details for support" (that function's own docstring already
called this out as the *only* channel real error text ever leaves the
machine through; it just had nothing real in it for this failure mode
until now). No new logging infrastructure added — this reuses the
existing support-bundle channel rather than building a new one.

---

## Epic 5 — Retag Stage ✅ Complete (2026-07-10)

`retag.py` ported into `retag_stage.py` — folder-name parsing (old +
new shapes), ID3 tag rewriting, dry-run support. Fixed a real bug over
the original script: it renamed the MP3s but never the containing
folder. Always manually triggered, never auto-run.

---

## Epic 6 — Backend / Flask Bridge ✅ Complete (2026-07-10)

`BatchRunner` (the stateful interactive engine the GUI's polling
contract is actually built on), `derive_batch_state()` (pure
State-Machine function, one documented precedence deviation — see its
own docstring), Pause/Cancel via `AudioStage`'s new `on_progress`/
`should_stop` Observer hooks, output-collision handling, dynamic
free-port launcher with a port-sidecar file, CLI wired to real stages
non-interactively via `pipeline/cli_runner.py`. **Post-commit security
review the same day** found and fixed two HIGH findings (upload path
traversal in `/api/books`; no CSRF/Origin protection on mutating
routes) plus three smaller bugs (support-bundle error text, a
retag-failure status code, a `BatchRunner.start()` no-op stranding
mid-run additions) — full detail in `CODEBASE_INDEX.md`'s Epic 6
session notes.

---

## Epic 7 — Frontend Scaffolding ✅ Complete (2026-07-11, combined with Epic 8)

Vite + React 19 + TypeScript; ESLint 9 (flat config) instead of
`create-vite`'s default oxlint, needed for `eslint-plugin-jsx-a11y`.
API-client facade (`src/api/`), `usePollingStatus`/`useFocusTrap`/
`useAriaLiveThrottled` hooks, Container/Presentational split. Vite
dev-proxy + Origin-header rewrite so dev traffic doesn't trip the
backend's CSRF/Origin check. Two backend routes (`GET /api/voices`,
voice-sample playback) found genuinely missing while building Epic 8's
screens against this scaffold, not pre-planned.

---

## Epic 8 — GUI Screens ✅ Complete (2026-07-11, combined with Epic 7)

Every screen from `03-gui-ux-design.md`'s encounter order, WCAG 2.1 AA
alignment via axe-core assertions in each screen's own test file (the
**manual** keyboard/NVDA/dyslexic-reader passes are Epic 9's own,
separately-scoped, not-yet-done checklist). **Decided:** the
session-local same-series voice default is not reproduced client-side
either — the backend only ever hands out one global default, and a
second client-only "current default" that could silently disagree with
the server was judged worse than the marginal convenience.
`useVoiceAssignmentView`'s own docstring has the full reasoning. Three
new backend routes found genuinely missing while building against the
real backend (`POST /api/books/<id>/metadata`, the two open-folder
routes). Two real pre-existing bugs found and fixed: the upload
route's collision-avoiding temp filename was leaking into what Screen
1 displayed, and `_maybe_enter_voice_pick()` was auto-starting
single-book generation before the voice picker could ever matter. Full
writeup: `CODEBASE_INDEX.md`'s Epic 7+8 session notes.

---

## Epic 8.5 — First real-user feedback pass ✅ Complete (2026-07-17)

Real hands-on run through the GUI surfaced this whole batch (starting
2026-07-12), before Epic 9's own separately-scoped manual accessibility
passes. Numbered `8.5` rather than renumbering Epic 9/10/11, which are
referenced by number throughout `CLAUDE.md` and `CODEBASE_INDEX.md`.
Build/test-verified via real `npm run build`/`lint`/`test` passes
(2026-07-16 for the earlier items, 2026-07-17 for the later batch — two
separate passes that day, both clean). Persistent `<header>` landmark
added (closed a WCAG landmark gap that was speced but never built);
general spacing/whitespace pass across every screen; rename-stage
AI-enrichment gained a per-field fallback chain (AI response →
filename-guess → EPUB-metadata), fixing two real bugs — AI enrichment
overwriting a fully-parseable filename's author/series info, and no-AI
mode showing "Author: Not set" despite clean EPUB metadata
(`NullProvider.identify_book()` + `RenameStage._merge_field_fallbacks()`,
a real AI answer still always wins when present); voice picker gained
Male/Female labels (reversing the original no-labels rule) and a 70px
Listen button; clickable-row selection became non-color-only (checkmark
+ darker background); Back buttons added, Home button restricted to
settings sub-views only; Remove-this-book generalized to every screen a
book can get stuck on (real bug: a permanently-stuck `ErrorScreen` with
no way out); Screen 1 gained per-file rejection dismissal and its four
settings entry points consolidated into one "⚙️ More options" hub;
header redesigned (card surface, wordmark badge, filled-pill Home
button); Working screen gained a chunk-progress readout + native
`<progress>` bar (not a styled `<div>` — the app-wide `style`-prop
ESLint ban forbids the dynamic inline `width` a hand-rolled bar would
need). **Two findings worth remembering beyond this epic:** Pause/
Cancel's *backend* logic was always correct
(`request_pause`/`request_cancel` just flag the request, applied at the
next chunk boundary) — the entire gap was `WorkingScreen` never
reflecting a paused book's real state, fixed with a "⏸️ Paused" badge +
Resume button reusing the existing `startGeneration()`. And a
**recurring nesting-depth spacing bug**, hit twice the same day: any
component rendering its own single wrapping element (`VoicePicker`,
`ConfirmMetadataScreen`'s `asOverlay` mode) loses its ancestor's
`main`/`.overlay` `> * + *` spacing rule for its own children — fixed
both times with new `.stack`/`.stack-md` CSS utilities, the 70px
row-height accessibility floor deliberately left unchanged despite the
added scroll. **Two real UI-polish items from this pass never got
built** — auto-load-from-folder on Screen 1, Field Correction Popup
format hints — moved to Epic 10 Phase A (2026-07-18) rather than left
sitting here. Full root-cause writeups: `CODEBASE_INDEX.md`'s Session
notes.

---

## Epic 8.6 — Visual polish pass (EMS ReadyKit-informed) ✅ Complete (2026-07-17)

Reviewed a reference deck (`EMS_ReadyKit`, a separate personal project
with a polished mobile-first UI) at Jennifer's request, to judge whether
this app's UI is "par for the type of app" — sorted what genuinely
transfers to a laptop-only, mouse/keyboard-primary app from what's
mobile convention that wouldn't fit (full "don't copy" reasoning:
`03-gui-ux-design.md` §Visual design system). Verified 2026-07-16 via a
real `npm run build`/`lint`/`test` (the first pass surfaced an unrelated
pre-existing `tsc` error, fixed and logged under Epic 8.5); confirmed
clean again 2026-07-17 alongside that day's Epic 8.5 batch. Added: an
ESLint rule forbidding the `style` prop app-wide (`no-restricted-syntax`,
not `eslint-plugin-react`'s `forbid-dom-props` — avoids a new dependency
for one rule); a card-surface audit pass (`WorkingScreen`, `ReviewScreen`,
`ConfirmMetadataScreen` standalone mode now match `FoldersScreen`'s
existing `.card` pattern); a new `.screen-actions` sticky bottom action
bar (opt-in per call site, never inside `.overlay`); a new `.icon-badge`
utility (the header wordmark's gradient tile, generalized for reuse). A
real bug found and fixed 2026-07-17 (real screenshot): `.screen-actions`
must stay the *last* DOM child of `main` — its negative margins/corner-
rounding assume this — `VoiceAssignmentScreen`'s `RemoveBookButton` broke
that, floating outside the card; worth a grep for the same mistake
elsewhere, since it's easy to reintroduce. **Explicitly out of scope,
not deferred:** a real inline-SVG icon system replacing emoji (real
accessibility-testing cost against marginal benefit, since emoji already
carry text alternatives). **Explicitly rejected, not just deferred:** a
bottom tab bar (misrepresents this app's linear wizard flow as peer/
lateral navigation) and any icon-only control without a visible text
label.

---

*Compacted 2026-07-18 — Epics 0–8.6 are closed; entries above are
condensed to the decisions/gotchas with lasting relevance. (An earlier
note here claimed this compaction happened 2026-07-17 for 8.5/8.6
specifically — that was inaccurate; both stayed in full checklist form
until this pass actually condensed them, moving their two still-open
items to Epic 10 Phase A in the process.) Full narrative detail
(root-cause investigations, exact test names, the full text of every
real-user report) is recoverable from git history and from
`CODEBASE_INDEX.md`'s own Session notes if ever needed again.*

---

## Epic 9 — Accessibility Verification

- [x] **"More options": a way to clear stuck in-progress book state
  ("nuke everything in progress").** **Built and verified 2026-07-18**
  (448 backend tests / 96% coverage, 216 frontend tests / 32 files, both
  clean via real `pytest --cov` and `npm run build && npm run lint &&
  npm test` passes): `POST /api/cleanup-in-progress`
  (`backend/bridge.py::reset_all_in_progress()`,
  `pipeline/state_manager.py::StateRepository.reset_all()`), a
  confirm-gated "🧹 Nuke everything in progress" button on
  `MoreOptionsScreen` reusing the existing `Overlay` confirm-dialog
  pattern. Real report (2026-07-17): the
  app opened to "Welcome back," reporting 3 books still waiting -- but
  she'd already deleted those EPUBs from the source folder herself,
  outside the app. There was no way to make that message go away; the
  stuck "waiting" count has no clear/reset action anywhere. **Directly
  related to the "Welcome back full resume" item below, but a
  different, simpler fix shape:** that item is about *properly
  resuming* pending work; this one is the necessary escape hatch for
  when resuming isn't possible (files already gone) or just isn't
  wanted -- a blunt "start over" action rather than asking her to
  diagnose or hand-edit state files herself, which fits this app's
  persona far better than a fiddly per-book cleanup UI would.
  **Requested shape, in her own words:** a "clean up" button in the
  "⚙️ More options" hub, plain and blunt ("nuke everything in
  progress"), not a technical explanation of what it does under the
  hood.
  - **Scope — decided 2026-07-17 (direct request):** "clean up" does
    both. It deletes any leftover files sitting in the
    `Library\00-Incoming → 01-Renamed → 02-Sanitized → 03-Audio`
    staging folders, *and* it clears whatever tracking makes the app
    think books are still pending (i.e. resets `state.json` so
    `StateRepository.incomplete_book_ids()` returns empty and
    "Welcome back" stops nagging). A genuine full reset, not just a
    flag clear -- matches her own "nuke everything in progress"
    framing exactly.
  - **Backend mechanism — decided 2026-07-17 (direct request):**
    best-effort, catch-and-continue -- attempt to delete each staging
    folder's contents, and if an individual delete fails (already
    gone, in use, permissions), swallow the error and keep going
    rather than aborting the whole operation. In practice this means
    the new route/function doesn't need to correlate with live
    tracked `Book` objects at all (the concern raised in the previous
    version of this note): it's a genuinely blanket sweep across all
    four `Library` stage folders regardless of what `BatchRunner`
    currently knows about, which is exactly right for the case that
    prompted this -- files deleted outside the app, with no live
    `Book` behind them anymore. Likely implementation:
    `shutil.rmtree(folder, ignore_errors=True)` per stage folder
    (or an explicit per-item `try`/`except (OSError, PermissionError)`
    loop if per-item failure visibility is wanted later, e.g. for a
    support-bundle log entry), then recreate each folder empty, plus
    a `state.json` reset/rewrite clearing pending-book tracking. This
    is a genuinely new backend route, not a composition of the
    existing per-book `cancel` route -- `cancel` was never built to
    delete arbitrary leftover files across all four stage folders,
    only a single book's own working files, and it always requires an
    actual tracked `Book` to operate on.
  - **Confirmation:** destructive, so needs the same
    confirm-before-firing pattern Cancel already uses -- but the
    confirmation copy itself should stay just as blunt and short as
    the button, not a wall of caveats.
  - **Leave the audit log alone** — it's a permanent record, not
    working state; "clean up" should only touch pipeline/state
    tracking and the staging folders, never `audit_log.csv`.
  - Needs a `03-gui-ux-design.md` update once built (no current screen
    spec mentions a reset/clear action at all) and a
    `01-architecture.md` route-reference update once the new route
    exists.
- [x] **Persistent step/progress indicator ("you are here" wizard bar)
  across the main batch flow.** **Built and verified 2026-07-18**
  (`frontend/src/components/shared/StepProgress.tsx`, wired into
  `AddBooksScreen`/`ConfirmMetadataScreen`/`VoiceAssignmentScreen`/
  `WorkingScreen`/`CollisionPrompt`/`ReviewScreen`/`FixInfoFlow` per the
  decisions below; the multi-book "most recently selected row" state
  turned out to already exist as `VoiceAssignmentScreen`'s own
  `changingVoiceFor`/`editingMetadataFor` local state, so no new state
  was actually needed there). Added 2026-07-17, real user feedback:
  almost every wizard/multi-step process has a visible "step N of M"
  cue at the top so the person knows where they are and what's next;
  this app has never had one, which is a real orientation gap for any
  first-time user and specifically a risk for the FMS persona
  (difficulty holding a multi-step process in mind) this app is
  designed around. Five stages, matching the screens that already
  exist: **Add Books → Confirm Info → Choose Voice → Convert →
  Review.** Shown only during the active batch flow — deliberately
  *not* during onboarding (Folders / AI Helper / Welcome back) or the
  "More options" sub-screens, since those are one-time setup rather
  than part of the per-batch pipeline, not a step the wizard "returns
  to." Should be a frontend-only presentational component: `state`
  from `usePollingStatus()` (already wraps `derive_batch_state()`)
  maps directly onto a stage, so no anticipated backend change.
  - **Multi-book "active book" — decided 2026-07-17 (direct request):**
    the stepper tracks whichever book the person is *currently on or
    has selected*, not a batch-wide aggregate. Concretely, per stage:
    - **Confirm Info:** already a per-book loop
      (`ConfirmMetadataScreen`) — the book currently being confirmed
      *is* the active book, no new state needed. Same when the
      metadata-edit overlay is reopened later from the voice table:
      whichever book's overlay is open is active for that moment.
    - **Choose Voice:** single-book mode — that one book is active,
      trivially. Multi-book table mode — no book is *inherently*
      current, since all rows sit in `voice_pick` simultaneously. Here
      "active" means whichever row the person most recently opened
      (clicked the title to edit info, or "Change Voice") — if nothing's
      been clicked yet, no single book is active and the stepper just
      shows "Choose Voice" as the stage without naming a book.
    - **Convert:** `AudioStage` generation is already serial (ADR-0009)
      — there's a real, single currently-generating book at any given
      moment, which is naturally the active one. Whatever field the
      Working screen's `progress` payload already uses to identify the
      in-flight book is the one to read here — check `usePollingStatus()`
      /`build_status_response()`'s existing shape before adding
      anything new.
    - **Review:** per-book Yes/No review already exists — same pattern
      as Confirm Info, the book currently being reviewed is active.
    - **Add Books:** batch-wide by nature, no active-book concept needed
      — everyone's adding books together at this stage.
    This resolves the original open question below without needing a
    second, possibly-disagreeing notion of "current stage" — it reuses
    per-book focus the app already tracks (or trivially can) at every
    stage except the multi-book voice table, where "most recently
    selected row" is the one genuinely new bit of state to add.
  - **Active-book display — decided 2026-07-17 (direct request):** the
    active book's title renders on its own line directly under the
    step-progress row, not inlined into the step label itself (i.e. not
    "Step 3 of 5: Choose a voice for 'Fated'" as one string). Keeps the
    step label itself short and consistent regardless of title length,
    and reads as two distinct facts -- "which stage" and "which book" --
    rather than one run-on sentence.
  - **Accessibility:** current step must not be color-only (same 3:1
    non-color-dependent requirement already applied to
    `.clickable-row--checked` — see Epic 8.5's own item on that), needs
    a real text label per step (not just a numbered dot/icon), and
    `aria-current="step"` on whichever stage is current for screen
    readers. A `<nav>`/`<ol>` landmark is the natural semantic fit. The
    active-book line under it should be associated with the step region
    (e.g. `aria-describedby`) so a screen-reader user gets both facts
    together, not the book title as a disconnected line of text.
  - **Visual placement:** shouldn't crowd the header card (Epic 8.5) or
    collide with the `.screen-actions` sticky footer (Epic 8.6) —
    likely its own thin band between them, sized so it doesn't push
    big-button targets further down the page on short viewports.
  - Needs a `03-gui-ux-design.md` update alongside the code once built
    (this doc's own rule: keep requirements/design/backlog reconciled),
    since no current screen spec mentions a step indicator at all.
  - **Follow-up, real user feedback (2026-07-18):** "I need to be able
    to use the cookie crumb bar to go backwards. It is normal and
    intuitive to expect it to work that way." The bar as originally
    built was a pure status indicator — no step was ever clickable.
    **Fixed:** `StepProgress` gained `clickableSteps`/`onStepClick`
    props; a completed step renders as a real `<button>` only where the
    current screen already has an existing, non-destructive way to act
    on it, reusing that exact action rather than inventing a new one —
    Choose Voice (single-book mode) and Review both wire "Confirm Info"
    to their existing edit-metadata/"No, let me fix it" flows. "Add
    Books" and "Choose Voice" (from Convert/Review) deliberately stay
    plain text — going back there would mean either reopening Screen 1
    mid-batch with other books already past it, or discarding
    already-generated audio, neither of which any existing action does
    today; making those clickable would need real backend design work,
    not just a click handler, so they're left honest rather than
    silently lossy. The multi-book voice table also stays non-clickable
    in the bar itself, for the same "no single unambiguous active book"
    reason its own active-book display already documents above — the
    table's per-row title click already covers going back there
    unambiguously. Full rule and per-screen mapping:
    `03-gui-ux-design.md` §Step progress indicator. 241 frontend tests /
    32 files, clean build/lint/test.
- [x] `axe-core` + `eslint-plugin-jsx-a11y` wired into CI — **already
  true**, confirmed 2026-07-18 by reading `.github/workflows/ci.yml`: the
  frontend `lint` job already runs `eslint-plugin-jsx-a11y` and the
  `coverage` job already runs the axe-core assertions present in every
  screen's own test file. No code change needed, just this checkbox.
- [ ] Manual keyboard-only pass, all screens
- [ ] Real NVDA pass + Narrator sanity check
- [x] **"Welcome back" Continue silently drops unresolved books —
  confirmed live 2026-07-16.** **Fixed via the "Full fix" option below,
  built and verified 2026-07-18:** `state.json` now persists each book's
  full status/data as a `"snapshot"` (schema v2,
  `pipeline/state_manager.py::StateRepository.save_book_snapshot()`/
  `incomplete_book_snapshots()`), and `backend/app.py::_build_app_state()`
  rebuilds a live `BatchRunner` from those snapshots at process startup
  (`BatchRunner.restore_books()`) before any request is served — so by
  the time "Continue" or the status poll is ever hit, the runner already
  has the real data. A `generating`/`paused` book restores to
  `voice_pick` (audio resumes via the existing per-chunk disk-file-size
  check, not persisted chunk counts); an `identifying` book restores to
  `pending` (rename/sanitize copy their source, never delete it, so
  redoing is always safe). Found and fixed a related pre-existing gap in
  the same pass: `_finalize_cancel` never marked the `cleanup` stage
  complete, so a cancelled book would have kept reappearing as "pending"
  forever. Reproduced via real screenshots: the
  welcome-back screen correctly degrades to a plain count ("2 books
  you hadn't finished yet") when it can't match the pending book ids
  `GET /api/welcome-back` returns against the live status poll's
  `books[]` — that part is working exactly as `WelcomeBack.tsx`'s own
  module comment says it should. But **"Continue"**
  (`App.tsx`: `onContinue={() => setPhase("main")}`) doesn't re-fetch
  or reconstruct anything — it just switches phase, and since the
  backend's live `BatchRunner` still doesn't know about those 2 books
  either, she lands on an empty Screen 1 ("No books added yet") with
  zero explanation for what happened to the books she was told she
  could continue. This is the same gap already flagged under
  `CLAUDE.md`'s "Welcome back" full resume item and this file's own
  Open Items table — now confirmed live, not just theoretical. Folded
  into this epic per direct request (2026-07-16) rather than left
  unowned. **A second, real report of the same underlying gap landed
  2026-07-17** (see the "clean up stuck in-progress state" item
  above, first in this epic's list, whose scope and mechanism are now
  both decided) -- worth deciding both fixes together, since "clean
  up" is likely the simpler complement to whichever resume fix (below)
  actually gets built, not a substitute for it: even a full resume fix
  still needs a manual escape hatch for the case where the person
  deleted the files herself and there's genuinely nothing to resume.
  **Fix size still undecided — pick one before starting:**
  - **Quick UX patch:** when Continue can't actually find the books it
    promised, say so honestly (e.g. "We couldn't reload your previous
    books — please add them again") instead of silently landing on an
    unexplained empty Screen 1. Frontend-only, small.
  - **Full fix:** rebuild a live `BatchRunner` from `state.json` on
    backend startup so Continue genuinely resumes the 2 books, not
    just detects that they exist. Backend-significant — this is the
    real, not-yet-scoped work `CLAUDE.md` has flagged since Epic 6/8.
- [ ] **Open:** screen-reader tester — confirm, or document the honest
  fallback framing if none materializes
- [ ] **Open:** her-facing copy read-through — real unassisted dry run
- [ ] **Open:** per-series voice memory, second look after real
  multi-book use

---

## Epic 10 — Packaging & First-Run Experience

**Resequenced 2026-07-18, direct request:** split into two phases so
real-person testing (the primary FMS/RA persona's own unassisted dry
run, `docs/BACKLOG.md` Epic 9's still-open "her-facing copy read-
through" item) can start against something that looks and runs like a
finished app — no visible terminal, no two-process dev setup — *without*
first paying for the full PyInstaller/SmartScreen/installer work, which
is genuinely slower to iterate on and not needed just to get a clean
single-click launch. **Phase A directly unblocks that testing and should
happen first; Phase B is deliberately deferred until after an initial
round of real-person feedback is in**, so bugs she finds get fixed by
editing code and restarting one process, not by re-running a multi-
minute PyInstaller build and re-doing a SmartScreen click-through on
every single fix (see the reasoning below Phase B for why that ordering
matters, not just convenience).

### Phase A — unblocks real-person testing, do first ✅ Complete (2026-07-18)

**Built and verified 2026-07-18** (472 backend tests / 96% coverage, 224
frontend tests / 32 files, both clean via real `pytest --cov` and
`npm run build && npm run lint && npm test` passes; plus a real live
smoke test, see below):

- [x] **Flask must gain a route serving `frontend/dist/`** (static files +
  a fallback to `index.html` for any non-`/api/*` GET). Confirmed missing
  while closing out Epic 7/8: `backend/app.py` currently only registers
  `/api/*` JSON routes, so `python launcher.py` alone opens a browser to
  a `404`. Dev mode works today because Vite serves the frontend
  directly on its own port and proxies `/api` through
  (`frontend/vite.config.ts`) — that path never needed Flask to serve
  anything but JSON. **Simpler than a typical SPA-router fallback:**
  `App.tsx` has no client-side routing (`react-router` or otherwise) —
  it's all internal component state (`phase`/`subView`), one real URL
  path (`/`) — so the fallback route doesn't need to distinguish "a real
  client route" from "a 404," it can serve `index.html` for any
  unmatched GET unconditionally (a mistyped `/api/*` path still gets a
  real 404, checked explicitly). **Built to already handle both the dev
  and frozen-`.exe` cases** (`_frontend_dist_dir()` checks
  `sys._MEIPASS` when frozen, else a path relative to `backend/app.py`)
  even though Phase B's PyInstaller work is what actually exercises the
  frozen branch.
- [x] **A no-console way to hand her a working GUI without a full
  `.exe`** — `run_gui.vbs` (repo root), a `pythonw.exe` wrapper around
  `launcher.py`. Live-tested via `cscript` (see below), not just written:
  confirmed no console window, no lingering process after `/api/quit`.
  Whoever sets her up creates a desktop shortcut to this file (right-
  click → "Send to" → "Desktop (create shortcut)"). Explicitly a
  **testing-phase stand-in, not a replacement for real packaging** — she
  still needs Python/the venv set up on whatever machine she tests on (a
  technical family member does that once, same pattern as AI-key
  provisioning and the SmartScreen click-through elsewhere in this doc),
  and Epic 10 isn't "done" until Phase B's real `.exe` removes that
  dependency too.
- [x] **Smoke-test the real single-process path end to end** — `npm run
  build` in `frontend/`, then a real `python launcher.py` run (no second
  terminal, no `npm run dev`), confirmed live via curl against the
  actual running server: `/` serves the real built `index.html`, a real
  static asset under `/assets/` serves correctly, `/api/status` returns
  real JSON, an arbitrary unknown path still falls back to `index.html`
  (no client routing to break), and `/api/some-typo` still returns a
  real 404 JSON rather than silently serving HTML. Then the same check
  again through `run_gui.vbs` specifically (via `cscript`, confirming
  the wrapper itself launches the real server, not just `launcher.py`
  directly) — both runs shut down cleanly via `/api/quit`. **What this
  didn't cover:** a full manual click-through of every screen (Screen 1
  → identification → voice picker → generation → review) in a real
  browser — the actual risk this item named (path-resolution/static-
  asset-caching bugs in the single-process path specifically, as opposed
  to route logic already covered by the full backend test suite) is
  confirmed fixed; a real end-to-end UI walkthrough is still worth doing
  before or during her actual testing.

**Moved here from Epic 8.5 (2026-07-18, direct request), also built and
verified in this pass:** two real UI-polish items that never got built.

- [x] **Screen 1: auto-load books already in `books_folder`** as a
  selectable checklist, alongside (not instead of) the existing
  drag-and-drop. `GET /api/books/from-folder` lists `.epub` files
  already in her remembered folder (excluding anything already added to
  the batch); `POST /api/books/from-folder` adds a checked subset,
  reusing the exact same per-file result shape as the upload route so
  the frontend's existing rejection-handling logic needed no changes.
  **Default-checked-state decision:** everything found starts pre-
  checked — fewest required actions for the common case, she unchecks
  what she doesn't want rather than checking everything she does.
  Refetches whenever the batch's book count changes, so an item she
  just added (from either source) drops off the list automatically.
- [x] **Format hint text on Field Correction Popup inputs** (Author:
  "Last name, first name -- like Jacka, Benedict"; Series Number: "Just
  the number -- like 1 or 2.5") — a new optional `hint` prop on the one
  shared `FieldCorrectionPopup` component, tied to the input via
  `aria-describedby`, wired at both call sites (`ConfirmMetadataScreen`,
  `FixInfoFlow`). Title/Series have no particular expected shape, so no
  hint for those.

**Real bug found and fixed post-verification, same day (2026-07-18) —
real user report:** "Change my folders" stopped opening the native
dialog at all, both for the books folder and the output folder. Not a
regression from the Phase A work above — `backend/dialogs.py` and
`FoldersScreen.tsx` are both untouched since Epic 7/8 — it was a
pre-existing bug that had simply never been exercised against a real
running server before, since every automated test mocks the dialog call
out entirely, and Phase A's own single-process path is what made
clicking through the real GUI this easy for the first time. **Root
cause, confirmed by live reproduction:** `tkinter`'s `Tk()`/dialogs need
one *consistent* thread, but every Flask route runs on a fresh thread
from `waitress`'s worker-thread pool on each request — calling the real
dialog directly from a route handler intermittently hangs forever
(reproduced by calling the route against a real running server and
watching it never return, while every other route kept responding
normally — proof exactly one of `waitress`'s *finite* worker threads got
permanently stuck, not that the whole server broke; enough unlucky
clicks would eventually exhaust all of them and take the whole app
down). **Fix:** `backend/dialogs.py::request_folder_pick()` — a single
background thread, started once and reused for the process's whole
lifetime, now owns every real `tkinter` call; a route submits a request
to it via a queue and blocks for the answer, same behavior as before,
just on the right thread. Full reasoning: `ADR-0006`'s own addendum.
**Live-verified, not just unit-tested:** a real running server with the
dialog's own deepest call faked (so it's driveable without a human
clicking through an OS dialog) handled 8 sequential and 6 concurrent
`POST /api/dialogs/folder` calls correctly and quickly (~200ms each),
staying fully healthy throughout — the same real-server test that
reproduced the original hang (empty response, full timeout, every time)
before the fix.

**A second real bug found and fixed the same day, also a real user
report:** auto-load-from-folder's "Add N books" button failed every
book whose filename had a space in it — real report: "The Dragon
Reborn.epub," visibly listed on the same screen a moment earlier, came
back "That file couldn't be found in your books folder" the instant she
tried to add it. **Root cause:** `_safe_folder_epub_path()` ran the
filename through `secure_filename()` before looking it up on disk —
copied from `_safe_upload_path()`'s own path-traversal defense above it,
which is the right tool for choosing a *new* filename to write to but
the wrong one for looking up an *existing* file by its exact,
already-known name: `secure_filename()` collapses whitespace runs into
a single `_` (confirmed directly: `secure_filename("The Dragon
Reborn.epub")` → `"The_Dragon_Reborn.epub"`, which never existed on
disk). **Fix:** drop the `secure_filename()` step entirely; reject any
filename containing a path-separator character outright (sufficient on
its own to block traversal as a single path component), on top of the
resolve()-and-containment check that was already there as defense in
depth. New regression test adds a real file with a space in its name
and confirms the full add flow succeeds.

**A real gap found and fixed the same day, while diagnosing the two bugs
above:** the only way to stop the background server was "Quit for now"
on the Working screen — every other screen had no way to end the
session at all except closing the browser tab, which (by design,
ADR-0001) never actually stops the server. This directly caused real
confusion diagnosing the two bugs above: a still-running server from an
earlier attempt got mistaken for "already closed," and its stale,
pre-fix code masked the actual fix behind what looked like a persistent
bug. **This was the original design's own scope, not a regression** —
`03-gui-ux-design.md` always said Quit belonged to the Working screen,
with a persistent header merely *allowed* as an alternative, never
built that way. **Fix:** `AppHeader` gained its own confirm-gated Quit
button ("Stop for now? You can pick up right where you left off next
time."), shown on every screen *except* first-launch onboarding
(nothing meaningful running yet) and the Working screen itself, which
already has its own — `App.tsx` computes visibility by mirroring the
same `state`/`needs_input` branching `renderScreen()` already uses, so
the collision prompt (the *other* thing `state: "working"` can mean,
which has no Quit button of its own) still gets the header's. New
tests cover every phase/state boundary directly, including a check that
exactly one "Quit for now" button ever renders on the Working screen,
never two.

**Why this ordering, not just "nice to have first":** once she's testing
against a real packaged `.exe`, every bug-fix cycle costs a full
PyInstaller rebuild (multi-GB, minutes, not seconds) *and* a fresh
SmartScreen "More info → Run anyway" click-through — Windows treats each
newly-built `.exe` as a distinct unrecognized file, so ADR-0011's
one-time-friction mitigation resets on every single rebuild, not just
the first install. Doing Phase A first means the bugs her testing
actually surfaces get found and fixed against the cheap single-process
path (edit code, restart `launcher.py`, refresh the browser), and only
the fixes that survive that round get carried into a `.exe` build — far
fewer total PyInstaller rebuilds and SmartScreen click-throughs than
packaging first and iterating against the finished artifact.

- [ ] Full PyInstaller build pipeline (`npm run build` → `dist/` → bundle)
- [ ] SmartScreen mitigation: installer runs it once first + fallback
  HTML file
- [ ] Browser-launch fallback: retry, then native `tkinter` dialog with
  clipboard-copied address — logic already built (`launcher.py`), this
  is verifying it on a real machine, not writing it
- [ ] First-run setup screen tied to the lazy trigger point
- [ ] Verify uninstall is genuinely two deletions
- [ ] **Moved from Epic 4:** CPU vs. GPU benchmarking on real target
  hardware — produces the real `SECONDS_PER_CHAR` constant
  (`pipeline/tts_engine.py`) the Working-screen time estimate needs,
  replacing the current placeholder. Only needs *real hardware*, not
  necessarily the finished `.exe` specifically — could in principle move
  earlier (even into Phase A) if real target hardware becomes available
  sooner than the rest of Phase B; left here since nothing else forces
  it before this point.
- [ ] **Moved from Epic 4:** Kokoro vs. Perchance output parity QA pass
  — a real side-by-side listen before fully retiring the old
  Selenium/Perchance path as a fallback option. Same real-hardware-not-
  necessarily-`.exe` caveat as the item above.

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
| Perchance vs. Kokoro output parity | 10 Phase B (moved from 4 — needs a real packaged `.exe` on real hardware) |
| CPU vs. GPU benchmarking (`SECONDS_PER_CHAR`) | 10 Phase B (moved from 4, same reason) |
| Flask doesn't serve the built frontend | 10 Phase A — done, built and verified 2026-07-18 (`_frontend_dist_dir()`/catch-all route in `backend/app.py`, live curl-verified against a real running server). |
| No-console GUI launch for real-person testing | 10 Phase A — done, built and verified 2026-07-18 (`run_gui.vbs`, live-tested via `cscript`). |
| "Change my folders" dialog not opening | 10 Phase A — **real user report, fixed and live-verified 2026-07-18**, same day. Pre-existing bug (unrelated to the Phase A code itself), surfaced by Phase A making real-server testing this easy for the first time: `tkinter` dialogs called from a Flask route handler hang intermittently, since every route runs on a fresh `waitress` worker thread. Fixed via a single persistent background thread owning all `tkinter` calls (`backend/dialogs.py::request_folder_pick()`). See `ADR-0006`'s addendum. |
| Auto-load-from-folder fails filenames with spaces | 10 Phase A — **real user report, fixed 2026-07-18**, same day. `_safe_folder_epub_path()` ran the filename through `secure_filename()` before the disk lookup, which collapses whitespace into `_` — a listed, real file like "The Dragon Reborn.epub" came back "couldn't be found." Fixed by dropping that step in favor of a plain separator-character check plus the existing containment check, neither of which mangles the filename. |
| Screen 1 auto-load-from-folder | 10 Phase A (moved from 8.5) — done, built and verified 2026-07-18 (`GET`/`POST /api/books/from-folder`). |
| Field Correction Popup format hints | 10 Phase A (moved from 8.5) — done, built and verified 2026-07-18 (`FieldCorrectionPopup`'s new `hint` prop). |
| MAX_FILES-exceeded rejection message, Screen 1 UI | 8 — done |
| Session-local same-series voice default | 8 — decided against (moved from 4): the backend only ever hands out one global default; a second, client-only "current default" risked silently disagreeing with the server for marginal convenience. |
| Her-facing copy wording, unassisted dry-run test | 9 |
| Screen-reader tester confirmation | 9 |
| Dyslexic-reader tester | **Moved to Wish List 2026-07-18** — the tester previously lined up (`00-overview-and-goals.md` §The accessibility targets, ADR-0015) is no longer available. See Wish List below. |
| Per-series voice memory, second look | 9 (same decision as above, revisit together if ever) |
| "Welcome back" full state-file-driven resume | 9 — done, built and verified 2026-07-18 (`state.json` schema v2 book snapshots + `BatchRunner.restore_books()` at process startup). |
| "More options": clean up stuck in-progress book state | 9 — done, built and verified 2026-07-18 (`POST /api/cleanup-in-progress`, `MoreOptionsScreen`'s "🧹 Nuke everything in progress"). |
| Persistent step/progress indicator across the main batch flow | 9 — done, built and verified 2026-07-18 (`StepProgress` shared component). |
| Vite dev-server Origin/CSRF proxy config | 7 — done |
| Screen 1 settings entry points → "More options" hub | 8.5 — done |
| Header (brand title + Home button) redesign | 8.5 — done |
| Rename stage AI-enrichment per-field merge | 8.5 — done |
| `AddBooksScreen.test.tsx` `BookRejectionReason` type error | 8.5 — done |
| Working screen: Pause/Cancel/Resume gave no visible feedback | 8.5 — done, verified 2026-07-17 |
| Voice picker: heading-to-list gap and inter-row spacing | 8.5 — done, verified 2026-07-17 |
| "Fix info" overlay: field-list-to-Save spacing | 8.5 — done, verified 2026-07-17 |
| Working screen: chunk-progress readout + real progress bar | 8.5 — done, verified 2026-07-17 |
| `.screen-actions` DOM-ordering bug, VoiceAssignmentScreen single-book mode | 8.6 — done, verified 2026-07-17 |
| Icon system (real SVG icons vs. emoji) | Not scheduled — future nice-to-have, Epic 8.6 notes |

---

## Wish List (not scheduled — real, wanted, but no current path to doing it)

Distinct from "Not scheduled" Open Items above (e.g. the icon system),
which are cost/benefit judgment calls that could be picked up any time
someone decides it's worth it. Everything here is blocked on something
outside this project's control — most often a real person's
availability — not on priority or engineering cost. Move an item back
into an epic's active checklist the moment that blocker clears.

- **Real dyslexic-reader test (unassisted).** Moved here 2026-07-18 —
  the tester previously lined up (`docs/requirements/00-overview-and-
  goals.md` §The accessibility targets, `ADR-0015`) is no longer
  available. Was originally Epic 9's own checklist item, framed as
  already scheduled since a real person had been identified; that's no
  longer true, so leaving it checked-off-pending on Epic 9's active list
  would have overstated how close it actually is. **Until a new tester
  is found, the dyslexic-reader side of this app's WCAG 2.1 AA alignment
  stays in exactly the same honest "designed and tested against WCAG 2.1
  AA criteria, not yet validated by a dyslexic reader" framing ADR-0015
  already uses for the screen-reader side** — never silently upgraded to
  "validated," here or anywhere else this project is described (README,
  the ADR itself, the requirements docs). The concrete design commitment
  this test would verify (left-aligned/never-justified body text,
  generous line-height/letter-spacing, plain sans-serif —
  `frontend/src/index.css`, `03-gui-ux-design.md` §Perceivable) is
  already built and unaffected; only the real-person verification step is
  blocked. Revisit if a tester becomes available again — no expiration
  date on this item.
