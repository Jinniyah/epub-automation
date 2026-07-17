# CLAUDE.md — AI Development Rules for epub-automation
# Last updated: 2026-07-17 — Epics 0-8 complete (413 backend tests / 96% coverage, 199 frontend tests across 31 files / ~85-90% coverage -- corrects an earlier "331 frontend tests" figure carried in these docs since Epic 7/8, which was simply wrong; confirmed via a real `npm test` run 2026-07-17, black/ruff/mypy --strict + eslint/tsc clean). Epic 8.5/8.6 (visual polish, real-user feedback) landed on top of that baseline. Five post-verification fixes landed 2026-07-17, all from real user reports/screenshots, **all confirmed clean across two separate real `npm run build && npm run lint && npm test` passes** (both reported by the user; neither run in this session -- filesystem-only MCP access throughout): `.screen-actions` DOM-ordering (VoiceAssignmentScreen single-book mode), Working-screen Pause/Cancel/Resume giving no visible feedback (backend logic was already correct; the gap was entirely frontend), VoicePicker heading/row spacing, the "Fix info" overlay's field-list-to-Save spacing (same underlying nesting-depth bug class as the VoicePicker fix, one level deeper -- see the recurring-gotcha note in the Frontend styling row below), and the Working screen's chunk-progress readout + real `<progress>` bar (landed in a second pass right after the first four were confirmed). New `.stack`/`.stack-md`/`.progress-bar` CSS utilities cover the spacing and progress-bar fixes; the 70px row-height accessibility floor was deliberately left unchanged despite the added scroll. See CODEBASE_INDEX.md's Session notes and docs/BACKLOG.md Epic 8.5/8.6. Full epic-by-epic history: CODEBASE_INDEX.md's Session notes. **`docs/BACKLOG.md`'s Epics 0-8.6 were compacted 2026-07-17** (narrative detail dropped, decisions/gotchas kept, same convention CODEBASE_INDEX.md already used on 2026-07-10) -- Epic 9 itself was left at full detail since it's the next epic to be worked. Next: Epic 9 (accessibility verification, plus the "Welcome back" full-resume gap folded in 2026-07-16, and a new step/progress indicator item added 2026-07-17) — see docs/BACKLOG.md.

---

## Startup protocol

1. **Epics 0-8 complete; Epic 9+ not started.** Before writing new code,
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
| Folder pickers | `tkinter.filedialog` via Flask backend | ADR-0006 |
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

## Flagged open items

| Item | Status |
|---|---|
| Kokoro vs. Perchance output parity | Side-by-side listen needed — Epic 10 (moved from 4, needs a real packaged `.exe` on real hardware) |
| CPU vs. GPU inference speed | Needs benchmarking — Epic 10 (moved from 4, same reason) |
| No per-series voice memory | Decided against at both the backend (Epic 4/6) and frontend (Epic 8) layers — the frontend's `useVoiceAssignmentView` deliberately doesn't reproduce it client-side either, to avoid a second, possibly-disagreeing notion of "current default." Revisit only if real use surfaces a real annoyance — Epic 9 |
| Her-facing copy wording | Drafted, not final — real dry-run needed — Epic 9 |
| Screen-reader tester | Being pursued, not confirmed — never claim "validated by a blind user" until it happens — Epic 9 |
| "Welcome back" full resume | **Confirmed live 2026-07-16** (real screenshots: Continue silently lands on an empty Screen 1, no explanation) — no longer just a theoretical risk. Detection-only endpoint exists (`GET /api/welcome-back`); the Epic 8 screen (`WelcomeBack.tsx`) degrades honestly to a plain count when it can't match pending ids, but `App.tsx`'s `onContinue` doesn't re-fetch or reconstruct anything on top of that. **Folded into Epic 9** (2026-07-16, direct request) with two candidate fix sizes (quick honest-message patch vs. full `BatchRunner` reconstruction from `state.json`) — see that epic's own checklist item for the full writeup. Fix size not yet chosen. |
| Flask doesn't serve the built frontend | Found closing out Epic 7/8: `backend/app.py` only registers `/api/*` JSON routes — `python launcher.py` alone opens a browser to a `404`. Dev mode (Vite's own server + a separately-running backend) is real and works; single-process production serving is genuinely Epic 10 packaging work (frozen-`.exe` path resolution for the bundled `dist/`), added there as its own checklist item, not silently deferred. |
| Icon system (real inline SVG icons vs. emoji) | Deferred, not scheduled to any epic — reviewed alongside a mobile-app UI reference and judged not worth its real cost (a fresh `aria-label` pass + a full app-wide axe re-run) against the benefit, since the existing emoji already carry text alternatives per Epic 8/8.5's WCAG work. Revisit only if it becomes a real complaint — Epic 8.6 notes, `03-gui-ux-design.md` §Visual design system. |
| Step/progress indicator across the main batch flow | Added to Epic 9's checklist 2026-07-17, real user feedback (no orientation cue for a first-time/FMS-persona user). Multi-book "active book" behavior and its on-screen placement both decided the same day — see `docs/BACKLOG.md` Epic 9's own checklist item. Not yet built. |
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
