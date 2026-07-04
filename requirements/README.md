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
the documents above. Nothing further is outstanding from that pass.
