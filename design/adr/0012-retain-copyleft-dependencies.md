# ADR-0012: Retain `mutagen` (GPL) and `ebooklib` (AGPL) rather than replace them

## Status
Accepted

## Context
This project's own code is MIT-licensed, matching the two already-MIT
source projects it merges (`epub-renamer`, `epub-to-audio`). Checking
actual PyPI/GitHub license listings directly (not assumed) surfaced two
bundled runtime dependencies that are copyleft, not permissive:

| Dependency | License | Used for |
|---|---|---|
| `mutagen` | GPL-2.0-or-later | ID3v2 tag reading/writing (audio + retag stages) |
| `ebooklib` | AGPL-3.0-or-later | EPUB reading (metadata, chapter text extraction) |

When a program imports a GPL/AGPL library directly (a normal Python
`import`, not a separate process) and the combined program is
distributed, the standard interpretation is that the *distributed
combined work* — here, the compiled `.exe` as a whole — is governed by
that copyleft license too, not solely by the MIT license covering the
author's own code. This is a real distinction affecting the distributed
artifact, not a technicality a NOTICE file alone resolves.

`ebooklib`'s usage is light enough that it could plausibly have been
replaced with a stdlib `zipfile`/`xml.etree` implementation.
`mutagen`'s ID3-writing role is more central and would need a
purpose-built replacement to avoid entirely.

## Decision
**Keep both dependencies as-is.** Given this project's actual expected
audience — a portfolio piece with realistically few adopters, distributed
as an open-source GitHub repo plus direct family use, not a
widely-distributed commercial product — the engineering cost of removing
both dependencies was judged not worth it. This decision is conditioned
on documenting the licensing situation clearly and honestly rather than
glossing over it: a dedicated `10-licensing-and-notices.md`
(source-of-truth for the tradeoff and full dependency inventory), a
`NOTICE` file at the repo root with concrete content, and a short,
visible summary in `00-overview-and-goals.md` so a reader doesn't have to
already know to look for the detailed file.

The practical mitigation for the copyleft distribution obligation
(recipients must be able to get corresponding source) is that this
entire project is already open source on a public GitHub repo — the
whole point of it being a portfolio piece — so that obligation is
substantively already met by the project's own nature, independent of
this decision.

This is explicitly **not legal advice**; if distribution scope ever
broadens beyond "public GitHub portfolio repo plus direct family use"
(e.g. wider public download, monetization, bundling into something
else), a real license review is needed before doing so.

## Consequences
- The compiled `.exe`, as a combined distributed work, is subject to
  GPL-2.0-or-later and AGPL-3.0-or-later terms — a fact that must be
  accurately represented anywhere licensing is discussed, not minimized.
- Saves the engineering cost of replacing `mutagen` (non-trivial —
  central to ID3 tag writing) and `ebooklib` (smaller, but still real
  work) with from-scratch or alternative implementations.
- Makes accurate, honest licensing documentation a load-bearing part of
  the project's own portfolio claim (`00-overview-and-goals.md`
  explicitly frames this as an engineering-maturity signal, not
  incidental paperwork) — the documentation isn't optional polish, it's
  what makes this decision defensible.
- If the project's distribution model changes in the future, this ADR's
  reasoning becomes stale and must be explicitly revisited, not silently
  assumed to still hold.

## Alternatives Considered
- **Replace `ebooklib` with a stdlib `zipfile`/`xml.etree`
  implementation** — considered viable given light usage, but rejected
  for this version: the engineering cost wasn't judged worth it relative
  to the mitigated real-world risk at this project's actual scale.
  Revisitable later at low cost if the calculus changes.
- **Replace `mutagen` with a purpose-built ID3 read/write
  implementation** — rejected: `mutagen`'s role is more central
  (tag reading/writing in both the audio and retag stages), making a
  replacement meaningfully more expensive to build and verify correct,
  for the same marginal real-world risk reduction.
- **Distribute without the copyleft dependencies documented, relying on
  MIT as the blanket claim** — rejected outright: inaccurate, and
  directly undermines the "honest documentation" portfolio value this
  project explicitly claims to demonstrate.

## References
- `requirements/10-licensing-and-notices.md` (full)
- `requirements/00-overview-and-goals.md` §Secondary goal: portfolio
  piece
- `requirements/01-architecture.md` (project structure — inline license
  notes on `mutagen`/`ebooklib` usage)
