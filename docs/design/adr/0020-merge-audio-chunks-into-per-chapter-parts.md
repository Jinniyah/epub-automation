# ADR-0020: Merge audio chunks into ~15-minute per-chapter "parts"

## Status
Accepted

## Context
`pipeline/audio_stage.py`'s `AudioStage.run()` wrote one MP3 per
~4,000-char text chunk (`chunk_text()`, `MAX_CHUNK_CHARS = 4,000`,
tuned originally for Perchance, not Kokoro — `04-tts-engine.md`'s own
open item). A real book ("The Risen Empire") had a chapter with 53
separate chunk files. Two distinct, real problems surfaced from a real
user's actual generated audiobook, investigated the same session as
ADR-0019:

1. **Fixed earlier the same session:** chunk filenames weren't
   zero-padded (`006_1.mp3` ... `006_10.mp3` ... `006_2.mp3`), so any
   player/device that sorts by filename (most basic phone players, car
   stereos — not just ID3-track-aware apps) played chapters with 10+
   chunks scrambled, sounding exactly like "cuts off and starts in
   strange locations, like the middle of a sentence." Fixed by
   zero-padding to 3 digits, matching the chapter-index's existing
   width; the real "Risen Empire" files on disk were renamed in place to
   match.
2. **This ADR:** even with chunks in the correct order, there's an
   audible "odd space" where one small chunk's MP3 ends and the next
   begins — a real, separate complaint from the ordering bug above. The
   fix the user asked for is fewer, larger merged files. A whole chapter
   merged into *one* file is too large for comfortable phone/tablet
   playback: chapter 12 of the same real book is 53 chunks / 205
   minutes / 188MB unmerged. **Chapter boundaries themselves are not the
   bug here** — direct inspection of the real EPUB's `nav.xhtml`/spine
   confirmed `extract_chapters()` already correctly treats one spine
   document as one chapter; "Pilot" genuinely is one continuous
   131,633-character chapter in the source file, not several chapters
   incorrectly merged. The real chapter is just long. Asked directly,
   the user chose a **~15 minute / ~15MB target per merged output
   file**, confirmed against this book's real per-chapter numbers.

## Decision

**1. Deterministic char-count pre-partitioning, computed before any
TTS/audio work.** New `pipeline/epub_utils.py::group_chunks_into_parts(chunks, max_part_chars)`
greedily groups an already-chunked chapter's text strings into larger
"part" groups by cumulative character count — the same greedy-accumulate
shape `chunk_text()` already uses one level up (paragraphs/sentences
into chunks). This is pure text math, computed once per chapter up
front, so it is exactly reproducible on a resumed run: same input text
→ same grouping, every time. Deliberately **not** based on actual
generated audio duration (accumulate PCM until real measured duration
hits the target, then flush) — that would make part boundaries depend
on Kokoro's actual output length, which isn't guaranteed bit-for-bit
deterministic across runs. A resumed run could then compute a different
boundary than what's partially on disk, silently breaking the "a file
exists on disk = this exact set of chunks is done" resume invariant
that makes the whole mechanism safe. Parts never span a chapter
boundary — `group_chunks_into_parts()` is called once per chapter.

