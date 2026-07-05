# epub-automation

A batch pipeline that renames, cleans, and converts EPUBs into tagged
MP3 audiobooks — accessible through two very different front doors: a
CLI for technical use, and a local web GUI designed for someone who
can't run scripts from a terminal and has real physical constraints
using a computer.

> **Status: design phase complete, no code written yet.** Everything in
> this README describes the target design, not a working build. Full
> requirement docs live in [`docs/requirements/`](docs/requirements/);
> a design-review pass produced
> [`docs/design/SYSTEM_DESIGN.md`](docs/design/SYSTEM_DESIGN.md) and
> [`docs/design/adr/`](docs/design/adr/) (one Architecture Decision
> Record per binding decision). A later, final pre-coding review —
> [`docs/design_review.md`](docs/design_review.md) — independently
> re-verified the reuse/licensing claims below against the actual
> source repos and closed a handful of gaps (schema versioning on
> `settings.json`, stale single-instance-lock recovery, and a few
> others) directly in the documents above; see that file's verdict and
> `docs/design/adr/README.md`'s "Post-review fixes" note for what
> changed and why. [`docs/design/PATTERNS.md`](docs/design/PATTERNS.md)
> then captures the concrete Python/React implementation patterns
> (Strategy, Pipeline, Repository, State Machine, and more) the actual
> build should follow, and [`docs/BACKLOG.md`](docs/BACKLOG.md)
> sequences all of it into epics/stories for the build itself. If
> you're looking at this repo before a build session has happened, the
> documentation *is* the deliverable so far.

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
  every stage and flag independently.
- **Accessible local web GUI** — built for a specific, real person: one
  with **fibromyalgia** (difficulty learning and holding multi-step
  processes in mind) and **rheumatoid arthritis in her fingers**
  (reduced fine-motor precision — small buttons, double-clicks, and
  drag-precision are all genuinely harder). Every GUI decision in this
  project is evaluated against those two constraints specifically, not
  a generic "make it friendly" goal. See
  [`docs/requirements/03-gui-ux-design.md`](docs/requirements/03-gui-ux-design.md)
  for the full screen-by-screen design.

The GUI runs as a background Flask server the browser talks to over
polling — not a desktop-window wrapper — specifically so that closing
the browser tab never kills a multi-hour audio generation job. See
[ADR-0001](docs/design/adr/0001-flask-waitress-react-over-pywebview.md).

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
| [`docs/BACKLOG.md`](docs/BACKLOG.md) | The implementation backlog — epics and stories sequencing the whole build, with risk-ordered priorities. Source of truth for *what order*. |
| [`CLAUDE.md`](CLAUDE.md) | AI-assistant development rules for this repo — also a decent quick-reference table of every key decision, if you don't want to read the full docs. |

`docs/requirements/` and `docs/design/` are kept explicitly reconciled
with each other; if you find them disagreeing, that's a bug in the
docs, not an intentional split of authority.

## Planned tech stack

| Layer | Choice |
|---|---|
| Core pipeline | Python 3.11+ |
| GUI backend | Flask, served via `waitress`, bound to `127.0.0.1` only |
| GUI frontend | React (Vite build), bundled static output — no Node/npm needed at runtime |
| Text-to-speech | `kokoro` (Kokoro-82M, local inference) |
| Packaging | PyInstaller, single `.exe` (Windows-only for v1) |

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
