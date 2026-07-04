# Pipeline Stages

Four stages total. Three run as an automatic sequence (with per-stage
skip options); the fourth (retag) is always manually triggered.

```
00-Incoming/ --[rename]--> 01-Renamed/ --[sanitize]--> 02-Sanitized/ --[audio]--> 03-Audio/
                                                                                       |
                                                                            [retag] (manual, on demand)
```

Each stage reads from the previous stage's output folder and writes to its
own. A shared state file tracks per-file, per-stage completion so re-runs
after an interruption skip work already done, without needing to inspect
the folders themselves.

---

## Stage 1: Rename

**Source:** `epub-renamer`

- Scans a folder (non-recursive is fine for this pipeline, since folder
  structure is now controlled by the pipeline itself) for `.epub` files.
- For each file, extracts embedded EPUB metadata (`epub_reader.py`) and a
  text sample.
- Calls whichever AI provider is configured for this install (`gemini`,
  `openai`, or `NullProvider` if `ai_provider` is `"none"` or unset — see
  `05-data-settings-and-logging.md`) to enrich/infer title, author, series,
  series number.
- Renames to: `Lastname, Firstname — Series #NN — Title.epub`
  (or `Lastname, Firstname — Title.epub` with no series).
- Already-normalized filenames are detected and skipped without an API
  call — reuses `FILENAME_PATTERN` from the existing `epub-renamer\renamer.py`
  verbatim:
  ```python
  FILENAME_PATTERN = re.compile(
      r"^[^,]+, [^—]+(— .+ #\d{2} — .+|— [^—]+)\.epub$",
      re.IGNORECASE,
  )
  ```
  A filename matches (and is skipped, no AI call made) only if it's
  already in exactly one of the two normalized shapes: `Lastname,
  Firstname — Series #NN — Title.epub` or `Lastname, Firstname —
  Title.epub`. This is the same mechanism the original tool already uses
  (`FILENAME_PATTERN.match(filename)` in `main.py`), including writing an
  audit row with `skipped_reason: "already_normalized"` and marking the
  file processed in the state file — both already match this project's
  audit log and state file design as-is, no adaptation needed.
- Writes a row to the shared audit log for every file, regardless of
  outcome (renamed, skipped, error).
- **Can be skipped** per run (see `03-gui-ux-design.md` / CLI flags). When
  skipped, files pass through to `01-Renamed/` unchanged rather than
  downstream stages needing to special-case "did renaming happen."

**Failure handling:** if the AI call fails or is rate-limited, fall back
silently to `NullProvider` behavior (EPUB metadata only) for that one file,
log it, and continue the batch — never block the whole run on one file's
AI call.

---

## Stage 2: Sanitize

**Source:** `epub-sanitize` (PowerShell, ported to Python for this project)

Must preserve every security control from the original script:

1. **Path-traversal guard** on ZIP extraction (reject entries that resolve
   outside the destination folder).
2. **Path-traversal / symlink guard** on ZIP repacking.
3. **Zip-bomb guard** — configurable max extracted size per EPUB.
4. **XXE prevention** — no DTD or external entity resolution when parsing
   XHTML/XML content.
5. **Profanity list size cap** — refuse to run with an unreasonably large
   list (guards against accidental bad input, not an adversarial actor).
6. Case-insensitive whole-word matching only (no partial-word matches).
7. Replacement is asterisks of the same length as the matched word.
8. Processes `.xhtml`, `.htm`, and `.html` content files inside the EPUB.
9. Mimetype file written first and uncompressed on repack (EPUB spec
   compliance).
10. Atomic-ish behavior: work happens in a temp directory; on any failure,
    clean up the temp directory and do not leave a partial output file.

