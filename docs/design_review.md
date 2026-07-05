# epub-automation — Final Pre-Coding Design Review

**Status: fixes applied (2026-07-05).** B1, B2, B3, S1, S3, and S4 below
have been resolved directly in the requirement docs, the affected ADRs,
`SYSTEM_DESIGN.md`, and `CLAUDE.md` — see `docs/design/adr/README.md`
§Post-review fixes for the consolidated list of what changed and where.
S2 (Kokoro/PyInstaller native-dependency risk) and S5 (testing/a11y scope
realism) were not document defects to "fix" so much as things to track —
S2 is now a named, tracked item in `SYSTEM_DESIGN.md` §9 and
`07-packaging-deployment.md` recommending an early spike; S5 is now an
explicit floor-vs-best-effort note in `09-testing-strategy.md`. This
review's content below is left as originally written, as the historical
record of what was found and why.

---

Reviewer role: final design-review checkpoint before implementation begins.
Reviewed: `CLAUDE.md`, all of `docs/requirements/` (README + 00–10), all of
`docs/design/` (`SYSTEM_DESIGN.md` + ADR README + ADR 0001–0015), and the
three source repositories (`epub-renamer`, `epub-sanitize`, `epub-to-audio`)
fetched directly from GitHub to spot-check reuse/licensing claims.

---

## 1. Executive Verdict: **GO WITH CONDITIONS**

This is an unusually disciplined pre-code design package — eleven
requirement docs, a synthesized system design, fifteen ADRs, and a
`CLAUDE.md` that all agree with each other, plus a documented track record
of the design process catching and correcting its own mistakes (the
`ai_providers/` reuse-attribution error, the `Library/` folder-mapping
contradiction, the audit-log-as-her-own-lookup-tool contradiction). I
independently re-verified a sample of the "checked against the actual
source repo" claims — filename regex, chunk size, the AI-provider registry
scope, the retag folder-rename bug, all ten of the sanitize stage's
security controls, and the licensing table — and every one held up exactly
as documented. That is a genuinely good sign about how this design was put
together, not a rubber stamp; see §6 for what I checked and how.

That said, this is a review, not a formality, and three things below are
real gaps that should be closed — cheaply, in the docs — before
implementation starts, because each one is the kind of thing that's a
one-line fix today and a breaking, user-facing problem after ship. None of
them require redesigning anything; they're gaps in an otherwise coherent
design, not evidence the design is wrong.

---

## 2. Blocking Issues

### B1. No recovery path for a stale single-instance lock file

**What it is:** `01-architecture.md` §Single-instance behavior, ADR-0007,
and `06-safety-error-handling.md` §Long-run resilience all specify a lock
file acquired by both `main.py` and `launcher.py`, checked at launch. None
of them specify what happens if the process that held the lock died
without releasing it — a crash, a forced Windows restart, a killed
process, or the machine losing power mid-audiobook. This is not a
theoretical edge case for this project: `06-safety-error-handling.md`
§Long-run resilience explicitly designs around "the machine sleeping, the
process being killed externally, or the app being fully quit" as expected
occurrences during a multi-hour audio job — exactly the scenarios that
leave a lock file orphaned.

**Why it matters:** if the next launch simply checks "does the lock file
exist" with no liveness check, every one of those expected-and-designed-for
interruption scenarios permanently locks the app until someone deletes a
file the mother doesn't know exists and wouldn't know how to find. That
directly contradicts the entire premise of this GUI — unassisted use by
someone for whom "an unfamiliar multi-step recovery process" is the exact
problem this app exists to avoid. It also silently defeats the "Welcome
back" screen: she'd never reach it, because the app would refuse to start
at all.

**Where:** `01-architecture.md` §Single-instance behavior, ADR-0007,
`06-safety-error-handling.md` §Long-run resilience.

**Suggested fix:** specify a liveness check as part of lock acquisition —
e.g., store the PID in the lock file and check whether a process with that
PID (and ideally that image name) is actually running before treating the
lock as held; or a heartbeat timestamp updated periodically while running,
with a staleness threshold after which a new launch treats the lock as
abandoned and proceeds (logging that it did so). Either mechanism is
small. What matters is that this gets decided now — it changes what
`launcher.py`'s very first few lines of code need to do, and retrofitting
it after the lock format is already in use on real installs is exactly
the kind of breaking change this project's own `settings.json`/state-file
atomicity reasoning (ADR-0005) argues against creating.

