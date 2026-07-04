# epub-automation — Overview & Goals

## What this project is

A combined pipeline that merges three existing standalone tools into one
program with two front doors:

1. **A CLI / advanced mode** for technical use (the author and their brother).
2. **An accessible local web GUI** for non-technical use (the author's mother),
   designed around real accessibility constraints, not just "simple UI."

The three source projects being merged:

| Project | Role | Language |
|---|---|---|
| `epub-renamer` | AI-assisted metadata enrichment + filename normalization | Python 3.11 |
| `epub-sanitize` | Profanity removal from EPUB text, repacks clean EPUB | PowerShell (to be ported to Python) |
| `epub-to-audio` | EPUB → tagged MP3 audiobook via TTS | Python 3.10 |

## Why this exists

Today these three tools are run manually, one after another, one file at a
time: rename → sanitize → drop into an input folder → convert. This project
automates that into one batch pipeline, and additionally makes the pipeline
usable by someone who can't run scripts from a terminal.

## Secondary goal: portfolio piece

This project doubles as a portfolio demonstration. Notable things worth
highlighting in that context:

- One shared pipeline engine powering two very different interfaces (CLI and
  accessible web GUI) — same tested core, two front doors. See
  `09-testing-strategy.md` for what backs this claim up: TDD discipline,
  an 80%+ coverage floor enforced in CI on both backend and frontend, and
  adversarial test cases for the security-critical guards specifically.
- Real accessibility-driven design decisions (see below), not just "big
  buttons."
- A local-first architecture: Flask + React GUI, local TTS inference, no
  cloud dependency for the core pipeline once set up.
- Migration off a fragile browser-automation TTS approach (Selenium driving
  a third-party web page) to a robust local Python TTS engine (Kokoro-82M),
  once it was discovered the third-party service was already running that
  same open-weight model client-side.
- **Honest, complete licensing documentation** (`10-licensing-and-notices.md`)
  — this project is MIT-licensed, but two bundled dependencies
  (`mutagen`, `ebooklib`) are copyleft, which affects the distributed
  `.exe` as a combined work. Documenting that clearly rather than
  glossing over it is itself part of the engineering-maturity signal
  this portfolio piece is going for.

## The accessibility persona driving GUI decisions

The GUI must be usable, unassisted, by the author's mother, who has:

- **FMS** (fibromyalgia syndrome), which for the purposes of this design
  means difficulty learning new/unfamiliar workflows and holding multi-step
  processes in mind at once.
- **Rheumatoid arthritis in her fingers**, meaning reduced fine motor
  precision — small buttons, double-clicks, drag-precision, and
  right-click/hover interactions are all harder for her than for an average
  user.

This is a *real constraint*, not a general "make it friendly" note. Every
GUI requirement in `03-gui-ux-design.md` should be evaluated against these
two constraints specifically. When in doubt, prioritize:

- Fewer decisions per screen (ideally one).
- Bigger click targets over denser layouts.
- Plain language over technical/pipeline terminology.
- Forgiving, reversible actions over efficient-but-risky ones.
- Consistency and repetition across sessions over novelty.

## Non-goals (explicitly out of scope for this version)

- Supporting ebook formats other than `.epub` (see `06-safety-error-handling.md`
  for why — none of the underlying libraries parse other formats reliably).
- **Mobile *and tablet* support, including Windows tablets.** "Desktop
  Windows only for v1" means laptop- or desktop-class hardware
  specifically — not just "not a phone." Kokoro inference is CPU/memory-
  intensive enough (see `04-tts-engine.md`'s CPU-vs-GPU benchmarking open
  item) that a multi-hour audio job is a real burden on tablet-class
  hardware: less RAM and a weaker CPU than a typical laptop, plus
  meaningful battery drain and thermal throttling from a sustained
  inference job even while plugged in. Since the packaging story
  (`07-packaging-deployment.md`) is already a Windows `.exe`, this mostly
  rules out a Windows tablet (e.g. Surface-class) running the app
  directly — phones and iPad/Android tablets were already excluded by
  the Windows-only packaging choice regardless.
- Multi-user / networked use of the GUI. It's a local, single-user tool
  bound to `localhost`.
- An auto-update mechanism for the shipped `.exe` (noted as a future
  consideration, not a v1 requirement).
- Cloning/synthesizing a specific person's voice. Kokoro is a fixed-voice
  model; voice selection is "pick from a list," not "clone a sample."
