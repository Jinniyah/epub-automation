# Data, Settings & Logging

## Where settings live

`%APPDATA%\EpubAutomation\settings.json` — deliberately **not** inside the
`.exe`'s own install location. Reasons:

- Stays writable even if the app is installed somewhere access-restricted
  (e.g. a Program-Files-style location).
- Survives app updates. If a new `.exe` is shipped to her machine, her
  saved folders, toggle preferences, last-used voice, and custom
  profanity words are not overwritten.
- Shared source of truth between the GUI and the CLI/advanced mode — no
  separate config paths to keep in sync.

**Everything this app stores locally lives under this same folder** — one
location, not scattered across the install directory and various OS
cache paths:

```
%APPDATA%\EpubAutomation\
├── settings.json          # see schema below
├── state.json             # resume tracking, see §State file below
├── audit_log.csv          # see §Audit log below
├── logs\
│   └── CleanReport_<timestamp>.csv   # sanitize sidecar reports, see 02-pipeline-stages.md §Stage 2
├── voice_samples\
│   ├── af_heart.mp3        # pre-generated ▶ Listen samples, see 04-tts-engine.md §Voice samples
│   ├── am_george.mp3
│   └── ...                 # one per voice, 28 total
└── Library\                # internal working folders, see 01-architecture.md §Folder mapping
    ├── 00-Incoming\        # copies of her books, from books_folder
    ├── 01-Renamed\
    ├── 02-Sanitized\       # also copied out to her output_folder as each book finishes this stage
    └── 03-Audio\           # also copied out to her output_folder as each book finishes
```

This answers a gap that existed until now: the voice sample cache
(`04-tts-engine.md` §Voice samples) never had an explicit location —
it's here, alongside everything else, for the same reason settings live
outside the install directory: easy to find in one place, survives app
updates, and doesn't require hunting across multiple OS-specific cache
locations to understand what the app has stored on her machine.

## Settings schema

```json
{
  "schema_version": 1,
  "books_folder": "C:\\Users\\Mom\\Documents\\My Books",
  "output_folder": "C:\\Users\\Mom\\Documents\\Audiobooks",
  "fix_names": true,
  "clean_language": true,
  "ai_provider": "gemini",
  "ai_api_key": "...",
  "last_voice": "am_george",
  "profanity_words": ["...", "..."]
}
```

Field notes:

- **`schema_version`** — an integer, starting at `1`, written on every
  save (resolved during review; see §Schema versioning below for the
  full reasoning and the policy for what a future version bump must do).
- `fix_names` / `clean_language` — the two Screen 1 toggles. Default
  `true` for both on first run.
- `ai_provider` — one of `"gemini"`, `"openai"`, or `"none"`. Selected once
  during the first-run "AI Helper Setup" step (see `03-gui-ux-design.md`
  §AI Helper Setup), changeable later via the same settings entry point.
  `"none"` routes to `NullProvider` regardless of whether `ai_api_key` is
  set — this is the pre-selected default on that setup screen.