### B2. `settings.json` and the state file have no schema version field

**What it is:** ADR-0005 makes atomic writes for `settings.json` and the
state file a "hard requirement, not a style preference," with a detailed
justification about how costly a corrupted or unreadable file would be for
this persona. But the settings schema shown in
`05-data-settings-and-logging.md` §Settings schema has no `schema_version`
(or equivalent) field, and nothing in `SYSTEM_DESIGN.md`, `01-architecture.md`,
or any ADR discusses how a *structurally* different future settings or
state shape (not a corrupted file — a deliberately changed one, from a
future app update) would be handled on an existing install.

**Why it matters:** this project explicitly plans to ship updates to an
existing install (`settings.json` living outside the install directory
specifically so it survives updates — ADR-0005), and the reuse/portfolio
framing all but guarantees the schema will need to change at least once
(a new AI provider needing different stored fields, a restructured
`profanity_words`, a new toggle). Without a version marker, there's no way
for a future version of the app to tell "this is an old-format file I
should migrate" from "this is a corrupted file I should reject" — exactly
the ambiguity ADR-0005 already worries about for corruption, just for a
different cause. This is cheap to add now (one field, defaulted on write)
and is the kind of thing that's much harder to retrofit once real installs
exist with unversioned files on disk.

**Where:** `05-data-settings-and-logging.md` §Settings schema, §State file;
ADR-0005.

