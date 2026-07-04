# GUI / UX Design

See `00-overview-and-goals.md` for the accessibility persona driving these
decisions. Every requirement below should be read against that persona:
reduced fine-motor precision (RA) and difficulty learning/holding
multi-step new processes in mind (FMS).

## General principles (apply to every screen)

- One decision per screen wherever possible.
- Big click targets — buttons at minimum ~70px tall with generous spacing.
- **Any radio-button or toggle row is fully clickable end-to-end** — the
  visible circle/switch is decorative, not the hit target. The whole row
  (icon, label, and surrounding whitespace) selects the option. A native
  radio input's actual circle is far too small for reduced fine motor
  precision (RA) to hit reliably; every radio-row screen in this doc
  (voice picker, AI helper choice, etc.) must be built this way, not just
  the ones that happen to call it out explicitly.
- No double-clicks, no right-clicks, no hover-to-reveal, no small
  checkboxes — use large toggle switches instead.
- No typing required in the normal flow. Text entry only appears when
  something can't be auto-parsed, one field at a time, with the
  best-guess value pre-filled.
- Plain language only — no "stage," "sanitize," "AI provider," "dry run,"
  "retag," etc. anywhere in her-facing copy. See the terminology table
  below.
- The app reopens to the same state it was in — no "where was I"
  confusion after closing and relaunching.
- Long waits get a friendly, unambiguous status message, never a bare
  spinner or a percentage that might look frozen.
- Nothing destructive happens without a clearly-worded, big confirmation
  step, and there is always a visible way back.
- Errors are phrased kindly and actionably, never as a stack trace (see
  `06-safety-error-handling.md` §Error Communication).

## Terminology mapping (internal name → her-facing label)

| Internal | Her-facing label |
|---|---|
| Rename stage | "Fix messy file names" |
| Sanitize stage | "Clean up bad language" |
| Audio stage | "Turn into audiobook" |
| Retag | "Does the audiobook chapters look right or do they need renamed?" (framed as a yes/no review, not a named feature) |
| Settings | "⚙️" / not labeled "Settings" — grouped as "Change my folders," "Words to clean up," and "File name helper" separately |
| Profanity list | "Words to clean up" |
| Voice (Kokoro voice key, e.g. `af_heart`) | First name only, e.g. "Heart" |
| AI provider (Gemini / OpenAI) | "File name helper" for the feature; "Google (free)" / "OpenAI" as the two choices — never "AI provider," "API," or the technical product name "Gemini" |
| Audit log | Never named as such to her; the one part of it she can see is surfaced as the plain-language "What voice did I use before?" screen |

## Screen-by-screen flow

### First launch only: one-time setup
```
Where are your book files?     [ Choose Folder... ]
Where should your finished books go?  [ Choose Folder... ]
                [ Done ]
```
Uses a native OS folder picker (see `01-architecture.md` for how a
browser-based GUI can still show a native dialog). Saved to
`settings.json` (see `05-data-settings-and-logging.md`). Never shown again
after this, except via the "⚙️ Change my folders" entry point available
from Screen 1 going forward.

### First launch only: AI Helper Setup (one-time, skippable)

**If `ai_api_key` is already present in `settings.json`** — e.g. pre-filled
by a technical family member before she ever opens the app — these screens
are skipped entirely and first launch goes straight from folder setup to
Screen 1. This is the expected path for her install: someone technical
sets this up once, ahead of time, so she never has to.

If no key is present yet, one screen, framed as fully optional:
```
Want help fixing messy file names automatically?
This uses a free online helper to guess titles and authors.

     [ Yes, help me ]      [ Skip, I'll do it myself ]
```
- "Skip" is a completely normal, equally-supported path — not a lesser
  option — and routes to `NullProvider` (`ai_provider: "none"`). Nothing
  breaks; "Fix messy file names" on Screen 1 still works using EPUB's own
  built-in info, just without AI-guessed improvements.
- Reachable again later, without redoing folder setup, via a "🤖 File
  name helper" entry point alongside "⚙️ Change my folders" and "🧼 Words
  to clean up" on Screen 1.

If "Yes, help me":
```
Pick a helper:

○ Google (free)
○ OpenAI

           [ Next ]
```
- Same big-radio-row pattern as the voice picker (see §Voice Assignment) —
  the entire row is the click target, not just the circle, per the
  general principle above.
