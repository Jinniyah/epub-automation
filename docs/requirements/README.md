# epub-automation — Requirement Documents

These documents capture the full design for `epub-automation`, arrived at
through an extended design conversation before any code was written. Read
in order for full context, or jump to the relevant file for a specific
area.

| File | Covers |
|---|---|
| `00-overview-and-goals.md` | What this is, why it exists, the accessibility persona driving GUI decisions, non-goals |
| `01-architecture.md` | Tech stack, project structure, and the reasoning behind each major technology choice |
| `02-pipeline-stages.md` | The four pipeline stages (rename, sanitize, audio, retag) in detail |
| `03-gui-ux-design.md` | Full screen-by-screen GUI design for the accessible web front end |
| `04-tts-engine.md` | Why/how the TTS engine moved from browser automation to local Kokoro inference |
| `05-data-settings-and-logging.md` | Settings storage, profanity list handling, audit log schema |
| `06-safety-error-handling.md` | Input validation, resource safety, cancel/cleanup behavior, error communication |
| `07-packaging-deployment.md` | PyInstaller packaging and first-run experience |
| `08-open-questions-and-assumptions.md` | Explicitly flagged items for the design review pass |
| `09-testing-strategy.md` | TDD discipline, 80%+ coverage floor (backend + frontend), CI enforcement |
| `10-licensing-and-notices.md` | MIT project license, third-party dependency inventory, the two copyleft dependencies and what they mean for the distributed `.exe` |

This design was arrived at through an extended review pass covering
internal contradictions, lifecycle gaps, accessibility fidelity against
the persona in `00`, under-specified areas, and previously-missing
categories (testing, licensing, privacy) — all resolved directly into
the documents above.

## A second, later review pass: `design/`

A follow-on design-review pass (once the three source repos — see
`00-overview-and-goals.md` §Source Projects — became public) produced
`../design/SYSTEM_DESIGN.md` (a synthesized high-level system design) and
`../design/adr/` (one Architecture Decision Record per binding decision,
including the full reuse-vs-new accounting for every stage). That pass
also surfaced and corrected one real inaccuracy in these requirement
docs — the `ai_providers/` registry had been described without any
reuse attribution, which read as new work when it's actually a direct
port of `epub-renamer`'s existing code. `01-architecture.md`,
`06-safety-error-handling.md`, and `08-open-questions-and-assumptions.md`
(item 4) have since been corrected to reflect this. See
`../design/adr/0014-reuse-existing-implementations-by-default.md` for
the full account.

These requirement docs remain the source of truth for *what* the system
does; `../design/` is the synthesized *why the shape is what it is* and
the decision-by-decision record — read both for full context.

---

*Both `requirements/` and `design/` live under this repo's `docs/`
folder as siblings (`docs/requirements/`, `docs/design/`) — the `../`
references above resolve correctly from here regardless.*
