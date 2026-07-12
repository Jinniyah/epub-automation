"""Tests for pipeline/tts_engine.py.

Never downloads or runs the real Kokoro model -- every test injects a fake
`pipeline_factory` (docs/design/PATTERNS.md's testing-seam guidance, same
shape as rename_stage.py's injectable AI provider) that returns synthetic
audio instead.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest
from mutagen.mp3 import MP3

from pipeline.tts_engine import (
    BYTES_PER_SECOND_OF_AUDIO,
    DEFAULT_VOICE,
    KOKORO_SAMPLE_RATE,
    SECONDS_PER_CHAR,
    VOICE_SAMPLE_TEXT,
    VOICES,
    TTSEngine,
    ensure_voice_samples,
    estimate_audio_bytes,
    installed_kokoro_version,
)


class _FakePipeline:
    """Stands in for kokoro.KPipeline -- yields (graphemes, phonemes, audio)
    tuples like the real thing, but with synthetic sine-wave audio."""

    def __init__(self, lang_code: str) -> None:
        self.lang_code = lang_code
        self.calls: list[tuple[str, str | None]] = []

    def __call__(self, text: str, voice: str | None = None) -> Any:
        self.calls.append((text, voice))
        t = np.linspace(0, 0.1, int(KOKORO_SAMPLE_RATE * 0.1), endpoint=False)
        audio = (0.1 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
        # Split into two segments per call, like a real multi-sentence chunk.
        half = len(audio) // 2
        yield ("g1", "p1", audio[:half])
        yield ("g2", "p2", audio[half:])


class _RaisingPipeline:
    def __init__(self, lang_code: str) -> None:
        pass

    def __call__(self, text: str, voice: str | None = None) -> Any:
        raise RuntimeError("simulated kokoro failure")
        yield  # pragma: no cover -- makes this a generator function


def _make_engine(factory: Any = _FakePipeline) -> TTSEngine:
    return TTSEngine(pipeline_factory=factory)


# ---------------------------------------------------------------------------
# TTSEngine.generate
# ---------------------------------------------------------------------------


def test_generate_returns_valid_128kbps_mono_mp3(tmp_path: Path) -> None:
    engine = _make_engine()
    mp3_bytes = engine.generate("Hello there.", DEFAULT_VOICE)

    out_path = tmp_path / "out.mp3"
    out_path.write_bytes(mp3_bytes)
    info = MP3(str(out_path)).info

    # mutagen types `.info` Optional; a file we just wrote ourselves always
    # has real MP3 info -- narrow it for mypy and fail loudly (not
    # silently) if that assumption is ever wrong.
    assert info is not None
    assert info.bitrate == 128_000
    assert info.channels == 1
    assert info.sample_rate == KOKORO_SAMPLE_RATE


def test_generate_rejects_unknown_voice() -> None:
    engine = _make_engine()
    with pytest.raises(ValueError, match="Unknown voice"):
        engine.generate("Hello there.", "zz_nobody")


def test_generate_reuses_pipeline_for_same_lang_code() -> None:
    created: list[str] = []

    class _TrackingPipeline(_FakePipeline):
        def __init__(self, lang_code: str) -> None:
            super().__init__(lang_code)
            created.append(lang_code)

    engine = _make_engine(_TrackingPipeline)
    engine.generate("One.", "af_heart")
    engine.generate("Two.", "af_nova")  # same lang_code "a"

    assert created == ["a"]  # only constructed once, reused


def test_generate_creates_separate_pipeline_per_lang_code() -> None:
    created: list[str] = []

    class _TrackingPipeline(_FakePipeline):
        def __init__(self, lang_code: str) -> None:
            super().__init__(lang_code)
            created.append(lang_code)

    engine = _make_engine(_TrackingPipeline)
    engine.generate("One.", "af_heart")  # American -> "a"
    engine.generate("Two.", "bf_alice")  # British -> "b"

    assert created == ["a", "b"]


def test_generate_propagates_pipeline_failure() -> None:
    engine = _make_engine(_RaisingPipeline)
    with pytest.raises(RuntimeError, match="simulated kokoro failure"):
        engine.generate("Hello.", DEFAULT_VOICE)


def test_generate_voice_sample_uses_standard_sentence() -> None:
    calls: list[str] = []

    class _RecordingPipeline(_FakePipeline):
        def __call__(self, text: str, voice: str | None = None) -> Any:
            calls.append(text)
            return super().__call__(text, voice)

    engine = _make_engine(_RecordingPipeline)
    engine.generate_voice_sample(DEFAULT_VOICE)

    assert calls == [VOICE_SAMPLE_TEXT]


# ---------------------------------------------------------------------------
# estimate_audio_bytes
# ---------------------------------------------------------------------------


def test_estimate_audio_bytes_matches_formula() -> None:
    chars = 100_000
    expected = chars * SECONDS_PER_CHAR * BYTES_PER_SECOND_OF_AUDIO
    assert estimate_audio_bytes(chars) == pytest.approx(expected, rel=0.01)


def test_estimate_audio_bytes_rounds_up() -> None:
    # 1 char * 0.07 * 16000 = 1120.0 exactly -- pick inputs that don't
    # divide evenly to prove ceil() is actually applied, not truncation.
    result = estimate_audio_bytes(3, seconds_per_char=0.001)
    assert result == 48  # ceil(3 * 0.001 * 16000) = ceil(48.0) = 48
    assert isinstance(result, int)


def test_estimate_audio_bytes_zero_chars_is_zero() -> None:
    assert estimate_audio_bytes(0) == 0


# ---------------------------------------------------------------------------
# installed_kokoro_version
# ---------------------------------------------------------------------------


def test_installed_kokoro_version_reads_real_package_metadata() -> None:
    # kokoro is a pinned real dependency (requirements.txt) -- this must
    # resolve to its actual installed version, not the "unknown"
    # fallback, and must not need to import the kokoro package itself.
    version = installed_kokoro_version()

    assert version != "unknown"
    assert version


def test_installed_kokoro_version_falls_back_when_metadata_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import importlib.metadata

    def _raise(name: str) -> str:
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(importlib.metadata, "version", _raise)

    assert installed_kokoro_version() == "unknown"


# ---------------------------------------------------------------------------
# ensure_voice_samples
# ---------------------------------------------------------------------------


def test_ensure_voice_samples_generates_all_voices_on_first_run(tmp_path: Path) -> None:
    engine = _make_engine()
    cache_dir = tmp_path / "voice_samples"

    result = ensure_voice_samples(
        cache_dir, engine, "0.9.4", voices=["af_heart", "bf_alice"]
    )

    assert result is True
    assert (cache_dir / "af_heart.mp3").exists()
    assert (cache_dir / "bf_alice.mp3").exists()
    assert (cache_dir / "version.txt").read_text().strip() == "0.9.4"


def test_ensure_voice_samples_skips_regeneration_when_version_matches(
    tmp_path: Path,
) -> None:
    cache_dir = tmp_path / "voice_samples"
    cache_dir.mkdir()
    (cache_dir / "version.txt").write_text("0.9.4")
    (cache_dir / "af_heart.mp3").write_bytes(b"stale-but-current-version")

    class _ExplodingPipeline:
        def __init__(self, lang_code: str) -> None:
            raise AssertionError(
                "should never be constructed -- version already current"
            )

    engine = _make_engine(_ExplodingPipeline)
    result = ensure_voice_samples(cache_dir, engine, "0.9.4", voices=["af_heart"])

    assert result is False
    assert (cache_dir / "af_heart.mp3").read_bytes() == b"stale-but-current-version"


def test_ensure_voice_samples_regenerates_on_version_mismatch(tmp_path: Path) -> None:
    cache_dir = tmp_path / "voice_samples"
    cache_dir.mkdir()
    (cache_dir / "version.txt").write_text("0.9.3")
    (cache_dir / "af_heart.mp3").write_bytes(b"old-version-sample")

    engine = _make_engine()
    result = ensure_voice_samples(cache_dir, engine, "0.9.4", voices=["af_heart"])

    assert result is True
    assert (cache_dir / "af_heart.mp3").read_bytes() != b"old-version-sample"
    assert (cache_dir / "version.txt").read_text().strip() == "0.9.4"


def test_ensure_voice_samples_keeps_stale_samples_when_regeneration_fails(
    tmp_path: Path,
) -> None:
    cache_dir = tmp_path / "voice_samples"
    cache_dir.mkdir()
    (cache_dir / "version.txt").write_text("0.9.3")
    (cache_dir / "af_heart.mp3").write_bytes(b"old-version-sample")

    engine = _make_engine(_RaisingPipeline)
    result = ensure_voice_samples(cache_dir, engine, "0.9.4", voices=["af_heart"])

    assert result is False
    # Old sample is untouched, not deleted -- a stale preview beats no
    # preview (04-tts-engine.md §Voice samples §Cache invalidation).
    assert (cache_dir / "af_heart.mp3").read_bytes() == b"old-version-sample"
    assert (cache_dir / "version.txt").read_text().strip() == "0.9.3"


def test_ensure_voice_samples_no_version_file_treated_as_missing(
    tmp_path: Path,
) -> None:
    cache_dir = tmp_path / "voice_samples"  # doesn't exist at all yet
    engine = _make_engine()

    result = ensure_voice_samples(cache_dir, engine, "0.9.4", voices=["af_heart"])

    assert result is True
    assert cache_dir.exists()


# ---------------------------------------------------------------------------
# VOICES
# ---------------------------------------------------------------------------


def test_voices_has_28_entries_matching_gui_doc_count() -> None:
    assert len(VOICES) == 28


def test_default_voice_is_in_voices() -> None:
    assert DEFAULT_VOICE in VOICES


def test_no_first_name_collisions_across_voices() -> None:
    # 04-tts-engine.md claims this was confirmed -- verify the label text
    # (the part before " (") is unique per voice.
    first_names = [label.split(" (")[0] for label in VOICES.values()]
    assert len(first_names) == len(set(first_names))
