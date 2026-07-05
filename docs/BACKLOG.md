# epub-automation — Implementation Backlog

Status: build not yet started. This is the source of truth for *what
order* things get built in — `docs/requirements/` is *what*,
`docs/design/` is *why*, `docs/design/PATTERNS.md` is *how*, this file
is *in what order and why that order*.

**Sequencing rationale (see `docs/design_review.md` and
`docs/design/SYSTEM_DESIGN.md` §7.6 for the full reasoning):**
scaffolding first, then the two highest-risk/highest-uncertainty items
early (the sanitize stage's from-scratch language port, and the Kokoro
packaging spike) rather than saving them for last, then the remaining
pipeline stages in reuse order, then the backend contract, then the
frontend and its accessibility layer, then packaging/QA/documentation
close-out. This mirrors the project's own reuse-by-default principle:
ported, already-tested logic carries less risk than new code, so new
code and unverified assumptions get front-loaded for attention, not
back-loaded as "the easy part we'll get to eventually."

**Confirmed at backlog kickoff** (see
`docs/requirements/08-open-questions-and-assumptions.md`): Windows-only
v1 scope, and acceptance of the Gemini free-tier data-use trade-off.
Both providers (Gemini, OpenAI) are built out as equally first-class
choices — see Epic 3.

**How to use this doc:** work top to bottom within an epic unless a
dependency says otherwise; epics themselves can overlap where noted
(Epic 1 runs in parallel with Epic 2). Mark stories `[ ]` → `[x]` as
they're completed, and add new stories here rather than only in
conversation if implementation surfaces work not already captured — see
`CLAUDE.md` §Documentation & session close.

---

## Epic 0 — Scaffolding & Cross-Cutting Infrastructure

Nothing here is stage-specific; it's the seams every later epic builds
on top of. Do this first so `docs/design/PATTERNS.md`'s patterns exist
as real interfaces before any stage logic is written against them.

- [ ] Repo structure matching `docs/requirements/01-architecture.md`
  §Project structure (`pipeline/`, `backend/`, `frontend/`, `main.py`,
  `launcher.py`, `tests/`, etc.)
- [ ] `Stage` protocol/interface (Pipeline pattern — `PATTERNS.md` §1
  sketch) with a minimal fake implementation and a test proving the
  interface itself is sufficient (not just concrete stages later)
- [ ] `Repository` wrappers for `state_manager.py` and
  `audit_logger.py` (PATTERNS.md §1), including `schema_version`
  read/write and the migration/mismatch policy from
  `05-data-settings-and-logging.md` §Schema versioning
- [ ] Atomic write-to-temp-then-rename helper for `settings.json` and
  the state file (ADR-0005) — TDD with a simulated crash-mid-write test
  (`09-testing-strategy.md` §TDD workflow)
- [ ] Single-instance lock with **PID-based stale-lock detection**
  (ADR-0007, `01-architecture.md` §Single-instance behavior) — TDD with
  a simulated dead-PID scenario proving the lock clears and the launch
  proceeds
- [ ] `SafeZipOperation` Template Method base (PATTERNS.md §1) — guard
  order: path-traversal → zip-bomb cap → XXE prevention, fixed and
  reused by every future zip-opening call site
- [ ] CI skeleton: `pytest` + `pytest-cov` (`--cov-fail-under=80`),
  `black`, `ruff`, `mypy --strict` — ported from `epub-renamer`'s
  existing toolchain, not invented fresh (`09-testing-strategy.md`)
- [ ] `profanity.txt` bundling + first-run copy-into-`settings.json`
  mechanism (`05-data-settings-and-logging.md` §Profanity list)
- [ ] `.env.example` for CLI/advanced use (`01-architecture.md`)

---

## Epic 1 — Kokoro/PyInstaller Packaging Spike *(run in parallel with Epic 2)*

The one open item with real architectural blast radius if it goes
badly — sequenced early specifically so a bad answer here can still
change downstream decisions cheaply.

- [ ] Minimal PyInstaller build that imports `kokoro`, loads the model,
  and generates one sample MP3
- [ ] Confirm or rule out a native (non-Python) dependency — e.g.
  `espeak-ng` — for the American/British-English voice scope this
  project actually uses (`04-tts-engine.md` §Voice samples)
- [ ] If a native dependency exists: add the bundling step to
  `07-packaging-deployment.md` §Known packaging constraints as a named
  build requirement
- [ ] Update `CLAUDE.md`'s "Packaging risk: Kokoro native deps" row and
  `docs/design/SYSTEM_DESIGN.md` §8/§9 with the finding either way

---

## Epic 2 — Sanitize Stage Port (PowerShell → Python)

Highest risk of the four stages: the only genuine language port, and
security-critical (untrusted, user-supplied ZIP archives). Do this
first among the stages while it has full attention, not last as
"just a port." See ADR-0004.