**Suggested fix:** add a `schema_version: 1` (or similarly named) field to
both `settings.json` and the state file now, and add one sentence to
ADR-0005 or `05-data-settings-and-logging.md` establishing the policy for
what happens on version mismatch (e.g., "migrate forward only; an
unrecognized *future* version — app was downgraded — falls back to the
corrupted-file recovery path already needed for atomic-write failures").

### B3. The polling status contract's `state`/per-book `status` relationship is underspecified

**What it is:** `01-architecture.md` §Status endpoint contract is the
single most load-bearing interface in the system — every screen in
`03-gui-ux-design.md` and the `aria-live` wiring in §Accessibility are
built directly against it (`SYSTEM_DESIGN.md` §6 says so explicitly). It
defines a top-level `state` enum (`idle | identifying | voice_pick |
working | review | done | error`) and a separate per-book `status` enum
(`pending, identifying, needs_input, identified, voice_pending, generating,
paused, complete, cancelled, error`) but never specifies the rule for
deriving one from the other. Two concrete ambiguities fall out of this:

1. During the per-book identification loop, books are simultaneously at
   different per-book statuses (the doc's own example: book 1 `complete`,
   book 2 `generating`, book 3 `pending`). What top-level `state` does the
   backend report while, say, book 1 is `identified` and book 2 is still
   `identifying`? Nothing says whether `state` reflects "the least-done
   book," "the book matching `active_book_id`," or some other rule.
2. The enums don't even use matching vocabulary for the same concept —
   top-level `voice_pick` vs. per-book `voice_pending` — and nothing says
   whether the single-book full-picker screen and the multi-book table are
   the same `state` value disambiguated by `books.length`, or ought to be
   distinct values. `03-gui-ux-design.md` §Voice assignment describes both
   flows in detail but never ties either back to this contract explicitly.

**Why it matters:** this is precisely the "could two competent engineers
read this and build materially different things" test the review brief
asks about, applied to the one contract everything else depends on.
Getting this wrong doesn't fail loudly in review — it fails when the
backend and frontend are built by (or built at different times by) someone
making a different implicit assumption than the one baked into the other
side, and the bug surfaces as "the working screen randomly doesn't update"
weeks into implementation.

**Where:** `01-architecture.md` §Status endpoint contract.

**Suggested fix:** add explicit derivation rules to the contract — e.g., a
short table or pseudocode: "`state` is computed as X given `books[]`," and
either rename `voice_pending`→`voice_pick` (or vice versa) for consistency,
plus one sentence confirming whether the single-book and multi-book voice
flows are the same `state` value.

---

## 3. Significant Concerns

### S1. Sanitize-stage regex has a Python-porting gotcha not flagged anywhere

Having read the actual `PS_Run-CleanUpEpub.ps1` source directly: its
whole-word-matching regex uses .NET's Unicode-category lookbehind/lookahead
(`(?<![\p{L}\p{N}_])...(?![\p{L}\p{N}_])`), and the script wraps that regex
in a hard 5-second execution timeout
(`System.Text.RegularExpressions.Regex(pattern, options, timeout)`) as a
ReDoS guard against pathological profanity-list entries. Python's stdlib
`re` module supports neither Unicode-property classes (`\p{L}`) nor a
per-match execution timeout — both require the third-party `regex` package
(or a hand-rolled equivalent using `\b` plus manual Unicode-alphanumeric
checks, and a separate timeout mechanism such as running the match in a
worker with a hard deadline). None of `02-pipeline-stages.md` §Stage 2,
ADR-0004, or `09-testing-strategy.md`'s security-guard coverage section
mention this — "case-insensitive whole-word matching only" (item 6) and
the general "preserve every security control" framing treat this as a
behavior to replicate, not a library dependency decision to make. This is
a concrete example of exactly the kind of thing ADR-0004 itself warns
about ("security-critical logic gets rewritten, not just transliterated
— every guard needs to be independently verified in the port").

**Suggested fix:** add a line to ADR-0004 or `02-pipeline-stages.md`
naming the `regex` package (or the chosen alternative) as a new dependency
for the sanitize port, and note the ReDoS-timeout behavior explicitly as
something the Python port must reproduce, not just the whole-word-matching
outcome.

**Confidence:** high — based on direct reading of the actual PowerShell
source, not inference.

### S2. PyInstaller + Kokoro packaging risk isn't named

`07-packaging-deployment.md` §Known packaging constraints anticipates a
large `.exe` and (correctly) removes the old Chrome-check requirement, but
doesn't mention the specific, known-hard packaging risks that come
*with Kokoro specifically*: PyTorch-based/ONNX-based ML packages are a
common source of PyInstaller hidden-import failures (dynamically loaded
extension modules, backend-selection logic that imports conditionally),
and Kokoro's G2P (text-to-phoneme) pipeline has historically depended on
`espeak-ng`, a native (non-Python) binary that PyInstaller does not bundle
automatically the way it does pure-Python dependencies. If the pinned
`kokoro` version needs it, that's a native binary that has to be located,
bundled, and pathed correctly inside a frozen `.exe` — a materially
different problem than "the exe will be large."

**Suggested fix:** do an early, small spike — package a minimal Kokoro
"hello world" with PyInstaller before committing implementation time
elsewhere — specifically to find out whether `espeak-ng` or any other
native dependency is actually required by the chunk of the voice list this
project uses (American/British English), and if so, add the bundling step
to `07-packaging-deployment.md` now.

**Confidence:** moderate — based on general knowledge of the Kokoro
package's dependency chain and common PyInstaller/ML-library friction
points, not verified against this project's specific pinned `kokoro`
version or a real packaging attempt. Worth treating as "go check this
early," not as a confirmed defect.

### S3. No spec for what happens when a batch exceeds `MAX_FILES`

The reused `MAX_FILES` cap (`06-safety-error-handling.md` §Resource & cost
safety, ADR-0003) is described as a hard, sane default that protects both
free-tier hygiene and paid-provider cost — but nothing describes what she
actually sees if she selects more books than the cap allows. Does the
batch silently process only the first `MAX_FILES` and stop? Does Screen 1
reject the excess files at add-time with an explanation? Given this
project's own stated design principle ("fewer decisions per screen," "no
error state should be a dead end with no visible next step"), a batch that
quietly stops partway through with no explanation is exactly the failure
mode the rest of `06-safety-error-handling.md` works hard to avoid
everywhere else.

**Suggested fix:** add one paragraph to `06-safety-error-handling.md`
§Resource & cost safety describing the her-facing behavior when a batch
exceeds the cap — most simply, reject the excess at Screen 1 with a
friendly "you can convert up to N books at a time — try the rest in
another batch" message, consistent with how every other Screen-1
validation failure is already handled.

### S4. First-run Kokoro model download timing is ambiguous

`04-tts-engine.md` §First-run setup and `07-packaging-deployment.md`
§First-run setup requirements both describe the ~300MB download as
happening "at first use" / "the same setup moment," but don't specify
*when* that moment is relative to first launch: eagerly, before Screen 1
is ever shown (which would mean a first launch with no internet blocks
the whole app, even though sanitize/rename don't need it), or lazily,
deferred until the first audio-stage invocation for that install (which
would mean the "Setting up for the first time..." message needs to appear
mid-batch rather than at launch, a different UX moment than the docs'
framing implies). This is a real product decision with UX consequences
either way, not just an implementation detail.

**Suggested fix:** one sentence in `04-tts-engine.md` or
`07-packaging-deployment.md` picking one of the two, since it affects both
the "Setting up for the first time" screen's placement in the flow and the
offline-first-launch failure mode.

### S5. Testing + accessibility scope is ambitious for a solo developer, and the docs should say so explicitly

This is judgment, not a defect — flagged because the review brief asks for
an honest read. The combined bar here is real: TDD discipline for pipeline
stages and every security guard, 80%+ enforced coverage on both backend
and frontend, near-100% adversarial coverage on security guards with
crafted malicious fixtures, `axe-core` + `eslint-plugin-jsx-a11y` in CI,
a full manual keyboard-only pass, a real NVDA/Narrator pass, a real
dyslexic-reader test, and a pursued-but-unconfirmed real screen-reader
test — on top of building the actual product (three ported codebases, a
Flask backend, a Vite/React frontend, PyInstaller packaging, and a new
TTS integration). Nothing here is unreasonable in isolation, and the
project's own "aligned, not certified" framing (ADR-0015) is honest about
scope — but the combination is a lot for one person's side project, and
the single most likely failure mode is exactly what
`09-testing-strategy.md` itself worries about for the 80% figure: some
part of this quietly slips under time pressure. My honest read is that
the manual accessibility passes (keyboard-only, real NVDA, real testers)
are the most likely casualty, precisely because — unlike the 80% coverage
number — nothing in the CI pipeline enforces them; they depend entirely on
developer discipline holding up over the course of the project.

**Suggested fix:** not a design change — but consider naming, in
`09-testing-strategy.md` or `CLAUDE.md`, which of these is the floor that
must not slip (my suggestion: security-guard coverage and the automated
a11y linting, since both are cheap to keep and CI-enforced) versus which
is best-effort given the project's actual solo-developer constraints, so
that if something has to give under time pressure, that's a conscious
choice made now rather than a silent, undocumented one made later.

---

## 4. Minor Observations / Nice-to-Haves

- **`epub-sanitize`'s repo includes a committed `.vs/` folder** (Visual
  Studio local state) — harmless, but worth a `.gitignore` fix in that
  source repo since it's public; not an `epub-automation` issue.
- **`ebooklib`'s AGPL exposure already exists in `epub-renamer` today**
  (confirmed: `epub-renamer/epub_reader.py` imports `ebooklib` directly),
  and that project's own README claims only "MIT License" with no mention
  of the AGPL implication. `epub-automation`'s licensing documentation
  (`10-licensing-and-notices.md`, ADR-0012) is actually *more* rigorous
  about this than the tool it inherited the dependency from — worth
  noting as a genuine improvement, not a gap, but also a reminder that
  `epub-renamer` itself has a latent version of the same documentation
  gap if it's ever distributed more broadly on its own.
- **Voice-sample cache regeneration** (`04-tts-engine.md` §Voice samples)
  requires network access if triggered by a `kokoro` version bump on an
  otherwise-offline machine; not addressed what she sees if that
  regeneration can't complete (stale/missing previews) — low-stakes, but
  a one-line "if offline, keep the old samples and retry next launch"
  note would close it.
- **`--stop-after`'s default phrase list** (multiple built-in trigger
  phrases in `epub-to-audio`) vs. the docs' framing of a single
  overridable phrase — minor wording-only mismatch between
  `02-pipeline-stages.md`/`04-tts-engine.md`'s description and the actual
  source behavior; worth a one-line correction for accuracy but has no
  design consequence.
- **CODEBASE_INDEX.md plan** (CLAUDE.md §Documentation & session close) is
  a good, cheap idea — no changes needed, just noting it's a good practice
  worth actually following through on at the first build session as
  planned.

---

## 5. What's Genuinely Well Done

- **The reuse-verification discipline is real, not just claimed.** I
  independently re-checked five of this design's "confirmed against actual
  source" claims — the `FILENAME_PATTERN` regex, the `--max-chunk` default
  of 4000, the `ai_providers/` registry's actual scope (openai + null
  only, confirming `gemini_provider.py` really is the only new file), all
  ten of the sanitize stage's named security controls, and the retag
  script's folder-rename gap — and every single one matched the docs
  exactly, including small details (the regex's precise pattern, the
  5-second-timeout ReDoS guard, the `MaxExtractedMB`/`MaxProfanityWords`
  defaults). That's a genuinely uncommon level of rigor for a pre-code
  design doc, and it shows the "verify, don't just trust" principle this
  project set for itself is actually being followed, not just stated.
