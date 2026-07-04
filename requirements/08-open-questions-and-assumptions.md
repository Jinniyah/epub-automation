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
   deleting it immediately.

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
   open items at once, not two separate efforts.

## Assumptions made during design that should be explicitly confirmed

- **RESOLVED during review: AI provider is now user-selectable**, not
  Gemini-only. Each install picks its own provider (Google/Gemini, OpenAI,
  or none) and supplies its own key — see `01-architecture.md`,
  `05-data-settings-and-logging.md`, and `03-gui-ux-design.md` §AI Helper
  Setup. The original Gemini-specific trade-off (free-tier data usage by
  Google) still applies to any install that chooses that option, but is no
  longer a project-wide assumption.
- **New open item from that change:** the intended normal path for the
  mother's install is for a technical family member to pre-fill
  `ai_api_key` in her `settings.json` before she ever opens the app, so
  she never has to visit an API provider's website herself. Confirm this
  is actually how it will be done in practice (vs. leaving her to hit the
  in-app "Get a code" flow unassisted) — the GUI screens exist either way,
  but the accessibility case for this feature really depends on the
  pre-fill happening.
- **Never enabling billing** on the Gemini API project (for any install
  that chooses Gemini) is a hard requirement to keep that install's free
  tier active — this should be documented somewhere durable (README /
  setup notes), since enabling billing on that project would silently
  remove the free tier and start charging.
- **Single Windows desktop target for v1** — no macOS/Linux packaging
  considered. Confirm this matches actual need (the mother's machine,
  presumably Windows, per the existing file paths in the source repos).
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
  existence.
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
  explicitly rejected.
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
  internal review doesn't.
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
