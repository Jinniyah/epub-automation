# Safety & Error Handling

## Input validation

- **EPUB only.** This is a hard constraint, not a preference — none of the
  underlying libraries (`ebooklib`, the custom `epub_reader.py`/
  `epub_utils.py`) reliably parse other ebook formats. Any other file type
  dropped or selected must be rejected individually with a friendly
  message (e.g. *"That doesn't look like a book file — only .epub files
  work here"*) without failing the rest of the batch.
- **All validation below runs immediately at Screen 1, on drop/choose,
  before "Start" is even reachable — never deferred into pipeline
  execution.** This was previously unspecified; resolved this way
  because it's what this section's own stated goal requires ("a
  confusing failure three stages downstream" is exactly what deferred
  validation would produce). Concretely, this means: extension check,
  zip-validity check, and the DRM check below all happen in the same
  pass, synchronously, as part of adding a file to "Your books" on
  Screen 1 — by the time she presses "Start," every file already in the
  list has passed all three. A file that fails any of them never appears
  in the list at all; it gets the friendly rejection message immediately
  instead.
- **Validate actual file content, not just the extension** — check that a
  `.epub` file is a genuine, well-formed zip with expected internals
  before proceeding through any stage. A renamed `.txt` file or a
  corrupted download should produce a clear *"This file looks damaged"*
  message, not a confusing failure three stages downstream.
- **DRM detection: concrete heuristic, resolved.** Check for the presence
  of `META-INF/encryption.xml` inside the EPUB's zip structure — this is
  the standard marker Adobe-DRM-protected EPUBs (the most common case for
  library loans and many purchased books) use to declare which files are
  encrypted. This check is cheap (just confirming a file's presence
  inside the zip, no parsing needed) and reliable, unlike inferring DRM
  after the fact from "the text came out garbled" — which would only be
  discoverable *after* wasting time on AI enrichment, sanitizing, or even
  TTS generation against content that was never going to parse
  correctly. If `META-INF/encryption.xml` is present, reject immediately
  with a specific, named friendly message (e.g. *"This book is protected
  and can't be opened here — try removing the protection first, or check
  if your library/store offers a DRM-free download"*), distinct from the
  generic "this file looks damaged" message above, since the underlying
  problem and her available next step are different.
- **Zip-bomb and path-traversal guards** (see `02-pipeline-stages.md`
  §Stage 2) must apply to **every** stage that opens a zip/epub, not only
  the sanitize stage — including this Screen 1 validation pass itself,
  since it's now the first stage to open the zip at all.

## Resource & cost safety

- **Disk space check** before starting a batch, especially the audio
  stage — full-novel audio output can be substantial. Check available
  free space up front and warn clearly rather than failing mid-batch on
  book 4 of 5.
- **This estimate must account for copy-based storage, not just final
  audio size.** Per `01-architecture.md`'s folder mapping, each book's
  source file is copied (not moved) into `Library/00-Incoming/`, then
  copied again into `output_folder` at two points (sanitized EPUB, then
  finished audiobook) — meaning a given book's content exists in more
  than one place on disk at once, on top of her own original in
  `books_folder`. The space estimate must sum: the incoming copies for
  the whole batch, plus the sanitized-EPUB copies, plus the estimated
  audio output size (see the concrete formula below) — not audio size
  alone.
- **Audio size estimate — concrete formula (resolved during review):**
  ```
  estimated_audio_bytes = total_chars_remaining_in_book × SECONDS_PER_CHAR × 16,000
  ```
  Two pieces, one known and one still a placeholder:
  - **16,000 bytes/sec is exact, not an estimate** — it's the direct
    consequence of the 128 kbps constant-bitrate mono encoding decided in
    `04-tts-engine.md` §MP3 encoding parameters (128,000 bits/sec ÷ 8).
    This part of the formula will never be wrong regardless of content,
    voice, or book.
  - **`SECONDS_PER_CHAR` is a placeholder pending real Kokoro
    benchmarking data** (same open item as CPU/GPU throughput in
    `08-open-questions-and-assumptions.md`) — there's no way to know
    exactly how many seconds of audio Kokoro produces per character of
    input without measuring it. Until that data exists, use a
    placeholder derived from typical audiobook narration pace (~150
    words/minute, ~5.7 characters/word including the space → roughly
    0.07 sec/char) and **sanity-checked against one real data point**: a
    140-chunk, ~400MB audiobook produced by the *original* Perchance-based
    tool (*Run For Your Life*, Patterson) implies a similar order of
    magnitude once run through this same formula — close enough to
    validate the approach, though not exact, since that reference used
    an unknown/likely-different bitrate than the 128kbps now specified.
    **Once real Kokoro output exists, replace this placeholder with an
    actual measured seconds-per-character figure** from real generated
    audio — this is a one-line constant to update, not a formula
    change.
  - `total_chars_remaining_in_book` is already available cheaply: it's
    the same character count the chunking logic
    (`02-pipeline-stages.md` §Stage 3, `chunk_text()`) already computes
    before generation starts, not new work to calculate.
  - This estimate should run **per book at Screen 1** (once files are
    validated, before "Start" is pressed) and be **summed across the
    whole batch** for the total disk-space check, so a 5-book batch warns
    her before committing to all 5, not one book at a time mid-run.
  - **Deliberately biased toward overestimating, not underestimating**
    — a disk-space warning that turns out unnecessary is a minor
    annoyance; running out of space mid-batch because the estimate was
    too optimistic is a real failure. If the placeholder rate needs
    adjusting before real benchmarking data exists, round up, not down.
- **AI API cost**: no longer categorically zero, now that the AI provider
  is user-selectable (`01-architecture.md`, `03-gui-ux-design.md` §AI
  Helper Setup) and can be a paid provider (e.g. OpenAI) as well as
  Gemini's free tier. `MAX_FILES`-style per-run caps must exist
  regardless of provider — for a `"none"`/Gemini-free-tier install this
  is general hygiene and a soft guard against free-tier rate limits; for
  an install using a paid key, the same cap is the actual cost-control
  mechanism, not just hygiene. The cap should be a fixed, sane default
  (not something either her or a technical user needs to tune per run) so
  it protects a paid-key install even if nobody thinks to configure it.
  **This cap is not new safety logic invented for this project** —
  `epub-renamer` already implements a `MAX_FILES` cap (and a
  `DRY_RUN=true` safe default) in its own `.env.example`; it carries
  straight into `pipeline/ai_providers/` as part of that package's port
  (see `01-architecture.md` §Project structure). What's new here is only
  that the cap now protects a paid-key install too, since the provider
  is no longer guaranteed to be a free tier.
- **Batches exceeding `MAX_FILES` (resolved during review):** the cap
  above previously had no specified her-facing behavior when exceeded —
  a real gap given this section's own stated goal that no error state
  should be a silent dead end. Resolved the same way every other
  Screen-1 validation failure already works: if she adds more books than
  `MAX_FILES` allows in a single batch, the excess books beyond the cap
  are rejected individually at add-time (not silently dropped mid-batch
  after "Start"), with a friendly, specific message — e.g. *"You can
  convert up to 50 books at a time — try the rest in another batch."*
  This keeps the cap consistent with the "confusing failure three stages
  downstream" problem this section otherwise avoids everywhere else, and
  requires no new UI pattern: it's the same per-file rejection mechanism
  already used for wrong-format, damaged, and DRM-protected files above.

## Long-run resilience

- Laptop sleep, wifi drop, or a crash mid-audiobook must not corrupt
  progress. The existing per-chunk "skip if MP3 already exists and is
  above a minimum size" logic is the core mechanism and must be
  preserved exactly.
- **On every launch, check the state file for any book not yet marked
  complete through every stage it needs**, and if found, offer to
  continue it (see `03-gui-ux-design.md` §"Welcome back" screen). This
  check is **state-file-driven, not crash-detection-driven** —
  deliberately simpler than trying to distinguish "the previous run ended
  abnormally" from "a clean stop": the state file already tracks exactly
  what's done and what isn't (`05-data-settings-and-logging.md` §State
  file), regardless of *how* the app stopped last, so there's no need for
  a separate abnormal-termination heuristic (e.g. a lock/pid file check)
  alongside it. Whether she used "Quit for now," the laptop lost power,
  or the process was killed externally, the answer to "is anything
  pending?" comes from the same place and is checked the same way.
- Single-instance lock (see `01-architecture.md`) prevents two copies of
  the app from running simultaneously and corrupting the shared state
  file. **This lock now includes a liveness/staleness check** (resolved
  during review, see `01-architecture.md` §Single-instance behavior and
  ADR-0007) — the same crash/forced-restart/lost-power scenarios this
  section treats as expected during a multi-hour audio job would
  otherwise leave an orphaned lock file that permanently refuses to
  start the app on the next launch, with no way for her to know why or
  how to recover. A stale lock (its recorded PID no longer running) is
  now detected and cleared automatically at launch, distinct from the
  state-file-driven "Welcome back" resume flow described above — the
  lock check only decides whether it's safe to start; recovering
  in-progress work is still handled entirely by the state file.
- Since the TTS engine is now local Python (no browser — see
  `04-tts-engine.md`), the class of failures around "browser/tab
  closed, backgrounded, or discarded" no longer applies. Remaining
  long-run risks are limited to: the machine sleeping, the process being
  killed externally, or the app being fully quit via "Quit for now."

## Cancel design

Two distinct actions, not one:

- **Pause** — stop now, resume later, exactly where it left off. No
  cleanup needed; this is just "stop calling the next chunk."
- **Cancel** — abandons the book currently in progress. Requires
  confirmation first (e.g. *"Stop working on Fated? The audiobook won't
  be finished."*), since it's more destructive than Pause.

**Cancel's cleanup behavior:**

- Delete any partial/temp extraction directories used by the sanitize
  stage for the book in question (mirrors the existing PowerShell
  script's use of a GUID-suffixed temp directory under `%TEMP%`).
- For the audio stage specifically, because generation is chunk-by-chunk
  and each finished chunk is already a real, valid MP3: **ask her at
  cancel time** whether to keep already-completed chunks (resume later)
  or discard everything for that book. Default/pre-selected choice should
  be "keep partial, resume later" — the safer, less-destructive option,
  consistent with Pause's behavior, in case Cancel is pressed by
  accident.
- Reset that book's entries in the state file to reflect reality (not
  "done," and correctly reflecting how much *is* actually kept, per the
  choice above) — a future run must not be confused about how far the
  cancelled book actually got.
- **Never touch other books already completed** in the same batch.

## Concurrency & duplicate handling

- Output name collisions (a target filename that already exists) must
  produce a clear choice for her — *"You already have a book called
  Fated — want to replace it or keep both?"* — never a silent skip and
  never a silent overwrite. Since `output_folder` now receives two
  artifacts per book (the cleaned/renamed EPUB and the finished
  audiobook — see `01-architecture.md`'s folder mapping), this check
  must cover both independently: it's possible for the EPUB copy to
  already exist while the audiobook doesn't yet (e.g. a prior run's
  audio stage was cancelled), and the two shouldn't be conflated into a
  single collision decision.
- A book already fully processed in a prior run should be detected and
  communicated plainly (*"You've already done this one"*) rather than
  silently reprocessing or throwing an error.

## Error communication

- She will not be able to read a stack trace, and the design must not
  assume she'll call for help — but that help path still needs to exist.
  A generic *"Something went wrong"* screen must include a single
  **"Copy details for support"** action that saves the real technical
  error (and relevant recent audit log context) to a file she can send
  along, without needing to read or understand it herself. This bundle
  must never include her `ai_api_key` (see
  `05-data-settings-and-logging.md`) or any other credential — the
  error/log context it pulls from should be assembled from a copy of
  settings with sensitive fields stripped, not the raw `settings.json`.
- **Data privacy note on this bundle's contents (addressed during
  review):** the audit log context pulled into this bundle includes book
  titles and sanitize-stage details — meaning sending it to someone (the
  author, for support) reveals what she's been reading and what content
  got cleaned up in it. Low-stakes for family support specifically, but
  worth being deliberate about rather than silent: this should be
  acknowledged in the shipped project's top-level `README.md` (not just
  buried here), as a short, plain "Privacy" note along these lines —
  *"The 'Copy details for support' feature includes recent book titles
  and cleanup details to help diagnose problems. It never includes
  passwords or API keys. Whoever you send this file to will be able to
  see what books you've been converting."* This mirrors how
  `10-licensing-and-notices.md`'s licensing situation is documented both
  in depth (its own file) and as a short, visible summary (in
  `00-overview-and-goals.md`) — the same two-tier pattern applies here:
  full detail where the feature is specified (this section), short
  visible acknowledgment where a reader/user would actually see it
  (the README).
- No error state should be a dead end with no visible next step — at
  minimum, always offer a way back to Screen 1 / Add Books.
- **Audit log read failures (missing, unreadable, or corrupted file) must
  degrade gracefully everywhere the log is read**, not just wherever this
  was first noticed. Two places currently read it: the
  "What voice did I use before?" lookup (`03-gui-ux-design.md` §Settings
  areas) and this section's own "Copy details for support" bundle above.
  Neither may crash or show a raw file error if the log can't be read.
  The lookup screen shows the generic *"Something went wrong finding your
  voice history"* pattern with the same Copy-details path. The support
  bundle is the trickier case: if the log itself is what's broken, the
  bundle must still be produced — include whatever *can* be gathered
  (the technical error, settings with sensitive fields stripped) plus an
  explicit note that the audit log could not be read, rather than the
  support flow silently failing at exactly the moment it's most needed.

## Dependency / environment failures

- **Model download failure** (Kokoro weights, ~300MB, on first run) —
  needs a clear "couldn't finish setting up, check your internet
  connection and try again" message, distinct from an in-batch
  processing error.
- **No internet at all** — the AI renaming step and first-run model
  download both need it; the audio and sanitize stages do not, once
  set up. The app should degrade gracefully: if rename can't reach
  Gemini, fall back to `NullProvider` per file (see
  `02-pipeline-stages.md` §Stage 1) rather than blocking the batch.
