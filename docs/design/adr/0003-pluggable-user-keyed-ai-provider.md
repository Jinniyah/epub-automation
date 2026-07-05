# ADR-0003: Pluggable, user-selected, user-keyed AI metadata provider

## Status
Accepted (supersedes an earlier Gemini-only decision made during initial
design)

## Context
Stage 1 (rename) uses an AI call to enrich/infer title, author, series,
and series number when EPUB metadata alone is insufficient. The initial
design assumed Gemini specifically, always, everywhere. During review
this was revisited: the CLI/advanced front door (author, brother) and
the GUI front door (mother) don't need to share a provider or a key, and
hardcoding one vendor bakes in that vendor's cost model, rate limits,
and data-use tradeoffs for every installation regardless of who's
running it.

**Correction made during this design-review pass:** earlier drafts of
this ADR described the pluggable-provider registry itself as new work
for epub-automation. Checked directly against the source repo
([github.com/Jinniyah/epub-renamer](https://github.com/Jinniyah/epub-renamer)),
that's inaccurate — `epub-renamer` **already implements** exactly this
pattern: `ai_providers/base.py` (an abstract `AIProvider` interface),
`ai_providers/registry.py` (provider-key → implementation), and two
existing implementations, `openai_provider.py` and `null_provider.py`
(offline metadata-passthrough fallback). It also already has a
`MAX_FILES` per-run cap and a `DRY_RUN=true` safe default in its `.env`
config. The registry, the abstraction, and the cap are a direct port,
not a new subsystem — see ADR-0014 for this correction in full context.

## Decision
Carry `epub-renamer`'s existing `ai_providers/` registry into
`pipeline/ai_providers/` largely as-is: the `AIProvider` base class, the
registry pattern, and the existing `OpenAIProvider`/`NullProvider`
implementations transfer directly. The one genuinely new piece is a
`gemini_provider.py` implementation, since `epub-renamer` doesn't ship
one today. `settings.json`'s `ai_provider` and `ai_api_key` are
per-install, user-selected and user-supplied — no provider or key is
embedded in the shipped application. `"none"` (or an unset key) routes
to `NullProvider` — the same offline-fallback behavior `epub-renamer`
already has when its `OPENAI_API_KEY` is left blank.

The GUI's first-run "AI Helper Setup" screen frames this as fully
optional and gives Skip equal visual/functional weight to Yes — see
`docs/requirements/03-gui-ux-design.md` §AI Helper Setup. The intended
practical path for the mother's install specifically is that a technical
family member pre-fills `ai_api_key` in her `settings.json` **before**
she ever opens the app, so she never has to visit a provider's website
herself — this remains an open item to explicitly confirm
(`docs/requirements/08-open-questions-and-assumptions.md`).

## Consequences
- Each install is fully independent: the author can use his own OpenAI
  key, the mother can use a free Gemini key (or a pre-provisioned one),
  and neither install's provider choice or key affects the other.
- Because the registry, base class, and two of three provider
  implementations are a direct port rather than new code, the actual new
  surface area for this decision is small and well-scoped: one new
  provider implementation (`gemini_provider.py`) plus the settings-schema
  wiring (`ai_provider`, `ai_api_key` fields) to let each install choose
  independently. This meaningfully de-risks the decision relative to
  treating it as new subsystem design.
- **Cost is no longer categorically zero.** Because a paid provider
  (OpenAI) is now a valid choice, the earlier assumption "there's no
  spend, so no spend-cap logic is needed" no longer holds
  unconditionally. This directly motivated the `MAX_FILES`-style
  per-run cap in `docs/requirements/06-safety-error-handling.md`
  §Resource & cost safety — which, per the correction above, doesn't
  need to be designed fresh; `epub-renamer`'s existing cap is the
  starting point.
- Any AI call failure or rate-limit falls back **silently, per file**,
  to `NullProvider` behavior — the batch never blocks on one file's API
  call (`docs/requirements/02-pipeline-stages.md` §Stage 1 Failure
  handling). This mirrors `epub-renamer`'s existing blank-key-falls-
  back-to-Null behavior, just triggered by a runtime failure instead of
  an absent key.
- **RESOLVED — confirmed by the user at backlog kickoff:** the Gemini
  free-tier data-use tradeoff (Google sees the text sent for enrichment)
  is accepted for any install that chooses that option — this is no
  longer an open assumption, it's a confirmed acceptance (see
  `docs/requirements/08-open-questions-and-assumptions.md`). It still
  only applies to installs that actually pick Gemini; the OpenAI path
  (already ported from `epub-renamer`, see Decision above) remains a
  first-class alternative for any install that would rather use a paid
  key than accept that tradeoff — neither provider is the "default" at
  the settings-schema level.
- Never enabling billing on the Gemini API project remains a hard
  requirement for any install using Gemini's free tier — enabling
  billing silently removes free-tier status. This needs durable
  documentation (README/setup notes), not just this ADR.
- Her-facing copy never exposes the technical product name, rate limits,
  quotas, or billing status — only "Google (free)" / "OpenAI" as plain
  choices (`docs/requirements/03-gui-ux-design.md` §What is explicitly
  NOT exposed to her).

## Alternatives Considered
- **Gemini-only, hardcoded** (the original decision) — rejected on
  review: unnecessarily couples every installation's enrichment feature
  to one vendor's free-tier terms and rate limits, with no path for a
  technical user to use a paid key they already have.
- **No AI enrichment at all (NullProvider only, always)** — rejected:
  would remove a real usability improvement (AI-guessed titles/authors
  for messy filenames) for no cost/safety benefit, since the pluggable
  design already makes "none" a fully first-class, equally-supported
  choice per install.
- **Design a new provider abstraction for epub-automation rather than
  porting `epub-renamer`'s** — rejected once the existing registry was
  confirmed to already fit the need: no reason to redesign working,
  already-tested plumbing (ADR-0014).

## References
- [`epub-renamer` repository](https://github.com/Jinniyah/epub-renamer)
  — see `ai_providers/base.py`, `registry.py`, `openai_provider.py`,
  `null_provider.py`, and `.env.example` for `MAX_FILES`/`DRY_RUN`
- `docs/requirements/01-architecture.md` §Why these specific technology
  choices (AI provider bullet)
- `docs/requirements/03-gui-ux-design.md` §First launch only: AI Helper
  Setup
- `docs/requirements/05-data-settings-and-logging.md` §Settings schema
- `docs/requirements/06-safety-error-handling.md` §Resource & cost
  safety
- `docs/requirements/08-open-questions-and-assumptions.md`
- ADR-0014 (reuse-by-default principle; the correction re: this
  registry's origin is documented there in full)
- `docs/BACKLOG.md` — Epic 3 (rename stage / AI provider port)
