# epub-automation — Design Patterns

Status: Reference doc for implementation. Not itself a source of new
*decisions* the way `docs/design/adr/` is — most of what's below either
names a pattern this project's design already committed to (so it has
consistent vocabulary across code, reviews, and future ADRs) or
recommends a concrete, low-ceremony way to implement something already
required elsewhere in `docs/requirements/`. Where a pattern choice
genuinely involves weighing real alternatives, that's called out
explicitly and a real ADR should back it, not this doc alone.

**When to read this:** during implementation, alongside
`docs/requirements/`, `docs/design/SYSTEM_DESIGN.md`, and
`docs/design/adr/`. This doc doesn't restate *what* the system does or
*why* the architecture is shaped the way it is — it's the *how*, one
level more concrete than an ADR, aimed at keeping the same seams and
vocabulary consistent as multiple pieces (pipeline stages, the Flask
bridge, the React frontend) get built out.

**Status column meaning:**
- **Already implicit** — the existing requirements/ADRs already describe
  this shape; this doc just names it and makes the implementation
  contract explicit.
- **Recommended** — not previously specified; a concrete way to satisfy
  an existing requirement (usually one the design review flagged) that
  should be adopted during implementation.

---

## 1. Backend / Python patterns

| Pattern | Where it applies | Why | Status |
|---|---|---|---|
| **Strategy** | `pipeline/ai_providers/` — `AIProvider` base class with interchangeable `GeminiProvider` / `OpenAIProvider` / `NullProvider` implementations, selected at runtime via `settings.json`'s `ai_provider` field | Ported wholesale from `epub-renamer` (`docs/design/adr/0003`, `0014`) — each install picks a provider independently, and adding a future provider means adding one new class, not touching call sites | Already implicit |
| **Registry** | `pipeline/ai_providers/registry.py` — maps a provider key string (`"gemini"`/`"openai"`/`"none"`) to a Strategy implementation | Same source as above; the same shape is a natural fit for the voice list (voice key → sample path/config) if that isn't already structured this way | Already implicit |
| **Adapter** | `backend/bridge.py` (Flask → pipeline) and `main.py` (CLI → pipeline) | ADR-0001's "thin caller" rule, made concrete: both are pure translation layers with zero business logic. Gives a sharp, testable rule — **if `bridge.py` or `main.py` contains a decision, that's a bug, not a style preference** | Already implicit |
| **Pipeline** | The four stages (rename → sanitize → audio → retag), currently described procedurally in `02-pipeline-stages.md` | Formalize a common `Stage` interface so both `main.py`'s `all` command and the GUI's per-book loop iterate an ordered list of stage objects instead of hand-wiring stage-specific calls. This also cleanly expresses the per-run skip toggles (`fix_names`/`clean_language`) as "this stage isn't in this run's pipeline," rather than an `if` scattered through the runner | **Recommended** |
| **State Machine** | The per-book status lifecycle (`pending → identifying → needs_input → identified → voice_pick → generating → paused → complete/cancelled/error`) and the derived top-level `state` field (`01-architecture.md` §Status endpoint contract §State derivation) | This is a finite state machine in everything but name already. Making it one explicitly — even a small hand-rolled transition table, no library needed — is what turns the design review's B3 fix (an explicit `state` derivation rule) into one tested function instead of logic re-derived wherever `bridge.py` gets implemented | **Recommended** |
| **Repository** | `pipeline/state_manager.py`, `pipeline/audit_logger.py` | Wrap state-file and audit-log reads/writes behind a repository interface instead of pipeline code touching file paths directly. Pays for itself immediately against the 80%-coverage/TDD goals in `09-testing-strategy.md` — pipeline-stage tests can mock a repository instead of hitting the real filesystem | **Recommended** |
| **Template Method** | Any code that opens a zip/EPUB — sanitize stage, Screen-1 validation, future stages | The design review found that the same zip-safety guards (path traversal, zip-bomb cap, XXE prevention) must apply everywhere a zip is opened, not just in sanitize (`02-pipeline-stages.md` §Stage 2, `06-safety-error-handling.md` §Input validation, ADR-0004/0013). A base `SafeZipOperation` class with a template method fixing the guard order makes "a new zip-touching code path forgot a guard" much harder to do by accident, rather than something to catch in code review every time | **Recommended** |
| **Command** | Pause / Cancel / Resume actions on a book (`06-safety-error-handling.md` §Cancel design) | One place to log/audit each action uniformly; makes the Cancel-time "keep-partial vs. discard" branch a single, testable object instead of inline route-handler logic | **Recommended** |
| **Observer** | Pipeline progress → the GUI's polling response | Pipeline stages emit progress events; `bridge.py` subscribes and accumulates them into the status-endpoint shape. Keeps ADR-0001's separation honest — the pipeline genuinely never needs to know an HTTP server exists, which also makes CLI progress reporting free to reuse the same event stream differently (e.g. a progress bar) | **Recommended** |

### Sketch: the `Stage` interface (Pipeline pattern)

Illustrative shape, not a final API — the point is a common seam every
stage implements, so the runner (CLI or GUI bridge) never special-cases
a particular stage:

```python
class Stage(Protocol):
    name: str  # "rename" | "sanitize" | "audio" | "retag"

    def applies_to(self, book: BookState, settings: Settings) -> bool:
        """False if this run's toggles skip this stage for this book."""

    def run(self, book: BookState) -> BookState:
        """Process one book, returning its updated state.
        Must be resumable: safe to call again on a book already
        partially processed by this stage (see 06-safety-error-handling.md
        §Long-run resilience)."""
```

