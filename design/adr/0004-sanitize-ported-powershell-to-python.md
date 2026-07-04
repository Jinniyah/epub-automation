# ADR-0004: Port sanitize stage from PowerShell to Python, preserving all security controls

## Status
Accepted

## Context
`epub-sanitize` (profanity removal, EPUB repack) is the only one of the
three merged tools not already in Python — it's a PowerShell script.
A single-language pipeline (Python 3.11+ throughout) is simpler to
maintain, test, and package into one `.exe`, but the existing script
carries several security-relevant behaviors that exist for real reasons
(it processes untrusted, user-supplied ZIP archives) and must not be
lost in translation.

## Decision
Port the sanitize stage to Python as `pipeline/sanitize_stage.py`,
preserving every one of the original script's security controls
exactly, not just its happy-path behavior:

1. Path-traversal guard on ZIP extraction.
2. Path-traversal/symlink guard on ZIP repacking.
3. Zip-bomb guard (configurable max extracted size).
4. XXE prevention (no DTD/external-entity resolution parsing XHTML/XML).
5. Profanity-list size cap (guards accidental bad input).
6. Case-insensitive, whole-word-only matching.
7. Asterisk replacement matching matched-word length.
8. Processes `.xhtml`/`.htm`/`.html` content files only.
9. Mimetype file written first, uncompressed, on repack (EPUB spec
   compliance).
10. Atomic-ish temp-directory workflow: clean up and leave no partial
    output on any failure.

Additionally, these same zip-safety guards (items 1–3) are extended to
**every** stage that opens a zip/EPUB, not just sanitize — including the
Screen 1 input-validation pass, which is now the first code to open the
zip at all (see ADR-0013).

The original script's per-`(book, file, word, count)` detail reporting
is preserved as a **sidecar CSV** (`CleanReport_<timestamp>.csv`),
separate from the unified cross-stage audit log, which instead gets a
single aggregate `words_replaced` integer per book plus a pointer to the
sidecar file.

## Consequences
- Security-critical logic gets rewritten, not just transliterated —
  every guard above needs to be independently verified in the port, not
  assumed correct because "the PowerShell version worked." This is
  reflected in the testing strategy's explicit call-out
  (`requirements/09-testing-strategy.md` §Priority coverage areas):
  security guards get adversarial, crafted-malicious-fixture tests
  targeting near-100% coverage, not incidental coverage from the happy
  path.
- The sanitize stage becomes a normal Python module reusable by both
  front doors, consistent with the shared-pipeline architecture
  (ADR-0001) — previously it was a standalone script with its own
  invocation model.
- The word list itself (66 words, editorial content) is carried over
  verbatim and is explicitly out of scope for this project to evaluate
  or change — only the mechanism for editing it is new.

## Alternatives Considered
- **Call the existing PowerShell script as a subprocess from Python** —
  rejected: keeps two languages/runtimes in the shipped `.exe`
  (PyInstaller bundling a PowerShell dependency is itself awkward),
  defeats the single-language-pipeline goal, and doesn't reduce the
  actual porting/verification work since the security controls would
  still need auditing either way.
- **Rewrite sanitize logic from scratch rather than port** — rejected:
  the existing script's security controls are already correct and
  tested-by-use; a from-scratch rewrite risks reintroducing bugs the
  original script already solved, for no benefit.

## References
- `requirements/02-pipeline-stages.md` §Stage 2
- `requirements/05-data-settings-and-logging.md` §Profanity list, §Audit
  log
- `requirements/09-testing-strategy.md` §Priority coverage areas