- "Gemini" (the actual product name) is shown to her as "Google (free)" —
  the parent company name is more recognizable than the product name, and
  "(free)" sets an honest expectation up front.

Then, for whichever helper she picked:
```
Paste your code from Google here:

[__________________________]

Don't have one yet?  [ Get a code ]

     [ Skip for now ]        [ Done ]
```
- `[ Get a code ]` opens that provider's key-creation page in her default
  browser — she'll need a technical family member's help with this part in
  practice (creating an account, generating a key, copying it back), and
  the design doesn't pretend otherwise; this is exactly why pre-filling
  the key ahead of time (above) is the intended normal path for her
  specifically, with this screen existing mainly for the CLI/advanced
  users and for the rare case she wants to change it herself later.
- `[ Skip for now ]` is always present here too, in case she starts this
  flow and decides not to finish it — routes to `NullProvider`, exactly
  like the top-level "Skip" button above, and can be revisited later from
  the same "🤖 File name helper" entry point.
- No jargon: never says "API key," "provider," or the key itself once
  entered (masked, like a password field).

### "Welcome back" screen (only appears if something's pending)

On every launch, before Screen 1 loads, the backend checks the state
file for any book not yet marked complete through every stage it needs
(see `06-safety-error-handling.md` §Long-run resilience). If nothing is
pending, this screen is skipped entirely and she lands straight on
Screen 1 as normal. If something is pending:
```
📚 Welcome back!

You were in the middle of:
📖 Cursed — getting the audio ready

     [ Continue ]           [ Not right now ]
```
- **"Continue"** takes her directly back into whichever screen matches
  that book's actual state — the Working screen if audio generation was
  in progress, the voice picker if a voice hadn't been chosen yet, the
  metadata review if identification wasn't finished, and so on. This
  reuses the same state-file-driven reconstruction already required for
  the status endpoint (see `01-architecture.md` §Status endpoint
  contract) — not a separate resume mechanism.
- **"Not right now"** goes to Screen 1 without discarding anything. The
  pending book stays exactly as it was; this screen simply reappears
  next launch as long as it's still incomplete. Nothing here is
  destructive — if she actually wants to abandon the book rather than
  finish it later, that's still a **Cancel**, done from within the
  resumed screen itself (see `06-safety-error-handling.md` §Cancel
  Design), not a separate discard option bolted onto this screen.
- If more than one book is pending (e.g. she quit partway through a
  3-book batch), list all of them the same way the multi-book voice
  table does — one row per book, same big click targets, same pattern,
  not a new list style invented for this one screen.
- This same screen covers every way the app could have stopped — "Quit
  for now," a crash, a laptop losing power — identically, since it's
  driven entirely by what the state file says is incomplete, not by
  detecting *how* the previous session ended.

### Screen 1: Add Books
```
📚 Drop your book files here, or  [ Choose Books... ]

Your books:
✓ Fated.epub                    [ Remove ]
✓ Cursed.epub                   [ Remove ]

🏷️  Fix messy file names    [ On ]
🧼  Clean up bad language   [ On ]

⚙️ Change my folders     🧼 Words to clean up     🤖 File name helper     🎙️ What voice did I use before?

           [ Start ]
```
- Both toggles default **On** (matches current manual usage pattern).
- Drag-and-drop is supported but never the *only* way in — the "Choose
  Books..." button must always be present and equally capable, since
  drag-and-drop requires more precise motor control than a big button.
- Files dropped/chosen that aren't valid `.epub` files are rejected
  individually with a friendly message — they do not block the rest of
  the batch (see `06-safety-error-handling.md` §Input Validation).
- "Choose Books..." opens a standard native file picker, **starting**
  in her remembered books folder — this is a starting location, not a
  restriction. It's a normal OS file dialog, so she can navigate
  anywhere else on the machine from there if the book she wants isn't in
  that folder (e.g. it landed in Downloads instead). Nothing about this
  design locks the dialog to a single folder; that would work against
  the point of using a native picker in the first place.
