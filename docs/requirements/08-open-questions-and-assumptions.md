# Open Questions & Assumptions

Flagging these explicitly so the design review pass can either confirm
the assumption or force a decision before build starts.

## Carried-over open items

1. **RESOLVED during review: retag chapter-title derivation**
   (`02-pipeline-stages.md` §Stage 4): confirmed by reading the actual
   `retag.py` source — the script has no mechanism to read the sanitized
   EPUB at all, so "pull the real heading instead" would be new
   correlation logic, not a preserve-vs-improve toggle on existing
   behavior. Decision: keep filename-suffix-derived chapter titles
   exactly as today. Separately, found and fixed a real gap in the
   original script while reading it: it renames MP3s but never renames
   the containing output folder, which would cause a future retag run to
   silently revert to stale metadata — the port now fixes this.

2. **Voice quality/parity verification** (`04-tts-engine.md`): local
   Kokoro output should be compared side-by-side against the original
   Perchance-generated audio before fully retiring the browser-based
   path, to confirm no regression in quality, pacing, or sample rate.
   **Resolution (decided during review):** treat this as a concrete
   pre-launch QA checklist, not an open design question — pick 2–3
   representative voices, generate matched samples of the same text
   through both the old (Perchance, if still reachable) and new
   (Kokoro-direct) paths, and do a side-by-side listen for volume
   normalization, sample rate/bit rate, and pacing/pause-length
   differences. Keep the Selenium code path in version control (a
   branch, not necessarily live) until parity is confirmed, rather than
   deleting it immediately. **Tracked as a backlog item** — see
   `docs/BACKLOG.md`.

3. **CPU vs. GPU inference performance** (`04-tts-engine.md`): needs
   benchmarking on the mother's actual target hardware to set realistic
   expectations for generation time, since Perchance's in-browser
   version likely used WebGPU and local CPU-only inference may behave
   differently. **Resolution (decided during review):** don't ship a
   fixed "This can take a few hours" string on the Working screen
   (`03-gui-ux-design.md`) based on an assumption — if her machine is
   CPU-only and slow, that estimate could be badly wrong and undermine
   trust in the "it's okay to leave this open" framing. Instead, make
   the time estimate **dynamic**, derived from throughput measured
   during the current job (e.g. after the first few chunks complete,
   extrapolate remaining time from actual chars/sec observed on her
   hardware) rather than a hardcoded guess. **This same benchmarking
   pass should also produce the `SECONDS_PER_CHAR` constant** needed by
   the disk-space estimation formula in `06-safety-error-handling.md`
   §Resource & cost safety — one round of real measurement answers both
   open items at once, not two separate efforts. **Tracked as a backlog
   item** — see `docs/BACKLOG.md`.

4. **RESOLVED during a later review pass: `ai_providers/` registry
   attribution** (`01-architecture.md` §Project structure): the three
   source repos weren't public when the earlier design docs above were
   written, so the `ai_providers/` package (§Provider-agnostic AI
   enrichment decision) was described without any reuse attribution —
   unlike `FILENAME_PATTERN` and `chunk_text()` elsewhere in this
   design, which are both explicitly flagged as verbatim ports with a
   source citation. Once the repos became public and were checked
   directly, this turned out to matter: `epub-renamer` **already
   implements** the entire registry — `ai_providers/base.py`,
   `registry.py`, `openai_provider.py`, `null_provider.py` — plus a
   `MAX_FILES` cap and `DRY_RUN=true` default in its `.env.example`.
   None of that is new work for this project. The only file this
   project actually adds to that package is `gemini_provider.py`, since
   `epub-renamer` doesn't ship a Gemini implementation today.
   `01-architecture.md` and `06-safety-error-handling.md` have been
   updated to attribute this correctly; see
   `../design/adr/0003-pluggable-user-keyed-ai-provider.md` and
   `../design/adr/0014-reuse-existing-implementations-by-default.md` for
   the full decision record. Generalized lesson: any future description
   of "what a legacy tool does or doesn't already have" should be
   checked against the actual source once available, not left as a
   holdover assumption from before the repos were public.

