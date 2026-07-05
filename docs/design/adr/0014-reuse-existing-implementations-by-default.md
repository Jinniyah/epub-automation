# ADR-0014: Reuse existing implementations by default; write new code only where there's a concrete reason

## Status
Accepted (revised — see "Correction" note below)

## Context
This project merges three already-working, independently-developed
tools, all public on GitHub:

- [`epub-renamer`](https://github.com/Jinniyah/epub-renamer) — MIT,
  Python 3.11+
- [`epub-sanitize`](https://github.com/Jinniyah/epub-sanitize) — no
  license file, PowerShell
- [`epub-to-audio`](https://github.com/Jinniyah/epub-to-audio) — MIT,
  Python 3.10+

Two of the three are already Python; the third is PowerShell. There was
a real choice to make about how much of each tool's existing logic to
carry forward as-is versus how much to redesign "while we're in there" —
redesigning has an obvious appeal (cleaner abstractions, a chance to fix
things), but it also discards logic that already works, is already
understood, and in some cases (the sanitize stage's security controls)
is genuinely security-critical and risky to casually rewrite.

**Correction made during this design-review pass:** an earlier version
of this ADR (and of `docs/design/SYSTEM_DESIGN.md` §7.6) listed the
`ai_providers/` pluggable registry as *new* work for epub-automation —
"the original tools had no pluggable-provider concept at all." That
claim was made from the requirements docs' description of the legacy
tools, without checking the actual repositories, which weren't public
yet at the time. Now that they are, direct inspection shows
`epub-renamer` **already has** this exact registry: `ai_providers/base.py`
(abstract `AIProvider`), `registry.py`, `openai_provider.py`, and
`null_provider.py`, plus a `MAX_FILES` cap and `DRY_RUN=true` default
already wired into its `.env` config. This is now corrected below and
in ADR-0003. The lesson generalized: claims about what a legacy tool
does or doesn't already have should be checked against the actual
source once it's available, not left as an assumption carried over from
an earlier design pass.

## Decision
Default to **porting and reusing existing logic verbatim or
near-verbatim**, across all three source tools, and write new
implementations only where there's a specific, nameable reason: a
changed constraint the old code didn't have to handle, a genuine
functional gap, or a known bug being fixed. Concretely, this shows up
as:

- **Reused verbatim:** `FILENAME_PATTERN` (`epub-renamer/renamer.py`),
  `chunk_text()` and `MAX_CHUNK_CHARS = 4,000` (`epub-to-audio/
  epub_utils.py`, confirmed as the `--max-chunk` default in that repo),
  3-tier metadata resolution, chapter extraction and `--stop-after`
  truncation, ID3 tagging, resume-by-existing-MP3 logic, every
  sanitize-stage security control (ADR-0004), the `epub-renamer` test
  suite and toolchain (`pytest`/`black`/`ruff`/`mypy --strict`), ported
  with import paths updated rather than rewritten — **and the entire
  `ai_providers/` registry** (`base.py`, `registry.py`,
  `openai_provider.py`, `null_provider.py`) plus its `MAX_FILES`/
  `DRY_RUN` safety defaults, all confirmed present in `epub-renamer`
  today (see Correction above).
- **Reused with a known, flagged caveat:** `MAX_CHUNK_CHARS = 4,000` was
  tuned for Perchance's request-size tolerance, not Kokoro's — carried
  over as the right default (reuse working logic) but explicitly flagged
  for re-validation once real Kokoro samples exist, not silently assumed
  correct just because it's inherited (ADR-0002).
- **New, for a concrete reason:** MP3 encoding parameters (the original
  tool never encoded MP3 itself — Perchance's server did, at parameters
  never controlled by this codebase); a `gemini_provider.py`
  implementation (the one provider `epub-renamer` doesn't already ship —
  it has OpenAI and Null only); the unified cross-stage audit log (the
  three original tools had no shared logging to unify — `epub-renamer`
  has its own per-tool audit CSV, but nothing spanning stages); zip-safety
  guards extended to every zip-opening stage, not just sanitize
  (previously only implicit in one script's scope).
- **New, as a bug fix during the port, not a redesign:** the retag
  stage's containing-folder rename. The original `retag.py` renames
  files but never the folder itself, which would cause a future retag
  run (reading `parse_folder_metadata()` from that stale folder name) to
  silently revert to old values. Found by reading the actual source
  during the port, fixed as part of it — a fix, not scope creep.

## Consequences
- Minimizes the amount of genuinely new, unverified logic in the
  system — most of the pipeline's correctness properties (metadata
  resolution priority, chapter extraction, security guards, and now
  confirmed, the entire AI-provider plumbing) are inherited from
  implementations that already exist and have already been exercised,
  not invented fresh for this project.
- Concentrates the real porting risk in one place: `epub-sanitize`
  (PowerShell → Python) is the only stage requiring a full language
  port, and even there, the decision is to preserve every control
  exactly (ADR-0004) rather than redesign them, which is itself an
  instance of this same reuse-by-default principle.
- Makes "what's actually new here" an explicit, answerable question
  (see the table in `docs/design/SYSTEM_DESIGN.md` §7.6) rather than an
  implicit blur between "ported" and "rewritten" — this matters for
  review, since new code deserves more scrutiny than ported code with a
  known track record. The correction in this ADR is itself an example
  of why that distinction needs to be checked against real source, not
  just asserted.
- Creates an ongoing obligation to keep inherited-but-caveated constants
  (like `MAX_CHUNK_CHARS`) visibly flagged rather than letting "it's
  always been this way" quietly become the justification — reuse is a
  default, not a reason to stop questioning a specific inherited value
  once better data exists.
- Test coverage strategy follows the same principle
  (`docs/requirements/09-testing-strategy.md`): existing `epub-renamer`
  tests are ported, not rewritten from scratch, while `epub-sanitize`
  and `epub-to-audio` — which have no or minimal existing automated
  tests — get new test suites written test-first, since there's nothing
  to reuse there.

## Alternatives Considered
- **Rewrite each stage's core logic fresh, using the old tools only as a
  functional reference** — rejected: discards already-working,
  already-battle-tested logic (especially the sanitize stage's security
  controls, and now confirmed, the AI-provider registry) for the sake of
  cleaner-looking code, introducing risk (subtly reintroduced bugs in
  security-critical paths) for a benefit (code aesthetics) that doesn't
  justify it at this project's scale.
- **Reuse everything unconditionally, including inherited constants that
  are known to be mistuned for the new context** — rejected:
  `MAX_CHUNK_CHARS` is the clear counter-example — reusing it as a
  starting point is right, but reusing it *silently*, without flagging
  it as Perchance-tuned and pending re-validation, would let a stale
  assumption masquerade as a validated one.
- **Leave the earlier "ai_providers/ is new" claim uncorrected since it
  doesn't change the end-state architecture** — rejected: even though
  the resulting pipeline design is the same either way, accurately
  crediting what's ported versus newly written affects review priority
  (new code warrants more scrutiny than a port) and is a small, cheap
  fix now that the source is available to check against.

## References
- [`epub-renamer` repository](https://github.com/Jinniyah/epub-renamer)
  — `ai_providers/`, `renamer.py`, `state_manager.py`, `audit_logger.py`,
  `tests/`, `DESIGN_DECISIONS.md`, `THREAT_MODEL.md`
- [`epub-to-audio` repository](https://github.com/Jinniyah/epub-to-audio)
  — `epub_utils.py`, `epub2audio.py`, `retag.py`
- [`epub-sanitize` repository](https://github.com/Jinniyah/epub-sanitize)
  — `PS_Run-CleanUpEpub.ps1`, `profanity.txt`
- `docs/design/SYSTEM_DESIGN.md` §1.1 Source Projects, §7.6 Reuse as a
  Design Principle
- `docs/requirements/02-pipeline-stages.md` (Stage 1 FILENAME_PATTERN,
  Stage 3 chunk_text/MAX_CHUNK_CHARS, Stage 4 retag folder-rename fix)
- `docs/requirements/04-tts-engine.md` §What stays exactly the same,
  §Open item for review
- `docs/requirements/09-testing-strategy.md` §Backend: reuse the
  existing toolchain, don't invent a new one
- ADR-0002 (Kokoro TTS — what stays the same vs. what's new)
- ADR-0003 (AI provider registry — corrected origin, see above)
- ADR-0004 (sanitize port — controls preserved exactly)
- ADR-0009 (serial audio + reserved `--workers` — reusing the engine's
  design rather than redesigning it for a feature not yet needed)
