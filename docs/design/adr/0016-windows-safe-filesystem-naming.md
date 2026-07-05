# ADR-0016: Windows-safe filesystem naming and long-path handling

## Status
Accepted

## Context
Found during a post-backlog "what's this project still missing"
review, not the earlier design-review pass: every filename and folder
name this project generates is built from arbitrary Title/Author/Series
text — either straight from EPUB metadata or from AI enrichment
(`02-pipeline-stages.md` Stage 1, Stage 4). Real book titles routinely
contain characters Windows filenames cannot legally contain: colons
(*"Spider-Man: Homecoming"*), question marks (*"Who Framed Roger
Rabbit?"*), quotes, slashes, and others (`< > : " / \ | ? *`). Nothing
in the design as written sanitizes for this — the `FILENAME_PATTERN`
reuse (`02-pipeline-stages.md`) only recognizes an *already-normalized*
name, it doesn't guard the *construction* of a new one.

Separately, but for the same underlying reason (arbitrary,
unpredictable-length text becoming path components), the generated
folder structure nests deep and the per-chunk audio filenames add
another path segment on top of that
(`%APPDATA%\EpubAutomation\Library\03-Audio\<book folder>\<Author —
Series #NN — Title> - <chapter>_<chunk>.mp3`). Windows' historical
260-character path limit (`MAX_PATH`) is a real, unremarkable-to-hit
constraint for a long series name combined with this filename shape,
not an exotic edge case.

## Decision
**Filename/folder sanitization:** add a shared utility,
`pipeline/epub_utils.py::sanitize_filesystem_name()`, used by both the
rename stage and the retag stage everywhere Title/Author/Series text
becomes part of a filename or folder name. It must, deterministically
and idempotently (running it twice produces the same result as running
it once — this matters because `FILENAME_PATTERN`'s already-normalized
check needs to keep recognizing a name this function already
sanitized):

1. Replace each Windows-reserved character (`< > : " / \ | ? *`) with a
   single space, then collapse repeated whitespace.
2. Strip trailing dots and spaces from every path component (Windows
   silently disallows both).
3. If a component's name (case-insensitive, ignoring extension) matches
   a reserved device name (`CON`, `PRN`, `AUX`, `NUL`, `COM1`–`COM9`,
   `LPT1`–`LPT9`), append a safe suffix rather than leaving it as-is.
4. Truncate each generated component to a conservative max length
   (e.g. 100 characters) as defense-in-depth for the long-path problem
   below, independent of whether long-path support is actually enabled
   on a given machine.

**Long-path handling:** ship the PyInstaller-built `.exe` with an
application manifest declaring `longPathAware`, so Python's own
long-path support (available since Python 3.6 on Windows) can work when
the OS-level "Enable Win32 long paths" policy is on. This is a
mitigation, not a guarantee — that OS policy defaults to *off* and,
depending on Windows edition, isn't always exposed in a friendly UI for
her to enable herself — which is exactly why the truncation guard above
exists as a second, independent line of defense rather than relying on
the manifest fix alone.

## Consequences
- The rename and retag stages both depend on this shared utility rather
  than each inventing their own escaping logic — one tested function,
  reused, consistent with this project's Repository/shared-utility
  pattern preference (`docs/design/PATTERNS.md`).
- `FILENAME_PATTERN`'s regex (`02-pipeline-stages.md` Stage 1) doesn't
  need to change — it matches the *shape* of an already-normalized name
  and was never asserting anything about which characters could appear
  inside the Title/Series segments, so sanitized text still matches it
  correctly.
- Truncating long components means an extremely long series or title
  string could end up visibly shortened in the final filename. Accepted
  as the safer failure mode versus a silent path-length failure deep in
  the audio stage after significant work has already been done on that
  book.
- This is a case where the project's reuse-by-default principle
  (ADR-0014) doesn't apply directly — none of the three source repos
  needed to solve this, since `epub-renamer` and `epub-to-audio` are
  developer-run CLI tools operating on filenames the developer already
  controls, not a pipeline whose only front door for a non-technical
  user takes arbitrary real-world book metadata as input.

## Alternatives Considered
- **Do nothing, let the OS error surface** — rejected: for the GUI
  persona specifically, a raw `OSError` mid-batch on book 4 of 5 because
  of a colon in a title is exactly the kind of opaque, unrecoverable
  failure `06-safety-error-handling.md` exists to prevent everywhere
  else in this design.
- **Reject/skip books whose metadata contains illegal characters** —
  rejected: would silently exclude a large fraction of real books
  (colons in subtitles are extremely common) for no real benefit over
  just sanitizing the text.
- **Rely solely on the long-path manifest fix, skip truncation** —
  rejected: the OS policy it depends on isn't guaranteed enabled on her
  machine, and even when it is, other tools that later touch these
  files (an antivirus scanner, a backup tool, a USB-transfer utility)
  may not all support long paths themselves.

## References
- `docs/requirements/02-pipeline-stages.md` Stage 1, Stage 4
- `docs/requirements/07-packaging-deployment.md` §Known packaging
  constraints (manifest requirement)
- `docs/BACKLOG.md` Epic 3 (rename), Epic 5 (retag), Epic 10 (manifest)