- `ai_api_key` — a single active key for whichever provider is currently
  selected, not a per-provider map. Switching `ai_provider` later requires
  re-entering a key for the new provider (matches the "single global
  value, not tracked per-anything" pattern already used for `last_voice`
  — simplicity over remembering multiple keys at once). **Stored in plain
  text** in `settings.json`, same as every other setting in this file —
  acceptable for a local, single-user, non-networked tool (see
  `01-architecture.md`'s localhost-only requirement), but this file must
  never be included in the "Copy details for support" bundle (see
  `06-safety-error-handling.md` §Error Communication) or written to the
  audit log under any circumstance.
- `last_voice` — a **suggestion only**, not a lock. Pre-selects the voice
  picker's default; updated every time she completes a voice selection,
  for any book. Explicitly **not** tracked per-series or per-author (see
  `03-gui-ux-design.md` §Voice Assignment for the reasoning — simplicity
  was chosen deliberately over that convenience, with the audit log
  serving as the fallback memory if she needs to look up a past choice).
- `profanity_words` — her personal, editable copy. See below for how it's
  seeded and why it's independent from the bundled default.

## Schema versioning (resolved during review)

**Gap this closes:** `settings.json` and the state file are both written
atomically (see §Write safety below) specifically because a corrupted,
unparseable file is an expensive failure mode for this persona — but
atomicity only protects against *accidental* corruption. Neither file
previously had any marker distinguishing "an old-but-valid file from a
prior app version" from "a corrupted file," which matters because this
project explicitly ships updates to an existing install (`settings.json`
living outside the install directory specifically so it survives them —
see §Where settings live above) and will need to change these schemas at
least once as the project grows (a new AI provider needing different
stored fields, a restructured `profanity_words`, a new toggle). Without a
version marker, a future version of the app has no way to tell those two
very different situations apart.

**Decision:** both `settings.json` and the state file (see §State file
below) carry a `schema_version` integer field, starting at `1` for this
version, written every time either file is saved.

**Policy for a version mismatch, going forward:**

- **An older `schema_version` than the running app expects** — the app
  migrates the file forward (filling in new fields with sane defaults,
  restructuring changed ones) rather than treating it as corrupt. Each
  future schema change should ship with its own small, explicit
  migration step, not an assumption that "the shape hasn't really
  changed."
- **A newer `schema_version` than the running app expects** (e.g. she was
  downgraded to an older `.exe`, or a technical family member's install
  and hers drift) — the app does not attempt to guess how to read a
  format it doesn't know. This falls back to the same corrupted-file
  recovery path already required for atomic-write failures
  (`schema_version` unrecognized is treated the same as unparseable
  content), rather than a third, bespoke failure mode.
- **No `schema_version` field at all** (a file written before this
  decision, or truly corrupted) — treated as `schema_version: 1` if the
  rest of the file otherwise parses and matches the version-1 shape
  (forward-compatible with any real installs that predate this field);
  otherwise treated as corrupted, same as always.

This is a one-field addition now, before any real install exists, versus
a much harder retrofit once unversioned files are already on real
machines — consistent with this project's general preference for paying
small costs early rather than larger ones later (see, e.g., the
WCAG alignment scope decision in ADR-0015, made for the same reason).

## Profanity list: bundled default vs. personal copy

- The bundled default ships at `pipeline/profanity.txt`, ported directly
  from the existing `epub-sanitize\profanity.txt` (66 words as of this
  writing) — no changes to the word list itself as part of this project;
  that list is the author's own editorial call.
- **On first run only**, this bundled list is copied into her
  `settings.json` → `profanity_words`. From that point on, her copy is
  independent.
- This means: future app updates can ship an improved/expanded base list
  without silently overwriting anything she's customized, and her
  personal edits never affect the author's own copy of the list or any
  other installation.
- The GUI's "Words to clean up" screen (see `03-gui-ux-design.md`) reads
  and writes `profanity_words` directly.
- Worth surfacing to her once (not repeatedly): a few entries in the
  starter list are broad by design (e.g. religious exclamations like
  "god," "hell," "Christ," "Jesus") — some people consider these
  profanity and others don't. Her "Remove" button is exactly the
  mechanism for adjusting that to her own sense of what counts, per word.

## Audit log

One CSV (or similar structured log) across **all** stages, not a
per-stage report file. Columns include, at minimum:

| Column | Notes |
|---|---|
| `timestamp` | UTC ISO 8601 |
| `stage` | rename / sanitize / audio / retag |
| `original_filename` | |
| `new_filename` | |
| `title`, `author`, `series`, `series_number` | Resolved metadata |
| `ai_used` | yes/no — was AI enrichment invoked for this file |
| `renamed` | yes/no |
| `skipped_reason` | e.g. `already_normalized`, `epub_read_error`, `dry_run` |
| `voice` | Audio stage only — which voice key was used for this book |
| `words_replaced` | Sanitize stage — **aggregate integer count** for this book in this run (e.g. `12`), mirroring the original PowerShell script's `$epubReplacements` running total. Never a per-word breakdown — see `sanitize_detail_report` below for that. |
| `sanitize_detail_report` | Sanitize stage — path to that run's detailed sidecar CSV (see `02-pipeline-stages.md` §Stage 2), which holds one row per `(book, file, word, count)`. Same value repeated across every sanitize row from the same run. |

This serves two purposes:

1. **Debugging/support** — if something goes wrong, the log is the first
   place to look, and it's also what gets referenced by the "Copy details
   for support" error-reporting flow (see
   `06-safety-error-handling.md`).
2. **Her own lookup tool** — since voice choice is deliberately *not*
   remembered per-series (see above), the audit log is the underlying
   data source she can use to answer "what voice did I use for this
   series last time," **surfaced through the small plain-language lookup
   screen specified in `03-gui-ux-design.md` §"What voice did I use
   before?" screen** — not by her opening or reading the raw CSV herself.
   (**RESOLVED during review:** earlier drafts called the raw audit log
   itself "her own lookup tool," which contradicted `03`'s explicit rule
   that the log's file path and internal format are never exposed to
   her. She has no stated way to open a CSV file, so that framing
   promised something she couldn't actually use unassisted. The real
   audit log remains an unstyled CSV for the author/support to read
   directly; what she gets is a small read-only screen built on top of
   it.)