### Sketch: state derivation as an explicit function (State Machine pattern)

This is the concrete fix for the design review's B3 finding
(`01-architecture.md` §Status endpoint contract §State derivation) — one
function, one place, unit-tested directly against the precedence rule
already written into that section:

```python
def derive_batch_state(books: list[BookState]) -> BatchState:
    """Pure function: given the current per-book statuses, return the
    single top-level `state` value the polling contract exposes.
    See 01-architecture.md §State derivation for the precedence rule
    this must implement exactly."""
```

---

## 2. Frontend / React patterns

| Pattern | Where it applies | Why | Status |
|---|---|---|---|
| **Custom hooks for cross-cutting accessibility behavior** | `useFocusTrap()`, `usePollingStatus()`, `useAriaLiveThrottled()` | WCAG focus-trap/return is required on *every* overlay (Field Correction Popup, full voice-picker, AI Helper Setup — `03-gui-ux-design.md` §Accessibility §Operable). Implementing it once as a hook and having every overlay use it is the difference between "accessible by construction" and "accessible until someone forgets on overlay #4" | **Recommended** |
| **Container / Presentational split** | One top-level container owns `usePollingStatus()`; screen components (`Screen1`, `Working`, `Review`, etc.) receive plain props | Keeps screen components pure and trivially testable with React Testing Library (`09-testing-strategy.md` §Frontend) — no fetch-mocking needed for most component tests | **Recommended** |
| **View-model mapping layer** | A hook between the raw polling contract and each screen, e.g. `useVoiceAssignmentView(books)` | This is the frontend half of the design review's B3 fix: `useVoiceAssignmentView()` returns `{ mode: 'single' \| 'table', ... }`, putting the "single-book vs. multi-book, disambiguated by `books.length`" rule (`01-architecture.md` §State derivation) in one tested place instead of every component re-deriving it | **Recommended** |
| **Reducer for local UI state** | `useReducer` for ephemeral state: which overlay is open, which field is mid-edit | More predictable than scattered `useState`, and a reducer's state shape is a natural thing to persist/restore for the "app reopens to the same state" requirement (`03-gui-ux-design.md` §General principles) | **Recommended** |
| **API-client facade** | A single typed module wrapping every `fetch` call to the Flask backend | Centralizes error handling; makes mocking trivial in component tests; keeps components from knowing the API's URL/shape directly | **Recommended** |
| **Compound/shared component reuse** | The Field Correction Popup (used identically in the pre-generation confirm-metadata step and the post-generation "No, let me fix it" flow — `03-gui-ux-design.md`), the fully-clickable radio-row pattern (voice picker, AI Helper Setup) | Already an explicit requirement, not a new suggestion — `03-gui-ux-design.md` is explicit that these are "one component, reused everywhere," not several bespoke editors. Named here so the *implementation* of that requirement is a literal shared component/hook, not three copies that started identical and drifted | Already implicit |

### Sketch: the polling/view-model seam

```
usePollingStatus()  →  { state, books, message, error, needsInput }
        │
        ├─▶ useVoiceAssignmentView(books)   →  { mode, rows, ... }
        ├─▶ useWorkingScreenView(books, activeBookId) → { title, progressText, ... }
        └─▶ useAriaLiveThrottled(message, error)      → announces at sane intervals
```

Each screen consumes its own narrow view-model hook, never the raw
polling payload directly — this is what keeps the `state`/`books[]`
derivation logic in one place instead of duplicated per-component
conditionals, which is exactly the class of bug the design review's B3
finding was about.

---

## 3. How to apply these during implementation

- These aren't ADR-level ceremony — most don't involve weighing real
  alternatives the way `docs/design/adr/` entries do, so they don't need
  their own ADRs. If implementation reveals a real tradeoff worth
  recording (e.g., a reason *not* to use one of these, or a materially
  different approach taken instead), that's ADR-worthy and should get
  one, per `CLAUDE.md`'s existing rule for new binding decisions.
- Reference the pattern by name in docstrings/PR descriptions where it's
  the reason for a structural choice (e.g., "`SafeZipOperation` is a
  Template Method — see `docs/design/PATTERNS.md`") — this keeps the
  vocabulary consistent across the codebase and this doc, rather than
  each contributor inventing their own name for the same shape.
- Tests should exercise the seam each pattern creates, not just the
  concrete implementation behind it — e.g., a `Stage` test suite should
  include at least one test that runs against a fake/minimal `Stage`
  implementation to prove the interface itself is sufficient, not only
  tests of `RenameStage`/`SanitizeStage`/etc. individually.
- If a recommended pattern turns out to be the wrong fit once real code
  exists, update this doc rather than silently drifting from it — same
  living-document principle `CLAUDE.md` already applies to
  `docs/requirements/` and `docs/design/`.

## References

- `docs/design/SYSTEM_DESIGN.md` — the architecture these patterns
  implement.
- `docs/design/adr/` — binding decisions; several patterns above are
  direct implementation details of ADR-0001, ADR-0003, ADR-0004,
  ADR-0007, ADR-0013, ADR-0014.
- `docs/requirements/01-architecture.md` §Status endpoint contract
  §State derivation, `docs/requirements/09-testing-strategy.md` — the
  requirements the State Machine, Repository, and view-model patterns
  above are concretely satisfying.
- `docs/design_review.md` — B3 (status-contract ambiguity) is the
  specific finding the State Machine and view-model-layer
  recommendations above are meant to close for good, on both the
  backend and frontend sides respectively.