- **The self-correction history is a good sign, not a red flag.** The
  `ai_providers/` reuse-attribution error, the `Library/` folder-mapping
  contradiction, and the "audit log is her own lookup tool" framing error
  were all found and fixed with clear before/after reasoning left in the
  docs. A design that never shows its own mistakes is often one that
  didn't look hard enough; this one clearly did.
- **The two-tier accessibility framing (ADR-0015) is honestly scoped.**
  "Aligned, not certified," explicit about what's validated (the primary
  persona, via a real dry run) versus what's designed-against-but-not-yet-
  tested (screen-reader use), and explicit about what's deliberately
  excluded (AAA, JAWS, a dedicated accessibility mode) — this is a more
  sophisticated and more honest accessibility claim than most portfolio
  projects attempt, and the docs consistently maintain the distinction
  rather than letting it blur under portfolio-framing pressure.
- **The disk-space and cost-safety reasoning is unusually rigorous for
  this project's scale** — deriving the exact byte-rate from the chosen
  MP3 encoding parameters, sanity-checking the placeholder
  `SECONDS_PER_CHAR` against a real reference data point from the old
  Perchance-based tool, and being explicit that the estimate should bias
  toward overestimating. This is exactly the kind of "pure function,
  clear expected output" reasoning that makes a formula trustworthy before
  real benchmarking data exists.
