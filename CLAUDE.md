# CLAUDE.md — AI Development Rules for epub-automation
# Last updated: 2026-07-04 — Design phase complete, no code written yet. Full requirement docs in `requirements/`, pending a design-review pass in a separate chat before build starts.

---

## Startup protocol

1. **No code exists yet.** This repo currently contains only `requirements/` (9
   numbered design docs + README + REVIEW_PROMPT). Before writing any code,
   read `requirements/README.md`, then the numbered docs in order.
2. Check `requirements/08-open-questions-and-assumptions.md` first — several
   items there are unresolved on purpose, pending a review pass. Don't build
   against an assumption listed there without either confirming it with the
   user or flagging that you're doing so.
3. If a design-review pass has since happened (look for review notes or
   updated requirement docs with a later "last reviewed" date), treat the
   reviewed/updated docs as current over anything summarized in this file —
   this file is a snapshot, the `requirements/` docs are the source of truth.
4. Once real code exists, this file should gain a `CODEBASE_INDEX.md`
   companion (file map, migration table, etc.) the same way sibling projects
   in this repos folder do — create it during the first build session rather
   than retrofitting it later.

## Project summary (see `requirements/00-overview-and-goals.md` for full detail)

Combines three existing standalone tools — `epub-renamer`, `epub-sanitize`,
`epub-to-audio` — into one batch pipeline with two front doors: a CLI/advanced
mode, and an accessible local web GUI built for a specific, real accessibility
persona (reduced fine-motor precision from RA; difficulty learning/holding
new multi-step processes in mind, from FMS). Also a portfolio piece.

## Environment

- Windows, PowerShell. Backslash paths. `;` not `&&` for chaining, once shell
  commands are relevant.
- Python 3.11+ for the pipeline/backend. Node/Vite for the React frontend —
  **build-time only**, never a runtime dependency on the end user's machine
  (see `requirements/07-packaging-deployment.md`).
- Target ships as a single PyInstaller `.exe` for a non-technical end user —
  do not introduce anything at build time that assumes Python, Node, or a
  terminal are available on the *target* machine.

## Filesystem rules (carried over from this environment's known quirks — assume these apply here too until proven otherwise)

- **Never use `filesystem:edit_file`** — on this Windows/CRLF setup it has
  silently failed on sibling projects (reports success, shows a valid diff,
  file on disk unchanged). Safe workflow, every file type, no exceptions:
  1. `filesystem:read_text_file` the FULL file
  2. Edit in memory
  3. `filesystem:write_file` the FULL file back
  Writing back a partial file silently truncates the rest.
- **No delete operation** — only `move_file`. Stage removed files in a
  `_removed/` folder at repo root; let the user `git rm` at a natural
  checkpoint.
- New files: `filesystem:write_file` only. Never a sandbox-only file-creation
  tool — that writes to a container, not this repo.
- `view_range` / `head`/`tail` on read tools can be unreliable for pinpointing
  a mid-file location — prefer a full read when precision matters.

## Paths (once scaffolded — see `requirements/01-architecture.md` for full structure)

