# TTS Engine

## Decision: local Kokoro Python package, no browser

**Rejected approaches and why:**

- **Embedding Perchance's page directly in the React GUI** — rejected for
  two reasons: (1) most sites, likely including Perchance, disallow being
  framed by a foreign origin (`X-Frame-Options`/CSP), so it may not even
  load; (2) even if it did, it would tie audio generation liveness to
  whether she keeps that specific browser tab open and focused — the
  exact fragility this decision is meant to eliminate, just relocated.
- **Keeping Selenium + Perchance, hardened** — considered as a fallback
  (headless mode, Chrome anti-throttling flags, sleep prevention, a
  watchdog to detect and recover from a fully-dead browser session). This
  would have worked but leaves a whole fragile subsystem (browser
  automation, blob-URL JS extraction, iframe context switching) in place
  for a problem that has a cleaner fix.
- **Chosen: call the underlying model directly in Python.** The voice
  names used throughout the original tool (`af_heart`, `am_puck`,
  `bf_alice`, etc.) are the exact voice identifiers from **Kokoro-82M**,
  an open-weight (Apache 2.0) TTS model. Perchance's browser-based tool is
  very likely running that same model client-side. An official Python
  package (`kokoro`, published by the model's author, `hexgrad`) runs it
  directly with no browser involved at all.

## What this eliminates

- Selenium, `webdriver-manager`, all Chrome-launch/anti-bot-detection
  flags.
- The iframe context-switching logic (`_enter_frame`, `IFRAME_ID`, etc.).
- The blob-URL JavaScript `fetch()` + `FileReader` → base64 → decode
  chain.
- All "is the browser/page still alive" concerns — generation is now a
  synchronous (or simply retryable) function call in the same process as
  everything else. No separate process to crash, sleep, or be closed.
- Dependency on Perchance's server-side load/GPU availability — the
  original README notes "budget 2–5 hours for a full novel" due to
  shared-service GPU contention; local inference depends only on her own
  machine.

## What stays exactly the same

- Chapter extraction, `--stop-after` back-matter truncation, text
  chunking (`chunk_text()`, `MAX_CHUNK_CHARS = 4,000`, both reused
  verbatim from `epub-to-audio\epub_utils.py` — see
  `02-pipeline-stages.md` §Stage 3), filename parsing, the 3-tier
  metadata resolution priority, ID3 tagging, and the
  resume-by-checking-existing-MP3s recovery logic — none of this needs to
  change structurally. Only the "turn this chunk of text into audio
  bytes" function is replaced. The one caveat: `MAX_CHUNK_CHARS` was
  tuned specifically for what Perchance's API would accept per request,
  not for Kokoro — see §Open item for review below.

## Interface sketch

```python
from kokoro import KPipeline

class TTSEngine:
    def __init__(self, lang_code: str = "a"):
        self._pipeline = KPipeline(lang_code=lang_code)

    def generate(self, text: str, voice: str) -> bytes:
        """Return encoded MP3 bytes for the given text and voice key."""
        segments = [audio for _, _, audio in self._pipeline(text, voice=voice)]
        return encode_mp3(concatenate(segments))
```

Normal Python exceptions on failure — the existing per-chunk retry logic
in the audio stage can catch and retry these the same way it retried
Selenium failures, just without any "reload the page" step.

## MP3 encoding parameters (decided during review)

**This is a genuinely new decision this project has to make** — the
original tool never encoded MP3 itself; it just downloaded whatever blob
Perchance's server produced, at whatever bitrate Perchance chose
internally (never specified or controlled by this codebase). Now that
`encode_mp3()` in the interface sketch above is something we implement,
the parameters are ours to set:

- **128 kbps, constant bitrate**
- **Mono (1 channel)** — spoken word has no stereo content to preserve;
  mono halves file size versus stereo at the same bitrate for no audible
  quality loss on narration.
- **48 kHz sample rate**

These three numbers matter beyond audio quality — bitrate alone
deterministically fixes the byte rate of the output, which is what makes
the disk-space estimate in `06-safety-error-handling.md` §Resource & cost
safety possible to compute at all: 128,000 bits/sec ÷ 8 = **16,000
bytes/sec of audio, always**, regardless of voice or content (sample rate
doesn't independently change this for constant-bitrate encoding — it
affects fidelity, not file size).

## First-run setup

- Model weights (~300MB) download from Hugging Face on first use and are
  cached locally afterward — fully offline-capable after that point.
- **Download timing, resolved during review:** this is deliberately
  **lazy, not eager** — the download is triggered the first time an
  install actually needs the audio stage (the first time a batch with
  "Turn into audiobook" enabled reaches the point of needing the model or
  a voice sample), not unconditionally at every first launch before
  Screen 1 is even shown. This matters concretely: renaming and
  sanitizing don't need Kokoro at all, so an install with no internet
  access yet (e.g. a freshly set-up machine before wifi is configured)
  can still open the app and use those stages on first launch. Blocking
  the entire first launch on a 300MB download the moment the app opens —
  regardless of whether that session ever touches the audio stage — would
  contradict the existing "no internet at all" degradation story in
  `06-safety-error-handling.md` §Dependency / environment failures, which
  already treats audio/sanitize as not needing a connection once set up.
  Concretely, the trigger point is: the first time the pipeline is about
  to call into `tts_engine.py` for this install (which also covers voice
  sample pre-generation, since a sample can't be generated without the
  model either) — whichever comes first, a real audio-stage run or her
  opening the voice picker for the first time.
- This fits into the same "Setting up for the first time..." first-launch
  message already planned for what was previously the Chrome/ChromeDriver
  check (see `07-packaging-deployment.md`), just shown at the point
  described above rather than at every app launch — see
  `07-packaging-deployment.md` §First-run setup requirements for how this
  screen is framed when it actually appears.
- New dependencies: `kokoro`, `soundfile`. Removed dependencies:
  `selenium`, `webdriver-manager`.

## Voice samples (for the GUI voice picker)

- **Language scope, made explicit (confirmed during review):** Kokoro
  ships 9 languages and ~54 voices total
  ([full list](https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md)),
  but this app only ever uses `lang_code="a"` (American English, 20
  voices) and `lang_code="b"` (British English, 8 voices) — 28 total,
  matching the "~28 voices" figure used throughout `03-gui-ux-design.md`.
  This was always the implicit assumption given the target audience
  reads English books; it just hadn't been written down as a decision
  anywhere. Confirmed no first-name collisions across all 28 (see
  `03-gui-ux-design.md` §Full voice-picker for the actual name list and
  the one future caveat if non-English voices are ever added).
- All 28 available voices get a **short sample line pre-generated once**,
  at the same first-run setup moment as the model download (see §First-run
  setup above for exactly when that moment is), and cached as small MP3
  files at `%APPDATA%\EpubAutomation\voice_samples\` — stored alongside
  settings, the state file, and the audit log rather than in a separate
  OS-specific cache location, so everything the app has stored locally
  lives in one findable place (see `05-data-settings-and-logging.md`
  §Where settings live for the full directory layout).
- **Cache invalidation:** if the `kokoro` package or its model weights
  are ever upgraded in a future app update, these cached samples must be
  regenerated, not left as-is — a stale sample could sound different
  from what that voice actually produces after an upgrade, which would
  be a confusing, hard-to-explain mismatch (the voice she picked based on
  the sample doesn't match what she gets). Simplest approach: tag the
  `voice_samples\` folder with the `kokoro` package version that
  generated it (e.g. a small `version.txt` alongside the MP3s), and wipe
  + regenerate the whole folder on launch if that version doesn't match
  the currently installed one. **If that regeneration can't complete
  because the machine happens to be offline at that moment**, keep the
  existing (stale-tagged) samples in place rather than deleting them
  first and leaving her with no previews at all, and retry the
  regeneration on a future launch rather than blocking anything in the
  meantime — a slightly-stale preview is a smaller problem than a missing
  one.
- The GUI's `▶ Listen` button plays back the cached sample instantly — it
  must never trigger a fresh generation per click, since a person
  auditioning several voices in a row needs each click to be immediate.
- Every voice uses the **same sample sentence** (something like *"Hello!
  This is what your audiobook will sound like."*) so the comparison is
  about the voice, not the content.

## Open item for review

- Voice quality/pacing should be compared side-by-side against the
  original Perchance output before fully retiring the old path, to
  confirm parity (same underlying model, but worth verifying in
  practice — e.g. output sample rate, any post-processing Perchance may
  have applied that isn't replicated here).
- **Also fold into that same comparison pass:** whether `MAX_CHUNK_CHARS =
  4,000` (reused as-is from `epub-to-audio\epub_utils.py`) is still a good
  number for Kokoro specifically. It was chosen for what Perchance's
  request size would tolerate, not for Kokoro's actual quality/latency
  characteristics per chunk — carried over unchanged for now since
  reusing existing, working logic is the right default, but this is the
  kind of tuning constant that's cheap to re-check once real side-by-side
  samples exist and shouldn't be assumed correct just because it's
  inherited.
- CPU vs. GPU inference: confirm target hardware assumptions. Kokoro
  supports CPU inference (slower) and GPU via `torch` if available.
  Perchance's in-browser version likely used WebGPU. Running on her
  actual machine's CPU-only hardware should be benchmarked before
  assuming parity on generation speed.
- **Packaging risk, flagged during review, not yet resolved:** whether
  the `kokoro` package's grapheme-to-phoneme pipeline pulls in a native
  (non-Python) dependency for the American/British English voices this
  project actually uses — some Kokoro deployments rely on `espeak-ng`
  for this — has not been checked against the specific pinned version
  this project will build against. If it does, that's a native binary a
  PyInstaller build has to locate and bundle correctly, which is a
  meaningfully different packaging problem than "the exe will be large."
  See `07-packaging-deployment.md` §Known packaging constraints for the
  suggested early spike to resolve this before it can block a real
  build.
