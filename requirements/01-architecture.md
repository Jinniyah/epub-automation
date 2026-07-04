# Architecture

## Tech stack summary

| Layer | Choice | Notes |
|---|---|---|
| Core pipeline | Python 3.11+ | Single language across all stages (sanitize ported from PowerShell) |
| GUI backend | Flask, served via `waitress`, bound to `127.0.0.1` only | Not Flask's dev server — needs to run stable for hours unattended. See §Network Binding & Security below — the localhost bind is a hard requirement, not a default. |
| GUI frontend | React (built with Vite), static build bundled into the app | Dev-time only needs Node; shipped `.exe` contains only the compiled static output |
| TTS engine | `kokoro` Python package (Kokoro-82M, Apache 2.0) | Replaces the original Selenium/Perchance browser-automation approach entirely |
| AI metadata enrichment | Pluggable provider (Gemini, OpenAI, or none) | User-selected and user-keyed — no single provider or embedded key baked into the app; see `ai_providers/` below and `03-gui-ux-design.md` §AI Helper Setup |
| Packaging | PyInstaller, single `.exe` | React `dist/` bundled alongside Python backend |
| Process model | Local launcher starts Flask/waitress in background, opens default browser to it | Not pywebview — chosen specifically so closing the browser tab doesn't kill an in-progress multi-hour audio job |

## High-level flow

```
Browser (React)  <--HTTP-->  Flask API (waitress)  <-->  pipeline/ (shared engine)
                                    |
                                    |-- native folder-picker dialogs (tkinter.filedialog)
                                    |-- reads/writes Library/, settings.json, audit log
                                    |-- calls kokoro directly for TTS (no browser/Selenium)
```

The **same `pipeline/` functions** are called by both the CLI (`main.py`) and
the Flask API (`backend/app.py`). Neither front end contains pipeline logic
itself — they are both thin callers.

## CLI: reserved `--workers` flag (decided during review)

