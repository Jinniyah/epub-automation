# CLAUDE.md — AI Development Rules for epub-automation
# Last updated: 2026-07-05 — Design phase complete, no code written. Full design in `docs/requirements/` + `docs/design/` (SYSTEM_DESIGN, ADRs, PATTERNS.md); reviewed in `docs/design_review.md`; sequenced in `docs/BACKLOG.md`. All open assumptions confirmed except the items in "Flagged open items" below. Still pending: a build-start session.

---

## Startup protocol

1. **No code exists yet.** Before writing any, read in order:
   `docs/requirements/README.md` → numbered docs 00–10 →
   `docs/design/SYSTEM_DESIGN.md` → `docs/design/adr/README.md` →
   `docs/design/PATTERNS.md` (implementation patterns to build against)
   → `docs/BACKLOG.md` (what order to build it in). `docs/design_review.md`
   explains why several decisions below look the way they do.
2. Check `docs/requirements/08-open-questions-and-assumptions.md` and
   this file's "Flagged open items" table first. Don't build against an
   open item without confirming with the user or flagging that you are.
3. `docs/requirements/`, `docs/design/`, and `docs/BACKLOG.md` are kept
   reconciled with each other — if a change to one affects another,
   update both, don't let them drift.
4. Create `CODEBASE_INDEX.md` at repo root during the first build
   session (file map, migration table), matching sibling projects.
5. **Apply the patterns in `docs/design/PATTERNS.md`** when writing
   pipeline/backend/frontend code (the `Stage` interface, `Strategy`/
   `Registry` for `ai_providers/`, `Repository` wrappers, the
   state-machine derivation function, the React hook layer). Flag it
   if a pattern turns out to be the wrong fit rather than silently
   diverging — update `PATTERNS.md` to match reality.
6. **Work from `docs/BACKLOG.md`, in sequence**, unless told otherwise —
   it already encodes risk ordering (sanitize port + Kokoro packaging
   spike early) and reuse-by-default (ported stages before new work).
   Check off items there as completed; add new ones if work surfaces
   that isn't captured yet.

## Project summary (full detail: `docs/requirements/00-overview-and-goals.md`)

Merges three existing standalone tools — all public on GitHub — into
one batch pipeline with two front doors: a CLI/advanced mode, and an
accessible local web GUI for a real accessibility persona (RA: reduced
fine-motor precision; FMS: difficulty holding multi-step processes in
mind), plus a broader WCAG 2.1 AA alignment layer (ADR-0015). Also a
portfolio piece.