- **Each book in the list has its own "Remove" button** — previously
  missing from this screen despite "Words to clean up" already
  establishing the same per-row pattern. Deliberately **not** styled red:
  unlike Cancel (which can lose real, already-in-progress work and needs
  a confirmation dialog), removing a book here is instant, costless, and
  fully reversible — she can just add the file again. It uses the same
  plain, unstyled treatment as "Words to clean up"'s Remove buttons, and
  likewise needs **no confirmation dialog** before removing.

### Per-book identification loop (after Start, before generation)
For each book in the batch, in sequence:
1. Rename step runs automatically if enabled (no screen shown unless it
   needs her input — e.g., AI enrichment failed and nothing could be
   inferred).
2. **Confirm metadata** — plain-language review of what was found
   (title/author/series), one field editable at a time if she wants to
   correct something, using the Field Correction Popup below.

This loop completes for **all** books in the batch before generation
starts for any of them — this is what makes the voice table (below)
possible, since a book's identity must be known before a sensible voice
suggestion can be shown.

### Field Correction Popup (reused everywhere a single field needs fixing)

One component, used identically by both the pre-generation "Confirm
metadata" step above and the post-generation "No, let me fix it" flow
below — not two separate designs. Tapping a field she wants to correct
opens this as a large overlay centered on screen, dimming everything
behind it:
```
✏️  Author

┌───────────────────────────────────┐
│  Jacka, Benedict                          │
└───────────────────────────────────┘

     [ ✕ Clear ]                    [ Save ]
```
- **Much larger than an inline text field** — a wide box with a large
  font, easy to see and easy to click into without precise aim, rather
  than a small inline input squeezed next to a label.
- **Full-replace, not precise cursor editing.** The existing value opens
  pre-filled and pre-selected (select-all on open), so simply typing
  replaces the whole thing immediately — she never has to position a
  cursor mid-word or drag-select a portion of text, which is exactly the
  kind of fine-motor-precision task (RA) this design avoids everywhere
  else.
- **A big ✕ Clear button** empties the field in one tap instead of
  requiring manual backspacing or selection — same reasoning as above.
