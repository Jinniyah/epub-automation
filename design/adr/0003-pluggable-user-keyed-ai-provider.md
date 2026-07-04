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

## Decision
`ai_providers/` is a registry mapping a provider key
(`"gemini" | "openai" | "none"`) to an implementation, all conforming to
an `AIProvider` base interface. `settings.json`'s `ai_provider` and
`ai_api_key` are per-install, user-selected and user-supplied — no
provider or key is embedded in the shipped application. `"none"` (or an
unset key) routes to `NullProvider`, a pure EPUB-metadata passthrough
that requires no network access at all.

The GUI's first-run "AI Helper Setup" screen frames this as fully
optional and gives Skip equal visual/functional weight to Yes — see
`requirements/03-gui-ux-design.md` §AI Helper Setup. The intended
practical path for the mother's install specifically is that a technical
family member pre-fills `ai_api_key` in her `settings.json` **before**
she ever opens the app, so she never has to visit a provider's website
herself — this remains an open item to explicitly confirm
(`requirements/08-open-questions-and-assumptions.md`).

## Consequences
- Each install is fully independent: the author can use his own OpenAI
  key, the mother can use a free Gemini key (or a pre-provisioned one),
  and neither install's provider choice or key affects the other.
- **Cost is no longer categorically zero.** Because a paid provider
  (OpenAI) is now a valid choice, the earlier assumption "there's no
  spend, so no spend-cap logic is needed" no longer holds
  unconditionally. This directly motivated the `MAX_FILES`-style
  per-run cap in `requirements/06-safety-error-handling.md` §Resource &
  cost safety, which now does double duty as real cost protection for
  paid-key installs, not just rate-limit hygiene.
- Any AI call failure or rate-limit falls back **silently, per file**,
  to `NullProvider` behavior — the batch never blocks on one file's API
  call (`requirements/02-pipeline-stages.md` §Stage 1 Failure handling).
- The Gemini free-tier data-use tradeoff (Google sees the text sent for
  enrichment) still applies to any install that chooses that option —
  it's just no longer a project-wide default everyone is implicitly
  opted into. This tradeoff is assumed acceptable but not yet explicitly
  confirmed by the user (open item).
- Never enabling billing on the Gemini API project remains a hard
  requirement for any install using Gemini's free tier — enabling
  billing silently removes free-tier status. This needs durable
  documentation (README/setup notes), not just this ADR.
- Her-facing copy never exposes the technical product name, rate limits,
  quotas, or billing status — only "Google (free)" / "OpenAI" as plain
  choices (`requirements/03-gui-ux-design.md` §What is explicitly NOT
  exposed to her).

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

## References
- `requirements/01-architecture.md` §Why these specific technology
  choices (AI provider bullet)
- `requirements/03-gui-ux-design.md` §First launch only: AI Helper Setup
- `requirements/05-data-settings-and-logging.md` §Settings schema
- `requirements/06-safety-error-handling.md` §Resource & cost safety
- `requirements/08-open-questions-and-assumptions.md`