5. **OPEN: neither the dyslexic-reader nor the screen-reader tester is
   currently confirmed** (added alongside the WCAG 2.1 AA alignment
   broadening —
   `../design/adr/0015-wcag-aa-alignment-broadened-accessibility-scope.md`,
   `00-overview-and-goals.md` §The accessibility targets). Originally a
   dyslexic reader *was* available and expected to actually test the app,
   the same way the primary FMS/RA persona gets a real unassisted dry
   run — that tester is **no longer available as of 2026-07-18**, moved
   to `docs/BACKLOG.md`'s Wish List rather than treated as a scheduled
   epic item, since there's currently no path to actually doing it. A
   screen-reader tester is being pursued through a contact who works
   professionally with people with disabilities, but is **not confirmed
   as of this writing** either. Until someone who actually is dyslexic or
   actually uses a screen reader has tried the app, any description of
   either side of this alignment must say "designed and tested against
   WCAG 2.1 AA criteria" — never "validated by a dyslexic reader" or
   "validated by a blind user," internally or in any portfolio-facing
   writeup, since that would overstate what's actually been confirmed.
   Revisit either item once a tester is secured (update the claim to
   reflect real results, good or bad) or once enough time has passed
   without one that the honest thing is to say so plainly rather than let
   the claim quietly go stale. **Tracked as a backlog item** — see
   `docs/BACKLOG.md`.

## Assumptions made during design that should be explicitly confirmed

- **RESOLVED during review: AI provider is now user-selectable**, not
  Gemini-only. Each install picks its own provider (Google/Gemini, OpenAI,
  or none) and supplies its own key — see `01-architecture.md`,
  `05-data-settings-and-logging.md`, and `03-gui-ux-design.md` §AI Helper
  Setup. The original Gemini-specific trade-off (free-tier data usage by
  Google) still applies to any install that chooses that option, but is no
  longer a project-wide assumption. **See item 4 above** for a correction
  to how this decision was originally documented — the pluggable-provider
  registry that makes this possible is a direct port of `epub-renamer`'s
  existing code, not new plumbing built for this project.
- **New open item from that change:** the intended normal path for the
  mother's install is for a technical family member to pre-fill
  `ai_api_key` in her `settings.json` before she ever opens the app, so
  she never has to visit an API provider's website herself. Confirm this
  is actually how it will be done in practice (vs. leaving her to hit the
  in-app "Get a code" flow unassisted) — the GUI screens exist either way,
  but the accessibility case for this feature really depends on the
  pre-fill happening.
- **RESOLVED — confirmed by the user at backlog kickoff:** the Gemini
  free-tier data-use trade-off (Google sees the text sent for enrichment)
  is accepted for any install that chooses that option. **Never enabling
  billing** on the Gemini API project remains a hard requirement to keep
  that install's free tier active — this should be documented somewhere
  durable (README / setup notes), since enabling billing on that project
  would silently remove the free tier and start charging. The OpenAI
  provider path (`openai_provider.py`, already ported from
  `epub-renamer` — see ADR-0003/ADR-0014) remains available as a
  first-class alternative for any install that prefers a paid key over
  Gemini's free tier; neither provider is more "default" than the other
  at the settings-schema level, only in what the first-run AI Helper
  Setup screen suggests.
- **RESOLVED — confirmed by the user at backlog kickoff: single Windows
  desktop target for v1.** No macOS/Linux packaging is planned; this
  matches the existing non-goal already stated in
  `00-overview-and-goals.md` §Non-goals, now with the assumption behind
  it explicitly confirmed rather than just inferred from the source
  repos' Windows-style file paths.
- **One book generates at a time**, never in parallel, in the audio
  stage — chosen for resource contention and progress-reporting
  simplicity. Confirm this is acceptable even for larger batches (e.g.
  15 books) where total wall-clock time could be very long.
  **Resolution (decided during review):** agree with serial-only for the
  GUI — progress-reporting simplicity matters more than throughput for
  this persona, and Kokoro's memory footprint makes concurrent jobs a
  real resource problem anyway (see `01-architecture.md` §Single-instance
  behavior). For the CLI/advanced front door, though, reserve a
  `--workers N` flag (default `1`) in the pipeline engine now, so
  parallelism can be added later for technical use without redesigning
  the engine — the GUI stays serial-only regardless of this flag's
  existence. Note this batch/serial-loop concept is itself new: the
  source `epub-to-audio` is a single-book CLI tool with no
  batch/parallelism notion at all.
