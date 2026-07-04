# ADR-0002: Local Kokoro TTS engine, not browser-automation (Perchance/Selenium)

## Status
Accepted

## Context
The original `epub-to-audio` tool drove Perchance's browser-based TTS
page via Selenium: headless Chrome, iframe context-switching, blob-URL
JS extraction via `fetch()` + `FileReader` → base64 → decode. This works
but is a genuinely fragile subsystem — a whole class of failures
("is the browser/page still alive," anti-bot detection, shared-service
GPU contention on Perchance's side) exists purely because of *how* the
TTS call is made, not because of anything about TTS itself.

During investigation it was discovered that the voice identifiers the
original tool already used (`af_heart`, `am_puck`, `bf_alice`, etc.) are
the exact voice keys from **Kokoro-82M**, an open-weight (Apache 2.0)
model — meaning Perchance's browser tool is very likely running that
same model client-side. An official Python package (`kokoro`, published
by the model's own author) can call it directly.

## Decision
Replace the entire browser-automation subsystem with a direct, in-process
call to the `kokoro` Python package. Only the "turn this chunk of text
into audio bytes" function changes — chapter extraction, chunking,
filename parsing, 3-tier metadata resolution, ID3 tagging, and the
resume-by-existing-MP3 recovery logic are all reused unchanged (see
`requirements/04-tts-engine.md` §What stays exactly the same).

MP3 encoding parameters (a genuinely new decision, since the original
tool just saved whatever blob Perchance produced) are fixed at
**128 kbps CBR, mono, 48kHz** — chosen deliberately because constant
bitrate makes the byte rate of output a fixed, known constant
(16,000 bytes/sec), which is what makes the disk-space estimate formula
in `requirements/06-safety-error-handling.md` computable at all.

## Consequences
- Eliminates an entire fragile subsystem: Selenium, `webdriver-manager`,
  Chrome-launch/anti-detection flags, iframe switching, blob-URL
  extraction, and all "is the browser alive" concerns.
- Removes a dependency on Perchance's server-side load/GPU availability
  — generation time now depends only on the user's own machine.
- Removes a previously-planned first-run "is Chrome installed?" check
  from the packaging story entirely.
- Introduces a **new** first-run cost: ~300MB of model weights must
  download from Hugging Face once, and are cached afterward (fully
  offline-capable from that point on). Needs its own clear "setting up
  for the first time" messaging, distinct from batch-processing status.
- Introduces a new open verification item, not yet closed: local Kokoro
  output has not yet been compared side-by-side against the original
  Perchance output for quality/pacing/sample-rate parity. Resolved as a
  concrete pre-launch QA checklist (`requirements/08-open-questions-and-
  assumptions.md` item 2), not a blocking design question — but real
  verification is still outstanding.
- `MAX_CHUNK_CHARS = 4,000`, inherited verbatim from the Perchance-era
  code, was tuned for what Perchance's API would accept per request —
  not for Kokoro. Carried over unchanged for now as the right default
  (reuse working logic), but flagged for re-validation once real
  Kokoro samples exist.
- CPU-only inference speed on actual target hardware is unverified;
  Perchance's browser version likely used WebGPU. Mitigated
  structurally (not by assuming a number) by making the GUI's time
  estimate dynamic — derived from observed throughput in the current
  job — rather than a hardcoded guess (see
  `requirements/03-gui-ux-design.md` §Screen: Working).

## Alternatives Considered
- **Embed Perchance's page directly in the React GUI** — rejected:
  likely blocked by `X-Frame-Options`/CSP even if attempted, and even if
  it worked, ties audio-generation liveness to a specific browser tab
  staying open/focused — the exact fragility this decision exists to
  remove, just relocated rather than fixed.
- **Keep Selenium + Perchance, hardened** (headless mode, anti-throttling
  flags, sleep prevention, a watchdog for dead sessions) — considered
  as a fallback; would likely have worked, but leaves the entire fragile
  subsystem in place for a problem that has a structurally cleaner fix.

## References
- `requirements/04-tts-engine.md` (full)
- `requirements/02-pipeline-stages.md` §Stage 3
- `requirements/08-open-questions-and-assumptions.md` items 2–3
