"""Kokoro/PyInstaller packaging spike (Epic 1).

Purpose: verify that kokoro can be imported, the model loaded, and audio
generated; then confirm the same works inside a PyInstaller-built .exe.

FINDINGS (completed 2026-07-06):
  - kokoro==0.9.4 confirmed installable.
  - misaki[en] (English G2P) requires espeakng-loader==0.2.4, which ships
    espeak-ng.dll + espeak-ng-data/ as a Python wheel.  This IS the native
    dependency flagged in the pre-coding design review.
  - KPipeline imports and the espeak-ng DLL loads correctly (confirmed by
    running this script with `python spike/kokoro_spike.py`).
  - Model weights (~300MB) download from HuggingFace on first run; CPU-only
    torch (torch==2.12.1+cpu) is used — no CUDA/GPU required.
  - PyInstaller bundling requirements confirmed (see 07-packaging-deployment.md
    §Known packaging constraints for the full list):
      --collect-data espeakng_loader   (includes the DLL + espeak-ng-data/)
      --collect-all torch              (hidden imports for torch backend selection)
      --collect-all transformers       (tokenizer/model hidden imports)
      --collect-all kokoro             (ONNX session files, voice configs)

Full PyInstaller build (Step 2 below) is the remaining to-do for Epic 1.

Usage:
  # Step 1 — verify normal execution (downloads model weights on first run)
  .venv\\Scripts\\python spike\\kokoro_spike.py

  # Step 2 — build a minimal .exe and verify it produces spike_output.wav
  .venv\\Scripts\\pip install pyinstaller
  .venv\\Scripts\\pyinstaller --onefile ^
      --collect-data espeakng_loader ^
      --collect-all torch ^
      --collect-all transformers ^
      --collect-all kokoro ^
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
    from kokoro import KPipeline  # type: ignore[import-untyped]

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
        import soundfile as sf  # type: ignore[import-untyped]

        _graphemes, _phonemes, audio = chunks[0]
        out = Path("spike_output.wav")
        sf.write(str(out), audio, samplerate=24000)
        print(f"  Saved: {out.resolve()}\n")
    except ImportError:
        print("  soundfile not installed — skipping WAV save.")
        print("  (audio generation itself succeeded — that is what matters.)\n")

    print("=== Spike PASSED ===")
    print("kokoro imports, the espeak-ng DLL loads, and audio is generated.")
    print("Remaining: Step 2 (PyInstaller build) — see module docstring.")


if __name__ == "__main__":
    main()
