# ADR-0019: Chapter-title detection broadened beyond "first `<h1>`-`<h3>`"

## Status
Accepted

## Context
Real user report, from actually listening to a generated audiobook ("The
Risen Empire"). Investigating it (`docs/BACKLOG.md` Epic 9, same session
as ADR-0020) surfaced a second, separate bug while inspecting two real
EPUBs already in the user's own library:
`pipeline/epub_utils.py::extract_chapters()` only ever looked for the
*first* `soup.find(re.compile(r"^h[1-3]$"))` per spine document, and used
that (or nothing) as the chapter title. Two different real books showed
two different failure modes of that one heuristic:

1. **The Risen Empire** — chapter names ("Pilot", "Senator") are plain
   `<p class="class_s3U">Pilot</p>` tags, bold via a CSS class, with
   **no heading tag anywhere in the document**. `extract_chapters()`
   found nothing, `ch_title` stayed empty, and
   `pipeline/audio_stage.py::_apply_tags()` silently fell back to a
   generic `"Chapter {track_number}"` — the real title never reached
   her anywhere, not the filename, not the ID3 tags.
2. **The Dragon Reborn** (Wheel of Time #3) — *does* use heading tags,
   but two of them: `<h3 class="calibre19">Chapter 1</h3>` immediately
   followed by `<em class="calibre18"><h4 class="calibre21">Waiting</h4></em>`.
   `soup.find(re.compile(r"^h[1-3]$"))` matches the first one it finds in
   document order — the generic "Chapter 1" — and never looks past it to
   the real, named title ("Waiting") one tag later.

Directly confirmed by user framing ("not all books are the same") that
these two failure modes are genuinely different EPUB authoring
conventions, not a single bug with one fix — any solution needs to be a
bounded, best-effort improvement, not a claim of universal correctness.
This mirrors the exact philosophy `pipeline/epub_utils.py` already uses
for `guess_author_from_filename()`/`guess_series_from_filename()`: *"a
wrong guess is worse than no guess."*

## Decision
Two additions to `pipeline/epub_utils.py`, wired into
`extract_chapters()` in place of the single `soup.find(...)` call, never
changing the surrounding chapter-boundary logic (one chapter per spine
document, unchanged — see ADR-0020's Context for why that boundary logic
itself was already correct and not part of this bug):

1. **`_extract_heading_title()`** — broadens the tag search from
   `h1`-`h3` to `h1`-`h6`, and collects every heading that appears
   before real narrative text has started (a small text budget, not an
   arbitrary "first N tags," so a heading appearing after substantial
   prose — a genuine mid-chapter section break — is correctly excluded),
   joining them in document order with `" — "`. Fixes the Dragon Reborn
   case (`"Chapter 1 — Waiting"`) without changing behavior for the
   overwhelmingly common single-heading case at all.

   Implementation note: walks `soup.body.descendants` (every `Tag` *and*
   `NavigableString` leaf, in document order), not
   `soup.find_all(True)`. A `Tag`'s own `get_text()` aggregates its
   entire subtree — summing that across every tag in a document
   (including outer wrappers like `<html>`/`<body>`) blows the text
   budget on the very first container tag, before ever reaching a real
   heading. This was caught directly: an earlier draft of this function
   passed its own unit tests but returned empty titles against the real
   Dragon Reborn file until traced to exactly this. Only
   `NavigableString` leaves contribute to the budget now, each real
   character counted exactly once regardless of nesting depth.

2. **`_find_de_facto_title()`** — a fallback consulted *only* when (1)
   found nothing at all. If the document's first text-bearing paragraph
   is short (≤60 chars), has no terminal sentence punctuation, and is
   followed by substantially more text (≥500 chars), treat it as a de
   facto chapter title. Fixes the Risen Empire case ("Pilot", "Senator")
   without ever touching a document that has a real heading.

## Consequences
- Best-effort only, by design — a headingless document whose opening
  paragraph doesn't match the short/unpunctuated/followed-by-more-text
  shape (e.g. a genuine prose-opening prologue) still gets an empty
  title, exactly as before. Never claims universal chapter-title
  detection; never worse than the prior behavior for any document this
  didn't previously handle correctly.
- `chapter["title"]` (the `extract_chapters()` return shape) is
  unchanged — still just a string, possibly empty. No caller
  (`AudioStage`, `RetagStage`) needed any change beyond receiving a
  frequently-more-accurate value.
- Directly benefits ADR-0020's merged "part" files: each part's ID3
  title tag now much more often carries the real chapter name instead
  of a generic "Chapter N" fallback.

## Alternatives Considered
- **CSS-class-based bold detection** (parse `stylesheet.css`, resolve
  which classes are `font-weight: bold`, require the candidate paragraph
  use one) — rejected: meaningfully more implementation complexity
  (parsing and associating an external stylesheet file per spine
  document) for marginal gain over the structural heuristic already
  chosen, and still wouldn't generalize to inline-styled or
  differently-authored bold text.
- **Join *every* heading found anywhere in a document**, not just those
  before real narrative text starts — rejected: unbounded, would pick
  up unrelated mid-chapter section-break headings and glue them onto the
  chapter title.
- **Do nothing, treat this as out of scope** — rejected: a real,
  concrete, user-visible defect (a named chapter title silently missing
  or wrong) found via real-world use of this exact tool, not a
  hypothetical.

## References
- `docs/requirements/02-pipeline-stages.md` §Stage 3
- `docs/BACKLOG.md` Epic 9
- `pipeline/epub_utils.py::extract_chapters()`,
  `_extract_heading_title()`, `_find_de_facto_title()`
- `docs/design/adr/0020-merge-audio-chunks-into-per-chapter-parts.md`
  (found and fixed in the same investigation)
