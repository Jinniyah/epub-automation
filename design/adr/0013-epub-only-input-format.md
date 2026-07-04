# ADR-0013: Accept `.epub` input only; validate content, not extension

## Status
Accepted

## Context
The three merged tools, and every underlying library available to this
project (`ebooklib`, the custom `epub_reader.py`/`epub_utils.py`), only
reliably parse `.epub`. Supporting other ebook formats (`.mobi`, `.azw3`,
PDF, etc.) would require entirely different parsing libraries and
downstream handling per format, for a use case (the mother's personal
library, the author's own books) where `.epub` is already the practical
norm.

A related, previously under-specified problem: validation needs a
concrete point in the pipeline where it happens, and a concrete way to
detect DRM-protected files specifically (the most common real-world case
being Adobe-DRM-protected library loans/purchases), since discovering
DRM only after wasted downstream work (AI enrichment, sanitizing, even
TTS generation against content that never parses correctly) is a poor
failure mode.

## Decision
Accept `.epub` only, as a hard constraint. All validation — extension
check, real-zip-validity check (a genuine well-formed zip with expected
internals, not just a renamed file), and DRM detection — runs
synchronously at Screen 1, on drop/choose, **before** "Start" is even
reachable, never deferred into pipeline execution. A file failing any
check is rejected individually, with a friendly, specific message,
without blocking the rest of the batch:

- Wrong file type entirely → "That doesn't look like a book file — only
  .epub files work here."
- Not a valid/well-formed zip (renamed `.txt`, corrupted download) →
  "This file looks damaged."
- `META-INF/encryption.xml` present in the zip (the standard Adobe-DRM
  marker) → a distinct, specific message pointing at removing protection
  or finding a DRM-free source, since the problem and her available next
  step differ from a generically damaged file.

The same zip-safety guards required for the sanitize stage (ADR-0004:
path traversal, zip-bomb cap) apply here too, since this validation pass
is the first code in the pipeline to open the zip at all.

## Consequences
- Simplifies every downstream stage — none of them need to handle format
  ambiguity, since by the time a file reaches "Your books," it's already
  a confirmed, well-formed, non-DRM `.epub`.
- A confusing failure three stages downstream (the explicit problem this
  decision's validation-timing rule is designed to prevent) cannot
  happen for any of the three checked conditions — the failure surfaces
  immediately, at the point of adding the file, with a message matched
  to the actual problem.
- DRM detection is cheap (checking for a file's presence inside a zip,
  no content parsing needed) and reliable for the common case
  (Adobe DRM), but is a heuristic, not a complete DRM-detection system —
  other, less common DRM schemes without this specific marker would not
  be caught by this check and would surface as a different failure mode
  later.
- Non-`.epub` ebook formats are a permanent non-goal for this version,
  not a "not yet implemented" gap — documented explicitly in
  `requirements/00-overview-and-goals.md` §Non-goals so it isn't
  mistaken for an oversight.

## Alternatives Considered
- **Best-effort support for other formats via a conversion step
  (e.g. shell out to Calibre)** — rejected: adds a new external
  dependency and failure surface for a use case that doesn't need it
  (the target libraries are already predominantly `.epub`), and
  contradicts the "none of the underlying libraries reliably parse
  other formats" constraint that motivates this decision in the first
  place — a conversion step would just relocate the reliability problem
  rather than solve it.
- **Defer validation into the pipeline stages themselves (fail at
  whichever stage first chokes on a bad file)** — rejected: this is
  exactly the "confusing failure three stages downstream" problem the
  decision is designed to avoid; validating once, up front, at the only
  point she's actively looking at the file list, is strictly better for
  the accessibility persona.
- **Skip DRM detection; let AI enrichment / sanitize / TTS fail
  naturally on encrypted content** — rejected: wastes real time and
  compute on content that was never going to work, and produces a
  confusing rather than specific failure message.

## References
- `requirements/06-safety-error-handling.md` §Input validation
- `requirements/00-overview-and-goals.md` §Non-goals
- `requirements/02-pipeline-stages.md` §Shared cross-stage requirements
  (input validation)
