# ADR-0004: Port sanitize stage from PowerShell to Python, preserving all security controls

## Status
Accepted

## Context
`epub-sanitize` (profanity removal, EPUB repack) is the only one of the
three merged tools not already in Python — it's a PowerShell script
([github.com/Jinniyah/epub-sanitize](https://github.com/Jinniyah/epub-sanitize),
confirmed to contain nothing but `PS_Run-CleanUpEpub.ps1`, `profanity.txt`,
and a `.gitignore` — no README, no license file, no design docs). A
single-language pipeline (Python 3.11+ throughout) is simpler to
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

**Regex/dependency note, found during review by reading the actual
source (item 6 above):** the original script's whole-word matching isn't
a plain regex — it uses .NET's Unicode-category lookbehind/lookaround
(`(?<![\p{L}\p{N}_])...(?![\p{L}\p{N}_])`) plus a hard 5-second execution
timeout on the match itself, as a ReDoS guard against a pathological
profanity-list entry. Python's stdlib `re` module supports neither
Unicode-property character classes nor a per-match timeout. The Python
port needs to make this an explicit dependency decision — most simply,
adopt the third-party `regex` package (which supports both) — rather
than silently dropping the timeout guard or approximating whole-word
matching with plain `\b`, which behaves differently on non-ASCII
alphabetic characters. This is called out here because it's exactly the
kind of thing ADR-0004's own "verify, don't just transliterate" framing
below is meant to catch.

## Consequences
- Security-critical logic gets rewritten, not just transliterated —
  every guard above needs to be independently verified in the port, not
  assumed correct because "the PowerShell version worked." This is
  reflected in the testing strategy's explicit call-out
  (`docs/requirements/09-testing-strategy.md` §Priority coverage areas):
  security guards get adversarial, crafted-malicious-fixture tests
  targeting near-100% coverage, not incidental coverage from the happy
  path — now explicitly including a test proving the ReDoS-timeout
  behavior survives the port, not just that ordinary words match.
- The sanitize stage becomes a normal Python module reusable by both
  front doors, consistent with the shared-pipeline architecture
  (ADR-0001) — previously it was a standalone script with its own
  invocation model.
- The word list itself (66 words, editorial content, from the source
  repo's `profanity.txt`) is carried over verbatim and is explicitly out
  of scope for this project to evaluate or change — only the mechanism
  for editing it is new.
- Because the source repo has no license file of its own, there's no
  separate license to reconcile when folding this logic into the
  MIT-licensed epub-automation project (see ADR-0012's licensing
  analysis for `mutagen`/`ebooklib`, which is a distinct concern from
  this stage's own code).
- Adds `regex` (or an equivalent chosen alternative) as a new pipeline
  dependency, not previously listed in
  `docs/requirements/10-licensing-and-notices.md`'s dependency
  inventory — that table should be updated once the specific package is
  chosen, for the same "complete, honest dependency accounting" reason
  every other dependency in that file is listed.

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
- **Approximate the original's Unicode-aware whole-word matching with
  Python stdlib `re`'s plain `\b`** — rejected as a silent substitution:
  `\b` boundary semantics differ from the original's explicit
  `\p{L}\p{N}_` character classes on non-ASCII alphabetic text, and
  stdlib `re` still can't reproduce the timeout guard regardless. If a
  behavior change here is ever accepted, it should be a stated decision
  with its own reasoning, not an implicit consequence of picking the
  "obvious" Python regex module.

## References
- [`epub-sanitize` repository](https://github.com/Jinniyah/epub-sanitize)
  — `PS_Run-CleanUpEpub.ps1`, `profanity.txt`
- `docs/requirements/02-pipeline-stages.md` §Stage 2
- `docs/requirements/05-data-settings-and-logging.md` §Profanity list,
  §Audit log
- `docs/requirements/09-testing-strategy.md` §Priority coverage areas