- **No device-specific logic needed.** This is a real text input, so on
  any touch-capable screen (e.g. a touchscreen laptop — see
  `00-overview-and-goals.md`'s laptop/desktop-only hardware scope) the
  operating system's on-screen keyboard appears automatically on focus,
  the same as it would for any other text field on that device. Nothing
  in the app has to detect the device type or decide whether to show a
  keyboard — one component, works the same everywhere it's used.
- "Save" commits the value and closes the popup, returning to whichever
  flow opened it (the per-book confirmation step, or "No, let me fix
  it").

### Voice assignment

**If only one book in the batch:** go straight from that book's metadata
confirmation into a single full voice-picker screen (see below), then
start generating immediately.

**If more than one book:** after all books are identified, show one table
covering the whole batch. **Before she changes anything, every row shows
the same voice** — her single global last-used voice — **except when two
or more books in this batch share the same series**, in which case those
specific rows default to the same voice as each other instead (still
computed fresh for this batch only, never persisted — see
§Default per row below for why this doesn't reopen the per-series-memory
question that was explicitly decided against). With no shared series in
the batch, this reduces to the plain single-global-default case shown
below:
```
🎙️ Choose a voice for each book

📖 Fated — Jacka, Benedict — Alex Verus #1
   Voice: George              [ Change Voice ]
───────────────────────────────────────────
📖 The Hating Game — Thorne, Sally
   Voice: George              [ Change Voice ]
───────────────────────────────────────────
📖 Winter's Heart — Jordan, Robert — Wheel of Time #9
   Voice: George              [ Change Voice ]

           [ Start All Books ]
```
If she decides a couple of these should sound different — a very normal
thing to want, since different books/genres often call for different
voices — she taps "Change Voice" on just the rows she wants to change.
After changing two of the three above, the same table looks like this:
```
🎙️ Choose a voice for each book

📖 Fated — Jacka, Benedict — Alex Verus #1
   Voice: George              [ Change Voice ]
─────────────────────────────────────
📖 The Hating Game — Thorne, Sally
   Voice: Bella               [ Change Voice ]
─────────────────────────────────────
📖 Winter's Heart — Jordan, Robert — Wheel of Time #9
   Voice: Heart               [ Change Voice ]

           [ Start All Books ]
```
Nothing forces her to change anything — pressing "Start All Books" with
every row still on the shared default is completely valid, if that's what
she wants.
- Each row is large, one book, one current voice, one button — no
  in-table controls beyond that, to keep click targets big.
- **The book title in each row is itself clickable**, reopening that
  book's metadata review (the same "Confirm metadata" step and Field
  Correction Popup from §Per-book identification loop) without leaving
  this screen or derailing the rest of the batch — closing the review
  returns her to this same table, updated. This is the "always a visible
  way back" principle applied here: previously, "Change Voice" was the
  only per-row control, with no way to notice-and-fix a wrong
  title/author/series while looking at this table.
- **Default per row: her single global last-used voice, applied
  identically to every row when the table first appears — unless two or
  more books in this batch share a series**, in which case those rows
  default to the same voice as each other instead (see the framing
  paragraph above). **This is session-local only** — computed fresh from
  whatever's in the current batch, never written to `settings.json` or
  any other persisted store, and forgotten the moment the batch ends. It
  is deliberately *not* full per-series memory across sessions (that
  remains explicitly rejected — adds edge cases for marginal benefit;
  the audit log covers "what did I use last time" if she needs to check,
  see `02-pipeline-stages.md` §Shared cross-stage requirements); it just
  solves the one most likely real annoyance — wanting series consistency
  — for books she happens to be converting in the same sitting. She's
  free to give different books different voices afterward regardless —
  that's exactly what "Change Voice" is for.
- "Change Voice" opens the full voice-picker overlay (below) for that row
  only, then returns to the table with the selection updated.

**Full voice-picker (single-book case, or opened via "Change Voice"):**
```
🎙️ Pick a voice for "Fated" (Alex Verus #1)

○ Heart      [▶ Listen]
○ George     [▶ Listen]   ← last used
○ Bella      [▶ Listen]
      ... (scrolls)

           [ Next ]
```
- Plain first names only, no technical voice keys, no gender/accent/
  quality-grade labels — just the name and a Listen button.
- Radio-button rows (not a dropdown) — dropdowns require more precise
  interaction than a plain list of big rows. **The entire row is the
  click target** (see General principles above) — tapping anywhere on a
  row, not just the small circle, selects that voice. The `▶ Listen`
  button is the one exception: it's a distinct nested target within the
  row so tapping it plays the sample without also selecting the voice.
- `▶ Listen` instantly plays a **pre-generated** sample (see
  `04-tts-engine.md` §Voice Samples) — same canned line for every voice,
  so she's comparing voices, not sentences. Must be instant, not a fresh
  generation per click.
- Selecting a voice and pressing Next both records the choice and updates
  her global "last used voice" default for next time.
- **Voice scope and first-name collision check (verified against the
  actual Kokoro voice list at
  [huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md](https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md)):**
  Kokoro ships 9 languages and ~54 voices total; this design's "~28
  voices" always meant **American + British English only** (20 + 8 = 28
  exactly), a scoping decision that was implicit until now. Confirmed:
  **zero first-name collisions** across all 28 English voices — no name
  repeats within American English, none within British English, and no
  overlap between the two lists. The "first name only" simplification is
  safe to ship as designed, no fix needed. One caveat for the future,
  not a current problem: `am_santa` (American) and Spanish's `em_santa`
  share a first name — a non-issue today since non-English voices are
  out of scope, but this "no collisions" guarantee would need
  re-verifying against the full list if non-English voice support is
  ever added later.

