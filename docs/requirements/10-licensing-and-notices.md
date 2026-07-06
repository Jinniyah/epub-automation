# Licensing & Notices

## This project's own code: MIT

All original code written for `epub-automation` is licensed under the
MIT License (`LICENSE` at the repo root). This matches the two source
projects already merged into it — confirmed directly against each
repository, not assumed:

- [`epub-renamer`](https://github.com/Jinniyah/epub-renamer) — MIT
  (`LICENSE.txt`)
- [`epub-to-audio`](https://github.com/Jinniyah/epub-to-audio) — MIT
  (`LICENSE.txt`)
- [`epub-sanitize`](https://github.com/Jinniyah/epub-sanitize) — no
  separate license file; the same author's own work, so folding it into
  an MIT project is unproblematic.

## Read this before assuming "the whole thing is MIT"

Two runtime dependencies this project bundles into the distributed
`.exe` are **copyleft, not permissive**, and this was checked directly
against their actual PyPI/GitHub license listings during review, not
assumed:

| Dependency | License | Used for |
|---|---|---|
| `mutagen` | **GPL-2.0-or-later** | ID3v2 tag reading/writing (audio + retag stages) |
| `ebooklib` | **AGPL-3.0-or-later** | EPUB reading (metadata, chapter text extraction) — this dependency is inherited from `epub-renamer`'s own `epub_reader.py`, which already imports it today; not newly introduced by this project (confirmed by reading that source directly during the final pre-coding review) |

**What this actually means:** when a program imports a GPL/AGPL library
directly (not as a separate process — a normal Python `import`) and the
combined program is distributed, the standard interpretation is that the
*distributed combined work* is governed by that copyleft license too,
not by whatever license the original author's own code carries. In
practice, that means the compiled `.exe` — as a whole, combined
artifact — is subject to GPL-2.0-or-later and AGPL-3.0-or-later terms,
even though every line of code the author wrote is individually MIT.
This is a real distinction, not a technicality to gloss over with a
NOTICE file alone — a NOTICE file is the right move for the *permissive*
dependencies below, but it doesn't resolve a copyleft conflict by
itself.

**Decision (made during review): keep both dependencies as-is rather
than replacing them.** `ebooklib`'s usage is light and could have been
swapped for a stdlib `zipfile`/`xml.etree` implementation; `mutagen`'s
ID3-writing role is more central and would need a purpose-built
replacement to avoid. Given this project's actual expected audience
(a portfolio piece with realistically few adopters, not a
widely-distributed product), the engineering cost of removing both
dependencies wasn't judged worth it — but that decision only holds up
if the licensing situation is documented clearly and honestly, which is
what this file and the `NOTICE` file below are for.

**What actually mitigates this in practice:** the GPL/AGPL's core
distribution obligation is that recipients of the compiled program must
be able to get the corresponding source. Since this entire project is
already open source on a public GitHub repo (the whole point of it being
a portfolio piece), that obligation is substantively already met —
anyone who receives the `.exe` can already find the exact source that
produced it. This isn't a substitute for accurate labeling (hence this
document), but it meaningfully de-risks the practical situation.

**This is not legal advice.** If this project is ever distributed more
broadly than "a public GitHub portfolio repo plus direct family use" —
e.g. packaged for wider public download, monetized, or bundled into
something else — get an actual license review before doing so. The
analysis above is a good-faith, reasonably researched summary, not a
substitute for one.

## Full third-party dependency inventory

| Dependency | License | Category |
|---|---|---|
| `mutagen` | GPL-2.0-or-later | **Copyleft — see above** |
| `ebooklib` | AGPL-3.0-or-later | **Copyleft — see above** |
| `kokoro` (Kokoro-82M) | Apache-2.0 | Permissive |
| Flask | BSD-3-Clause | Permissive |
| `waitress` | ZPL 2.1 (Zope Public License) | Permissive |
| React | MIT | Permissive |
| Vite | MIT | Permissive |
| `beautifulsoup4` | MIT | Permissive |
| `soundfile` | BSD-3-Clause | Permissive (wraps `libsndfile`, which is LGPL — LGPL is specifically designed to permit this kind of bundling without the larger program needing to adopt it, unlike GPL/AGPL; still listed here for accuracy) |
| `tkinter` | PSF License (Python stdlib) | Permissive |
| `regex==2026.6.28` | Apache-2.0 (confirmed against the PyPI metadata for this version) | Permissive |
| PyInstaller | GPL with a linking exception for compiled output | Permissive in effect — PyInstaller's own license explicitly exempts programs built with it from needing to be GPL themselves; worth a final check against PyInstaller's actual current license text before publishing, rather than trusting this summary alone |

**Updated (Epic 2, 2026-07-06):** the `regex` entry was listed as
*proposed* at design time. It is now confirmed: `regex==2026.6.28` is
pinned in `requirements.txt`, Apache-2.0 per the PyPI metadata for that
version, and actively used by `pipeline/sanitize_stage.py` for
Unicode-aware whole-word matching with a ReDoS timeout. The entry in the
table above has been updated to reflect this.

This table is the source for the actual `NOTICE` file shipped in the
repo (see below) — keep both in sync if dependencies change.

## `NOTICE` file (to create at repo root alongside `LICENSE`)

Concrete content, not just "have a notice file" as an abstract todo:

```
epub-automation
Copyright (c) [year] [author]

This project's original source code is licensed under the MIT License
(see LICENSE).

This software bundles or depends on the following third-party
components. Some are permissively licensed; two are copyleft — see
below for what that means for the distributed application as a whole.

--- Copyleft dependencies (affects the distributed application) ---

mutagen — GPL-2.0-or-later
  https://github.com/quodlibet/mutagen

ebooklib — AGPL-3.0-or-later
  https://github.com/aerkalov/ebooklib

Because this program imports these libraries directly, the compiled/
distributed application as a combined work is governed by the terms of
these licenses, not solely by the MIT license above. Full source code
for this entire project is available at [repo URL], which is how the
source-availability requirement of these licenses is satisfied.

--- Permissive dependencies ---

kokoro (Kokoro-82M) — Apache License 2.0
Flask — BSD-3-Clause
waitress — Zope Public License 2.1
React — MIT License
Vite — MIT License
beautifulsoup4 — MIT License
soundfile — BSD-3-Clause (wraps libsndfile, LGPL)
regex==2026.6.28 — Apache License 2.0 (confirmed for this version)
PyInstaller — GPL with linking exception for compiled output

Full license texts for each dependency are available from their
respective project pages linked above, or in this repo's
third-party-licenses/ folder.
```

## Cross-references

- `00-overview-and-goals.md` claims this project as a portfolio piece —
  accurate, honest licensing documentation is part of what makes that
  claim hold up under scrutiny, not just the code itself.
- `01-architecture.md`'s tech stack table should note `mutagen` and
  `ebooklib`'s licenses inline where they're first introduced, not just
  here, so a reader doesn't have to already know to look for this file.
- `02-pipeline-stages.md` §Stage 2 and `docs/design/adr/0004` — the
  `regex` package's proposed addition, and why the sanitize port needs
  it (a Python stdlib `re` limitation, not a preference).
- `07-packaging-deployment.md` — the compiled `.exe` is the actual
  artifact this licensing situation applies to; the `NOTICE` file should
  be readable from the same repo the `.exe`'s build instructions live in.
- `../design/adr/0012-retain-copyleft-dependencies.md` — the ADR-form
  version of this same decision, cross-checked against all three source
  repos directly as part of the later `design/` review pass.