| Root | Path |
|---|---|
| Repo root | `C:\Users\jinni\source\repos\epub-automation\` |
| Requirements (current source of truth) | `C:\Users\jinni\source\repos\epub-automation\requirements\` |
| Pipeline core (planned) | `...\epub-automation\pipeline\` |
| Flask backend (planned) | `...\epub-automation\backend\` |
| React frontend (planned) | `...\epub-automation\frontend\` |
| Library staging folders (planned) | `...\epub-automation\Library\00-Incoming` → `01-Renamed` → `02-Sanitized` → `03-Audio` |

## Key architectural decisions

| Decision | Rule | Rationale (see doc) |
|---|---|---|
| GUI transport | Flask (served via `waitress`, not the dev server) + React (Vite build, bundled static) | `01-architecture.md` |
| GUI process model | Background launcher opens default browser to a locally-running Flask server; **not** pywebview | Closing the tab must not kill a multi-hour audio job — `01-architecture.md` |
| TTS engine | Local `kokoro` Python package (Kokoro-82M) — **no browser, no Selenium** | Perchance's browser TTS is this same model; direct call removes an entire fragile subsystem — `04-tts-engine.md` |
| AI metadata enrichment | Google Gemini API, **free tier only** (Flash-Lite); never enable billing on that project | Zero cost at expected volume; enabling billing silently removes the free tier — `01-architecture.md`, `08-open-questions-and-assumptions.md` |
| AI failure handling | Fall back to `NullProvider` (EPUB metadata passthrough) per-file on any AI error/rate-limit | Never block a batch on one file's API call — `02-pipeline-stages.md` |
| Sanitize implementation | Ported from PowerShell to Python; **must preserve every security control** (path traversal on extract + repack, zip-bomb cap, XXE prevention, profanity-list size cap) | `02-pipeline-stages.md` |
| Native folder pickers | `tkinter.filedialog`, invoked from the Flask backend, result handed to the React page | Browsers can't open native OS pickers or read arbitrary paths directly — `01-architecture.md` |
| Voice selection timing | **Per book, after that book's metadata is resolved** — never at batch-start | A book's genre/identity isn't knowable until after renaming — `03-gui-ux-design.md` |
| Voice selection UI (multi-book) | One table, one row per book, "Change Voice" opens the full picker overlay | `03-gui-ux-design.md` |
| Voice default | Single global "last used voice" suggestion only — **no per-series/per-author memory** | Deliberately simplified; audit log is the fallback lookup — `03-gui-ux-design.md`, `05-data-settings-and-logging.md` |
| Voice previews | Pre-generated once at first-run setup, cached, played back instantly — never regenerated per click | `04-tts-engine.md` |
| Settings location | `%APPDATA%\EpubAutomation\settings.json` — **not** inside the install location | Must survive app updates and stay writable regardless of install location — `05-data-settings-and-logging.md` |
| Profanity list | Bundled default copied into her personal settings on **first run only**, then fully independent | App updates must not silently overwrite her edits, and her edits must not affect the bundled default — `05-data-settings-and-logging.md` |
| Input format | **`.epub` only** — validate real zip contents, not just the extension; reject other types individually without failing the batch | None of the underlying libraries reliably parse other formats — `06-safety-error-handling.md` |
| Cancel vs. Pause | Two distinct actions. Pause = resume later, no cleanup. Cancel = confirm first, then choose keep-partial (default) vs. discard for that book only | `06-safety-error-handling.md` |
| Retag stage | **Always manual**, never auto-run in a batch — triggered via a plain-language "does this look right?" prompt or run standalone later | `02-pipeline-stages.md`, `03-gui-ux-design.md` |
| Audit log | One CSV across all stages (not per-stage reports), with a `stage` column and a `voice` column; doubles as the mother's own lookup tool for past choices | `05-data-settings-and-logging.md` |
| Batch concurrency | Audio generation is **one book at a time**, never parallel | Resource contention + honest progress reporting — `02-pipeline-stages.md` |
| Single-instance | Lock file; a second launch opens a new tab to the existing server instead of starting a second instance | `01-architecture.md`, `06-safety-error-handling.md` |
| Progress reporting | Simple polling from React, not WebSockets | `03-gui-ux-design.md` |
| Terminology | Her-facing UI never uses internal names ("stage," "sanitize," "AI provider," "retag," etc.) — see the mapping table in `03-gui-ux-design.md` | Accessibility persona — `00-overview-and-goals.md` |

## Flagged open items (do not silently resolve these — confirm or surface them)

See `requirements/08-open-questions-and-assumptions.md` for full detail. In short:

| Item | Status |
|---|---|
| Retag chapter-title derivation (filename-suffix-only vs. pulling real EPUB headings) | Undecided |
| Kokoro vs. original Perchance output — quality/pacing parity | Needs a side-by-side listen before fully retiring the old approach conceptually |
| CPU vs. GPU inference speed on the actual target machine | Needs benchmarking, not assumed |
| Gemini free-tier data-use trade-off | Assumed acceptable, not yet explicitly confirmed by the user |
| Windows-only v1 scope | Assumed, not yet explicitly confirmed |
| No per-series voice memory | Decided, but flagged as worth a second look on reflection |
| Exact wording of all her-facing copy | Drafted for tone, not final — needs a fresh read-through |

## Documentation & session close (once building starts)

1. Treat `requirements/` as living documents during build — if implementation
   reveals a requirement doc was wrong or incomplete, **update the doc**,
   don't just diverge from it silently.
2. Create `CODEBASE_INDEX.md` at repo root during the first build session
   (file map + any migration/schema table), matching the pattern used in
   sibling projects in this repos folder.
3. Update the "Key architectural decisions" table above whenever a new
   binding decision gets made during implementation that isn't already
   covered by a requirement doc.
4. Keep this file's header timestamp/summary line current, same convention
   as sibling projects.
