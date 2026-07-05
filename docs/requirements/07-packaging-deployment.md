# Packaging & Deployment

## Target: single bundled `.exe` via PyInstaller

Chosen specifically for the mother's use case — no Python installation,
no terminal, no setup steps beyond double-clicking a desktop icon.

## Build pipeline (author-side, not her-side)

1. `npm run build` in `frontend/` → produces a static `dist/` bundle
   (HTML/CSS/JS). Node.js is a build-time-only tool; never required on
   her machine.
2. PyInstaller bundles that static `dist/` output alongside the Python
   backend (`launcher.py`, `backend/`, `pipeline/`) into the final
   `.exe`.

## What she experiences on launch

1. Double-clicks a desktop shortcut.
2. `launcher.py` starts Flask (via waitress) quietly in the background —
   no visible console window she could accidentally close.
3. Finds a free local port automatically.
4. Opens her default browser directly to the running app — she never
   sees or types a URL.
5. If she double-clicks the icon again while already running, it opens a
   new tab to the existing server rather than starting a second instance
   (single-instance lock, see `01-architecture.md` and
   `06-safety-error-handling.md`).

## Windows SmartScreen (decided during review)

**The problem, stated precisely:** an unsigned PyInstaller `.exe`
triggers Windows' "Windows protected your PC" SmartScreen warning,
requiring an unfamiliar "More info → Run anyway" click-through. This is
an **OS-level dialog that appears before the browser/webpage exists at
all** — it's the very first thing she'd see on double-clicking the icon,
before `launcher.py` even starts Flask. Nothing built into the app's
webpage can address this specific moment, since there's no webpage yet
when it happens.

**Decision: don't pay for code signing.** A standard (OV) certificate
doesn't suppress SmartScreen immediately — Windows builds trust from
download volume over time, and a small family-scale app would likely
still trigger the warning for a long while even signed. An EV certificate
does get instant trust, but costs several hundred dollars/year and
requires business verification — disproportionate for this project's
scale, and explicitly not worth it just to remove one click-through.

**Primary fix: she should never see it at all.** This follows the same
pattern already established for AI key provisioning
(`03-gui-ux-design.md` §AI Helper Setup) — a technical family member
handles the one-time technical friction before handing the machine over:

- Whoever installs the app for her runs the `.exe` themselves first and
  clicks through "More info → Run anyway" once.
- Windows remembers that specific `.exe` was explicitly allowed and will
  not ask again on that machine, for that file.
- This costs nothing, requires no code changes, and means the SmartScreen
  dialog is a one-time technical-setup step (like the AI key), not
  something she personally has to navigate — consistent with this
  project's general approach of front-loading technical friction onto
  whoever's setting the machine up, not onto her.

**Fallback, for the rare case she reinstalls without help nearby:** a
short local HTML file (not a PDF, not a printed sheet — matching this
project's own tech stack rather than introducing a new artifact type),
two sentences plus one screenshot, showing exactly which two things to
click. This can't be shown inside the running app itself (per the timing
problem above), so it lives as a separate file next to the shortcut —
something she already has access to, not something the app displays.

## Browser-launch fallback (resolved during review)

Step 4 above (`webbrowser.open()` or equivalent) can fail — no default
browser registered, a broken/corrupted browser install, or a transient
OS hiccup. Unlike the SmartScreen problem above, **the Flask server is
already running by this point** — the only thing that failed is opening
a window to it, which makes this a much easier problem to solve well:

1. **Retry once, automatically, after a short delay** (e.g. 1 second) —
   covers the most common case (a transient failure right after login
   or wake-from-sleep) without her ever seeing anything.
2. **If it still fails, fall back to a native dialog via `tkinter`** —
   already a dependency for the folder-picker dialogs
   (`01-architecture.md`), so this adds nothing new to the build. Shows
   the local address in large, plain text: *"Almost there! Please open
   any web browser and go to this address:"* followed by the address
   itself.
3. **The address is automatically copied to her clipboard** the moment
   this dialog appears — she pastes, she doesn't type or transcribe.
   Asking her to read and accurately retype a URL would contradict the
   "no typing required in normal flow" principle
   (`03-gui-ux-design.md` §General principles) just as much as any
   in-app text field would.
4. **A "Try Again" button** on the same dialog re-attempts the automatic
   browser launch, in case whatever caused the failure resolves itself
   before she's tried pasting the address manually.

This dialog is deliberately minimal and native (not a webpage — there's
nowhere to show a webpage yet, since a browser window is exactly what
failed to open) but otherwise follows the same plain-language, no-typing
principles as the rest of the app.

## First-run setup requirements

