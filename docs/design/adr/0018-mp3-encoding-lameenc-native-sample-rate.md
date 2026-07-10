# ADR-0018: MP3 encoding via `lameenc`, at Kokoro's native 24kHz

## Status
Accepted

## Context
`04-tts-engine.md` §MP3 encoding parameters specified 128kbps constant
bitrate, mono, 48kHz — a genuinely new decision for this project, since
the original `epub-to-audio` never encoded MP3 itself (it downloaded
whatever blob Perchance's server produced, at whatever bitrate Perchance
chose internally). Once Epic 4 needed a real `encode_mp3()` implementation
(the interface sketch in that doc), two problems surfaced that hadn't been
checked against a real spike when the doc was originally written:

1. **Bitrate control.** `soundfile` (already pinned from Epic 1's WAV-
   writing spike) wraps libsndfile, which can technically write MP3
   (confirmed: `"MP3" in sf.available_formats()`), but only exposes a
   `compression_level` quality knob (0.0–~0.9), not a real bitrate
   parameter. Measured directly: the highest quality setting produced
   ~21kbps output — nowhere near the 128kbps CBR this app's disk-space
   estimate formula (`06-safety-error-handling.md` §Resource & cost
   safety) depends on being exact.
2. **Sample rate.** The doc said 48kHz. Kokoro-82M's actual output is
   24kHz — the already-verified Epic 1 spike (`spike/kokoro_spike.py`)
   itself hardcodes `sf.write(str(out), audio, samplerate=24000)`, and
   `kokoro.KPipeline.Result.audio` is confirmed (via the installed
   `kokoro==0.9.4` package source) to always be a 24kHz `torch.FloatTensor`.
   The 48kHz figure predates a real spike confirming what the model
   actually produces.

## Decision
**Encoding library:** `lameenc` — a compiled Python binding to the LAME
encoder, with prebuilt Windows wheels and no subprocess/external-binary
dependency. Verified directly: `encoder.set_bit_rate(128)` at 24kHz input
produces exact 128000bps CBR output, matching the 16,000 bytes/sec the
disk-space formula requires exactly.

**Sample rate:** encode at Kokoro's native 24kHz rather than resampling
up to 48kHz. Upsampling cannot recover detail that was never captured at
24kHz — it would add a new resampling dependency for no audible fidelity
gain. `04-tts-engine.md` has been corrected to state 24kHz, with a note
explaining why the number changed from the original draft.

Both `soundfile` (still used for reading/writing WAV, e.g. the Epic 1
spike) and `lameenc` are now pinned; `numpy` is pinned explicitly too,
since `pipeline/tts_engine.py` now imports it directly to convert
Kokoro's `torch.FloatTensor` output to the PCM `int16` bytes `lameenc`
expects.

## Consequences
- `pipeline/tts_engine.py::_encode_mp3()` is the only place MP3 encoding
  happens; `BYTES_PER_SECOND_OF_AUDIO = 16_000` derives directly from the
  128kbps constant, so the disk-space estimate formula
  (`estimate_audio_bytes()`) is exact, not approximate, exactly as
  `06-safety-error-handling.md` requires.
- One more compiled third-party dependency to verify in the eventual
  PyInstaller build (Epic 10) — `lameenc` ships prebuilt wheels the same
  way `espeakng-loader`/`soundfile` do, so this is expected to package the
  same way those did, but isn't yet build-verified (that verification is
  Epic 10 scope, same as the rest of the packaging pipeline).
- mypy strict flagged unrelated fallout from adding a real mutagen (ID3
  tagging) call path in `pipeline/audio_stage.py` at the same time — see
  `pyproject.toml`'s `[[tool.mypy.overrides]]` for `pipeline.audio_stage`
  and `CODEBASE_INDEX.md`'s Epic 4 session notes; unrelated to the MP3
  decision itself but landed in the same epic.

## Alternatives Considered
- **`soundfile` only, accept the lower/VBR bitrate it actually
  produces** — rejected: silently ships audio that doesn't match this
  app's own stated quality target, and breaks the disk-space formula's
  exactness (it would become file-content-dependent, not a fixed
  bytes/sec constant).
- **Shell out to an external `lame.exe`/`ffmpeg` binary via
  `subprocess`** — rejected: this app ships as a single self-contained
  PyInstaller `.exe` with nothing assuming an external binary or PATH
  entry exists on the target machine (`07-packaging-deployment.md`).
  `lameenc`'s compiled-extension shape avoids that class of problem
  entirely, the same way `espeakng-loader` does for espeak-ng.
- **Resample Kokoro's 24kHz output to 48kHz** to match the original doc
  literally — rejected: no real fidelity gain (upsampling can't invent
  detail that was never captured), a new dependency purely to hit a
  number, and the disk-space formula is already sample-rate-independent
  for constant-bitrate encoding, so there was no downstream requirement
  actually forcing 48kHz.

## References
- `docs/requirements/04-tts-engine.md` §MP3 encoding parameters
- `docs/requirements/06-safety-error-handling.md` §Resource & cost safety
- `docs/BACKLOG.md` Epic 4
- `pipeline/tts_engine.py`