**RESOLVED:** the original PowerShell script (`PS_Run-CleanUpEpub.ps1`)
already produces exactly the "detailed per-word breakdown" the audit log
doc left unresolved — a CSV with one row per `(Epub, File, Word, Count)`,
timestamped filename so repeated runs never silently overwrite each
other. Reused as-is (ported to Python, same four-column shape), this
becomes a **sidecar report**, separate from the unified cross-stage audit
log:

- **Sidecar report** (one per pipeline run, not per book — matches the
  original script's behavior exactly): every non-zero `(book, file, word,
  count)` row for every book sanitized in that run, written to
  `%APPDATA%\EpubAutomation\logs\CleanReport_<timestamp>.csv`, using the
  same timestamped-filename pattern as the original script.
- **Unified audit log's `words_replaced` column** (see
  `05-data-settings-and-logging.md` §Audit log): a single aggregate
  integer per book — the sum of all replacements for that book in that
  run, mirroring the original script's `$epubReplacements` running total.
  A second column, `sanitize_detail_report`, holds the sidecar file's
  path for that row, so the detailed breakdown is always one click away
  from the summary row without cramming variable-length detail into a
  single CSV cell.

**Output:** cleaned EPUB (suffix configurable, default `_cln`), plus the
sidecar CSV report described above.

**Editable word list:** the profanity list is user-editable (see
`03-gui-ux-design.md` for the GUI, and `05-data-settings-and-logging.md`
for where it's stored). The bundled default is a starter list; her copy
forks from it on first run and is never silently overwritten by app
updates.

---

## Stage 3: Audio

**Source:** `epub-to-audio`, with the TTS engine replaced (see
`04-tts-engine.md`)

Per book:

1. Resolve metadata (EPUB internal → filename parse → CLI/GUI overrides,
   same 3-tier priority as the original tool).
2. Extract chapters in spine order (existing `extract_chapters` logic,
   including `--stop-after` back-matter truncation).
3. Chunk each chapter's text to a max character length suitable for the
   TTS engine — reuses `chunk_text()` from the existing
   `epub-to-audio\epub_utils.py` verbatim, including its `MAX_CHUNK_CHARS =
   4,000` constant and its paragraph-boundary-first, sentence-boundary-
   fallback splitting logic. This was tuned for Perchance specifically
   (per that file's own comment: "Max characters fed to Perchance per TTS
   request") — carried over unchanged for now, but worth re-checking
   against Kokoro's actual behavior as part of the voice
   quality/parity verification already flagged in
   `08-open-questions-and-assumptions.md` (item #2), since a limit tuned
   for one TTS backend isn't guaranteed to be optimal for another.
4. **Voice selection happens here, per book** — see
   `03-gui-ux-design.md` §Voice assignment for the full UX. This cannot
   happen earlier in the pipeline because the book's identity (genre,
   series) isn't known until after renaming/metadata resolution.
5. Generate audio per chunk via the local Kokoro engine (no browser, no
   network dependency once the model is cached).
6. Write MP3s named `<Author — Series #NN — Title> - <chapter>_<chunk>.mp3`,
   tagged with ID3v2.3 (title, artist, album, track number, cover art).
7. **Resume support:** any existing MP3 above a minimum size threshold is
   treated as already-generated and skipped — this must keep working
   exactly as today, since it's what makes Pause/Cancel/interruption
   recovery safe (see `06-safety-error-handling.md`).

**Batch behavior:** unlike the original single-file CLI tool, this stage
loops over every book in `02-Sanitized/`, running the full per-book flow
(voice pick if needed, generate, resume-check) for each in sequence. Books
never generate in parallel — one at a time, to avoid resource contention
and to keep progress reporting simple and truthful.

---

## Stage 4: Retag (manual only)

**Source:** `retag.py` (existing implementation at
`epub-to-audio\retag.py` — ported into `pipeline/retag_stage.py` largely
as-is; see the two behavior notes below for the only changes from the
original script).

- Operates on a **single already-generated audiobook output folder**, not
  a batch queue.
- Parses author/title/series/number from the *folder name* (handles both
  old and new naming conventions already supported by the original
  script).
