# Packaging & Deployment

## Target: single bundled `.exe` via PyInstaller

Chosen for the mother's use case — no Python install, no terminal, no
setup beyond double-clicking a desktop icon.

## Testing-phase stand-in: `run_gui.vbs` (docs/BACKLOG.md Epic 10 Phase A)

Before the real `.exe` (Phase B) exists, `run_gui.vbs` (repo root) gets
her to the same "no visible console, one double-click" experience for
real-person testing, without any PyInstaller/signing/installer work: a
`pythonw.exe` (the windowless CPython interpreter, already present in
any normal install) wrapper around `launcher.py`. Whoever sets her up
creates a desktop shortcut to this file the same way they'd eventually
hand her a shortcut to the real `.exe`. **Explicitly not a substitute
for real packaging** — she still needs Python and this project's
`.venv` set up on whatever machine she tests on first (same one-time
technical-friction pattern as AI-key provisioning and the SmartScreen
click-through below), and this file is never what actually ships.
Live-verified via `cscript` (2026-07-18): no console window, no
lingering process after `/api/quit`.

## Build pipeline (author-side)

1. `npm run build` in `frontend/` → static `dist/` bundle. Node.js is
   build-time only, never required on her machine.
2. PyInstaller bundles `dist/` alongside `launcher.py`, `backend/`,
   `pipeline/` into the final `.exe`.

## What she experiences on launch

1. Double-clicks a desktop shortcut.
2. `launcher.py` starts Flask (waitress) quietly, no visible console.
3. Finds a free local port automatically.
4. Opens her default browser directly — she never sees or types a URL.
5. Re-launching while already running opens a new tab to the existing
   server (single-instance lock).

## Windows SmartScreen

**Problem:** an unsigned `.exe` triggers SmartScreen's "Run anyway"
click-through — an OS-level dialog that appears *before* Flask/the
browser exist, so nothing in-app can address it.

**Decision: no code signing purchased.** A standard cert doesn't
suppress SmartScreen immediately; an EV cert gives instant trust but
costs several hundred dollars/year plus business verification —
disproportionate for this project's scale (ADR-0011).

**Primary fix:** whoever installs the app for her runs the `.exe` once
first and clicks through "More info → Run anyway." Windows remembers
that specific file thereafter — same pattern as AI key provisioning
(a technical family member absorbs the one-time friction).

**Fallback:** a short local HTML file (two sentences + one screenshot)
next to the shortcut, for the rare reinstall-without-help case.

## Browser-launch fallback

`webbrowser.open()` can fail (no default browser, broken install,
transient OS hiccup) — but the Flask server is already running by this
point, so:

1. Retry once automatically after ~1 second.
2. If still failing, native `tkinter` dialog (already a dependency for
   folder pickers) showing the local address in large plain text.
3. Address auto-copied to clipboard — she pastes, never types/transcribes.
4. "Try Again" button re-attempts the automatic launch.

## First-run setup requirements

- **Kokoro model weights** (~300MB from Hugging Face) — cached after
  first download, fully offline afterward. Triggered **lazily**, first
  actual need (not eager at launch), so a fresh install without
  internet can still use rename/sanitize normally.
- **Voice sample pre-generation** (~28 samples) — same lazy trigger
  point as the model download.

Suggested framing: one *"Setting up for the first time..."* screen at
whichever moment the trigger fires.

## Known packaging constraints

- `.exe` will be large (multi-GB) — expected, not a bug to chase.
- `%APPDATA%\EpubAutomation\` must live outside the `.exe`'s install
  location, so it survives app updates.
- Local Kokoro (not Selenium/Chrome) removes the "Chrome isn't
  installed" first-run check entirely.

### Kokoro native-dependency footprint — confirmed, verified 2026-07-08

`kokoro==0.9.4` → `misaki[en]` → `espeakng-loader==0.2.4` ships
`espeak-ng.dll` + `espeak-ng-data/` as a Python wheel — loaded via
`ctypes` at runtime, invisible to PyInstaller's static analysis. The
full build+exe test (running the actual built `.exe`, not just a venv)
surfaced three further gaps of the same kind (data loaded via
ctypes/`importlib.resources`) plus one genuinely new runtime
dependency:

- `language_tags` (via `phonemizer`→`csvw`) ships bundled JSON data
- `misaki` ships its own G2P dictionary data
- `soundfile` wraps the native `libsndfile` binary
- **New dependency:** `en_core_web_sm` (spaCy model) — misaki
  auto-downloads it via `pip` on first use if absent, which works in a
  venv but fails inside a frozen exe (no `pip` available). Fixed by
  pre-installing the wheel before building.

**Confirmed working build command:**

```
pip install https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl

pyinstaller --onefile \
    --collect-data espeakng_loader \
    --collect-data language_tags \
    --collect-data misaki \
    --collect-all en_core_web_sm \
    --collect-all torch \
    --collect-all transformers \
    --collect-all kokoro \
    --collect-all soundfile \
    spike/kokoro_spike.py
```

(See `spike/kokoro_spike.py` for the full spike script.)

**Verification: done.** `dist\kokoro_spike.exe`, run standalone on
Windows, produced a real 153KB `spike_output.wav`. Tracked in
`docs/BACKLOG.md` Epic 1 (complete).

## Uninstalling

- Delete the desktop shortcut + `.exe`.
- Delete `%APPDATA%\EpubAutomation\` — removes settings, both
  remembered folder paths, her profanity list, audit log, state file,
  cached voice samples, and internal `Library\` working copies. Her
  actual books/audiobooks are untouched — everything under `%APPDATA%`
  is internal working state or already-copied-out finished output.
- No uninstaller script for v1 — two manual deletions is sufficient at
  this scale.

**New-machine migration out of scope** — fresh install + re-pointing
"Change my folders" is the supported path; nothing needs building to
copy `%APPDATA%\EpubAutomation\` between machines.

## Explicitly out of scope for v1

- Auto-update mechanism.
- Code signing / installer (MSI) — see §Windows SmartScreen.
- Uninstaller script, migration/import tooling.