- [ ] Port all ten security controls from `PS_Run-CleanUpEpub.ps1`
  exactly (`02-pipeline-stages.md` §Stage 2, ADR-0004): path-traversal
  guard (extract + repack), zip-bomb cap, XXE prevention, profanity-list
  size cap, whole-word matching, asterisk replacement, `.xhtml`/`.htm`/
  `.html` scope, mimetype-first uncompressed repack, temp-dir atomic
  cleanup
- [ ] Adopt the `regex` package (or equivalent) for the Unicode-category
  whole-word matching **and** its 5-second ReDoS execution timeout —
  Python's stdlib `re` supports neither (found during the design
  review; see ADR-0004's "Regex/dependency note" and
  `10-licensing-and-notices.md`'s proposed dependency entry)
- [ ] Build `sanitize_stage.py` on top of the `SafeZipOperation`
  Template Method from Epic 0
- [ ] Sidecar CSV report (`CleanReport_<timestamp>.csv`,
  `(book, file, word, count)` rows) + aggregate `words_replaced` /
  `sanitize_detail_report` audit-log columns (`02-pipeline-stages.md`
  §Stage 2)
- [ ] Adversarial fixtures: a path-traversal zip, a zip bomb, an XXE
  payload, and a pathological profanity-list entry proving the ReDoS
  timeout actually fires — target near-100% coverage on this stage
  (`09-testing-strategy.md` §Priority coverage areas)
- [ ] Editable word-list read/write against `settings.json`'s
  `profanity_words` (`05-data-settings-and-logging.md`)

---

## Epic 3 — Rename Stage Port

- [ ] Port `ai_providers/` registry from `epub-renamer` **as-is**:
  `base.py`, `registry.py`, `openai_provider.py`, `null_provider.py`
  (ADR-0003, ADR-0014 — direct port, not new code)
- [ ] Write `gemini_provider.py` — the one genuinely new provider
  implementation (ADR-0003)
- [ ] Confirm both `"gemini"` and `"openai"` are equally selectable via
  `settings.json`'s `ai_provider` field and the GUI's AI Helper Setup
  screen — **neither is more "default" than the other** at the
  settings-schema level (per backlog-kickoff confirmation, see
  `08-open-questions-and-assumptions.md`)
- [ ] Port `MAX_FILES` cap + `DRY_RUN=true` safe default from
  `epub-renamer`'s `.env`-driven config (`06-safety-error-handling.md`
  §Resource & cost safety)
- [ ] `FILENAME_PATTERN` verbatim reuse + already-normalized-skip logic,
  including the `skipped_reason: "already_normalized"` audit row
  (`02-pipeline-stages.md` §Stage 1)
- [ ] Per-file silent fallback to `NullProvider` on AI failure/rate-limit
  (`02-pipeline-stages.md` §Stage 1 Failure handling)
- [ ] MAX_FILES batch-overflow UX: reject excess books individually at
  Screen 1 add-time with a friendly message (`06-safety-error-handling.md`
  §Resource & cost safety, resolved during the design review)

---

## Epic 4 — Audio Stage (Kokoro TTS Integration)

- [ ] `tts_engine.py` wrapping `kokoro.KPipeline` (`04-tts-engine.md`
  §Interface sketch)
- [ ] Reuse `chunk_text()` / `MAX_CHUNK_CHARS = 4,000` verbatim from
  `epub-to-audio/epub_utils.py` — flagged for re-validation once real
  Kokoro samples exist, not assumed correct just because inherited
- [ ] MP3 encoding: 128kbps CBR, mono, 48kHz (`04-tts-engine.md` §MP3
  encoding parameters) — this is what makes the disk-space formula's
  16,000 bytes/sec constant exact
