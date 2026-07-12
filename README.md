# epub-automation

A batch pipeline that renames, cleans, and converts EPUBs into tagged
MP3 audiobooks — accessible through two very different front doors: a
CLI for technical use, and a local web GUI designed for someone who
can't run scripts from a terminal and has real physical constraints
using a computer.

> **Status: the shared pipeline core, both API surfaces, and the
> accessible GUI's React frontend are all built and tested — one real
> gap stands between that and a single-command working GUI.** Epics
> 0–8 are complete: every pipeline stage, the CLI front door, the
> Flask/JSON backend, and every screen in
> [`03-gui-ux-design.md`](docs/requirements/03-gui-ux-design.md) are
> real, working, tested code — 413 backend tests (~96% coverage) + 331
> frontend tests (~85-90% coverage), `black`/`ruff`/`mypy --strict` +
> `eslint`/`tsc` all clean, all CI-enforced, and the full flow
> (Screen 1 → identification → voice picker → generation → review) has
> been live-tested end to end against the real backend and the real
> Kokoro TTS engine, not just mocks. **The one thing not yet wired up:
> Flask doesn't yet serve the built frontend** — dev mode (Vite's own
> dev server + a separately-running backend, two processes) shows the
> real GUI today, but `python launcher.py` alone still opens a browser
> to a `404`, since nothing has told Flask how to serve `frontend/dist/`
> yet. That's genuinely packaging-shaped work (Epic 10 — see
> `docs/BACKLOG.md`), not a frontend gap. The CLI is fully usable right
> now regardless — see [Getting started](#getting-started) below. Full
> requirement docs live in [`docs/requirements/`](docs/requirements/);
> [`docs/design/SYSTEM_DESIGN.md`](docs/design/SYSTEM_DESIGN.md) and
> [`docs/design/adr/`](docs/design/adr/) (one Architecture Decision
> Record per binding decision, several refined post-implementation as
> real gaps were found — see that folder's `README.md`) capture *why*
> it's built this way, [`docs/design/PATTERNS.md`](docs/design/PATTERNS.md)
> the concrete implementation patterns it follows, and
> [`docs/BACKLOG.md`](docs/BACKLOG.md) the epic-by-epic build order —
> [`CODEBASE_INDEX.md`](CODEBASE_INDEX.md) is the up-to-date file map of
> what's real versus still a placeholder.

## What it does

Three previously separate, manually-run tools become one pipeline with
a shared, tested core:

```
your books  ──[rename]──▶  ──[sanitize]──▶  ──[text-to-speech]──▶  tagged audiobook
                                                       │
                                              ──[retag]  (manual, on demand)
```

1. **Rename** — normalizes messy filenames using EPUB metadata plus
   optional AI enrichment (title/author/series inference) when the
   metadata alone isn't enough.
2. **Sanitize** — removes profanity from the EPUB's text and repacks a
   clean copy, using a user-editable word list.
3. **Audio** — converts the cleaned EPUB into a chaptered, ID3-tagged
   MP3 audiobook using a local, fully-offline text-to-speech engine.
4. **Retag** — a manual, on-demand fixer for correcting audiobook
   metadata after the fact, without regenerating the audio.

Both front doors — the CLI and the GUI — call into the exact same
pipeline engine. Neither contains its own copy of the pipeline logic.

## Two front doors, one real reason for each

- **CLI / advanced mode** — for technical use, scriptable, exposes
  every stage and flag independently. **Working today** — see
  [Getting started](#getting-started).
- **Accessible local web GUI** — built for a specific, real person: one
  with **fibromyalgia** (difficulty learning and holding multi-step
  processes in mind) and **rheumatoid arthritis in her fingers**
  (reduced fine-motor precision — small buttons, double-clicks, and
  drag-precision are all genuinely harder). Every GUI decision in this
  project is evaluated against those two constraints specifically, not
  a generic "make it friendly" goal. See
  [`docs/requirements/03-gui-ux-design.md`](docs/requirements/03-gui-ux-design.md)
  for the full screen-by-screen design. **Built and tested** — every
  screen, the backend API it calls
  ([full reference](docs/requirements/01-architecture.md#full-api-route-reference-epic-6-backendapppy)),
  and the wiring between them. **Runnable in dev mode today** (see
  [Getting started](#getting-started)); the single-command production
  path (`python launcher.py` alone) is blocked on Flask gaining a route
  to serve the built frontend, tracked as Epic 10 packaging work.

The GUI runs as a background Flask server the browser talks to over
polling — not a desktop-window wrapper — specifically so that closing
the browser tab never kills a multi-hour audio generation job. See
[ADR-0001](docs/design/adr/0001-flask-waitress-react-over-pywebview.md).

## Getting started

Windows only, Python 3.11+. This sets up the CLI — the one front door
that's actually usable today (see the status note at the top of this
README).

```powershell
git clone https://github.com/Jinniyah/epub-automation.git
cd epub-automation
make venv
.\.venv\Scripts\Activate.ps1
make install
```

The CLI reads `books_folder`/`output_folder` from
`%APPDATA%\EpubAutomation\settings.json` (created empty on first run —
see [`05-data-settings-and-logging.md`](docs/requirements/05-data-settings-and-logging.md)).
There's no GUI yet to set these through, so either hand-edit that file,
or just leave them unset — both default to the current directory, so
running a command from a folder full of `.epub` files works too:

```powershell
python main.py rename      # normalize filenames using EPUB metadata
python main.py sanitize    # remove profanity, using the bundled word list
python main.py audio       # generate a chaptered, tagged MP3 audiobook
python main.py all         # rename -> sanitize -> audio in one pass
python main.py retag <audiobook-folder> --title "..." --author-last "..."
```

`ai_provider`/`ai_api_key` (for AI-assisted metadata enrichment) live in
the same `settings.json`; `ai_provider` defaults to `"none"`, which
still works fine using each EPUB's own embedded metadata.

Common development commands (see the [`Makefile`](Makefile) for the
full list):

```powershell
make test      # pytest, fast (excludes slow/real-Kokoro tests)
make coverage  # pytest with the 80%+ coverage gate CI enforces
make check     # lint + typecheck + coverage -- what CI actually runs
make format    # black + ruff --fix
```

### Running the GUI (dev mode)

Two processes, in separate terminals — Flask doesn't yet serve the
built frontend directly (see the status note at the top of this
README; that's Epic 10 packaging work):

```powershell
# Terminal 1 -- backend, fixed dev port so Vite's proxy can find it
python -c "from waitress import serve; from backend.app import create_app; serve(create_app(), host='127.0.0.1', port=5000)"

# Terminal 2 -- frontend
cd frontend
npm install
npm run dev
```

Then open the URL Vite prints (`http://localhost:5173`). `python
launcher.py` alone (no `frontend` terminal) starts the same backend on
a dynamically-assigned port and opens a browser tab to it, but that tab
will 404 today — it's built for the eventual single-origin production
path, not dev mode.

## Accessibility beyond the primary persona: WCAG 2.1 AA alignment

An EPUB-to-audiobook tool that already insists on plain language and
large, unambiguous controls is most of the way toward being genuinely
useful to two more groups it wasn't originally scoped for: people who
use a screen reader (blindness/low vision) and dyslexic readers. This
GUI is additionally designed to **align with WCAG 2.1 Level AA** for
both — real keyboard operability, ARIA live regions for status updates,
semantic HTML and labeled form controls, color-contrast minimums, and
dyslexia-friendly typography.

**Said plainly: "aligned," not "certified."** There's no formal
third-party audit here. A dyslexic tester is lined up to actually try
the app; a screen-reader tester is being pursued but not yet confirmed.
Until that testing happens, the screen-reader side of this is described
as *designed and tested against WCAG 2.1 AA criteria* — not *validated
by a blind user*. See
[ADR-0015](docs/design/adr/0015-wcag-aa-alignment-broadened-accessibility-scope.md)
for the full reasoning (including the pros/cons weighed before deciding
to take this on), and
[`docs/requirements/03-gui-ux-design.md`](docs/requirements/03-gui-ux-design.md#accessibility-wcag-21-aa-alignment-secondary-target-audience)
for the complete requirement set.

## Built on three existing projects, not from scratch

This project merges three already-working, independently-developed
repositories, all public on GitHub:

| Project | License | Role |
|---|---|---|
| [`epub-renamer`](https://github.com/Jinniyah/epub-renamer) | MIT | Filename normalization, AI-assisted metadata enrichment |
| [`epub-sanitize`](https://github.com/Jinniyah/epub-sanitize) | — (author's own work) | Profanity removal, EPUB repack |
| [`epub-to-audio`](https://github.com/Jinniyah/epub-to-audio) | MIT | EPUB → audiobook conversion, retagging |

**A stated design principle, not just a habit:** reuse each source
project's existing, working implementation by default, and write new
code only where there's a concrete reason — a changed constraint, a
real functional gap, or a known bug fix. In practice, that means more
of this project is a *direct port* than a first glance suggests: a
pluggable AI-provider registry, a chunking algorithm, an entire test
toolchain, and every security control in the sanitize stage all carry
over from the source repos largely as-is. Only the sanitize stage needs
a full language port (PowerShell → Python), and even that preserves
every security control exactly rather than redesigning it. The full
accounting of what's reused verbatim versus genuinely new is in
[ADR-0014](docs/design/adr/0014-reuse-existing-implementations-by-default.md) —
the one large, honest exception is the WCAG accessibility layer above,
which is entirely new since none of the source tools had a GUI at all.

## Local-first, no required cloud dependency

Once set up, the core pipeline — sanitize and audio conversion — runs
entirely offline. Text-to-speech uses a local model
([Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M), Apache 2.0),
called directly in Python rather than driving a third-party website
through a browser, which is how the original `epub-to-audio` tool
worked. See [ADR-0002](docs/design/adr/0002-local-kokoro-tts-over-browser-automation.md)
for why that migration happened.

AI-assisted metadata enrichment is the one genuinely optional,
network-dependent feature — pluggable per install (Gemini free tier or
OpenAI's paid API, or none at all), with no vendor or API key hardcoded
into the app and neither provider treated as more "default" than the
other. See [ADR-0003](docs/design/adr/0003-pluggable-user-keyed-ai-provider.md).

## Documentation

| Path | What it is |
|---|---|
| [`docs/requirements/`](docs/requirements/) | The full functional design — what the system does, screen by screen and stage by stage. Source of truth for *what*. |
| [`docs/design/SYSTEM_DESIGN.md`](docs/design/SYSTEM_DESIGN.md) | A synthesized, high-level architecture doc — how the pieces fit together and why. |
| [`docs/design/adr/`](docs/design/adr/) | One Architecture Decision Record per binding decision — the alternatives considered and the tradeoffs accepted. Source of truth for *why*. |
| [`docs/design/PATTERNS.md`](docs/design/PATTERNS.md) | The concrete Python/React design patterns (Strategy, Pipeline, Repository, State Machine, and more) implementation should follow. Source of truth for *how*. |
| [`docs/design_review.md`](docs/design_review.md) | A final pre-coding design review — independent verification of the reuse/licensing claims above against the actual source repos, plus a GO/NO-GO verdict and the fixes it produced. |
| [`docs/BACKLOG.md`](docs/BACKLOG.md) | The implementation backlog — epics and stories sequencing the whole build, with risk-ordered priorities. Source of truth for *what order*, and for what's actually done vs. not yet started. |
| [`CODEBASE_INDEX.md`](CODEBASE_INDEX.md) | The file map — every real module, what it does, and which epic built it, kept current as placeholders become real code. Start here if you want to know "is *this* actually implemented." |
| [`CLAUDE.md`](CLAUDE.md) | AI-assistant development rules for this repo — also a decent quick-reference table of every key decision, if you don't want to read the full docs. |

`docs/requirements/` and `docs/design/` are kept explicitly reconciled
with each other; if you find them disagreeing, that's a bug in the
docs, not an intentional split of authority.

## Tech stack

| Layer | Choice | Status |
|---|---|---|
| Core pipeline | Python 3.11+ | Built |
| GUI backend | Flask, served via `waitress`, bound to `127.0.0.1` only | Built |
| GUI frontend | React 19 + TypeScript (Vite build), bundled static output — no Node/npm needed at runtime | Built, dev-mode runnable; Flask-serves-`dist/` wiring is Epic 10 |
| Text-to-speech | `kokoro` (Kokoro-82M, local inference) | Built |
| Packaging | PyInstaller, single `.exe` (Windows-only for v1) | Packaging spike verified working; full build pipeline is Epic 10 |
| Testing | Backend: `pytest` + `pytest-cov` (80%+ floor), `black`, `ruff`, `mypy --strict`. Frontend: Vitest + React Testing Library + `vitest-axe` (80%+ floor), `eslint` incl. `eslint-plugin-jsx-a11y`, `tsc`. Both CI-enforced. | Built, 413 backend + 331 frontend tests passing |

## License

This project's own code is MIT-licensed. That said, **the distributed
`.exe` bundles two copyleft dependencies** (`mutagen`, GPL-2.0-or-later;
`ebooklib`, AGPL-3.0-or-later) which affect the combined distributed
artifact's licensing — this is documented in full, not glossed over, in
[`docs/requirements/10-licensing-and-notices.md`](docs/requirements/10-licensing-and-notices.md)
and [ADR-0012](docs/design/adr/0012-retain-copyleft-dependencies.md).
If you're planning to redistribute this beyond personal/family use,
read that document first.

## Privacy note

The GUI's error-reporting feature ("Copy details for support") bundles
recent book titles and cleanup details to help diagnose problems. It
never includes API keys or other credentials. Whoever you send that
file to will be able to see what books you've been converting.

## Why this project exists

Two reasons, both real:

1. A family member needed this — audiobook conversion, entirely
   self-serve, for someone who can't be handed a script and a terminal.
2. It's also a portfolio piece: one shared, tested pipeline engine
   behind two genuinely different front doors, real accessibility-driven
   design decisions across multiple distinct kinds of need (not just
   "big buttons"), and documentation (licensing, testing, architecture,
   decision records) treated as a deliverable in its own right rather
   than an afterthought.
