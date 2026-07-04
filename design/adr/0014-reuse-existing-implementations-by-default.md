# ADR-0014: Reuse existing implementations by default; write new code only where there's a concrete reason

## Status
Accepted

## Context
This project merges three already-working, independently-developed
tools (`epub-renamer`, `epub-sanitize`, `epub-to-audio`). Two of the
three are already Python; the third is PowerShell. There was a real
choice to make about how much of each tool's existing logic to carry
forward as-is versus how much to redesign "while we're in there" —
redesigning has an obvious appeal (cleaner abstractions, a chance to fix
things), but it also discards logic that already works, is already
understood, and in some cases (the sanitize stage's security controls)
is genuinely security-critical and risky to casually rewrite.

## Decision
Default to **porting and reusing existing logic verbatim or
near-verbatim**, across all three source tools, and write new
implementations only where there's a specific, nameable reason: a
changed constraint the old code didn't have to handle, a genuine
functional gap, or a known bug being fixed. Concretely, this shows up
as:

- **Reused verbatim:** `FILENAME_PATTERN` (`epub-renamer`), `chunk_text()`
  and `MAX_CHUNK_CHARS` (`epub-to-audio`), 3-tier metadata resolution,
  chapter extraction and `--stop-after` truncation, ID3 tagging,
  resume-by-existing-MP3 logic, every sanitize-stage security control
  (ADR-0004), and the `epub-renamer` test suite and toolchain
  (`pytest`/`black`/`ruff`/`mypy --strict`), ported with import paths
  updated rather than rewritten.
- **Reused with a known, flagged caveat:** `MAX_CHUNK_CHARS = 4,000` was
  tuned for Perchance's request-size tolerance, not Kokoro's — carried
  over as the right default (reuse working logic) but explicitly flagged
  for re-validation once real Kokoro samples exist, not silently assumed
  correct just because it's inherited (ADR-0002).
- **New, for a concrete reason:** MP3 encoding parameters (the original
  tool never encoded MP3 itself — Perchance's server did, at parameters
  never controlled by this codebase); the `ai_providers/` pluggable
  registry (the original tools had no multi-provider concept at all);
  the unified cross-stage audit log (the three original tools had no
  shared logging to unify); zip-safety guards extended to every
  zip-opening stage, not just sanitize (previously only implicit in one
  script's scope).
- **New, as a bug fix during the port, not a redesign:** the retag
  stage's containing-folder rename. The original `retag.py` renames
  files but never the folder itself, which would cause a future retag
  run (reading `parse_folder_metadata()` from that stale folder name) to
  silently revert to old values. Found by reading the actual source
  during the port, fixed as part of it — a fix, not scope creep.

## Consequences
- Minimizes the amount of genuinely new, unverified logic in the
  system — most of the pipeline's correctness properties (metadata
  resolution priority, chapter extraction, security guards) are
  inherited from implementations that already exist and have already
  been exercised, not invented fresh for this project.
- Concentrates the real porting risk in one place: `epub-sanitize`
  (PowerShell → Python) is the only stage requiring a full language
  port, and even there, the decision is to preserve every control
  exactly (ADR-0004) rather than redesign them, which is itself an
  instance of this same reuse-by-default principle.
- Makes "what's actually new here" an explicit, answerable question
  (see the table in `design/SYSTEM_DESIGN.md` §7.6) rather than an
  implicit blur between "ported" and "rewritten" — this matters for
  review, since new code deserves more scrutiny than ported code with a
  known track record.
- Creates an ongoing obligation to keep inherited-but-caveated constants
  (like `MAX_CHUNK_CHARS`) visibly flagged rather than letting "it's
  always been this way" quietly become the justification — reuse is a
  default, not a reason to stop questioning a specific inherited value
  once better data exists.
- Test coverage strategy follows the same principle
  (`requirements/09-testing-strategy.md`): existing `epub-renamer` tests
  are ported, not rewritten from scratch, while `epub-sanitize` and
  `epub-to-audio` — which have no or minimal existing automated tests —
  get new test suites written test-first, since there's nothing to
  reuse there.

## Alternatives Considered
- **Rewrite each stage's core logic fresh, using the old tools only as a
  functional reference** — rejected: discards already-working,
  already-battle-tested logic (especially the sanitize stage's security
  controls) for the sake of cleaner-looking code, introducing risk
  (subtly reintroduced bugs in security-critical paths) for a benefit
  (code aesthetics) that doesn't justify it at this project's scale.
- **Reuse everything unconditionally, including inherited constants that
  are known to be mistuned for the new context** — rejected:
  `MAX_CHUNK_CHARS` is the clear counter-example — reusing it as a
  starting point is right, but reusing it *silently*, without flagging
  it as Perchance-tuned and pending re-validation, would let a stale
  assumption masquerade as a validated one.

## References
- `design/SYSTEM_DESIGN.md` §7.6 Reuse as a Design Principle
- `requirements/02-pipeline-stages.md` (Stage 1 FILENAME_PATTERN, Stage 3
  chunk_text/MAX_CHUNK_CHARS, Stage 4 retag folder-rename fix)
- `requirements/04-tts-engine.md` §What stays exactly the same, §Open
  item for review
- `requirements/09-testing-strategy.md` §Backend: reuse the existing
  toolchain, don't invent a new one
- ADR-0002 (Kokoro TTS — what stays the same vs. what's new)
- ADR-0004 (sanitize port — controls preserved exactly)
- ADR-0009 (serial audio + reserved `--workers` — reusing the engine's
  design rather than redesigning it for a feature not yet needed)