### Screen: Working (per book, during generation)
```
Working on: Fated
Book 1 of 3

🔊 Making the audiobook now...
About 3 more hours, based on how this book is going so far.
It's okay to leave this open and come back later.

[ Pause ]                [ Cancel ]
Stop for now, come      Stop working on this
back anytime.            book completely.
```
- Friendly, unambiguous status text — never a bare percentage or spinner
  alone. **The time estimate is dynamic, not a fixed string**
  (`08-open-questions-and-assumptions.md` §2—resolution): derived from
  throughput actually observed so far in this job (e.g. chars/sec over
  the chunks completed so far, extrapolated to what's left), not a
  hardcoded "a few hours" guess. A fixed estimate could be badly wrong on
  her actual hardware and undermine trust in the "it's okay to leave
  this open" framing if reality diverges a lot from what was promised.
  Before enough chunks have completed to extrapolate from (e.g. the
  first chunk or two), fall back to the friendly "Making the audiobook
  now..." line without a time estimate at all, rather than guessing.
- Closing the browser tab/window here is safe and does not stop
  generation (see `01-architecture.md` for why — background Flask
  process, not tied to the browser tab).
- **Pause** vs **Cancel** are distinct (full behavior spec in
  `06-safety-error-handling.md` §Cancel Design):
  - Pause: stop now, resume later, exactly where it left off.
  - Cancel: asks first, then either keeps already-completed chunks for
    that book (default/safer option) or fully discards it, per her
    choice at cancel time.
- **Color-coded to signal they aren't equally risky:** Pause is a
  yellow/amber button, Cancel is a red button — a low-effort visual cue
  that one is safe-and-reversible and the other is more serious, on top
  of (not instead of) the confirmation dialog Cancel already requires.
  Color is a supplement here, never the only signal — the caption text
  below each button (next bullet) carries the actual meaning
  independent of color.
- **The difference is explained with permanent caption text under each
  button, not a hover tooltip.** Hover doesn't fit this design: it
  directly violates the "no hover-to-reveal" rule in General principles
  above, established because hovering-without-clicking-to-confirm is
  itself a fine-motor-precision task for the RA persona, independent of
  which device she's on. The caption text is always visible instead,
  matching the pattern this screen already uses ("It's okay to leave
  this open and come back later" is the same kind of always-visible
  reassurance, not something she has to discover by hovering).
- A big, plain **"Quit for now"** control must be reachable from this (or
  a persistent header) — closing the tab is safe, but there needs to be
  an explicit, deliberate way to fully stop the background server too.

### Screen: Review (per book, after generation)
```
✅ Fated is ready!

Author: Jacka, Benedict
Title:  Fated
Series: Alex Verus #1

📂 See the audiobook files

Does the audiobook chapters look right or do they need renamed?

[ Yes, looks good ]      [ No, let me fix it ]

📂 See all my finished books
```
- "📂 See the audiobook files" opens **this book's own subfolder** directly
  in File Explorer — not the whole output folder — so she's looking only
  at the chapters that belong to the book she's currently reviewing, not
  scrolling through everything else in `output_folder`. This is
  deliberately placed *above* the question, before she has to decide
  Yes/No, so she can actually look at the real chapter file names before
  answering rather than judging purely from the Author/Title/Series text
  on this screen.
- "📂 See all my finished books" is the general link, unchanged from the
  original design: opens her remembered `output_folder` directly, showing
  every book so far, not just this one. This is still needed alongside
  the book-scoped link above — per the `01-architecture.md` folder-mapping
  decision, `output_folder` holds **two things per book**, the
  cleaned/renamed EPUB *and* the audiobook subfolder, and the EPUB copy
  specifically is only reachable through this general link, not through
  "See the audiobook files" above.
- "Yes" moves to the next book in the batch (or ends the run if this was
  the last one).
- "No, let me fix it" opens the flow below.

### "No, let me fix it" flow

This reuses the exact same Field Correction Popup already specified in
§Per-book identification loop's "Confirm metadata" step — not a new UI
pattern — pre-filled with this book's current values:
```
Let's fix Fated's info.

Author: [ Jacka, Benedict                    ]

           [ Next ]
```
She steps through Author, Title, Series, and Series Number this way (only
the fields that apply — no Series step for a standalone book), same
pattern as pre-generation confirmation. On completing the last field:
```
🔄 Fixing Fated's files now...

[brief — this is a fast local rename/retag pass, not a regeneration;
no audio is re-created, so this should take seconds, not minutes]
```
Then a confirmation screen:
```
✅ Fixed!

📂 See the audiobook files

           [ Done ]
```
- Whatever she entered is passed straight through as the retag stage's
  author/title/series/series-number overrides (see `02-pipeline-stages.md`
  §Stage 4) — every MP3 in that book's folder gets retagged and renamed to
  match, and the folder itself is renamed too.
- **There is no way to correct an individual chapter's label from this
  screen** — the underlying tool has no per-chapter correction mechanism
  (see `02-pipeline-stages.md` §Stage 4's resolution of the chapter-title
  open item). If a chapter's actual audio content is wrong, that isn't a
  "retag" problem and isn't handled by this flow at all — it would require
  regenerating that chapter's audio, which is out of scope here.
- "📂 See the audiobook files" appears again on the confirmation screen so
  she can immediately verify the fix actually took, using the same
  book-scoped folder link as the Review screen above.
- "Done" returns to the next book in the batch (or ends the run), same as
  pressing "Yes" would have.

### Settings areas (reachable via "⚙️" entry points, not a single combined settings page)

**Change my folders:**
```
Where are your book files?     [ Choose Folder... ]  (currently: ...)
Where should your finished books go?  [ Choose Folder... ]  (currently: ...)
           [ Done ]
```

**Words to clean up:**
```
[existing word]      [ Remove ]
[existing word]      [ Remove ]
...  (scrolls)

Add a new word:
[______________]  [ Add ]

           [ Done ]
```
- One word at a time — no multi-select, no inline editing (remove and
  re-add to fix a typo).
- Full spec for where this data lives and how it forks from the bundled
  default in `05-data-settings-and-logging.md`.

**What voice did I use before?** (read-only, no editing controls)
```
🎙️ What voice did I use before?

📖 Alex Verus (series)         George
📖 The Hating Game             Bella
📖 Wheel of Time (series)      Heart
...  (scrolls)

           [ Done ]
```
- **Resolves the gap this doc previously had:** `05-data-settings-and-
  logging.md` describes the audit log as her way to answer "what voice
  did I use for this series last time" (the documented justification for
  *not* remembering voice per-series/per-author — see §Voice Assignment
  above), but she has no way to open a raw CSV, and this doc's own rule
  says the audit log's file path and format are never exposed to her.
  This screen is what actually delivers on that promise: one row per
  series (or per standalone book, if it has no series), showing the most
  recent voice used for it, derived from the audit log's `voice` column
  (see `05-data-settings-and-logging.md` §Audit log) without her ever
  seeing the log itself.
