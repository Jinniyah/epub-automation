# epub-automation — Overview & Goals

## What this project is

A combined pipeline that merges three existing standalone tools into one
program with two front doors:

1. **A CLI / advanced mode** for technical use (the author and their brother).
2. **An accessible local web GUI** for non-technical use (the author's mother),
   designed around real accessibility constraints, not just "simple UI."

The three source projects being merged (all public on GitHub):

| Project | Repository | Role | Language |
|---|---|---|---|
| `epub-renamer` | [github.com/Jinniyah/epub-renamer](https://github.com/Jinniyah/epub-renamer) | AI-assisted metadata enrichment + filename normalization | Python 3.11 |
| `epub-sanitize` | [github.com/Jinniyah/epub-sanitize](https://github.com/Jinniyah/epub-sanitize) | Profanity removal from EPUB text, repacks clean EPUB | PowerShell (to be ported to Python) |
| `epub-to-audio` | [github.com/Jinniyah/epub-to-audio](https://github.com/Jinniyah/epub-to-audio) | EPUB → tagged MP3 audiobook via TTS | Python 3.10 |

These aren't just prior art to reference — see `01-architecture.md` and
`../design/adr/0014-reuse-existing-implementations-by-default.md` for how
much of each is carried into this project directly (verbatim regexes,
an already-existing pluggable AI-provider registry, an entire test
toolchain) versus genuinely rebuilt. Treating "port what already works"
as the default, not the exception, is itself one of this project's
stated design principles (see §Secondary goal: portfolio piece below).

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
- Real accessibility-driven design decisions across **two distinct kinds
  of accessibility need** (see §The accessibility targets below), not
  just "big buttons."
- A local-first architecture: Flask + React GUI, local TTS inference, no
  cloud dependency for the core pipeline once set up.
- Migration off a fragile browser-automation TTS approach (Selenium driving
  a third-party web page) to a robust local Python TTS engine (Kokoro-82M),
  once it was discovered the third-party service was already running that
  same open-weight model client-side.
- **Deliberate reuse over rewriting.** Where an existing implementation
  from one of the three source projects above already works — a regex,
  a chunking algorithm, an entire AI-provider abstraction, a test
  suite — it's ported as-is, and new code is written only where there's
  a concrete reason (a changed constraint, a real gap, or a known bug
  fix). Treating this as a first-class, explicitly documented principle
  — not an implicit habit — is itself part of what this portfolio piece
  demonstrates; see `../design/adr/0014-reuse-existing-implementations-by-
  default.md` for the full accounting of what's reused verbatim versus
  genuinely new, and `../design/SYSTEM_DESIGN.md` §1.1/§7.6 for the
  synthesis.
- **Honest, complete licensing documentation** (`10-licensing-and-notices.md`)
  — this project is MIT-licensed, but two bundled dependencies
  (`mutagen`, `ebooklib`) are copyleft, which affects the distributed
  `.exe` as a combined work. Documenting that clearly rather than
  glossing over it is itself part of the engineering-maturity signal
  this portfolio piece is going for.
- **The same honesty applies to the accessibility claims below** — the
  broader WCAG 2.1 AA alignment (screen readers, dyslexia) is described
  as *aligned*, not *certified*, and the docs say plainly what has and
  hasn't actually been verified by a real person. See
  `../design/adr/0015-wcag-aa-alignment-broadened-accessibility-scope.md`
  for the full reasoning, including why this was a deliberate scope
  decision rather than an assumed "of course we should."

## The accessibility targets

This project has **one real, validated persona** and **one broader,
alignment-level target** layered on top of it. They're deliberately kept
distinct rather than blurred together, because the confidence behind each
is different.

### The primary persona (real, validated with an actual unassisted dry run)

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

### The broadened target: WCAG 2.1 AA alignment (screen readers, dyslexia)

Added during a later design-review pass, on the observation that a tool
which already converts books to audio, and already insists on plain
language and big, unambiguous controls, is most of the way toward being
genuinely useful to two more groups it wasn't originally scoped for:
people who use a screen reader (blindness/low vision) and dyslexic
readers.

This is treated as a **second, explicitly separate target**, not folded
into the primary persona above, for an important reason: it isn't
validated by watching one specific real person use the app the way the
primary persona is. It's stated as an honest alignment goal — see
`03-gui-ux-design.md` §Accessibility: WCAG 2.1 AA alignment for the full
cross-cutting requirements (keyboard operability, ARIA live regions,
color contrast, focus management, semantic HTML, dyslexia-friendly
typography), and `09-testing-strategy.md` §Accessibility testing for how
it actually gets checked — automated linting plus real manual testing
where testers are available, not just internal review.

**Testers identified for this pass:** a dyslexic reader is available to
test directly. A screen-reader tester is being pursued through a contact
who works professionally with people with disabilities — not yet
confirmed as of this writing. Until a real screen-reader user has
actually tried the app, the screen-reader side of this alignment should
be described as *designed and tested against WCAG 2.1 AA criteria*, not
as *validated by a blind user*, even internally — see
`08-open-questions-and-assumptions.md` for this tracked as an open item.

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
- **A certified WCAG conformance claim, or support for paid/legacy
  assistive technology (e.g. JAWS).** The WCAG 2.1 AA work above is an
  alignment target, tested against Windows Narrator and the free NVDA
  screen reader — not a formal audit, and not scoped to every possible
  assistive technology.