- **The Cancel/Pause design and the "partially-completed book must look
  different from a finished one" resolution** show real attention to the
  actual persona — catching that a keep-partial default could otherwise
  produce a confusing half-finished folder with no visual distinction from
  success is a genuinely non-obvious finding for a design-review pass to
  surface.
- **CLAUDE.md is currently in sync with the underlying docs.** I checked
  this explicitly, as the review brief asked — every row in its "Key
  architectural decisions" table and its "Flagged open items" table
  matches what the underlying requirement docs and ADRs actually say, with
  no drift found.

---

## 6. Confidence Notes

| Finding | Confidence | Basis |
|---|---|---|
| B1 — stale lock file recovery | High | Confirmed absent by reading all three docs that discuss single-instance locking; this is a documentation-completeness finding (no code exists to check against). |
| B2 — no schema version field | High | Confirmed absent by reading the full settings schema and every doc referencing `settings.json`/state file. |
| B3 — status contract ambiguity | High (that the ambiguity exists) / Moderate (on real-world impact) | Directly read `01-architecture.md`'s full contract spec and `03-gui-ux-design.md`'s screen-by-screen usage; the derivation rule is genuinely absent. Impact is inferred, not observed, since no implementation exists yet. |
| S1 — sanitize regex porting gotcha | High | Based on direct reading of the actual `PS_Run-CleanUpEpub.ps1` source fetched from GitHub, not inference from the requirements docs' description of it. |
| S2 — Kokoro/PyInstaller packaging risk | Moderate | Based on general knowledge of the `kokoro` package's dependency chain and common ML-library PyInstaller friction; not verified against this project's specific pinned version or an actual packaging attempt. |
| S3 — MAX_FILES batch UX gap | High (gap exists) / Moderate (severity) | Confirmed absent from all safety/UX docs; severity depends on how often real batches would exceed 50 books, which I can't know. |
| S4 — first-run download timing ambiguity | High | Directly read both sections describing first-run setup; neither resolves eager-vs-lazy timing. |
| S5 — testing/a11y scope realism | N/A (judgment call) | Explicitly flagged as opinion per the review brief's calibration guidance, not a factual defect. |
| Reuse/licensing claims (§5, first bullet) | High | Independently re-fetched and read the actual source files (not just repo READMEs) for each claim checked. |
