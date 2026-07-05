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

## Realism check (added during review): what must not slip vs. best-effort

The combined scope below is genuinely ambitious for one person's side
project running alongside three ported codebases, a new frontend, and a
new packaging story — worth naming explicitly rather than leaving as an
implicit assumption that all of it happens on schedule. Not every part
of this section carries the same cost of slipping, so if something has
to give under time pressure, this should be a conscious choice made now,
not a silent one made later:

- **Must not slip (cheap to maintain, CI-enforced, and highest-value if
  something has to be prioritized):** the security-guard adversarial
  tests (§Priority coverage areas), and the automated accessibility
  linting (`axe-core`, `eslint-plugin-jsx-a11y`, §Accessibility testing).
  Both are gated by CI already, both stay cheap to keep passing once
  written, and both cover the areas where a regression is either
  security-critical or silently excludes a whole category of user.
- **Best-effort, and the most likely to actually slip:** the manual
  accessibility passes — the keyboard-only pass, the real NVDA/Narrator
  pass, and the real dyslexic-reader and (if secured) screen-reader
  tests. Unlike the 80% coverage figure, nothing in CI enforces these;
  they depend entirely on discipline holding up over the life of the
  project, which is exactly the kind of thing that quietly slips under
  time pressure. This isn't a reason to drop them from the plan — see
  ADR-0015's own reasoning for why they matter — just an honest
  acknowledgment of where the real risk sits, so their absence (if it
  happens) is a known, named gap rather than a surprise discovered late.
- The 80%+ coverage floor itself sits in between: CI-enforced like the
  "must not slip" items above, but achievable at varying quality (see
  the next section's own warning about weak-assertion coverage) — worth
  periodically sanity-checking that it's testing the right things, not
  just hitting the number.

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
  probably works" isn't good enough. This includes the sanitize stage's
  ported whole-word-matching regex (`02-pipeline-stages.md` §Stage 2,
  item 6) — its ReDoS-timeout behavior specifically needs a test proving
  a pathological profanity-list entry can't hang the process, not just a
  test that ordinary words match correctly.
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
- **The single-instance lock's stale-lock detection**
  (`01-architecture.md` §Single-instance behavior, ADR-0007) — a test
  simulating a lock file left behind by a dead PID, proving the next
  launch clears it and proceeds rather than refusing to start, is what
  makes that fix durable rather than something that quietly regresses.

## Accessibility testing

Backs the WCAG 2.1 AA alignment target described in
`03-gui-ux-design.md` §Accessibility: WCAG 2.1 AA alignment and
`../design/adr/0015-wcag-aa-alignment-broadened-accessibility-scope.md`.
Two distinct layers — automated and manual — because automated tooling
genuinely cannot catch everything here, and pretending otherwise would
undercut the "aligned, not certified" honesty that decision depends on.

### Automated (CI-enforced, catches the mechanical stuff)

- **`axe-core`** (via `vitest-axe` or `@axe-core/react` in dev) run
  against every frontend component's tests — catches missing labels,
  insufficient contrast, missing landmark roles, and other mechanically
  detectable violations. Added to the same `vitest run` invocation
  already gating the 80% coverage floor, so an accessibility regression
  fails CI the same way a coverage drop does — not a separate, easily-
  ignored report.
- **Lint rule: `eslint-plugin-jsx-a11y`** — catches obvious authoring
  mistakes (a `<div onClick>` with no keyboard handler or role, an
  `<img>` with no alt text, a form input with no associated label)
  before a component is even tested, as part of the existing lint step.
- These two catch real, common mistakes cheaply and continuously, but
  neither one can verify that focus actually moves correctly on modal
  open, that a live region announces at a sane cadence, or that the
  overall experience navigating with a screen reader actually makes
  sense — that requires the manual pass below.

### Manual (does not automate away)

- **A full keyboard-only pass** — unplug the mouse, navigate every
  screen in `03-gui-ux-design.md` using only Tab/Shift+Tab/Enter/Space/
  Escape. This alone catches most focus-trap and unreachable-control
  bugs cheaply, before involving a real assistive-tech tester.
- **A real screen-reader pass**, targeting **NVDA** (free, the practical
  standard for Windows screen-reader testing) plus Windows Narrator as a
  baseline sanity check — walking through first-launch setup, adding
  books, the per-book identification loop, voice assignment, and the
  Working/Review screens, listening for: whether status changes are
  announced at all, whether progress announcements are throttled sanely
  rather than spammy, and whether the multi-book voice table's rows make
  sense read out loud.
- **A real test with a dyslexic reader** — a genuine person is already
  identified for this (`00-overview-and-goals.md` §The accessibility
  targets); this should happen the same way the primary persona's
  acceptance test does: a real, unassisted or lightly-observed run
  through first-launch setup and a full single-book conversion, not just
  a design review of static mockups/copy.
- **A real test with a screen-reader user**, once a tester is confirmed
  (currently being pursued — see
  `08-open-questions-and-assumptions.md`). Until this happens, any
  claim about screen-reader usability should be phrased as "designed and
  tested against WCAG 2.1 AA criteria," not "validated by a blind user."

### What this does not include

Consistent with `03-gui-ux-design.md`'s explicit non-goals for this
alignment: no testing against JAWS or other paid screen readers, no
formal third-party accessibility audit, and no separate test track for
an "accessibility mode" — the one UI is what gets tested, since it's
also the only UI that ships.

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
  backend, and the frontend's lint + `vitest run --coverage` equivalent
  (including the `axe-core`-backed accessibility assertions from
  §Accessibility testing above — these run as part of the same command,
  not a separate opt-in step).
- **Fails the build below 80% coverage on either side**, and fails on
  any `axe-core` violation surfaced in component tests — this is what
  makes both numbers requirements rather than suggestions.
- A coverage badge in the repo README is a small, cheap addition that
  makes this visible at a glance to anyone looking at the portfolio
  piece, without needing to dig into CI logs.
