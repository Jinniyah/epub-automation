# Testing Strategy

Referenced but never specified elsewhere: `01-architecture.md` lists a
`tests/` folder in the project structure, and `00-overview-and-goals.md`
claims "same **tested** core" as a portfolio highlight — this doc is what
actually backs that claim up.

## Why this matters here specifically

Beyond ordinary code-quality reasons, this project is explicitly a
portfolio piece (`00-overview-and-goals.md`). A visible, enforced test
suite with real coverage — not just a `tests/` folder that exists for
show — is one of the clearest, most checkable signals of engineering
maturity a reviewer can look at directly: a coverage badge, a CI
pipeline that actually gates merges, and tests that were evidently
written *before or alongside* the code they cover (not bolted on after,
which reads very differently in a diff history) all say something a
README claim alone doesn't.

## Target: 80%+ coverage, both backend and frontend

- **Backend** (`pipeline/`, `backend/`, `main.py`, `launcher.py`):
  minimum 80% line coverage, measured via `pytest-cov`.
- **Frontend** (`frontend/src/`): minimum 80% line coverage, measured via
  Vitest's built-in coverage provider.
- **This is a floor, not a target to hit exactly** — 80% line coverage
  with weak assertions is worse than 75% with meaningful ones. The
  number is a useful, checkable proxy and a good CI gate, but §Priority
  coverage areas below matters more than the percentage itself.
- Enforced in CI (see §CI enforcement below), not just run locally and
  trusted — a coverage requirement that isn't gated by CI is a
  suggestion, not a requirement.

## Backend: reuse the existing toolchain, don't invent a new one

`epub-renamer` already has an established, working setup — reuse it
directly rather than starting fresh:

- **`pytest`** — already the test runner (`pyproject.toml`
  `[tool.pytest.ini_options]`, `Makefile`'s `test` target).
- **`black`** (line length 88) + **`ruff`** (rules E, F, I, B) — already
  the formatter/linter pairing.
- **`mypy --strict`** — already the type checker.
- **Add `pytest-cov`** — the one piece not yet present. Add
  `--cov=pipeline --cov=backend --cov-report=term-missing
  --cov-fail-under=80` to the `Makefile`'s `test` target (or a new
  `coverage` target), so `make test` fails outright below 80%, not just
  reports a number to ignore.
- **Existing tests get ported, not rewritten from scratch**: `epub-renamer/tests/`
  already covers `epub_reader`, `renamer`, `state_manager`, the AI
  provider base class, and `main` — these port directly to
  `pipeline/`'s equivalent modules (`epub_reader.py`, `rename_stage.py`,
  `state_manager.py`, `ai_providers/base.py`) with import paths updated,
  same as the production code itself is being ported. `epub-sanitize`
  and `epub-to-audio` have no existing automated tests (`epub-sanitize`
  is PowerShell being ported to Python from scratch; `epub-to-audio` has
  none) — those need new test suites written as part of the port, ideally
  test-first (see §TDD workflow below), not retrofitted after the port
  is "done."

## Frontend: Vitest + React Testing Library

- **Vitest** — pairs naturally with the existing Vite build
  (`01-architecture.md`), faster than Jest for a Vite project, same
  config file typically.
- **`@testing-library/react`** — test component *behavior* (what she'd
  see and click) rather than implementation details (internal state,
  component structure), which also happens to make tests resilient to
  the kind of visual refactoring a portfolio piece tends to get.
- **Coverage via Vitest's built-in `--coverage`** (v8 provider) —
  `frontend/src/` as the coverage root, 80% floor, same enforcement
  principle as the backend.
- Priority: the components with real conditional logic (Field Correction
  Popup's full-replace behavior, the "Welcome back" screen's
  pending/not-pending branch, the voice table's same-series-default
  logic) matter more for coverage quality than purely presentational
  components.

## TDD workflow (the actual practiced discipline, not just a target)

For **backend pipeline logic and safety-critical code specifically**:
write a failing test that encodes the expected behavior — including the
edge/error case, not just the happy path — before writing the
implementation. This applies most rigorously to:

- Each pipeline stage's core transform (rename, sanitize, chunk, retag).
- Every security guard (see §Priority coverage areas below).
- The atomic-write logic for `settings.json`/state file
  (`05-data-settings-and-logging.md` §Write safety) — the failure mode
  being guarded against is exactly the kind of thing that's easy to
  "test" by eyeballing the code and easy to get subtly wrong in practice;
  a real test that simulates a crash mid-write is the actual proof.
- The disk-space and time-estimate formulas (`06-safety-error-handling.md`,
  `08-open-questions-and-assumptions.md`) — pure functions with clear
  expected outputs for given inputs, ideal for test-first development.

For **frontend components**: write the Testing-Library test describing
what the user should be able to do and see, before or alongside building
the component to satisfy it. Less rigorously enforced than backend TDD
for purely visual/layout work, where a test-first approach adds friction
without much correctness benefit — the discipline matters most where
there's actual conditional logic to get right.

## Priority coverage areas (beyond the blanket 80% floor)

These deserve deliberate, adversarial test cases, not incidental
coverage from testing the happy path:

- **Security guards** (path traversal, zip bomb — `02-pipeline-stages.md`
  §Stage 2, and the DRM/zip-validity checks in
  `06-safety-error-handling.md` §Input validation): target near-100%,
  with actual crafted malicious fixture files (a zip with `../` path
  entries, a zip bomb, a `META-INF/encryption.xml`-bearing EPUB), not
  just mocked inputs. These are exactly the kind of code where "it
  probably works" isn't good enough.
- **3-tier metadata resolution priority** (EPUB internal → filename parse
  → CLI/explicit override) — test each tier winning independently and
  the priority order between them, not just one happy-path combination.
- **`FILENAME_PATTERN` matching** (`02-pipeline-stages.md`, reused from
  `epub-renamer`) — both the already-normalized-skip case and realistic
  near-miss filenames that should *not* match.
- **The retag folder-rename fix** (`02-pipeline-stages.md` §Stage 4) —
  this is a bug fix relative to the original script; a regression test
  proving the folder actually gets renamed (not just the files inside
  it) is what makes this fix durable rather than something that quietly
  regresses later.

## What's deliberately NOT chasing the 80% figure

- **Full end-to-end runs through actual Kokoro TTS generation** — slow,
  resource-heavy, and not meaningfully more informative per-run than a
  mocked `TTSEngine.generate()` for most test purposes. A small number of
  real, marked-slow integration tests (`@pytest.mark.slow`, excluded from
  the default `make test` run, run separately/less often) covering the
  full pipeline end-to-end are still worth having, but the 80% figure
  and CI gate apply to the fast, default suite.
- **Full-flow GUI automation** (e.g. Playwright driving the actual
  browser through first-launch setup, a full conversion, etc.) — valuable
  but expensive to build and maintain; per the original review's
  under-specification finding, a manual QA checklist covering the key
  screen flows is the pragmatic choice at this project's scale, alongside
  (not instead of) the component-level Vitest coverage above.

## CI enforcement

Given the portfolio framing, this should be a real, visible GitHub
Actions workflow, not just a documented convention:

- Runs on every push/PR: `make check` (lint + typecheck + test) for the
  backend, and the frontend's lint + `vitest run --coverage` equivalent.
- **Fails the build below 80% coverage on either side** — this is what
  makes the number a requirement rather than a suggestion.
- A coverage badge in the repo README is a small, cheap addition that
  makes this visible at a glance to anyone looking at the portfolio
  piece, without needing to dig into CI logs.