**2. Raw-PCM concatenation, not finished-MP3-byte concatenation.**
`pipeline/tts_engine.py::TTSEngine.generate(text, voice) -> bytes`
used to do PCM synthesis and `_encode_mp3()` in one call, with a fresh
`lameenc.Encoder()` session per call. New `generate_pcm(text, voice) -> np.ndarray`
returns the raw float32 PCM (what the encoder step used to receive
internally); `generate()` becomes a thin wrapper
(`encode_mp3(self.generate_pcm(text, voice))`) so every existing caller
(`generate_voice_sample()`/`ensure_voice_samples()`, single-shot, no
chaptering) is completely unaffected. `AudioStage` now calls
`generate_pcm()` per chunk, accumulates a part's PCM arrays in memory,
and encodes+writes exactly one MP3 (one `lameenc` session) once every
chunk in that part has succeeded. Concatenating independently-encoded
MP3 byte streams risks audible splice-point artifacts; routing a whole
part's audio through one encoder session avoids that by construction —
and mirrors what the code already does *within* a single chunk today
(Kokoro's own multi-segment output is already `np.concatenate`d with no
gap inserted), so this introduces no new class of artifact, just
extends an existing operation to a larger scope.
`pipeline/tts_engine.py::_encode_mp3()` is renamed to public
`encode_mp3()` since `AudioStage` now calls it directly — this also
fixes a pre-existing mismatch with `04-tts-engine.md`'s own interface
sketch, which already named it `encode_mp3()` without the underscore.

**3. ~15-minute soft target, not a hard limit.**
`TARGET_PART_MINUTES = 15` and
`MAX_PART_CHARS = round(TARGET_PART_MINUTES * 60 / SECONDS_PER_CHAR)`
(`pipeline/tts_engine.py`), reusing the existing `SECONDS_PER_CHAR`
placeholder (`06-safety-error-handling.md` §Resource & cost safety,
`08-open-questions-and-assumptions.md` item #3 — pending real hardware
benchmarking). Real measured data from the real book showed actual
encoded audio runs roughly 18% shorter than this estimate predicts —
the estimate is conservative, not likely to overshoot the target.
Accuracy improves for free, no code change needed, once the
already-tracked real-hardware `SECONDS_PER_CHAR` benchmarking backlog
item lands.

**4. Resume/Pause/Cancel loss unit changes from "one chunk" to "up to
one in-progress, not-yet-flushed part."** A part's MP3 file is only
written once every one of its chunks has succeeded — the resume check
(`mp3_path.exists() and .stat().st_size > MIN_VALID_MP3_BYTES`) now
operates at the part level, and a hit skips the TTS engine entirely for
every chunk in that part. If generation is interrupted partway through
a part (Pause, Cancel, or exhausting retries after a chunk failure),
whatever PCM its earlier chunks already produced is discarded — never
partially written — and the whole part is regenerated from scratch on
the next run. This is a **deliberate, bounded tradeoff**: worst case
~15 minutes of re-work, never a whole chapter or book, and never a
corrupted/partial file landing on disk. `AudioStage.run()` tracks two
counters to keep this honest: `track_num` (chunks whose PCM has
completed this run — drives the live progress display, fired
progressively per chunk, not batched at part-flush, since batching
would freeze the Working screen's progress bar for up to ~15 minutes at
a stretch) and `flushed_chunk_count` (chunks belonging only to
fully-written parts — the number actually reported as `chunks_done`
whenever the stage stops). The same bounded-loss consequence applies to
a mid-part generation failure, not just Pause/Cancel — no special-casing
needed, it falls out of the same "nothing is written until every chunk
in the part succeeds" rule.

**5. ID3 `track_number`/`total_tracks` now count parts (physical
files), not original text chunks.** This aligns `AudioStage`'s initial
tagging with `RetagStage`'s own already-per-physical-file numbering
convention (`track_number_from_tag()`'s fallback enumerates actual
files on disk) — previously these only happened to agree because one
file equaled one chunk.

**6. `on_progress` semantics are unchanged: still fires once per
original ~4,000-char chunk**, with the same running-total `chunks_total`
count as before. Zero frontend/`bridge.py` changes required — the
Working screen's existing chunk-progress bar keeps working exactly as
it did.

## Consequences
- Peak memory: one part's PCM in memory at a time (~15 min mono
  float32 @ 24kHz ≈ 86MB), never a whole chapter (chapter 12 unmerged
  would be ~1.1GB) — confirms per-part, not per-chapter, in-memory
  flushing is necessary even before considering disk output size.
