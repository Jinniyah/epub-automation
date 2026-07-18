# ADR-0015: Broaden accessibility scope to WCAG 2.1 AA alignment (screen readers, dyslexia), layered on top of the original persona

## Status
Accepted

## Context
The GUI was originally scoped around one real, specific accessibility
persona (`00-overview-and-goals.md` §The accessibility targets) — the
author's mother, who has FMS (difficulty learning/holding multi-step
processes in mind) and rheumatoid arthritis in her fingers (reduced
fine-motor precision). That persona is validated by design: the intended
acceptance test is an actual unassisted dry run by her or someone with a
similar profile (`08-open-questions-and-assumptions.md`).

During a later design-review pass, the observation was made that a tool
which already converts books to audio, and already insists on plain
language and large, unambiguous controls, is most of the way toward
being genuinely useful to two groups it wasn't originally scoped for:
people who use a screen reader (blindness/low vision) and dyslexic
readers. This raised a real question — whether to formally broaden the
project's accessibility scope, and if so, how far.

The tradeoffs were weighed explicitly rather than assumed:

- **In favor:** this is the cheapest possible point to decide it (zero
  code exists yet — semantic HTML/ARIA/keyboard support is nearly free
  to build in from the start and expensive to retrofit later); it's
  coherent with the project's existing motivation rather than bolted on
  for optics; and it's a more sophisticated accessibility claim for a
  portfolio piece than "big buttons," since it distinguishes motor/
  cognitive accessibility from sensory accessibility explicitly.
- **Against:** unlike the primary persona, there was initially no real
  person available to validate the screen-reader/dyslexia work against —
  an unvalidated accessibility claim risks reading worse than no claim
  at all if it's subtly broken in ways only real assistive-tech use
  would surface (focus traps, live-region spam, missed labels). Full
  WCAG AA conformance is also a large, ongoing discipline tax on every
  future screen, not a one-time cost, and sits in some tension with this
  project's own stated minimalism (ADR-0014, the non-goals list).

That calculus changed materially once real testers became available: a
dyslexic reader who can test directly, and a lead (through a contact who
works professionally with people with disabilities) on a screen-reader
tester. That doesn't make this a certified, audited claim — but it moves
"designed against a checklist, never verified" to "designed against a
checklist, with a real plan to verify it," which is a meaningfully
different, more honest position to build from.

## Decision
Broaden the GUI's accessibility target to **WCAG 2.1 Level AA
alignment**, covering screen-reader users and dyslexic readers, layered
on top of — not replacing — the original FMS/RA persona. This is
explicitly framed as **"aligned," not "certified"**: designed and tested
against WCAG 2.1 AA criteria, without a formal third-party audit.

Scope, concretely (full detail in `03-gui-ux-design.md` §Accessibility:
WCAG 2.1 AA alignment):

- **Perceivable** — color contrast minimums, no color-only meaning, text
  alternatives for every status icon/emoji, resizable text to 200%,
  left-aligned non-justified body text with generous spacing.
- **Operable** — every interactive element is a real keyboard-focusable
  control (not a mouse-only styled `<div>`), visible focus indicators,
  no drag-and-drop-only interactions, focus-trapping and focus-return on
  every overlay, no keyboard traps.
- **Understandable** — mostly already satisfied by the existing
  plain-language and consistency principles built for the primary
  persona; no separate wording standard needed.
- **Robust** — semantic HTML landmarks and heading structure, real
  `<label>` associations on every form field, real `<table>` markup for
  the multi-book voice table.
- **Screen-reader status updates** — the polling status contract gets
  `aria-live="polite"` for routine messages and `aria-live="assertive"`
  for errors, with progress announcements throttled to meaningful
  intervals rather than read on every poll tick.

Explicitly out of scope, stated as such rather than left ambiguous: WCAG
AAA conformance, support for paid/legacy assistive technology (JAWS) —
testing targets Windows Narrator and the free NVDA — a dedicated
"accessibility mode" or alternate UI, and a mandatory dyslexia-specific
font (an optional toggle may be offered, but isn't load-bearing, since
evidence such fonts outperform an ordinary well-spaced sans-serif is
mixed).

