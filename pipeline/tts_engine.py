"""Thin wrapper around `kokoro.KPipeline` (docs/requirements/04-tts-engine.md).

Replaces `epub-to-audio`'s Selenium/Perchance browser automation with a
direct, in-process call to the same underlying open-weight model
(ADR-0002) -- see 04-tts-engine.md §Decision for the full reasoning.

Two implementation decisions resolved during Epic 4 that the requirements
doc left open or got wrong before a real spike existed to check against
(04-tts-engine.md §MP3 encoding parameters has the full writeup):
  - MP3 encoding uses `lameenc`, not `soundfile` -- `soundfile`/libsndfile's
    MP3 writer only exposes a `compression_level` quality knob, not a real
    bitrate control (measured ~21kbps at its highest setting, nowhere near
    the 128kbps CBR this app requires for its disk-space estimate formula
    to hold, docs/requirements/06-safety-error-handling.md §Resource & cost
    safety).
  - Output stays at Kokoro's native 24kHz rather than being resampled up to
    48kHz -- 24kHz is what the model actually produces (confirmed by the
    already-verified Epic 1 spike, which hardcodes `samplerate=24000`);
    upsampling can't add real fidelity and would need a new resampling
    dependency for no audible benefit.

`KPipeline` itself is never imported at module load time -- only inside
`_get_pipeline()`, the first time a lang_code is actually needed. This is
what makes the "lazy, not eager" model-download trigger
(04-tts-engine.md §First-run setup) possible: constructing a `TTSEngine`
costs nothing, and nothing calls `generate()`/`ensure_voice_samples()`
until a real audio-stage run or the voice picker needs it. Epic 4 delivers
that laziness at this layer; *deciding when* to call `ensure_voice_samples()`
for the first time is `bridge.py`/GUI wiring (Epic 6/8), the same split
Epic 3 used for `DEFAULT_MAX_FILES` (pipeline/rename_stage.py).
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Callable, Iterable, Protocol

import numpy as np

# ---------------------------------------------------------------------------
# Voices -- ported verbatim from epub-to-audio\epub2audio.py's VOICES dict
# (ADR-0014), restricted to the American ("a") and British ("b") English
# voices this app actually uses (04-tts-engine.md §Voice samples confirms
# this scope and that there are no first-name collisions across all 28).
# Exported for reuse by the Epic 8 voice picker, not just this module.
# ---------------------------------------------------------------------------

VOICES: dict[str, str] = {
    # Female  en-us
    "af_heart": "Heart (Female, en-us)",
    "af_alloy": "Alloy (Female, en-us)",
    "af_aoede": "Aoede (Female, en-us)",
    "af_bella": "Bella (Female, en-us)",
    "af_jessica": "Jessica (Female, en-us)",
    "af_kore": "Kore (Female, en-us)",
    "af_nicole": "Nicole (Female, en-us)",
    "af_nova": "Nova (Female, en-us)",
    "af_river": "River (Female, en-us)",
    "af_sarah": "Sarah (Female, en-us)",
    "af_sky": "Sky (Female, en-us)",
    # Male  en-us
    "am_adam": "Adam (Male, en-us)",
    "am_echo": "Echo (Male, en-us)",
    "am_eric": "Eric (Male, en-us)",
    "am_fenrir": "Fenrir (Male, en-us)",
    "am_liam": "Liam (Male, en-us)",
    "am_michael": "Michael (Male, en-us)",
    "am_onyx": "Onyx (Male, en-us)",
    "am_puck": "Puck (Male, en-us)",
    "am_santa": "Santa (Male, en-us)",
    # Female  en-gb
    "bf_alice": "Alice (Female, en-gb)",
    "bf_emma": "Emma (Female, en-gb)",
    "bf_isabella": "Isabella (Female, en-gb)",
    "bf_lily": "Lily (Female, en-gb)",
    # Male  en-gb
    "bm_daniel": "Daniel (Male, en-gb)",
    "bm_fable": "Fable (Male, en-gb)",
    "bm_george": "George (Male, en-gb)",
    "bm_lewis": "Lewis (Male, en-gb)",
}

DEFAULT_VOICE = "af_heart"

# Every voice uses the same sample sentence so a comparison across voices
# is about the voice, not the content (04-tts-engine.md §Voice samples).
VOICE_SAMPLE_TEXT = "Hello! This is what your audiobook will sound like."

# ---------------------------------------------------------------------------
# MP3 encoding constants (04-tts-engine.md §MP3 encoding parameters)
# ---------------------------------------------------------------------------

KOKORO_SAMPLE_RATE = 24_000  # Kokoro-82M's native output rate -- see module docstring.
MP3_BIT_RATE_KBPS = 128
MP3_CHANNELS = 1  # mono

# Direct consequence of 128kbps CBR mono -- this is what makes the
# disk-space estimate formula below exact, not an approximation
# (06-safety-error-handling.md §Resource & cost safety).
BYTES_PER_SECOND_OF_AUDIO = MP3_BIT_RATE_KBPS * 1000 // 8  # 16,000

# Placeholder pending real Kokoro benchmarking data (06-safety-error-
# handling.md §Resource & cost safety) -- derived from ~150 words/minute,
# ~5.7 chars/word (including the space) -> ~0.07 sec/char. Replace this
# one constant, not the formula, once real measured data exists.
SECONDS_PER_CHAR = 0.07


def estimate_audio_bytes(
    total_chars_remaining: int, seconds_per_char: float = SECONDS_PER_CHAR
) -> int:
    """Estimate output audio size in bytes for a given remaining character
    count -- the concrete formula from 06-safety-error-handling.md
    §Resource & cost safety, deliberately biased toward overestimating
    (round up, not down) since an unnecessary disk-space warning is a
    minor annoyance but running out of space mid-batch is a real failure.
    """
    return math.ceil(
        total_chars_remaining * seconds_per_char * BYTES_PER_SECOND_OF_AUDIO
    )


def _lang_code_for_voice(voice: str) -> str:
    """Kokoro's `lang_code` is the single letter a voice key already starts
    with (`af_`/`am_` -> "a", `bf_`/`bm_` -> "b") -- no separate mapping
    table needed."""
    return voice[0]


def _audio_to_numpy(audio: Any) -> np.ndarray:
    """Kokoro's `Result.audio` is a `torch.FloatTensor` -- convert without
    importing torch here (this module has no other reason to depend on
    it directly). Plain numpy/array-like input passes through unchanged,
    which keeps this usable in tests with fake, torch-free audio arrays.
    """
    if hasattr(audio, "detach"):
        audio = audio.detach()
    if hasattr(audio, "cpu"):
        audio = audio.cpu()
    if hasattr(audio, "numpy"):
        audio = audio.numpy()
    return np.asarray(audio, dtype=np.float32)


def _encode_mp3(audio: np.ndarray, sample_rate: int = KOKORO_SAMPLE_RATE) -> bytes:
    """Encode float32 PCM audio (range [-1, 1]) as 128kbps CBR mono MP3."""
    import lameenc

    encoder = lameenc.Encoder()
    encoder.set_bit_rate(MP3_BIT_RATE_KBPS)
    encoder.set_in_sample_rate(sample_rate)
    encoder.set_channels(MP3_CHANNELS)
    encoder.set_quality(2)  # 2 = high quality per lameenc's 0(best)-9(fastest) scale

    pcm_int16 = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16)
    mp3_bytes = encoder.encode(pcm_int16.tobytes())
    mp3_bytes += encoder.flush()
    return bytes(mp3_bytes)


class TTSEngineLike(Protocol):
    """The structural interface `AudioStage`/`BatchRunner` actually need
    from a TTS engine -- just `generate()`. Typed as a Protocol rather
    than the concrete `TTSEngine` class below so tests can supply a
    plain duck-typed fake (never touching real Kokoro) without mypy
    --strict treating it as an argument-type mismatch; a real
    `TTSEngine` instance already satisfies this structurally, no change
    needed at any real call site.
    """

    def generate(self, text: str, voice: str) -> bytes: ...


class TTSEngine:
    """Generates MP3 audio bytes for a chunk of text via Kokoro.

    `pipeline_factory`, if given, replaces `kokoro.KPipeline` -- the seam
    that lets tests supply a fake pipeline instead of downloading and
    running the real ~300MB model (docs/design/PATTERNS.md's general
    testing-seam guidance, same shape as `rename_stage.py`'s injectable
    AI provider).
    """

    def __init__(self, pipeline_factory: Callable[[str], Any] | None = None) -> None:
        self._pipeline_factory = pipeline_factory
        self._pipelines: dict[str, Any] = {}

    def _get_pipeline(self, lang_code: str) -> Any:
        pipeline = self._pipelines.get(lang_code)
        if pipeline is None:
            factory = self._pipeline_factory
            if factory is None:
                from kokoro import KPipeline

                factory = KPipeline
            pipeline = factory(lang_code)
            self._pipelines[lang_code] = pipeline
        return pipeline

    def generate(self, text: str, voice: str) -> bytes:
        """Return 128kbps CBR mono MP3 bytes for *text* spoken in *voice*.

        Raises `ValueError` for an unknown voice key, and lets any
        exception from the underlying pipeline call propagate -- retrying
        a transient failure is the audio stage's job
        (docs/requirements/04-tts-engine.md §Interface sketch), not this
        engine's.
        """
        if voice not in VOICES:
            raise ValueError(f"Unknown voice: {voice!r}")

        pipeline = self._get_pipeline(_lang_code_for_voice(voice))
        segments = [
            _audio_to_numpy(audio) for _, _, audio in pipeline(text, voice=voice)
        ]
        if not segments:
            raise RuntimeError(f"No audio generated for voice {voice!r}")
        full_audio = np.concatenate(segments)
        return _encode_mp3(full_audio)

    def generate_voice_sample(self, voice: str) -> bytes:
        """Generate the standard voice-sample line for *voice*
        (04-tts-engine.md §Voice samples)."""
        return self.generate(VOICE_SAMPLE_TEXT, voice)


def ensure_voice_samples(
    cache_dir: Path,
    tts_engine: TTSEngine,
    kokoro_version: str,
    voices: Iterable[str] = VOICES,
) -> bool:
    """Regenerate the cached `▶ Listen` voice samples if `cache_dir`'s
    tagged `kokoro` version doesn't match the currently installed one
    (04-tts-engine.md §Voice samples §Cache invalidation).

    Returns True if samples were (re)generated, False if the cache was
    already current or regeneration failed. On failure (e.g. offline,
    first-run model download not reachable), existing samples are left
    untouched rather than deleted first -- a stale preview is a smaller
    problem than no preview, and a future launch retries the same check.
    """
    version_path = cache_dir / "version.txt"
    current = version_path.read_text().strip() if version_path.exists() else None
    if current == kokoro_version:
        return False

    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        for voice in voices:
            sample_bytes = tts_engine.generate_voice_sample(voice)
            (cache_dir / f"{voice}.mp3").write_bytes(sample_bytes)
        version_path.write_text(kokoro_version)
        return True
    except Exception:
        return False