- **No per-series/per-author voice memory** — deliberately simplified to
  a single global "last used voice" default, with the audit log serving
  as the fallback lookup mechanism. Confirm this trade-off still feels
  right on reflection, since it was decided somewhat late in the design
  process. **Resolution (decided during review):** keep the general
  simplification, but add one small, cheap enhancement rather than
  fully declining: within a single multi-book batch, default same-series
  books to the same voice as each other (session-local only, computed
  from the batch itself, no persisted per-series storage) — see
  `03-gui-ux-design.md` §Voice assignment. This solves the single most
  likely real annoyance (wanting series consistency within one batch)
  without reintroducing the cross-session per-series complexity that was
  explicitly rejected. Still flagged as **worth a second look on
  reflection** once real use exists — tracked as a backlog item, see
  `docs/BACKLOG.md`.
- **Profanity list word choices themselves are out of scope** — this
  project ports the existing 66-word list verbatim and builds tooling
  around editing it; it does not evaluate or change which words are on
  it. Confirm that's the intended boundary.
- **RESOLVED during review: no parallel/networked use case** — the GUI is
  single-user, `localhost`-bound, and this is now an explicit hard
  requirement (`01-architecture.md` §Network Binding & Security), not just
  an assumption. If multi-device/networked access is ever wanted later
  (e.g. a phone on the same home network), that needs a real
  authentication story first — treat it as a new design discussion, not a
  config change.
- **RESOLVED during review: accessibility scope now formally includes
  WCAG 2.1 AA alignment**, not just the FMS/RA persona — see item 5
  above for the one piece of this that's genuinely still open (the
  screen-reader tester), and
  `../design/adr/0015-wcag-aa-alignment-broadened-accessibility-scope.md`
  for the full decision record, including what was deliberately kept
  out of scope (AAA conformance, JAWS support, a formal audit).

## Things worth a second look during review specifically because they were decided quickly

- The **exact wording** of all her-facing copy (terminology table in
  `03-gui-ux-design.md`) — drafted for tone/clarity, not final copy.
  Worth a full read-through as if seeing it for the first time with no
  context. **Resolution (decided during review):** an internal
  read-through, however careful, isn't the real test — the actual
  acceptance test is having someone matching the persona (ideally the
  mother herself, or someone with a similar profile) do a genuine
  unassisted dry run of first-launch setup through a complete single-book
  conversion, watched but not helped, before treating any copy as final.
  Wording issues that read fine to someone who already knows what the
  app does are exactly the kind a fresh, unassisted run surfaces and an
  internal review doesn't. **Tracked as a backlog item** — see
  `docs/BACKLOG.md`.
- Whether **"Cancel" defaulting to keep-partial** (vs. defaulting to
  full-discard) is actually the safer choice in practice, or whether it
  could confuse her about whether the book "worked or didn't."
  **Resolution (decided during review):** keep-partial-by-default is the
  right call, but it surfaces a related gap that needed its own fix: a
  partially-cancelled book sitting in the output location needs to be
  **visually distinguishable from a finished one** — no ✅ checkmark, and
  no "📂 See the audiobook files" / "finished book" framing offered for it
  — until it's actually completed later. Without that distinction, she
  could open a folder expecting a finished audiobook and find it stops
  partway through with no explanation of why. This should be reflected
  wherever partially-completed books might be surfaced to her (e.g. the
  "Welcome back" screen's per-book status in `03-gui-ux-design.md`
  already frames it as "getting the audio ready," not finished —
  consistent with this resolution).