## Consequences
- Most of the concrete engineering cost lands as "build it right the
  first time" rather than new invented complexity: real `<button>`
  elements instead of clickable `<div>`s, real `<label>`s, real
  `<table>` markup — none of this is more expensive to write than the
  alternative, it just has to be a stated requirement so it doesn't get
  skipped under time pressure.
- The genuinely new, ongoing costs are: ARIA live-region design and
  throttling logic for the polling contract, focus-trap/focus-return
  logic on every overlay, and a permanent discipline requirement that
  every *future* screen added to this project re-verifies the same
  keyboard/ARIA/contrast properties — this doesn't get easier over time
  the way a one-off feature would.
- Accessibility testing (`09-testing-strategy.md` §Accessibility
  testing) now needs both automated linting (axe-core, cheap, CI-
  enforceable) and real manual verification (screen-reader testing
  specifically does not automate away) — a new, recurring category of
  QA work this project didn't previously need.
- The claim made anywhere this project is described (README, this ADR,
  the requirements docs) must consistently say "aligned," never
  "compliant" or "certified," and must not overstate the screen-reader
  side specifically until a real screen-reader user has actually tried
  it — the tester lead is real but not yet confirmed as of this
  writing (`08-open-questions-and-assumptions.md`).
- If a screen-reader tester never materializes, the honest fallback is
  to keep the "designed and tested against WCAG 2.1 AA criteria, not yet
  validated by a screen-reader user" framing indefinitely, rather than
  quietly upgrading the claim once enough time has passed that no one
  remembers it was never actually confirmed.

### Addendum (2026-07-18): the dyslexic-reader tester also fell through

The "against" reasoning above and this decision's own Context both
originally treated the dyslexic-reader tester as a settled, available
fact ("a dyslexic reader who can test directly"), not a lead — that
tester is no longer available as of this date. This doesn't change the
Decision itself: the design commitment (left-aligned/never-justified
body text, generous line-height/letter-spacing, plain sans-serif —
already built, `frontend/src/index.css`) stands regardless of who
verifies it. What changes is verification status only, and the same
fallback rule the bullet above already states for the screen-reader
tester now applies symmetrically to the dyslexic-reader side too: keep
the "designed and tested against WCAG 2.1 AA criteria, not yet validated
by a dyslexic reader" framing indefinitely, never silently upgraded.
Tracked as a Wish List item, not a dropped one — see `docs/BACKLOG.md`.

## Alternatives Considered
- **Do nothing — keep the original FMS/RA-only scope** — rejected: this
  was a real, deliberated option (see the "against" reasoning above),
  but the balance shifted once real testers became available, and the
  marginal engineering cost for most of the requirements (semantic
  HTML, real form controls) is low enough that declining it outright
  would have left value on the table for a small cost.
- **Pursue full, certified WCAG 2.1 AA conformance (formal audit)** —
  rejected as disproportionate for this project's scale (a portfolio
  piece plus small-scale family/personal use, not a commercial or
  publicly-mandated product) — the cost of a real accessibility audit
  isn't justified here, and "aligned" already captures the design intent
  honestly without that expense.
- **Add a separate, alternate "accessibility mode" UI** — rejected: the
  goal is one UI that already works this way by default for everyone,
  consistent with how the primary persona's requirements were already
  integrated directly into the one real design rather than as a special
  mode.

## References
- `docs/requirements/00-overview-and-goals.md` §The accessibility
  targets
- `docs/requirements/03-gui-ux-design.md` §Accessibility: WCAG 2.1 AA
  alignment (full requirement detail)
- `docs/requirements/09-testing-strategy.md` §Accessibility testing
- `docs/requirements/08-open-questions-and-assumptions.md` (screen-reader
  tester availability, tracked as unresolved)
- ADR-0014 (reuse-by-default principle — this ADR's "build it right the
  first time rather than invent new complexity" framing follows the same
  underlying discipline)