Two one-time downloads need clear, friendly messaging distinct from
normal batch processing status, since both can take real time:

- **Kokoro model weights** (~300MB from Hugging Face) — see
  `04-tts-engine.md`. Cached after first download; fully offline-capable
  afterward. **Timing (resolved during review):** this download is
  triggered lazily, the first time an install actually needs the audio
  stage or the voice picker — not unconditionally at first launch before
  Screen 1 is shown — so a first launch on a machine without internet
  yet can still use "Fix messy file names" and "Clean up bad language"
  normally. See `04-tts-engine.md` §First-run setup for the exact trigger
  point.
- **Voice sample pre-generation** — all ~28 voice samples generated once
  and cached, at the same setup moment as the model download above (so
  the same lazy trigger point applies to both).

Suggested framing for both: a single *"Setting up for the first time...
this only happens once"* screen, shown at whichever moment the trigger
above actually fires, rather than two separate unexplained delays or a
delay that appears regardless of whether that session ever needs it.

## Known packaging constraints to design around

- PyInstaller bundles the Python runtime and dependencies, so the
  resulting `.exe` will be large — expected and not a bug to chase down.
- The settings/data directory (`%APPDATA%\EpubAutomation\`) must live
  **outside** wherever the `.exe` itself is installed, so it survives
  future app updates (see `05-data-settings-and-logging.md`).
- Since the TTS engine is now local Kokoro rather than Selenium/Chrome
  (see `04-tts-engine.md`), the previously-planned "Chrome isn't
  installed" first-run check is no longer needed — this removes a
  dependency and a failure mode from the packaging story entirely.
- **Kokoro's own native-dependency footprint, flagged during review, not
  yet resolved:** ML packages like `kokoro` (PyTorch/ONNX-backed) are a
  common source of PyInstaller hidden-import failures — dynamically
  loaded extension modules and backend-selection logic that pure static
  analysis can miss — and some Kokoro deployments additionally depend on
  `espeak-ng`, a native (non-Python) binary, for grapheme-to-phoneme
  conversion. Neither risk is confirmed one way or the other for the
  specific `kokoro` version and the American/British-English-only voice
  scope this project actually uses (`04-tts-engine.md` §Voice samples).
  **Recommended before relying on the packaging plan above:** an early,
  small spike — package a minimal "load Kokoro, generate one sample"
  script with PyInstaller, before investing implementation time
  elsewhere — specifically to confirm whether any native binary needs to
  be located and bundled, and if so, add that bundling step here as a
  named build requirement rather than discovering it late in packaging.

## Uninstalling

**Simple by design, matching the simple install:**

- Delete the desktop shortcut and the `.exe` (or its install folder).
- Delete `%APPDATA%\EpubAutomation\` — this removes everything the app
  ever stored: settings, both remembered folders' paths, her custom
  profanity list, the audit log, the state file, the cached voice
  samples, and the internal `Library\` working folders (see
  `05-data-settings-and-logging.md` §Where settings live for the full
  list of what lives there). Her actual book files and finished
  audiobooks are untouched either way — nothing under `%APPDATA%`
  overlaps with her `books_folder` or `output_folder` content;
  `Library\` only ever holds internal working *copies*, and anything
  already finished was already copied out to `output_folder` as it
  completed (see `01-architecture.md` §Folder mapping), so deleting an
  in-progress `Library\` working copy loses nothing she doesn't still
  have a source or finished copy of elsewhere.
- No uninstaller script needed for v1 — two manual deletions is
  consistent with "a plain `.exe` + desktop shortcut" being sufficient
  for this deployment's scale (see §Explicitly out of scope for v1
  below).

**New-machine migration is explicitly out of scope (decided during
review):** if she gets a new computer, the answer is a fresh install, not
a migration path. Her actual books and audiobooks live in whatever
folders she picked (not tied to the old machine), so a fresh install
plus pointing "Change my folders" at the same books/output locations
(if they're on a shared drive) or just starting fresh is sufficient.
Nothing needs to be built to support copying `%APPDATA%\EpubAutomation\`
between machines — this was considered and deliberately not pursued, to
avoid designing a migration feature nobody asked for.

## Explicitly out of scope for v1

- Auto-update mechanism for the shipped `.exe` (noted in
  `00-overview-and-goals.md` as a future consideration).
- Code signing / installer (MSI, etc.) — decided against for cost/benefit
  reasons specific to SmartScreen, see §Windows SmartScreen above; a
  plain `.exe` + desktop shortcut remains sufficient for this
  deployment's scale (family use, not public distribution).
- An uninstaller script, and any new-machine migration/import tooling
  (see §Uninstalling above) — manual deletion and fresh installs are both
  sufficient at this scale.