- **Read-only** — no Change Voice button here, no editing. This is a
  lookup, not a settings control; changing a voice going forward still
  happens through the normal per-book §Voice Assignment flow.
- Reachable from Screen 1's "🎙️ What voice did I use before?" entry
  point, alongside the other "⚙️" entry points.
- **Two distinct empty-looking states, worded differently on purpose:**
  - **Legitimately nothing yet** (log exists, has zero rows — she hasn't
    made an audiobook yet): *"You haven't made any audiobooks yet—once
    you do, you'll be able to check what voice you used here."* This is
    not an error; nothing is wrong.
  - **The log itself is missing, unreadable, or corrupted** (a real
    failure, not an empty state): *"Something went wrong finding your
    voice history."* with the same **"Copy details for support"** action
    used everywhere else in this design
    (`06-safety-error-handling.md` §Error Communication), and a way back
    to Screen 1 — same pattern as every other error state in this app,
    not a special case invented just for this screen. This must **never**
    crash the screen or show her a raw file-not-found/parse error; the
    two cases above must never be conflated into one ambiguous "nothing
    here" message, since one means "you haven't gotten there yet" and the
    other means "something broke and support may be needed."

## Progress reporting mechanism

Simple polling (React calls a status endpoint every few seconds), not
WebSockets. Chosen for robustness through a bundled local server and
because a progress screen a human glances at doesn't need live-streamed
updates — see `01-architecture.md`. The endpoint's exact response shape
(the `state`/`books`/`message`/`needs_input`/`error` contract every screen
above is built against) is defined in `01-architecture.md` §Status
endpoint contract (`bridge.py`).

## What is explicitly NOT exposed to her

- Rate-limit information, technical error codes, or any provider-side
  status — even on the AI Helper Setup screens, which show only the
  plain-language provider choice and a place to paste a code, never
  anything about quotas, billing, or request limits.
- Her entered code itself, once saved (masked like a password field, not
  redisplayed in plain text anywhere in her UI).
- Any file paths other than the two folders she picked.
- Chunk sizes, retry counts, timeouts, or any other tuning parameter.
- The existence of the CLI/advanced mode, the state file, or the audit
  log's own file path/CSV format — she never opens or sees the raw log.
  The one thing derived from it that she does see is the "What voice did
  I use before?" screen (§Settings areas above), which reads the log on
  her behalf and shows her only a plain series/book → voice list, nothing
  else from the log's contents (no timestamps, no other stages' rows, no
  file paths).