## State file (resume tracking)

Separate from the audit log — the audit log is a human-readable history;
the state file is the machine-readable "what's already done" tracker the
pipeline itself reads to decide what to (re)process. Carries its own
`schema_version` integer field (see §Schema versioning above — the same
policy applies to this file as to `settings.json`). Needs to support,
per file, per stage:

- Marked complete → skipped on future runs.
- Reset to incomplete → for the Cancel flow's cleanup behavior (see
  `06-safety-error-handling.md` §Cancel Design), so a cancelled book is
  correctly re-attempted rather than assumed done or assumed further
  along than it actually is. A cancelled book also marks its `cleanup`
  stage complete at the same time (docs/BACKLOG.md Epic 9) — otherwise it
  would stay "incomplete" forever and incorrectly keep reappearing as
  pending on every future launch, since it never reaches the normal
  `_mark_complete()` path that marks `cleanup` for a finished book.

**Schema v2 addition (docs/BACKLOG.md Epic 9, full "Welcome back"
resume):** each book entry may also carry a `"snapshot"` key —
`{"status": ..., "data": ...}`, the book's full in-memory state, not just
its per-stage completion flags. Written by `StateRepository
.save_book_snapshot()` on every status-changing mutation
(`pipeline/batch_runner.py::BatchRunner._set_book()`), deliberately
*not* on the high-frequency per-chunk audio-progress callback (see that
method's own docstring for why `chunks_done` doesn't need to be
persisted for correct resume). `StateRepository
.incomplete_book_snapshots()` returns every not-yet-`cleanup`-complete
book's snapshot; `BatchRunner.restore_books()` seeds a freshly-
constructed, empty runner from that list at process startup
(`backend/app.py::_build_app_state()`), coarse-graining a `generating`/
`paused` book to `voice_pick` (audio resumes via `AudioStage`'s own
existing per-chunk disk-file-size check, not via persisted chunk counts)
and an `identifying` book to `pending` (rename/sanitize copy their
source rather than deleting it, so redoing identification from scratch
is always safe). A book with no snapshot yet (a v1 file migrated to v2,
or one that died before its first status change was ever persisted) is
silently skipped by full resume — nothing to reconstruct it from — but
stays visible to "clean up stuck in-progress state" (docs/BACKLOG.md
Epic 9), which sweeps by folder contents rather than by snapshot.

## Write safety: atomic writes required for settings.json and the state file

**Hard requirement:** both `settings.json` and the state file must be
written using a write-to-temp-then-rename pattern, never overwritten
in place. Concretely: write the new content to a temp file in the same
directory (e.g. `settings.json.tmp`), flush it, then perform a single
atomic rename over the real file (`os.replace()` on Windows). Never
`open(path, "w")` directly on the live file.

**Why this matters enough to spell out:** an in-place write is not
instantaneous or all-or-nothing — the OS opens the file, truncates it,
writes the new bytes, then closes it, and that takes measurable time. If
the process is killed partway through (power loss, a Windows-forced
restart, antivirus locking the file mid-write, a crash), the file can be
left truncated or half-old/half-new content — invalid JSON that fails to
parse on next launch. A rename, by contrast, either fully happens or
fully doesn't; there's no partial state to land in.

**Why it matters specifically for this app, not just as general hygiene:**
`settings.json` holds everything she's configured — both folders, her
voice preference, her custom profanity list, her AI key. Nothing in this
doc set describes a graceful recovery from a corrupted, unparseable
`settings.json` — without one, a corrupted file would either crash the
app on launch or silently reset her to a blank first-run state, forcing
her to redo folder selection, rebuild her word list, and re-enter her AI
key with no explanation of why. For a persona for whom unfamiliar
multi-step setup is already hard, that's a bad failure mode to leave
possible when the fix (atomic rename) is cheap and standard. The same
reasoning applies to the state file: a corrupted state file breaks the
"resume where you left off" guarantee that `06-safety-error-handling.md`
§Long-run resilience depends on. (This is also, per §Schema versioning
above, distinct from an *old-but-valid* file — atomicity guards against
accidental corruption; `schema_version` guards against a deliberate
future shape change being mistaken for corruption, or vice versa.)

This mirrors a pattern already required elsewhere in this design (the
sanitize stage's temp-directory-then-clean-up handling,
`02-pipeline-stages.md` §Stage 2, item 10) — this section just extends
the same principle to the two files everything else in the app depends
on being readable.