- `06-safety-error-handling.md` §Long-run resilience/§Cancel design's
  language ("stops before the next chunk," "each finished chunk is
  already a real, valid MP3") described the old per-chunk unit exactly
  — updated to describe "part" instead, with the bounded-loss tradeoff
  stated explicitly, not left to silently diverge from the code.
- `pipeline/retag_stage.py` needed no code change: its filename-suffix
  parsing (`_SUFFIX_RE`, `chapter_title_from_stem()`,
  `_new_mp3_stem()`) already operates generically on "whatever the
  second number in a `-NNN_MMM` suffix means" — `"Chapter N, Part M"`
  wording becomes *more* accurate under this change (M now means a real
  ~15-minute segment, not an arbitrary ~4,000-char slice).
- `pipeline/disk_space.py`'s pre-batch estimate is unaffected — it
  estimates total audio bytes for a book from total character count,
  independent of how many files that total gets split into.
- Test fallout: every fake `TTSEngineLike` implementation across the
  test suite (`tests/test_audio_stage.py`, `tests/test_batch_runner.py`,
  `tests/test_app.py`) gained a `generate_pcm()` method, since that's
  what `AudioStage` calls now — mechanical, same call-recording/
  failure-injection pattern each fake's `generate()` already had.
  `tests/test_audio_stage.py` needed the heaviest rework: several tests
  that asserted "one chunk = one flushed file" needed their assertions
  inverted to prove the new, correct "nothing is flushed until the
  whole part succeeds" behavior instead.

## Alternatives Considered
- **Actual-audio-duration-based flushing** — rejected, see Decision
  point 1: breaks the resume-determinism invariant.
- **Merge into one file per full chapter** — rejected per the real
  user's own stated preference and the real numbers: chapter 12's 205
  min / 188MB as a single file is too large for comfortable phone/
  tablet scrubbing and re-transfer after an interruption.
- **Finished-MP3 byte concatenation** — rejected, see Decision point 2:
  independent `lameenc` encoder sessions risk audible splice-point
  artifacts; raw PCM through one encoder session avoids this by
  construction.
- **Keep per-chunk files, rely on the OS/player for gapless playback**
  — rejected: this app has no control over her actual device/player,
  and this is the same reasoning that produced the (separately fixed)
  sort-order bug — many basic players neither gapless-play nor reliably
  order by ID3 track number.
- **Attempt to detect and split on the EPUB's own narrative chapter
  breaks** (e.g. the mid-file POV/scene headers found while
  investigating this book, like `class_s5R`-styled "Captain"/"Doctor"
  labels within the "Pilot" chapter) — considered and rejected: real
  inspection showed these are POV/scene labels, not chapter boundaries
  the source book itself distinguishes structurally from chapter
  titles, and the user's own framing ("not all books are the same")
  argues directly against relying on a book-specific typographic
  convention for something as consequential as where a file boundary
  falls. Size-based splitting is universal across every EPUB's
  structure; narrative-boundary detection is not (see ADR-0019, which
  *does* take on a bounded, best-effort version of this for chapter
  *titles* specifically, a much lower-stakes guess than an audio file
  boundary).

## References
- `docs/requirements/02-pipeline-stages.md` §Stage 3
- `docs/requirements/04-tts-engine.md` §Interface sketch, §MP3 encoding
  parameters
- `docs/requirements/06-safety-error-handling.md` §Long-run resilience,
  §Cancel design
- `docs/requirements/08-open-questions-and-assumptions.md` items #2, #3
  and §New items found during a post-backlog-kickoff review
- `docs/BACKLOG.md` Epic 9
- `pipeline/audio_stage.py`, `pipeline/tts_engine.py`,
  `pipeline/epub_utils.py`
- `docs/design/adr/0018-mp3-encoding-lameenc-native-sample-rate.md`
  (the encoder this ADR now calls directly)
- `docs/design/adr/0019-chapter-title-detection-broadened.md` (found and
  fixed in the same investigation)