- Rebuilds chapter titles from the **MP3 filename suffix** (e.g.
  `013_10.mp3` → "Chapter 13, Part 10"), not from old tag text.
- Accepts **author/title/series/series-number overrides**, exactly as the
  original script does (`--author`/`--title`/`--series`/`--series-number`
  in the CLI) — this is the actual mechanism by which a wrong
  Author/Title/Series gets corrected; see §"No, let me fix it" flow below
  for how the GUI drives this.
- Rewrites ID3 Title/Artist/Album tags and renames files to match current
  naming conventions.
- **New behavior, not in the original script:** also renames the
  **containing output folder** to match the corrected metadata, not just
  the MP3 files inside it. The original script only renames files, never
  the folder — which means today, running it with an override leaves the
  folder name stale. Since `parse_folder_metadata()` reads that same
  folder name to auto-detect metadata on any future run, an unrenamed
  folder would cause a later retag (run without repeating the same
  overrides) to silently revert to the old, wrong values. Fixing this now
  avoids shipping a known regression.
- Never runs automatically. Triggered either:
  - Via her answering "Does the audiobook chapters look right or do they
    need renamed?" on the post-generation review screen for that book
    (see `03-gui-ux-design.md` §Screen: Review), or
  - Manually later, any time, on any folder in `03-Audio/`.
- Always supports dry-run (preview changes without writing).

**RESOLVED (was open item #1):** chapter titles stay exactly as the
original script derives them — mechanically from the MP3 filename suffix,
never from EPUB headings. The original script has no mechanism to pull a
real chapter heading (it doesn't even read the sanitized EPUB at all,
only the output folder's MP3s), and building that correlation (matching
an MP3's numeric index back to a specific spine entry in
`02-Sanitized/<book>.epub`, then extracting that entry's real heading
text) would be new functionality, not a port of existing behavior. Given
the available lever is really "fix Author/Title/Series, which cascades
to every file being retagged and renamed," not "fix an individual
chapter's label," the flow behind "No, let me fix it"
(`03-gui-ux-design.md` §"No, let me fix it" flow) is scoped to match
what the tool actually does today. Real EPUB-heading correlation remains
a valid future improvement, but is out of scope for this port.

**What "No, let me fix it" does, concretely:** reopens the same
one-field-at-a-time metadata editor already used in the pre-generation
"Confirm metadata" step (§Per-book identification loop above), pre-filled
with the current Author/Title/Series/series-number. Whatever she corrects
is passed straight through as `retag_stage.py`'s
author/title/series/series-number overrides — the same parameters the
original script already accepts via CLI flags. There is no separate
per-chapter correction UI, since the underlying tool has no per-chapter
correction mechanism (see resolution above).

---

## Shared cross-stage requirements

- **State file** (`state_manager.py`): tracks per-file, per-stage
  completion. Must support: resuming a batch after interruption without
  reprocessing completed files; being safely reset for a single
  cancelled book without affecting others in the same batch (see
  `06-safety-error-handling.md` §Cancel).
- **Audit log** (`audit_logger.py`): one CSV across all stages, with a
  `stage` column, timestamp, and stage-specific fields (adds a `voice`
  column for the audio stage). This is also the underlying data source
  behind the "What voice did I use before?" lookup screen
  (`03-gui-ux-design.md` §Settings areas), which is how she answers "what
  voice did I use for this series last time" without the app needing to
  track or infer that itself — she never reads the raw log directly (see
  `03-gui-ux-design.md` §Voice assignment — per-row default is
  intentionally simple/global, not per-series, specifically so the audit
  log can serve as the memory instead of hidden app logic beyond the
  one session-local same-series exception noted there).
- **Input validation**: every stage that opens a ZIP (sanitize, and
  anywhere EPUBs are read) applies the same path-traversal/zip-bomb
  guards, not just the sanitize stage.