- **RESOLVED during review: the retag review screen's "No, let me fix
  it"** flow now has a full spec (`03-gui-ux-design.md` §"No, let me fix
  it" flow) — it reuses the existing metadata-editor pattern, feeds
  corrections through as retag overrides, and explicitly does *not*
  attempt per-chapter correction, since the underlying tool has no lever
  for that (see item #1 above). A book-scoped "See the audiobook files"
  link was also added so she can look at the real files before deciding
  Yes/No, rather than judging only from the Author/Title/Series text on
  screen.

## New items found during a post-backlog-kickoff review

A follow-up "what's this project still missing" pass, done after the
backlog was already sequenced, surfaced five items decided outright
(clear-cut, no real tradeoff to weigh) and two genuinely left open for
the user to decide.

**Decided outright:**

- **RESOLVED: Windows-illegal filename characters and path length.**
  Every generated filename/folder name comes from arbitrary real-world
  book metadata, which routinely contains characters Windows filenames
  can't have (colons, question marks, etc.) — previously entirely
  unaddressed. See `../design/adr/0016-windows-safe-filesystem-naming.md`
  for the sanitization rules and the long-path manifest mitigation.
  **Tracked as a backlog item** — see `docs/BACKLOG.md` Epic 3/5/10.
- **RESOLVED: `Library/` staging copies now have a cleanup policy.**
  Previously nothing ever deleted the internal working copies after a
  book completed, risking unbounded disk growth over the tool's real
  lifetime. See `../design/adr/0017-library-staging-cleanup.md`.
  **Tracked as a backlog item** — see `docs/BACKLOG.md` Epic 5/10.
- **RESOLVED: dependency versions will be exactly pinned** (a lockfile,
  not loose ranges) for both the Python backend and the frontend —
  `kokoro`/`torch` in particular are exactly the kind of dependency
  that can silently change TTS output or break the PyInstaller build on
  a minor-version bump. **Tracked as a backlog item** — see
  `docs/BACKLOG.md` Epic 0.
- **RESOLVED: a real-world EPUB corpus test pass is required before
  calling v1 done**, separate from the security-fixture/unit-test
  suite in `09-testing-strategy.md`. Real commercial/library EPUBs vary
  far more in structural quality (EPUB2 vs. 3, malformed OPF, non-linear
  spines) than synthetic test fixtures do. **Tracked as a backlog
  item** — see `docs/BACKLOG.md`.

**OPEN — needs the user's decision, not a unilateral call:**

- **OPEN: PyInstaller `--onefile` vs. `--onedir` packaging.** The
  current implicit assumption is a single `.exe` (ADR-0011), but
  `--onefile` builds are meaningfully more likely to trigger antivirus
  false-positive quarantine (a different, more severe failure mode than
  the SmartScreen click-through already handled in
  `07-packaging-deployment.md` — quarantine can silently remove the app
  entirely, with no dialog to click through). `--onedir` (a folder
  containing the `.exe` plus its dependencies, still launched via a
  single desktop shortcut, so her double-click experience is identical
  either way) has a lower false-positive rate and faster startup, at the
  cost of the author handing off/distributing a folder instead of one
  file. Recommend `--onedir` plus submitting built releases to
  Microsoft's Defender sample-submission portal, but this changes
  distribution mechanics the author experiences directly, so it's the
  user's call, not something to decide on their behalf.
- **OPEN: does correcting metadata via "No, let me fix it" need to
  re-deliver the EPUB too, not just rename the audiobook?** Surfaced
  2026-07-20 while fixing the sanitized-EPUB-never-reached-`output_folder`
  bug (see `docs/BACKLOG.md` Epic 9). `RetagStage`
  (`pipeline/retag_stage.py`) only ever operates on the audiobook's
  `.mp3` files and containing folder — it has no mechanism to touch any
  `.epub` file, and `BatchRunner.retag_book()` never references the
  EPUB's `output_folder` copy at all. Before today's fix this didn't
  matter, since the EPUB never reached `output_folder` in the first
  place. Now that it does (copied early, at sanitize time, before she's
  had a chance to review/correct anything), a post-Review correction
  leaves her with a correctly-renamed audiobook folder and a
  stale-named/stale-metadata EPUB for the same book — a real, new
  inconsistency this fix introduces rather than one it fixes. Needs a
  decision on the right fix shape (re-copy the EPUB under the corrected
  name at retag time? rename it in place, mirroring what `RetagStage`
  already does for the audiobook folder? something else?) before
  building it. **Tracked as a backlog item, not yet decided** — see
  `docs/BACKLOG.md` Epic 9.
- **RESOLVED 2026-07-20: per-chunk audio files vs. a merged per-chapter
  file.** The audio stage (inherited from `epub-to-audio`) produced one
  MP3 per text chunk, which could mean dozens of small files per
  chapter and hundreds per book — this stopped being hypothetical once
  a real user reported the resulting listening experience directly
  ("cuts off and starts in strange locations, like the middle of a
  sentence") after actually listening to a real generated audiobook.
  Investigating it found the audible gap between chunk files really was
  a genuine, separate problem from an already-fixed sort-order bug in
  the same report. Resolution, decided directly with the user against
  real per-chapter size numbers from her own library (she listens on
  phones/tablets): merge chunks into ~15-minute/~15MB "parts" instead of
  either extreme (one file per ~4,000-char chunk, or one file per
  chapter — the latter would have meant a single 205-minute/188MB file
  for one real chapter in her library). See
  `../design/adr/0020-merge-audio-chunks-into-per-chapter-parts.md` for
  the full decision, including the bounded resume-loss tradeoff this
  introduces. **Tracked as a backlog item, done** — see
  `docs/BACKLOG.md` Epic 9.