- [ ] Voice sample pre-generation + cache at
  `%APPDATA%\EpubAutomation\voice_samples\`, with `version.txt`
  cache-invalidation tied to the installed `kokoro` version
  (`04-tts-engine.md` §Voice samples)
- [ ] **Lazy** first-run trigger for both the model download and voice
  sample generation — first actual need, not eager at every launch
  (`04-tts-engine.md` §First-run setup, resolved during the design
  review)
- [ ] Per-chunk resume: skip any existing MP3 above the minimum size
  threshold (`02-pipeline-stages.md` §Stage 3, `06-safety-error-handling.md`
  §Long-run resilience)
- [ ] Disk-space estimate formula (`estimated_audio_bytes =
  total_chars_remaining × SECONDS_PER_CHAR × 16,000`) with the
  placeholder `SECONDS_PER_CHAR`, biased toward overestimating
  (`06-safety-error-handling.md` §Resource & cost safety)
- [ ] Session-local same-series voice default within a multi-book batch
  (ADR-0010, `03-gui-ux-design.md` §Voice assignment) — no persisted
  per-series memory
- [ ] **CPU vs. GPU benchmarking pass** on real target hardware — this
  single measurement produces both the `SECONDS_PER_CHAR` constant above
  and the dynamic Working-screen time estimate (never a hardcoded "a few
  hours" string) — tracked open item, see
  `08-open-questions-and-assumptions.md` item 3
- [ ] **Perchance-parity QA pass** — 2–3 representative voices, matched
  text through old (Perchance, if reachable) and new (Kokoro) paths,
  side-by-side listen for volume/sample-rate/pacing differences before
  fully retiring the Selenium code path (keep it in version control
  until parity is confirmed) — tracked open item, see
  `08-open-questions-and-assumptions.md` item 2

---

## Epic 5 — Retag Stage

- [ ] Port `retag.py` into `retag_stage.py` largely as-is
  (`02-pipeline-stages.md` §Stage 4)
- [ ] **Folder-rename bug fix**: rename the containing output folder to
  match corrected metadata, not just the MP3 files inside it — a real
  gap in the original script, found by reading the source directly
- [ ] Regression test proving the folder itself gets renamed, not just
  its contents (`09-testing-strategy.md` §Priority coverage areas) —
  this is what makes the bug fix durable rather than something that
  quietly regresses
- [ ] Dry-run support (preview without writing)
- [ ] Author/title/series/series-number override plumbing, matching the
  original script's CLI flags exactly

---

## Epic 6 — Backend / Flask Bridge

- [ ] `launcher.py`: waitress bind to `127.0.0.1` only (fixed constant,
  ADR-0008), free-port discovery, single-instance lock acquisition
  (Epic 0), browser-launch with retry-then-native-fallback
  (`07-packaging-deployment.md` §Browser-launch fallback)
- [ ] `backend/app.py` routes + `backend/dialogs.py`
  (`tkinter.filedialog` bridge, ADR-0006)
- [ ] `backend/bridge.py` — thin Adapter into `pipeline/` (ADR-0001,
  PATTERNS.md §1); **zero business logic**, translation only
- [ ] Status endpoint: implement the explicit state-machine derivation
  function per the fixed precedence rule in `01-architecture.md` §Status
  endpoint contract §State derivation — unit-test the function directly
  against that precedence table, independent of any HTTP plumbing
- [ ] Progress → polling via an Observer-style event stream from
  pipeline stages (PATTERNS.md §1), so `pipeline/` never needs to know
  an HTTP server exists
- [ ] `main.py` CLI: thin Adapter mirroring `bridge.py`'s role; reserve
  `--workers N` (default `1`) on the `audio` command without
  implementing parallelism yet (ADR-0009)
- [ ] Error communication: generic "Something went wrong" + "Copy
  details for support" bundle, built from settings with sensitive
  fields stripped (`ai_api_key` never included), degrading gracefully
  if the audit log itself can't be read (`06-safety-error-handling.md`
  §Error communication)
- [ ] Output-collision handling: distinct prompts for EPUB-copy vs.
  audiobook collisions in `output_folder`
  (`06-safety-error-handling.md` §Concurrency & duplicate handling)

---

## Epic 7 — Frontend Scaffolding

- [ ] Vite + React project setup (build-time only — confirm no runtime
  Node/npm dependency leaks into the packaged `.exe`)
- [ ] API-client facade wrapping every `fetch` call to the Flask backend
  (PATTERNS.md §2)
- [ ] `usePollingStatus()` hook (PATTERNS.md §2)
- [ ] `useFocusTrap()` hook — focus-trap-on-open, focus-return-on-close,
  Escape-to-close (`03-gui-ux-design.md` §Accessibility §Operable)
- [ ] `useAriaLiveThrottled()` hook — `polite` for routine messages,
  `assertive` for errors, throttled progress announcements (not every
  poll tick) (`03-gui-ux-design.md` §Accessibility §Status updates)
- [ ] `useReducer`-based local UI state (which overlay is open, which
  field is mid-edit) — supports the "app reopens to the same state"
  requirement (PATTERNS.md §2)
- [ ] Container/Presentational split: one top-level container owns
  `usePollingStatus()`; screens receive plain props (PATTERNS.md §2)

---

## Epic 8 — GUI Screens

Build in the order a first-time user encounters them, per
`03-gui-ux-design.md`. Every screen must satisfy
`03-gui-ux-design.md` §Accessibility: WCAG 2.1 AA alignment before being
considered done (`CLAUDE.md` rule #5) — real focusable controls, labels,
focus management, `aria-live` wiring where relevant.

- [ ] First-launch one-time setup (folder pickers via `dialogs.py`)
- [ ] AI Helper Setup (provider choice, key entry, masked display) —
  both Gemini and OpenAI paths fully supported, Skip equally weighted
- [ ] "Welcome back" screen, driven entirely by state-file content
  (`06-safety-error-handling.md` §Long-run resilience)
- [ ] Screen 1: Add Books (drag-and-drop + equally-capable "Choose
  Books..." button, per-book Remove, the two stage toggles)
- [ ] **Field Correction Popup** — one shared component (Compound
  Component reuse, already implicit per `03-gui-ux-design.md`), used
  identically by pre-generation confirm-metadata and post-generation
  "No, let me fix it"
- [ ] Per-book identification loop
- [ ] Voice assignment — single-book full picker and multi-book table,
  both driven by the same `useVoiceAssignmentView(books)` view-model
  hook (PATTERNS.md §2) disambiguated by `books.length`
- [ ] Screen: Working — dynamic time estimate (from Epic 4's
  benchmarking), Pause/Cancel with color **and** permanent caption text,
  "Quit for now" control
- [ ] Screen: Review — book-scoped "See the audiobook files" link above
  the Yes/No question, general output-folder link
- [ ] "No, let me fix it" flow (reuses Field Correction Popup, feeds
  `retag_stage.py` overrides)
- [ ] Settings areas: Change my folders, Words to clean up, "What voice
  did I use before?" (read-only, degrades gracefully on audit-log read
  failure)

---

## Epic 9 — Accessibility Verification

- [ ] `axe-core` (via `vitest-axe`/`@axe-core/react`) wired into the
  same `vitest run` invocation gating the 80% coverage floor
- [ ] `eslint-plugin-jsx-a11y` added to the existing lint step
- [ ] Manual keyboard-only pass across every screen in Epic 8
- [ ] Real NVDA pass + Windows Narrator baseline sanity check
- [ ] Real test with the already-identified dyslexic reader — genuine
  unassisted/lightly-observed run, not a design review of mockups
- [ ] **Screen-reader tester** — confirm or, if enough time passes
  without one, explicitly document the honest fallback framing
  ("designed and tested against WCAG 2.1 AA criteria," never "validated
  by a blind user") — tracked open item, see
  `08-open-questions-and-assumptions.md` item 5
- [ ] **Her-facing copy read-through** — the real acceptance test is an
  unassisted dry run by the mother (or someone with a similar profile)
  through first-launch setup and a full single-book conversion, watched
  but not helped — tracked open item, see
  `08-open-questions-and-assumptions.md` (copy wording)
- [ ] **Per-series voice memory, second look** — revisit once real
  multi-book batches have actually been run, per ADR-0010's own
  "worth a second look on reflection" flag

---

## Epic 10 — Packaging & First-Run Experience

- [ ] PyInstaller build pipeline (`npm run build` → `dist/` → bundle
  alongside `backend/` + `pipeline/`)
- [ ] SmartScreen mitigation: primary (technical family member runs it
  once first) + fallback local HTML file with one screenshot
  (`07-packaging-deployment.md` §Windows SmartScreen)
- [ ] Browser-launch fallback: retry once, then native `tkinter` dialog
  with clipboard-copied address and a "Try Again" button
- [ ] First-run "Setting up for the first time..." screen tied to the
  **lazy** trigger point from Epic 4, not eager at launch
- [ ] Verify uninstall is genuinely just two deletions
  (`.exe`/shortcut + `%APPDATA%\EpubAutomation\`) with nothing else left
  behind

---

## Epic 11 — Documentation & Release Wrap-Up

- [ ] `CODEBASE_INDEX.md` at repo root (file map + migration/schema
  table), per `CLAUDE.md` §Documentation & session close #2
- [ ] `NOTICE` file at repo root, generated from
  `10-licensing-and-notices.md`'s dependency table (confirm the `regex`
  package's actual license once chosen in Epic 2)
- [ ] Coverage badge in the repo README
- [ ] Privacy note confirmed present in the shipped README (already
  drafted, `06-safety-error-handling.md` §Error communication)
- [ ] Final CLAUDE.md / ADR / SYSTEM_DESIGN.md consistency pass — this
  project's own stated practice (`CLAUDE.md` rule #3) of keeping
  `docs/requirements/` and `docs/design/` reconciled, applied one more
  time before calling v1 done

---

## Open items carried from `08-open-questions-and-assumptions.md`

For quick reference — each also appears inline above at the epic where
it's actually resolved:

| Item | Epic |
|---|---|
| Kokoro/PyInstaller native-dependency packaging risk | Epic 1 |
| Perchance vs. Kokoro output parity | Epic 4 |
| CPU vs. GPU benchmarking (also produces `SECONDS_PER_CHAR`) | Epic 4 |
| Her-facing copy wording, real unassisted dry-run test | Epic 9 |
| Screen-reader tester confirmation | Epic 9 |
| Per-series voice memory, second look | Epic 9 |