`main.py`'s `audio` command accepts a `--workers N` flag, **defaulting to
`1`** (serial, matching the GUI's behavior and rationale exactly). This
is a reserved seam, not a currently-implemented parallel-execution
feature — see the `08-open-questions-and-assumptions.md` for the reasoning:
the GUI stays serial-only always (progress-reporting simplicity for her
persona, plus Kokoro's memory footprint making concurrent jobs a real
resource problem, see §Single-instance behavior below), but the
CLI/advanced front door shouldn't be architecturally prevented from
adding real parallelism later just because the GUI doesn't need it. The
flag exists now so the pipeline engine's design doesn't have to be
revisited if parallelism is ever added — it does not need to *do*
anything beyond validate and default to `1` for this version.

## Project structure

```
epub-automation/
├── main.py                    # CLI entry point: rename | sanitize | audio | retag | all
├── launcher.py                # Starts Flask/waitress, opens browser, single-instance lock
├── backend/
│   ├── app.py                 # Flask API routes (JSON API, see 03-gui-ux-design.md)
│   ├── dialogs.py             # Native folder-picker bridge (tkinter.filedialog)
│   └── bridge.py              # Adapts pipeline/ functions to HTTP request/response + polling state
├── frontend/                  # React + Vite project (dev-time only)
│   ├── src/
│   ├── package.json
│   └── dist/                  # Built static output — this is what gets bundled into the .exe
├── pipeline/
│   ├── rename_stage.py        # AI-assisted rename (from epub-renamer)
│   ├── sanitize_stage.py      # Profanity cleaning (ported from epub-sanitize PowerShell)
│   ├── audio_stage.py         # Batch TTS conversion (from epub-to-audio, browser removed) — uses mutagen (GPL-2.0-or-later), see 10-licensing-and-notices.md
│   ├── retag_stage.py         # Manual post-hoc MP3 tag/filename fixer (from retag.py) — uses mutagen (GPL-2.0-or-later), see 10-licensing-and-notices.md
│   ├── tts_engine.py          # Thin wrapper around kokoro.KPipeline
│   ├── epub_reader.py         # Shared EPUB DC-metadata extraction — uses ebooklib (AGPL-3.0-or-later), see 10-licensing-and-notices.md
│   ├── epub_utils.py          # Shared chunking, filename parsing, sanitize() helper
│   ├── ai_providers/
│   │   ├── base.py            # Abstract AIProvider interface
│   │   ├── registry.py        # Provider registry — maps a provider key ("gemini", "openai", "none") to an implementation
│   │   ├── gemini_provider.py # Gemini implementation (works with either free-tier or paid key)
│   │   ├── openai_provider.py # OpenAI implementation (paid key required)
│   │   └── null_provider.py   # Offline / "no AI helper" fallback — passthrough of EPUB metadata only
│   ├── state_manager.py       # Per-stage processed-file tracking, resume support
│   ├── audit_logger.py        # Unified CSV audit log across all stages
│   └── config.py              # Settings load/save (settings.json), env/default merging
├── Library/                    # DEV-TIME ONLY — at runtime this does not live here;
│   ├── 00-Incoming/            # see §Folder mapping below, it actually lives at
│   ├── 01-Renamed/             # %APPDATA%\EpubAutomation\Library\, for the same
│   ├── 02-Sanitized/           # reason settings.json isn't bundled with the .exe:
│   └── 03-Audio/               # stays writable, survives app updates.
├── profanity.txt              # Bundled default list (starter: 66 words, see source repo)
├── requirements.txt
├── .env.example                # For CLI/advanced use only — GUI never exposes env vars directly
├── tests/                      # see 09-testing-strategy.md — 80%+ coverage target, TDD workflow
└── README.md
```

## Status endpoint contract (`bridge.py`)

`03-gui-ux-design.md` specifies polling ("React calls a status endpoint
every few seconds") but never defines what that endpoint returns. This is
the contract `bridge.py` must implement and every screen that polls must
build against — it isn't meant to be the final word on every field name,
but a reasonable engineer should not have to invent this shape from
scratch.

```json
{
  "state": "idle | identifying | voice_pick | working | review | done | error",
  "active_book_id": "b2",
  "message": "Making the audiobook now...",
  "needs_input": null,
  "books": [
    {
      "id": "b1",
      "original_filename": "Fated.epub",
      "status": "complete",
      "title": "Fated",
      "author": "Jacka, Benedict",
      "series": "Alex Verus #1",
      "voice": "am_george"
    },
    {
      "id": "b2",
      "original_filename": "Cursed.epub",
      "status": "generating",
      "title": "Cursed",
      "author": "Jacka, Benedict",
      "series": "Alex Verus #2",
      "voice": "am_george",
      "progress": { "chunks_done": 112, "chunks_total": 340 }
    }
  ],
  "error": null
}
```

Field meanings and how each screen in `03-gui-ux-design.md` consumes them:

- **`state`** — which screen is currently active. Maps directly:
  `identifying` → per-book identification loop (§Per-book identification
  loop), `voice_pick` → single-book voice picker or the multi-book voice
  table (§Voice assignment), `working` → §Screen: Working, `review` →
  §Screen: Review, `done` → whole batch finished (back to Screen 1),
  `error` → the generic "Something went wrong" screen
  (`06-safety-error-handling.md` §Error Communication).
- **`books`** — one entry per book in the current batch, present for the
  whole run so the multi-book voice table can render every book at once.
  `status` is per-book (`pending`, `identifying`, `needs_input`,
  `identified`, `voice_pending`, `generating`, `paused`, `complete`,
  `cancelled`, `error`) since different books are at different points
  simultaneously (e.g. book 1 `complete`, book 2 `generating`, book 3
  still `pending`). `title`/`author`/`series`/`voice` are populated once
  known, not before. `progress` only appears on whichever book is
  currently `generating`.
- **`active_book_id`** — which book the current screen concerns, for
  states that focus on one book at a time (`identifying`, single-book
  `voice_pick`, `working`, `review`). Ignored for the multi-book voice
  table, which renders all of `books` at once.
- **`message`** — the exact friendly status string to display (e.g. "Making
  the audiobook now..."). The backend owns this copy, not the frontend,
  so wording stays consistent and centrally editable — see
  `08-open-questions-and-assumptions.md`'s note that all her-facing copy
  needs a full read-through pass regardless.
- **`needs_input`** — `null` normally; otherwise an object like
  `{ "book_id": "b1", "type": "confirm_metadata" | "ai_enrichment_failed" | "pick_voice" | "review_result" }`
  telling the frontend which one-off screen to show for that book before
  polling can continue past it.
- **`error`** — `null` normally; otherwise
  `{ "book_id": "b1" | null, "summary": "Something went wrong", "support_bundle_available": true }`.
  `summary` is always the friendly, non-technical message
  (`06-safety-error-handling.md` §Error Communication); the real
  stack trace/technical detail is never in this response — it's written
  to the audit log / support bundle and pulled from there only when she
  presses "Copy details for support," not exposed over this polling
  endpoint at all.

This endpoint reflects state derived from the state file / in-memory batch
runner — it is not itself a second source of truth alongside
`state_manager.py` (`05-data-settings-and-logging.md`); on backend
restart, this response must be reconstructable entirely from the state
file on disk, which is also what makes the "Pick up where you left off?"
flow (`06-safety-error-handling.md` §Long-run resilience) possible.

## Why these specific technology choices (for the design review)

- **Flask + React over pywebview**: pywebview's window is tied to the
  process; closing it stops everything, including a multi-hour audio job.
  A background Flask/waitress server survives the browser tab closing,
  which matters a lot given how long the audio stage can run unattended.
- **waitress over Flask's built-in dev server**: avoids the "development
  server, do not use in production" warning surface, and is more stable for
  a long-lived local background process.
- **React over server-rendered Flask templates**: cleaner separation
  (Flask becomes a pure JSON API), easier to make visually polished for
  portfolio purposes, and a more conventional production architecture to
  showcase.
- **Native folder dialogs via `tkinter.filedialog`, called from Flask**:
  browsers cannot open native OS file/folder pickers or read arbitrary
  filesystem paths directly (sandboxing). Since Flask itself runs
  natively on her machine (not sandboxed), it can pop a real Windows
  dialog and hand the chosen path back to the page. This preserves the
  "pick once, remembered forever" UX without the page ever needing
  filesystem access itself.
- **Kokoro over Perchance+Selenium**: see `04-tts-engine.md` for full
  reasoning — in short, Perchance's TTS is the same underlying open-weight
  model, callable directly in Python with no browser dependency at all.
- **Provider-agnostic AI enrichment, user-supplied key**: the `ai_providers/`
  registry (already structured this way) means no single AI vendor is
  hardcoded into the pipeline. Each installation picks its own provider and
  supplies its own API key — the author can use his own OpenAI key on his
  install, the mother can use a free Gemini key (or have one pre-provisioned
  for her — see `03-gui-ux-design.md` §AI Helper Setup), and neither
  install's key or provider choice affects the other's. This replaces the
  earlier Gemini-only decision; the trade-off called out below (free-tier
  data usage by Google) now applies only to whichever installs actually
  choose Gemini's free tier, not universally.
- **Cost is no longer categorically zero.** Because a paid provider (e.g.
  OpenAI) is now a valid choice, the earlier assumption that "there's no
  spend, so no spend-cap logic is needed" no longer holds unconditionally —
  see the updated `06-safety-error-handling.md` §Resource & Cost Safety for
  the per-run cap that now does double duty as real cost protection, not
  just hygiene, when a paid provider is in use.

## Folder mapping: her two folders vs. the internal Library/ pipeline

**Resolved contradiction (found during review):** the Project structure
diagram above shows `Library/` as a sibling of `main.py`/`backend/`/
`pipeline/`, which reads as if it's part of the installed app's own
folder — but that would mean it's bundled inside (or next to) the
read-only PyInstaller `.exe` output, which can't be written to reliably
and wouldn't survive app updates, exactly the problem `settings.json`
living outside the install directory already solves. That diagram entry
is dev-time-only, as now noted inline. At runtime,
`Library/00-Incoming` through `Library/03-Audio` actually live at
`%APPDATA%\EpubAutomation\Library\` — not directly exposed to her, but
stored the same way and for the same reasons as everything else in
`05-data-settings-and-logging.md` §Where settings live.

The mapping between her two chosen folders and this internal structure
is:

- **On "Start":** every selected file is **copied** (never moved) from her
  `books_folder` into `Library/00-Incoming/`. Her originals in `books_folder` are
  never modified, renamed, or deleted by any stage. If anything downstream goes
  wrong, her source copy is untouched and unaffected.
- **`output_folder` receives two things per book, not one, added incrementally as
  each is ready rather than batched at the end of the run:**
  1. The cleaned, renamed EPUB (`Library/02-Sanitized/<book>`) — copied into
     `output_folder` as soon as the sanitize stage finishes for that book, so she has
     a usable renamed/cleaned ebook even if the audio stage is still running or fails
     partway through the batch.
  2. The finished audiobook (`Library/03-Audio/<book>/`) — copied into
     `output_folder` as soon as audio generation completes for that book.
- Both pieces land in the same `output_folder` she picked once during first-run
  setup — she never needs to know there are two different internal source locations
  feeding it.

## Network Binding & Security

**Hard requirement, not a default to be casually changed:** waitress must
bind to `127.0.0.1` (localhost) only, never `0.0.0.0` or any other
interface. This was previously only an implicit assumption ("single-user,
localhost-bound" in `00-overview-and-goals.md` / `08-open-questions-and-
assumptions.md`) — promoted here to an explicit requirement because
nothing else in this design provides authentication for the Flask API,
and that API can pop native file dialogs and read/write the filesystem.
An accidental `0.0.0.0` bind — even a temporary one made for local
debugging convenience and never reverted — would expose that unauthenticated
surface to anything else on the same home network (other devices, a
compromised IoT device, a neighbor within wifi range), not just to her own
browser.

Concretely:

- `waitress.serve(app, host="127.0.0.1", port=...)` — the host argument is
  never a configurable setting, environment variable, or CLI flag; it's a
  fixed constant in `launcher.py`.
- If multi-device/networked access is ever wanted in a future version
  (e.g. reaching the GUI from a phone on the same home network), that is
  a deliberate, separate design decision requiring an actual
  authentication story first — not a one-line change to the bind address.
- This requirement doesn't change anything about single-instance locking
  or the folder-picker approach, both of which already assume single-
  machine, single-user use — it just makes the assumption those other
  pieces were already built on into something the code itself enforces.

## Single-instance behavior

**Scope confirmed:** each family member runs their own separate install on
their own machine (own `%APPDATA%\EpubAutomation\`, own `Library/`, own
settings and audit log) — there is no shared/networked instance across
the family, consistent with the `127.0.0.1`-only binding above. "Single
instance" therefore means *per machine*, not one instance for the whole
family.

Only one instance should run at a time **on a given machine**, and this
covers **both front doors, not just the GUI** — the lock must be acquired
the same way whether the process launching is `launcher.py` (GUI) or
`main.py` (CLI). Two reasons, not one:

- **State-file integrity** (original reason): protects the shared state
  file/audit log from concurrent writes.
- **Kokoro's memory footprint** (confirmed during review): TTS inference
  is memory-intensive enough that two simultaneous runs on the same
  machine — say, her GUI mid-audiobook while a CLI `audio` run is also
  started on that same machine — isn't just a data-integrity risk, it's a
  real resource-contention problem on its own. Even if the state file were
  made perfectly concurrency-safe, running two Kokoro inference jobs at
  once on typical hardware is something to prevent outright, not just
  tolerate carefully.

Implementation: a lock file (e.g. in the settings directory) checked at
launch, acquired by `main.py` and `launcher.py` identically. If the GUI is
already running and she double-clicks the icon again, a second launch
just opens a new browser tab to the existing server instead of starting a
second one (as before). If the CLI is invoked while the GUI (or another
CLI run) already holds the lock, it must fail fast with a clear message
(e.g. "epub-automation is already running — finish or quit that first")
rather than queuing, blocking silently, or attempting to run anyway.
