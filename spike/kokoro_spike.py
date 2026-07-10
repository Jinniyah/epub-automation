"""Kokoro/PyInstaller packaging spike (Epic 1). COMPLETE as of 2026-07-08.

Purpose: verify that kokoro can be imported, the model loaded, and audio
generated; then confirm the same works inside a PyInstaller-built .exe.

FINDINGS (spike portion completed 2026-07-06):
  - kokoro==0.9.4 confirmed installable.
  - misaki[en] (English G2P) requires espeakng-loader==0.2.4, which ships
    espeak-ng.dll + espeak-ng-data/ as a Python wheel.  This IS the native
    dependency flagged in the pre-coding design review.
  - KPipeline imports and the espeak-ng DLL loads correctly (confirmed by
    running this script with `python spike/kokoro_spike.py`).
  - Model weights (~300MB) download from HuggingFace on first run; CPU-only
    torch (torch==2.12.1+cpu) is used — no CUDA/GPU required.

FINDINGS (full PyInstaller build + end-to-end .exe test completed 2026-07-08):
  - Three further data-only packaging gaps found, all the same underlying
    cause as espeak-ng above (a data file loaded via ctypes/
    importlib.resources at runtime, invisible to PyInstaller's static
    import-graph analysis) — none of these were caught by the 2026-07-06
    spike because that only ran inside an activated venv, never as a
    built exe:
      * phonemizer -> csvw -> language_tags ships data/json/index.json
      * misaki ships its own G2P dictionary data (e.g. data/us_gold.json)
      * soundfile wraps the native libsndfile binary
  - One genuinely new runtime dependency, not just a build flag: misaki's
    English G2P auto-downloads spaCy's en_core_web_sm model via `pip` on
    first use if absent. That succeeds silently in a venv (pip exists),
    which is why the spike run didn't catch it — but a frozen .exe has no
    pip executable to shell out to, so it fails hard ("No package
    installer found") and aborts the whole process. Fixed by
    pre-installing the model as a wheel before building (see Step 2 below)
    so misaki finds it already present and never attempts the download.
    Now pinned in requirements.txt.
  - Verified result: dist\\kokoro_spike.exe, run standalone on Windows (no
    venv activation needed to *run* it, only to *build* it), completes all
    5 steps below and writes a real 153KB spike_output.wav.

See 07-packaging-deployment.md §Known packaging constraints for the full
writeup, and docs/BACKLOG.md Epic 1 for the session history.

Usage:
  # Step 1 — verify normal execution (downloads model weights on first run)
  .venv\\Scripts\\python spike\\kokoro_spike.py

  # Step 2 — build a minimal .exe and verify it produces spike_output.wav
  # (PowerShell syntax below — use ^ instead of ` for cmd.exe)
  .venv\\Scripts\\pip install pyinstaller
  .venv\\Scripts\\pip install https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl
  .venv\\Scripts\\pyinstaller --onefile `
      --collect-data espeakng_loader `
      --collect-data language_tags `
      --collect-data misaki `
      --collect-all en_core_web_sm `
      --collect-all torch `
      --collect-all transformers `
      --collect-all kokoro `
      --collect-all soundfile `
      spike\\kokoro_spike.py
  dist\\kokoro_spike.exe
"""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    print("=== Kokoro/PyInstaller Packaging Spike ===\n")

    # 1. Verify espeakng_loader can find and load the native DLL.
    print("Step 1: load espeak-ng native library...")
    import espeakng_loader

    espeakng_loader.make_library_available()
    dll_path = espeakng_loader.get_library_path()
    data_path = espeakng_loader.get_data_path()
    print(f"  espeak-ng.dll : {dll_path}")
    print(f"  espeak-ng-data: {data_path}")
    print("  OK\n")

    # 2. Import KPipeline — this triggers misaki's phonemizer init.
    print("Step 2: import KPipeline...")
    from kokoro import KPipeline

    print("  OK\n")

    # 3. Instantiate the pipeline (downloads model weights ~300MB on first run).
    print("Step 3: init KPipeline(lang_code='a') [American English]...")
    print("  NOTE: first run downloads ~300MB from HuggingFace — may take time.")
    pipeline = KPipeline(lang_code="a")
    print("  OK\n")

    # 4. Generate audio for the standard voice-sample sentence.
    sample_text = "Hello! This is what your audiobook will sound like."
    voice = "af_heart"
    print(f"Step 4: generate audio — voice={voice!r}...")
    chunks = list(pipeline(sample_text, voice=voice))
    if not chunks:
        print("  ERROR: no audio chunks generated")
        sys.exit(1)
    print(f"  OK — {len(chunks)} chunk(s) returned\n")

    # 5. Save the first chunk as a WAV for manual verification.
    print("Step 5: save spike_output.wav...")
    try:
        import soundfile as sf

        _graphemes, _phonemes, audio = chunks[0]
        out = Path("spike_output.wav")
        sf.write(str(out), audio, samplerate=24000)
        print(f"  Saved: {out.resolve()}\n")
    except ImportError:
        print("  soundfile not installed — skipping WAV save.")
        print("  (audio generation itself succeeded — that is what matters.)\n")

    print("=== Spike PASSED ===")
    print("kokoro imports, the espeak-ng DLL loads, and audio is generated.")


if __name__ == "__main__":
    main()
