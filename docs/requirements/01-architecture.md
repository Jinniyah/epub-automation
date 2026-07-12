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
anything beyond validate and default to `1` for this version. Note this
one is genuinely new, not ported: the source `epub-to-audio` is a
single-book CLI tool with no batch or parallelism concept at all (see
`02-pipeline-stages.md` §Stage 3).

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
│   ├── ai_providers/          # PORTED FROM epub-renamer, ALMOST ENTIRELY AS-IS — see note below
│   │   ├── base.py            # Abstract AIProvider interface — from epub-renamer, unchanged
│   │   ├── registry.py        # Provider registry — maps a provider key ("gemini", "openai", "none") to an implementation — from epub-renamer, unchanged
│   │   ├── gemini_provider.py # Gemini implementation (works with either free-tier or paid key) — NEW; epub-renamer does not ship a Gemini provider today
│   │   ├── openai_provider.py # OpenAI implementation (paid key required) — from epub-renamer, ported as-is
│   │   └── null_provider.py   # Offline / "no AI helper" fallback — passthrough of EPUB metadata only — from epub-renamer, ported as-is
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

**On the `ai_providers/` package specifically:** verified directly against
[github.com/Jinniyah/epub-renamer](https://github.com/Jinniyah/epub-renamer)
during the design-review pass (an earlier draft of this doc's "Why these
specific technology choices" section below described this registry
ambiguously, in a way that could be misread as new work for this
project — it isn't). `base.py`, `registry.py`, `openai_provider.py`, and
`null_provider.py` all already exist in `epub-renamer` today, along with
a `MAX_FILES` per-run cap and a `DRY_RUN=true` safe default in its
`.env.example` (see `06-safety-error-handling.md` §Resource & cost safety
for where that cap is reused). The **only new file in this package is
`gemini_provider.py`** — `epub-renamer` ships OpenAI and Null providers
only. See `../design/adr/0003-pluggable-user-keyed-ai-provider.md` and
`../design/adr/0014-reuse-existing-implementations-by-default.md` for the
full decision record.

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
  `identified`, `voice_pick`, `generating`, `paused`, `complete`,
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

### State derivation (resolved during review)

The previous version of this contract defined `state` (top-level) and
`status` (per-book) as separate enums without ever specifying how one is
computed from the other, and used a different vocabulary for the same
voice-assignment concept in each (`voice_pick` at the top level,
`voice_pending` per-book) — a real ambiguity, since a batch has multiple
books at different per-book statuses simultaneously. Both are resolved
here:

- **Vocabulary aligned:** the per-book voice-assignment status is now
  named `voice_pick`, matching the top-level enum value, above — there is
  one name for this concept, not two.
- **Derivation rule:** `state` is computed from the batch's `books[]` as
  the *earliest* pipeline step any book in the batch is currently
  waiting on, using this fixed precedence (earliest wins):
  `error` (any book has an unresolved `error` status) →
  `identifying` (any book is `pending`, `identifying`, or `needs_input`)
  → `voice_pick` (all books are past identification and at least one is
  `identified`/`voice_pick` and none are yet `generating`) →
  `working` (at least one book is `generating` or `paused`) →
  `review` (all books are `complete`, `cancelled`, or `error`, and at
  least one just finished and hasn't been acknowledged via the Review
  screen) → `done` (every book has been acknowledged). This means the
  frontend always has one unambiguous screen to show even mid-batch,
  without needing its own copy of this precedence logic — `bridge.py`
  computes it once, server-side.
- **Single-book vs. multi-book voice assignment is the same `state`
  value** (`voice_pick`), disambiguated purely by `books.length`: exactly
  one book renders the full single-book voice-picker
  (`03-gui-ux-design.md` §Voice assignment), more than one renders the
  multi-book table. No separate state value is needed for this, but it
  is a contract rule, not an implicit convention — any frontend code
  branching on `state === "voice_pick"` must branch again on
  `books.length` to choose which screen to render.

This endpoint reflects state derived from the state file / in-memory batch
runner — it is not itself a second source of truth alongside
`state_manager.py` (`05-data-settings-and-logging.md`); on backend
restart, this response must be reconstructable entirely from the state
file on disk, which is also what makes the "Pick up where you left off?"
flow (`06-safety-error-handling.md` §Long-run resilience) possible.

**Implementation note (Epic 6, `backend/bridge.py::derive_batch_state()`):**
the precedence rule above buckets *any* `needs_input` book under
`identifying`, written before `needs_input.type` grew two more values this
epic needed — `review_result` (a book awaiting her Yes/No after
generation) and `output_collision` (a naming clash with an existing file
in `output_folder`, mid-generation; see §Full API route reference below).
Taken completely literally, a book awaiting Review would incorrectly
demote the whole batch back to the per-book identification screen. The
actual implementation instead buckets a `needs_input` book by *which*
step it's waiting on: `confirm_metadata`/`ai_enrichment_failed` still
mean `identifying` (the rule's original intent), `output_collision` means
`working` (it happens mid-generation, blocking only that one book), and
`review_result` means `review`. Every other precedence boundary above is
implemented exactly as written. Full reasoning in that function's own
docstring — this note exists so this document and the code it describes
don't silently diverge.

## Full API route reference (Epic 6, `backend/app.py`)

Every route below is namespaced under `/api/`, returns JSON, and is a
thin Adapter over `pipeline/batch_runner.py`'s `BatchRunner` (ADR-0001,
`docs/design/PATTERNS.md` §1) — none of them contain a decision beyond
parsing the request and shaping the response. `GET` routes are
side-effect-free; every other method (`POST`/`PUT`/`DELETE`/`PATCH`) is
rejected with `403` unless its `Origin` header (when the browser sends
one at all) matches the address the request actually arrived on — see
ADR-0008's "Origin-header check" addendum.

**Dev-time note (Epic 7):** this Origin check is correct in production
(single origin: Flask serves the built React `dist/`), but Vite's dev
server runs on a separate port, which makes plain dev-time `fetch()`
calls genuinely cross-origin and therefore `403`'d by design. This is
resolved on the frontend side — Vite proxy config + an Origin-header
rewrite so the request Flask receives looks same-origin, matching
production traffic — not by relaxing this check itself, since dev and
prod share the same backend code path. Full config and rationale:
`frontend/README.md`.

A mutating route's JSON success body always includes `"ok": true`; a
failure is a non-2xx status with `{"ok": false, "error": "..."}` — with
one exception, `POST /api/books`, which reports success/failure
per-uploaded-file inside a `200` response rather than for the request as
a whole (see below).

### Status polling

| Method & path | Body | Response | Notes |
|---|---|---|---|
| `GET /api/health` | — | `{"status": "ok"}` | Liveness only, not part of the polling contract. |
| `GET /api/status` | — | The full status contract above | What every screen polls. |

### Settings (`05-data-settings-and-logging.md`)

| Method & path | Body | Response | Notes |
|---|---|---|---|
| `GET /api/settings` | — | `settings.json`'s contents, with `ai_api_key` replaced by `has_ai_api_key: bool` | `ai_api_key`'s real value is never returned over this API, ever (masked like a password field, `03-gui-ux-design.md`). |
| `POST /api/settings` | Any subset of settings fields to update (e.g. `{"books_folder": "...", "profanity_words": [...]}`) | `{"ok": true}` | A partial update, merged into the existing settings and saved atomically (ADR-0005). `schema_version` in the body is silently ignored (server-owned). No read-modify-write protection beyond the single-process lock already implicit in one `BatchRunner`/app instance — acceptable for a single local user (ADR-0008's threat model), but a frontend doing "fetch current list, mutate one word, POST the whole array back" (`profanity_words`, `03-gui-ux-design.md` §Words to clean up) should still fetch-then-send in that order, not assume anything about concurrent writers. |

### Native folder picker (ADR-0006)

| Method & path | Body | Response | Notes |
|---|---|---|---|
| `POST /api/dialogs/folder` | `{"title": "...", "initial_dir": "..."}` (both optional) | `{"path": "C:\\..." \| null}` | `null` means she cancelled the dialog. Pops a real native OS dialog — this call blocks until she closes it. |

### Screen 1: Add Books

| Method & path | Body | Response | Notes |
|---|---|---|---|
| `POST /api/books` | `multipart/form-data`, one or more `files` fields | `{"results": [{"ok": bool, "original_filename": str, "book_id": str \| null, "reason": str \| null, "message": str \| null}, ...]}` | One result per uploaded file, **not** a single pass/fail for the whole request — a batch of 5 files where 1 is DRM-protected still returns `200` with 4 successes and 1 `ok: false` entry (`06-safety-error-handling.md` §Input validation: rejected individually, never a silent skip). `reason` is one of `not_epub` / `damaged` / `drm_protected` / `max_files_exceeded` (`pipeline/input_validation.py::RejectionReason`); `message` is the exact plain-language string to show her. Once the current batch is `done`, the next call to this route transparently starts a fresh batch (`backend/app.py::_current_runner()`). |
| `DELETE /api/books/<book_id>` | — | `{"ok": bool}` | `ok: false` if the book isn't in `pending` status (already started processing — use Cancel instead, `03-gui-ux-design.md` §Screen 1). |
| `GET /api/disk-space` | — | `{"estimated_total_bytes": int, "any_insufficient": bool, "checked_paths": [{"path": str, "free_bytes": int, "sufficient": bool}, ...]}` | Pre-Start disk-space check, summed across every book currently in the batch (`06-safety-error-handling.md` §Resource & cost safety). Call again after adding/removing books. |

### Batch lifecycle

| Method & path | Body | Response | Notes |
|---|---|---|---|
| `POST /api/batch/start` | — | `{"ok": true}` | Starts the identification loop (rename → sanitize) for every `pending` book. Safe to call repeatedly, including while it's already running — a book added afterward is picked up automatically, not stranded. |
| `POST /api/batch/start-generation` | — | `{"ok": true}` | "Start All Books" — starts serial audio generation (ADR-0009) for every book at `voice_pick`, and resumes any `paused` book. Also safe to call repeatedly. Never needed for a single-book batch — picking a voice already auto-starts it (`03-gui-ux-design.md` §Voice assignment). |

### Per-book identification loop

| Method & path | Body | Response | Notes |
|---|---|---|---|
| `POST /api/books/<book_id>/confirm` | `{"corrections": {"title": ..., "author_first": ..., "author_last": ..., "series": ..., "series_number": ...} \| null}` | `{"ok": true, "status": str}` or `409` if the book isn't currently awaiting confirmation | The "Confirm metadata" step (`03-gui-ux-design.md` §Per-book identification loop) — send only the fields she actually changed via the Field Correction Popup, or `null`/`{}` to accept as-is. The whole batch only advances to voice assignment once every book has been confirmed. |

### Voice assignment

**New this epic (Epic 8) — the frontend's own voice picker needed a way
to learn what voice keys exist and let her preview them; nothing in the
Epic 6 route set provided either:**

| Method & path | Body | Response | Notes |
|---|---|---|---|
| `GET /api/voices` | — | `{"voices": [{"key": "af_heart", "name": "Heart"}, ...]}` | Plain first-name-only list (`backend/bridge.py::voice_choices()`) — "no technical voice keys, no gender/accent/quality-grade labels" (`03-gui-ux-design.md` §Voice assignment). **Also this app's chosen trigger point for the lazy voice-sample cache build**: the first call after a `kokoro` version change blocks while `ensure_voice_samples()` regenerates all 28 samples (real-hardware-measured ~48s on CPU); every call after that is a cheap version-tag check. Call once when the voice picker screen opens, not per-row. |
| `GET /api/voice-samples/<voice>` | — | `audio/mpeg` bytes, or `404` `{"ok": false, "error": str}` if the voice key is unknown or its sample isn't cached yet | "▶ Listen" — set as an `<audio>` element's `src` directly; instant once cached, per `04-tts-engine.md` §Voice samples. |

| Method & path | Body | Response | Notes |
|---|---|---|---|
| `POST /api/books/<book_id>/voice` | `{"voice": "af_heart"}` (a key from `pipeline/tts_engine.py::VOICES`) | `{"ok": true, "voice": str}`, `400` if `voice` missing, `409` if the book isn't at `voice_pick` | "Change Voice" (multi-book table) or the single-book picker's selection. |
| `POST /api/books/<book_id>/metadata` | `{"corrections": {"title": ..., "author_first": ..., "author_last": ..., "series": ..., "series_number": ...}}` | `{"ok": true, "status": str}`, `409` if the book isn't currently at `voice_pick` | **New this epic (Epic 8):** the multi-book voice table's clickable book title (`03-gui-ux-design.md` §Voice assignment: "reopening that book's metadata review ... without leaving this screen"). Distinct from `confirm` above (only accepts a book still awaiting identification confirmation) and `retag` below (rewrites already-generated files on disk) — this just patches the in-memory metadata a book already past identification will generate/tag with, no filesystem work at all. |

### Pause / Cancel (`06-safety-error-handling.md` §Cancel design)

| Method & path | Body | Response | Notes |
|---|---|---|---|
| `POST /api/books/<book_id>/pause` | — | `{"ok": true}` | No-op if the book isn't currently generating. Takes effect before the *next* chunk, not mid-chunk. |
| `POST /api/books/<book_id>/cancel` | `{"keep_partial": bool}` (default `true`) | `{"ok": true, "status": "cancelled"}` | `keep_partial: true` (the default/safer option, pre-selected per spec) leaves already-generated chunks on disk for a later resume; `false` deletes them. |

### Output collision (this epic's own addition — see the state-derivation note above)

| Method & path | Body | Response | Notes |
|---|---|---|---|
| `POST /api/books/<book_id>/collision` | `{"choice": "replace" \| "keep_both"}` | `{"ok": true, "status": str}`, `400` for an invalid `choice`, `409` if there's no pending collision | Surfaces when a finished audiobook's folder name already exists in `output_folder` (`06-safety-error-handling.md` §Concurrency & duplicate handling). The pending collision's detail (`{"artifact": "audiobook", "path": "..."}`) is on the `needs_input` object in `/api/status` when `needs_input.type == "output_collision"`. |

### Review + "No, let me fix it" (`02-pipeline-stages.md` §Stage 4)

| Method & path | Body | Response | Notes |
|---|---|---|---|
| `POST /api/books/<book_id>/review` | `{"looks_good": bool}` | `{"ok": true, "status": str}`, `409` if there's no pending review | `looks_good: true` marks the book `complete` and triggers ADR-0017 cleanup. `looks_good: false` leaves the book parked, waiting for the corrected fields via the `retag` route below — it does not, by itself, open any correction UI (that's a frontend concern). |
| `POST /api/books/<book_id>/retag` | `{"overrides": {"title": ..., "author_first": ..., "author_last": ..., "series": ..., "series_number": ...}}` | `{"ok": true, "status": "complete"}` on success; `{"ok": false, "error": str}` with **`422`** if the retag itself failed (e.g. author/title still can't be resolved) | The one place a `2xx`-vs-failure distinction rides entirely on the JSON body's `ok` field doesn't apply — a genuine failure here is a real non-2xx status, unlike the upload route above. |

### Opening folders in File Explorer (`03-gui-ux-design.md` §Screen: Review)

**New this epic (Epic 8) — same reasoning as the native folder picker
above (ADR-0006): a browser page cannot open a native Explorer window
on an arbitrary local path itself, so Flask does it on the page's
behalf. Neither route ever takes or returns a real filesystem path**
— consistent with `03-gui-ux-design.md`'s "What is explicitly NOT
exposed to her" rule ("any file paths other than the two folders she
picked") — the path is always resolved server-side.

| Method & path | Body | Response | Notes |
|---|---|---|---|
| `POST /api/books/<book_id>/open-folder` | — | `{"ok": true}`, or `{"ok": false, "error": "That folder couldn't be found."}` (not a 4xx — a friendly-degradation case, same pattern as everywhere else in this API) | "📂 See the audiobook files" — opens *this book's own* subfolder, resolved from its own already-tracked `output_audio_folder`. |
| `POST /api/open-output-folder` | — | Same shape as above | "📂 See all my finished books" — opens her remembered `output_folder`. |

### "What voice did I use before?" (`03-gui-ux-design.md` §Settings areas)

| Method & path | Body | Response | Notes |
|---|---|---|---|
| `GET /api/voice-history` | — | `{"ok": true, "history": [{"label": str, "voice": str}, ...]}`, or `{"ok": false, "error": "Something went wrong finding your voice history."}` with `500` | `history: []` (with `ok: true`) means legitimately no audiobooks made yet; the `500` case means the audit log itself couldn't be read — render these two states with different copy, never conflate them (`03-gui-ux-design.md`'s own explicit requirement). |

### Error communication (`06-safety-error-handling.md` §Error communication)

| Method & path | Body | Response | Notes |
|---|---|---|---|
| `POST /api/support-bundle` | `{"technical_error": "..."}` (optional) | `{"ok": true, "path": "C:\\...\\logs\\support_bundle.txt"}` | The real technical error is looked up server-side from whichever book is currently `error`-status if the request body doesn't supply one — the client is never able to supply this itself in practice, since no other route ever exposes a book's raw error text (`backend/bridge.py::current_error_detail()`). The written file never contains `ai_api_key` or any other secret. |

### "Welcome back" — detection only (`06-safety-error-handling.md` §Long-run resilience)

| Method & path | Body | Response | Notes |
|---|---|---|---|
| `GET /api/welcome-back` | — | `{"pending_book_ids": [str, ...]}` | Answers "is anything pending" from `state.json` alone. **Does not** reconstruct a live `BatchRunner` for those books. The Epic 8 "Welcome back" screen (`frontend/src/screens/WelcomeBack.tsx`) is built against exactly this — when the current status poll still has the pending books loaded (the common case: she just closed the tab, the background process kept running) it shows their real titles/phase; when it doesn't (a genuine backend restart, no reconstruction), it degrades honestly to a plain count rather than inventing detail. Actually reconstructing a live `BatchRunner` from `state.json` after a restart remains genuinely open — no epic currently owns it, see `docs/BACKLOG.md`'s Open Items. |

### Quit

| Method & path | Body | Response | Notes |
|---|---|---|---|
| `POST /api/quit` | — | `{"ok": true}` | Stops the background server itself (ADR-0001's "closing the tab isn't enough" requirement), not just the browser tab. Exits the process directly (`os._exit(0)`, from a short-delayed background thread so the response reaches her first) rather than a graceful in-process waitress shutdown — see ADR-0007's stale-lock detection, which already treats an abruptly-terminated process as an expected, recoverable case. |

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
  registry is a direct port of `epub-renamer`'s existing registry
  (`base.py`, `registry.py`, `openai_provider.py`, `null_provider.py` all
  already exist there — see §Project structure above for the full
  breakdown of what's ported versus new) — it means no single AI vendor
  is hardcoded into the pipeline. Each installation picks its own
  provider and supplies its own API key — the author can use his own
  OpenAI key on his install, the mother can use a free Gemini key (or
  have one pre-provisioned for her — see `03-gui-ux-design.md` §AI Helper
  Setup), and neither install's key or provider choice affects the
  other's. This replaces the earlier Gemini-only decision; the trade-off
  called out below (free-tier data usage by Google) now applies only to
  whichever installs actually choose Gemini's free tier, not universally.
- **Cost is no longer categorically zero.** Because a paid provider (e.g.
  OpenAI) is now a valid choice, the earlier assumption that "there's no
  spend, so no spend-cap logic is needed" no longer holds unconditionally —
  see the updated `06-safety-error-handling.md` §Resource & Cost Safety for
  the per-run cap that now does double duty as real cost protection, not
  just hygiene, when a paid provider is in use. That cap itself is also a
  direct port of `epub-renamer`'s existing `MAX_FILES` mechanism, not new
  safety logic designed for this project.

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

**Stale lock detection (resolved during review):** a lock file with no
liveness check is a real risk given the failure modes this design
explicitly plans for elsewhere (`06-safety-error-handling.md` §Long-run
resilience treats a crash, a forced restart, or a lost-power event during
a multi-hour audio job as expected, not exceptional) — every one of those
would otherwise leave the lock file in place after the process that held
it is gone, permanently refusing to start on the next launch with no
visible recovery step for her. The lock file must therefore store enough
information to check whether its holder is actually still running, not
just whether the file exists:

- Write the holding process's PID (and ideally its image name, to guard
  against PID reuse by an unrelated process after a reboot) into the lock
  file at acquisition time.
- On a new launch, if a lock file is present, check whether a process
  with that PID (and image name, if recorded) is actually running before
  treating the lock as held. If it isn't, treat the lock as abandoned:
  log that a stale lock was cleared, delete/overwrite it, and proceed
  with a normal launch rather than refusing to start.
- This check applies identically to both front doors, the same as lock
  acquisition itself — a stale-lock check only implemented for the GUI
  (or only for the CLI) would leave the other path permanently blocked
  by an abandoned lock from the other.
- This is a liveness check, not a full crash-recovery mechanism — it
  only decides whether it's safe to proceed with a normal launch; actual
  recovery of in-progress work is still the state-file-driven "Welcome
  back" flow (`06-safety-error-handling.md` §Long-run resilience,
  `03-gui-ux-design.md` §"Welcome back" screen), unaffected by this
  change.