- [`epub-renamer`](https://github.com/Jinniyah/epub-renamer) (MIT, Python)
- [`epub-sanitize`](https://github.com/Jinniyah/epub-sanitize) (no license, PowerShell)
- [`epub-to-audio`](https://github.com/Jinniyah/epub-to-audio) (MIT, Python)

**Explicit design principle:** reuse each source project's existing
implementation by default; write new code only for a changed
constraint, a real gap, or a bug fix — see ADR-0014 for the full
verbatim-vs-new accounting. The one large exception is the WCAG layer
(ADR-0015): none of the three source tools had a GUI at all.

## Environment

- Windows, PowerShell. Backslash paths. `;` not `&&` for chaining.
- Python 3.11+ for pipeline/backend. Node/Vite for React — **build-time
  only**, never a runtime dependency on the target machine.
- Ships as a single PyInstaller `.exe` for a non-technical end user —
  nothing at build time should assume Python/Node/a terminal exist on
  the *target* machine.

## Filesystem rules (this environment's known quirks — assume they apply here too)

- **Never use `filesystem:edit_file`** — silently fails on this
  Windows/CRLF setup (reports success, file unchanged). Always: full
  `read_text_file` → edit in memory → full `write_file` back. A partial
  write silently truncates the rest.
- **No delete operation** — only `move_file`. Stage removals in a
  `_removed/` folder at repo root for the user to `git rm` later.
- New files: `filesystem:write_file` only — sandbox file-creation tools
  write to a container, not this repo.
- Prefer a full read over `head`/`tail`/`view_range` when precision matters.

## Paths

| Root | Path |
|---|---|
| Repo root | `C:\Users\jinni\source\repos\epub-automation\` |
| Requirements (*what*) | `...\docs\requirements\` |
| Design + ADRs (*why*) | `...\docs\design\` |
| Patterns (*how*) | `...\docs\design\PATTERNS.md` |
| Final pre-coding review | `...\docs\design_review.md` |
| Backlog (*what order*) | `...\docs\BACKLOG.md` |
| Pipeline / backend / frontend (planned) | `...\pipeline\`, `...\backend\`, `...\frontend\` |
| Library staging (planned) | `...\Library\00-Incoming → 01-Renamed → 02-Sanitized → 03-Audio` |

## Key architectural decisions

Detail and rationale live in the linked doc — this table is a lookup
index, not a substitute for reading it.

| Decision | Rule | Doc |
|---|---|---|
| GUI transport | Flask/waitress + React (Vite, static build) | `01-architecture.md`, ADR-0001 |
| GUI process model | Background launcher opens browser to Flask; not pywebview — tab close ≠ job death | ADR-0001 |
| Status contract | One polling endpoint; `state` derived from `books[]` via a fixed precedence rule (backend state-machine fn); frontend reads it via per-screen view-model hooks | `01-architecture.md` §State derivation |
| TTS engine | Local `kokoro` (Kokoro-82M) — no browser/Selenium | `04-tts-engine.md`, ADR-0002 |
| Kokoro download timing | Lazy — first real need, never eager at launch | `04-tts-engine.md` |
| AI provider | Pluggable: Gemini / OpenAI / none — user-selected + keyed, neither is default. `ai_providers/` (base/registry/openai/null) ported verbatim from `epub-renamer`; only `gemini_provider.py` is new | ADR-0003, ADR-0014 |
| AI failure handling | Falls back to `NullProvider` per-file; never blocks the batch | `02-pipeline-stages.md` |
| MAX_FILES overflow | Excess books rejected individually at Screen 1, not silently dropped after Start | `06-safety-error-handling.md` |
| Sanitize | PowerShell→Python port; preserve all 10 original security controls, incl. Unicode whole-word regex + ReDoS timeout (needs the `regex` package); shared Template Method zip-guard base | ADR-0004 |
| Folder pickers | `tkinter.filedialog` via the Flask backend | ADR-0006 |
| Voice selection | Per book, after metadata resolved; single global default + session-local same-series default; no persisted per-series memory | `03-gui-ux-design.md`, ADR-0010 |
| Voice previews | Pre-generated once, cached, instant playback | `04-tts-engine.md` |
| Settings | `%APPDATA%\EpubAutomation\settings.json`; atomic writes; `schema_version` field with a migration/mismatch policy | ADR-0005 |
| Profanity list | Bundled default → personal copy on first run only, independent thereafter | `05-data-settings-and-logging.md` |
| Input format | `.epub` only, content-validated not just by extension | ADR-0013 |
| Cancel vs. Pause | Pause = resume later. Cancel = confirm, then keep-partial (default) or discard | `06-safety-error-handling.md` |
| Retag | Always manual, never auto-run | `02-pipeline-stages.md` |
| Audit log | One CSV, all stages, `stage` + `voice` columns | `05-data-settings-and-logging.md` |
| Batch concurrency | Audio generation serial only; CLI reserves an unused `--workers N` | ADR-0009 |
| Single-instance | Lock file with PID-based stale-lock detection — auto-clears a dead-process lock rather than blocking forever | ADR-0007 |
| Network binding | `127.0.0.1` only, fixed constant, never configurable | ADR-0008 |
| Progress reporting | Polling, not WebSockets | `03-gui-ux-design.md` |
| Terminology | No internal jargon in her-facing UI | `03-gui-ux-design.md` |
| Target platform | Windows-only v1 — confirmed, not just assumed | `00-overview-and-goals.md` |
| Packaging | PyInstaller single `.exe`, no code signing purchased | ADR-0011 |
| Packaging risk | Kokoro native-dependency (e.g. `espeak-ng`) unverified — spike in `docs/BACKLOG.md` Epic 1 | `07-packaging-deployment.md` |
| Copyleft deps | `mutagen` (GPL) + `ebooklib` (AGPL) retained, documented explicitly | ADR-0012 |
| Reuse principle | Port existing implementations by default; new code only for a real gap/fix | ADR-0014 |
| Accessibility | WCAG 2.1 AA alignment (not certified) via shared hooks (`useFocusTrap`, `useAriaLiveThrottled`); automated tests + security-guard coverage are the CI floor, manual passes are best-effort | ADR-0015 |

## Flagged open items (confirm or surface — don't silently resolve)

Full detail and history: `docs/requirements/08-open-questions-and-assumptions.md`
and `docs/design/adr/README.md`. Each is a tracked `docs/BACKLOG.md` item.

| Item | Status |
|---|---|
| Kokoro vs. Perchance output parity | Side-by-side listen needed — Backlog Epic 4 |
| CPU vs. GPU inference speed | Needs benchmarking on real hardware — Backlog Epic 4 |
| No per-series voice memory | Decided; worth a second look after real use — Backlog Epic 9 |
| Her-facing copy wording | Drafted for tone, not final — real unassisted dry-run needed — Backlog Epic 9 |
| Screen-reader tester | Being pursued, not confirmed — never claim "validated by a blind user" until it happens — Backlog Epic 9 |
| Kokoro native-dependency packaging risk | Unverified against pinned version — Backlog Epic 1 |

## Documentation & session close (once building starts)

1. Treat `docs/requirements/`, `docs/design/`, and `docs/BACKLOG.md` as
   living documents — update them when implementation reveals a gap,
   don't diverge silently. Update both sides of a requirement/ADR pair
   together.
2. Create `CODEBASE_INDEX.md` at repo root during the first build session.
3. Add new binding decisions to the "Key architectural decisions" table
   above, and a new ADR under `docs/design/adr/` if it clears the bar
   (real alternatives considered, real tradeoffs accepted).
4. Keep this file's header line current.
5. **Every new frontend screen/component must satisfy
   `03-gui-ux-design.md` §Accessibility: WCAG 2.1 AA alignment** before
   being done — real focusable controls, labels, focus management,
   `aria-live` wiring where relevant (ADR-0015).
6. **New code should use the patterns in `docs/design/PATTERNS.md`**
   rather than ad hoc structures — keeps future sessions consistent.
7. **Mark items complete in `docs/BACKLOG.md` as they're worked**, and
   add stories there when work surfaces that isn't captured yet.
